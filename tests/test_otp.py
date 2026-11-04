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


class RefillTests(unittest.IsolatedAsyncioTestCase):
    async def test_refill_writes_captured_layout_and_requires_read_back(self):
        wire = Wire(b'TEST' + bytes.fromhex('050017010003e9000c000c0000'))
        wire.get_remote_otps = AsyncMock(side_effect=[[], [{'slot': 12, 'code': '123456'}]])
        from unittest.mock import patch
        with patch.object(otp.time, 'time', return_value=0x12345678), patch('secrets.randbelow', return_value=23456):
            self.assertEqual(await wire.refill_otps(), [{'slot': 12, 'code': '123456'}])
        expected = (b'TEST' + bytes.fromhex('050017000303e9000c02000003e9')
                    + b'123456' + bytes(6) + bytes.fromhex('12345678')
                    + bytes(4) + bytes.fromhex('ffffffff') + bytes(5) + b'\x01')
        self.assertEqual(wire._execute_step.call_args.args[0], expected)
        self.assertEqual(wire.get_remote_otps.await_count, 2)

    async def test_lost_ack_is_not_retried_or_reported_as_success(self):
        wire = Wire(None)
        wire.get_remote_otps = AsyncMock(return_value=[])
        wire._execute_step.side_effect = TimeoutError()
        with self.assertRaisesRegex(RuntimeError, '0 of 2.*unacknowledged'):
            await wire.refill_otps(2)
        self.assertEqual(wire._execute_step.await_count, 1)

    async def test_missing_read_back_rejects_acknowledged_write(self):
        wire = Wire(b'TEST' + bytes.fromhex('050017010003e9000c000c0000'))
        wire.get_remote_otps = AsyncMock(return_value=[])
        with self.assertRaisesRegex(RuntimeError, '1 of 1'):
            await wire.refill_otps()

    async def test_invalid_counts_do_not_contact_lock(self):
        wire = Wire(None)
        wire.get_remote_otps = AsyncMock()
        for count in (0, 11, -1, True, 1.5):
            with self.assertRaises(ValueError):
                await wire.refill_otps(count)
        wire.get_remote_otps.assert_not_awaited()

    async def test_wrong_sequence_and_failure_status_are_not_accepted(self):
        for fields in ('0600170100', '0500170000'):
            wire = Wire(b'TEST' + bytes.fromhex(fields + '03e9000c000c0000'))
            wire.get_remote_otps = AsyncMock(return_value=[])
            with self.assertRaisesRegex(RuntimeError, '0 of 1'):
                await wire.refill_otps()

    async def test_partial_batch_stops_at_first_failed_write(self):
        wire = Wire(None)
        wire.get_remote_otps = AsyncMock(return_value=[])
        wire._execute_step.side_effect = [b'TEST' + bytes.fromhex('050017010003e9000c000c0000'), TimeoutError()]
        with self.assertRaisesRegex(RuntimeError, '1 of 3'):
            await wire.refill_otps(3)
        self.assertEqual(wire._execute_step.await_count, 2)


if __name__ == '__main__':
    unittest.main()
