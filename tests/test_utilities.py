from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rompatcher.headers import is_snes_copier_headered
from rompatcher.n64 import convert_n64_byte_order, detect_n64_byte_order


class UtilityTests(unittest.TestCase):
    def test_snes_header_detection(self) -> None:
        payload = bytes(262144)
        rom = bytes(512) + payload
        self.assertTrue(is_snes_copier_headered(Path("game.smc"), rom))

    def test_n64_byte_order_conversion(self) -> None:
        z64 = bytes.fromhex("80371240") + b"\xAA\xBB\xCC\xDD"
        v64 = convert_n64_byte_order(z64, "v64")
        n64 = convert_n64_byte_order(z64, "n64")
        self.assertEqual(detect_n64_byte_order(v64), "v64")
        self.assertEqual(detect_n64_byte_order(n64), "n64")
        self.assertEqual(convert_n64_byte_order(v64, "z64"), z64)
        self.assertEqual(convert_n64_byte_order(n64, "z64"), z64)
