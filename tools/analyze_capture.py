"""Summarize Atomberg iPhone traces offline without exposing credential payloads."""
from __future__ import annotations

import argparse
import json
import struct
from collections import Counter
from pathlib import Path

from extract_keys import FACTORY_KEY, collect_hsj_frames, decrypt_frame


def read_packetlogger(path: Path) -> list[dict]:
    """Read either byte order of Apple's length-prefixed PacketLogger format.

    Reassemble ACL fragments by connection and direction before decoding ATT.
    """
    data = path.read_bytes()
    if len(data) < 13:
        raise ValueError("Capture is empty or truncated")
    endian = "<" if 9 <= struct.unpack_from("<I", data)[0] <= len(data) - 4 else ">"
    offset = 0
    records = []
    pending = {}
    while offset + 13 <= len(data):
        length = struct.unpack_from(endian + "I", data, offset)[0]
        if length < 9 or offset + 4 + length > len(data):
            break
        kind = data[offset + 12]
        payload = data[offset + 13:offset + 4 + length]
        offset += 4 + length
        if kind not in (2, 3) or len(payload) < 4:
            continue
        handle, acl_length = struct.unpack_from("<HH", payload)
        if acl_length != len(payload) - 4:
            raise ValueError("Truncated ACL packet")
        identity = (kind, handle & 0xFFF)
        if (handle >> 12) & 3 == 1:
            if identity not in pending:
                continue  # Capture can begin midway through an unrelated message.
            pending[identity].extend(payload[4:])
        else:
            pending[identity] = bytearray(payload[4:])
        message = pending[identity]
        if len(message) < 4:
            continue
        size, cid = struct.unpack_from("<HH", message)
        if len(message) < size + 4:
            continue
        del pending[identity]
        if len(message) != size + 4:
            raise ValueError("Invalid L2CAP length")
        if cid != 4:
            continue
        # Normalize iOS Write Request to the upstream decoder's Write Command.
        if message[4:5] == b"\x12":
            message[4] = 0x52
        packet = b"\x02" + struct.pack("<HH", handle & 0xFFF, len(message)) + message
        records.append({"number": len(records) + 1, "data": packet})
    if offset == len(data):
        if any(len(m) >= 4 and m[2:4] == b"\x04\x00" for m in pending.values()):
            raise ValueError("Incomplete ATT message at end of capture")
        return records
    raise ValueError("Invalid or truncated PacketLogger file")


def read_master_key(path: Path) -> bytes:
    """Read the one required value without executing or sourcing the .env file."""
    for line in path.read_text().splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == "STATIC_MASTER_KEY":
            value = value.strip().strip("\"'")
            key = bytes.fromhex(value) if len(value) == 32 else value.encode()
            if len(key) == 16:
                return key
    raise ValueError("The .env file must contain a 16-byte STATIC_MASTER_KEY")


def summarize(records: list[dict], master_key: bytes) -> dict:
    frames = collect_hsj_frames(records)
    session_key = None
    counts = Counter()
    undecoded = 0
    for item in frames:
        plaintext = None
        # Session payloads must use the negotiated key. F0/F1/F3 may use the
        # stored pairing key, or the factory key in an initial provisioning trace.
        for key in (session_key, master_key, FACTORY_KEY):
            if key is None:
                continue
            candidate = decrypt_frame(item["frame"], key)
            if not candidate or len(candidate) < 13:
                continue
            if key != session_key and candidate[5:7] not in (
                b"\x00\xf0", b"\x00\xf1", b"\x00\xf3", b"\x00\xc6",
            ):
                continue
            plaintext = candidate
            break
        if plaintext is None:
            undecoded += 1
            continue
        opcode = int.from_bytes(plaintext[5:7], "big")
        counts[(item["direction"], f"0x{opcode:04x}", len(plaintext))] += 1
        if opcode == 0xF0:
            session_key = None
        if opcode == 0xF1 and item["direction"] == "RX" and len(plaintext) >= 29:
            session_key = plaintext[13:29]
    return {
        "complete_frames": len(frames),
        "undecoded_frames": undecoded,
        "commands": [
            {"direction": direction, "opcode": opcode, "payload_length": length,
             "count": count}
            for (direction, opcode, length), count in sorted(counts.items())
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--env-file", type=Path, default=Path(__file__).resolve().parents[1] / ".env")
    args = parser.parse_args()
    try:
        summary = summarize(read_packetlogger(args.capture), read_master_key(args.env_file))
    except (OSError, ValueError):
        parser.exit(1, "Could not analyze capture: check file format, fragmentation, and .env key.\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
