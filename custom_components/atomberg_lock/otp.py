"""Experimental OTP pool operations observed in SL1 Pro iOS captures."""
from __future__ import annotations

import asyncio
import time


def parse_otp_record(response: bytes) -> dict | None:
    """Extract type-2 six-digit credentials; never return other credential types."""
    if len(response) != 54 or response[5:8] != bytes.fromhex("001901"):
        raise ValueError("Unexpected OTP enumeration response")
    body = response[13:]
    pin = body[27:33]
    if body[12] != 2 or not all(48 <= byte <= 57 for byte in pin):
        return None
    return {"slot": int.from_bytes(body[15:17], "big"), "code": pin.decode("ascii")}


class OTPProtocolMixin:
    async def get_remote_otps(self) -> list[dict]:
        """Read existing OTP credentials; this does not issue or consume a code."""
        sequence = self.seq_counter
        self.seq_counter = (sequence + 1) & 0xFF
        request = self.session_token + bytes([sequence]) + bytes.fromhex("0019000003e9001600000000")
        response = await self._execute_step(request, self.session_key, frame_seq=3,
                                            expected_op=b"\x00\x19")
        deadline = time.monotonic() + 6.0
        credentials = []
        total = None
        seen = 0
        while True:
            if len(response) != 54 or response[4] != sequence or response[5:8] != b"\x00\x19\x01":
                raise RuntimeError("Invalid OTP enumeration response")
            count = int.from_bytes(response[13:15], "big")
            if total is None:
                total = count
            if count != total or count > 256 or response[8] not in (0, 2):
                raise RuntimeError("Invalid OTP enumeration count or terminator")
            seen += 1
            credential = parse_otp_record(response)
            if credential:
                credentials.append(credential)
            if response[8] == 2:
                if seen != total:
                    raise RuntimeError("Incomplete OTP enumeration")
                if len({item["slot"] for item in credentials}) != len(credentials):
                    raise RuntimeError("Duplicate OTP credential slots")
                return credentials
            if seen >= total or time.monotonic() >= deadline:
                raise RuntimeError("OTP enumeration did not finish")
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("OTP enumeration timed out")
                encrypted = await asyncio.wait_for(self.recv_queue.get(), remaining)
                from .crypto import decrypt_ecb
                response = decrypt_ecb(self.session_key, encrypted)
                if len(response) >= 7 and response[5:7] == b"\x00\x19":
                    break

    async def refill_otps(self, count: int = 1) -> list[dict]:
        """Provision random six-digit credentials using the captured refill layout.

        Never retry writes: a lost acknowledgement may follow a successful write.
        Read back the pool before returning any generated credentials.
        """
        import secrets

        if type(count) is not int or not 1 <= count <= 10:
            raise ValueError("Refill count must be between 1 and 10")
        existing = await self.get_remote_otps()
        used = {item["code"] for item in existing}
        created = []
        try:
            for _ in range(count):
                code = str(100000 + secrets.randbelow(900000))
                while code in used:
                    code = str(100000 + secrets.randbelow(900000))
                used.add(code)
                sequence = self.seq_counter
                self.seq_counter = (sequence + 1) & 0xFF
                body = (bytes.fromhex("02000003e9") + code.encode().ljust(12, b"\x00")
                        + int(time.time()).to_bytes(4, "big") + bytes(4)
                        + bytes.fromhex("ffffffff") + bytes(5) + b"\x01")
                request = self.session_token + bytes([sequence]) + bytes.fromhex("0017000303e9000c") + body
                response = await self._execute_step(request, self.session_key, frame_seq=3,
                                                    expected_op=b"\x00\x17")
                if (len(response) != 17 or response[4] != sequence
                        or response[5:9] != bytes.fromhex("00170100")
                        or response[15:17] != bytes(2)):
                    raise RuntimeError("OTP write was not acknowledged")
                slot = int.from_bytes(response[13:15], "big")
                if slot == 0 or slot in {item["slot"] for item in existing + created}:
                    raise RuntimeError("Unexpected OTP slot in acknowledgement")
                created.append({"slot": slot, "code": code})
            verified = await self.get_remote_otps()
            if any(item not in verified for item in created):
                raise RuntimeError("OTP read-back verification failed")
            return created
        except Exception:
            raise RuntimeError(
                f"OTP refill incomplete: {len(created)} of {count} writes acknowledged. "
                "The lock may have accepted an unacknowledged write. "
                "Read the pool before retrying; do not automatically retry."
            ) from None
