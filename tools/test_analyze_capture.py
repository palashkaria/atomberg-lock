"""Offline parser regression checks using synthetic, non-secret packets."""
import struct
import tempfile
import unittest
from pathlib import Path

from analyze_capture import read_packetlogger


def record(kind, payload, endian="<"):
    return struct.pack(endian + "III", 9 + len(payload), 0, 0) + bytes([kind]) + payload


class CaptureTests(unittest.TestCase):
    def parse(self, data):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "capture.pklg"
            path.write_bytes(data)
            return read_packetlogger(path)

    def test_byte_orders_and_write_request_normalization(self):
        message = struct.pack("<HH", 4, 4) + bytes.fromhex("120100aa")
        acl = struct.pack("<HH", 0x2001, len(message)) + message
        for endian in ("<", ">"):
            with self.subTest(endian=endian):
                parsed = self.parse(record(2, acl, endian))
                self.assertEqual(parsed[0]["data"][9:], bytes.fromhex("520100aa"))

    def test_fragment_reassembly(self):
        message = struct.pack("<HH", 5, 4) + bytes.fromhex("1b0100aabb")
        first = struct.pack("<HH", 0x2001, 6) + message[:6]
        second = struct.pack("<HH", 0x1001, 3) + message[6:]
        parsed = self.parse(record(3, first) + record(3, second))
        self.assertEqual(parsed[0]["data"][9:], bytes.fromhex("1b0100aabb"))

    def test_reject_truncated_record(self):
        with self.assertRaises(ValueError):
            self.parse(record(1, bytes(20))[:-1])

    def test_reject_incomplete_att_message(self):
        message = struct.pack("<HH", 20, 4) + b"abc"
        with self.assertRaises(ValueError):
            self.parse(record(3, struct.pack("<HH", 0x2001, len(message)) + message))


if __name__ == "__main__":
    unittest.main()
