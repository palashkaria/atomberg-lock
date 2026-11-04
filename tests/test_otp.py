"""Synthetic protocol fixtures: no captured PINs or key material."""
import asyncio
import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

PACKAGE = '_atomberg_protocol_tests'
package = types.ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1] / 'custom_components/atomberg_lock')]
sys.modules.setdefault(PACKAGE, package)
otp = importlib.import_module(PACKAGE + '.otp')
crypto = importlib.import_module(PACKAGE + '.crypto')


def enumeration(pin=b'123456', kind=2, slot=12, total=1, last=True, seq=5):
    body = bytearray(41)
    body[:2] = total.to_bytes(2, 'big')
    body[12] = kind
    body[15:17] = slot.to_bytes(2, 'big')
    body[27:33] = pin
    return b'TEST' + bytes([seq]) + bytes.fromhex('001901') + bytes([2 if last else 0]) + bytes.fromhex('03e90016') + body


class Wire(otp.OTPProtocolMixin):
    def __init__(self, response):
        self.seq_counter = 5
        self.session_token = b'TEST'
        self.session_key = b'0123456789abcdef'
        self.recv_queue = asyncio.Queue()
        self._execute_step = AsyncMock(return_value=response)


class OTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_pool_read_filters_other_credentials_and_unsolicited_events(self):
        wire = Wire(enumeration(total=2, last=False))
        wire.recv_queue.put_nowait(crypto.encrypt_ecb(wire.session_key, b'TEST' + bytes.fromhex('05000a0140') + bytes(32)))
        wire.recv_queue.put_nowait(crypto.encrypt_ecb(wire.session_key, enumeration(kind=1, total=2)))
        self.assertEqual(await wire.get_remote_otps(), [{'slot': 12, 'code': '123456'}])
        self.assertEqual(wire._execute_step.call_args.args[0], b'TEST' + bytes.fromhex('050019000003e9001600000000'))

    async def test_rejects_count_mismatch(self):
        wire = Wire(enumeration(total=2))
        with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
            await wire.get_remote_otps()

    async def test_rejects_wrong_sequence(self):
        with self.assertRaisesRegex(RuntimeError, 'Invalid'):
            await Wire(enumeration(seq=6)).get_remote_otps()

    async def test_rejects_duplicate_slots(self):
        wire = Wire(enumeration(total=2, last=False))
        wire.recv_queue.put_nowait(crypto.encrypt_ecb(wire.session_key, enumeration(total=2)))
        with self.assertRaisesRegex(RuntimeError, 'Duplicate'):
            await wire.get_remote_otps()

    async def test_pin_must_be_six_ascii_digits(self):
        self.assertIsNone(otp.parse_otp_record(enumeration(pin=b'12\x00345')))
        with self.assertRaises(ValueError):
            otp.parse_otp_record(b'bad')


if __name__ == '__main__':
    unittest.main()
