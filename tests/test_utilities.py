from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rompatcher.core import apply_patch, default_output_path
from rompatcher.headers import is_snes_copier_headered
from rompatcher.models import HeaderAction, PatchMetadata, ValidationInfo
from rompatcher.n64 import convert_n64_byte_order, detect_n64_byte_order


class UtilityTests(unittest.TestCase):
    def test_patch_metadata_and_validation_helpers(self) -> None:
        metadata = PatchMetadata()
        self.assertTrue(metadata.is_empty())
        metadata.extra["series"] = "Test"
        self.assertFalse(metadata.is_empty())

        validation = ValidationInfo(algorithm="CRC32", expected=["1234", "5678"])
        self.assertEqual(validation.display_expected(), "1234, 5678")

    def test_snes_header_detection(self) -> None:
        payload = bytes(262144)
        rom = bytes(512) + payload
        self.assertTrue(is_snes_copier_headered(Path("game.smc"), rom))

    def test_default_output_path_uses_new_extension(self) -> None:
        output = default_output_path(Path("game.smc"), HeaderAction(new_extension=".sfc"))
        self.assertEqual(output.name, "game (patched).sfc")

    def test_apply_patch_renames_manual_smc_output_to_sfc_when_header_removed(self) -> None:
        payload = b"ABCDEF"
        rom = _write_temp_file("headered_game.smc", bytes(512) + payload + bytes(262144 - len(payload)))
        patch = _write_temp_file("headered_patch.ips", b"PATCH" + b"\x00\x00\x00" + b"\x00\x01" + b"Z" + b"EOF")
        requested_output = ROOT / ".tmp_tests" / "headered_game_patched.smc"

        result = apply_patch(rom, patch, output_path=requested_output)

        self.assertEqual(result.output_path.suffix, ".sfc")
        self.assertTrue(result.header_action.removed)
        self.assertEqual(result.output_path.read_bytes()[0], ord("Z"))

    def test_n64_byte_order_conversion(self) -> None:
        z64 = bytes.fromhex("80371240") + b"\xAA\xBB\xCC\xDD"
        v64 = convert_n64_byte_order(z64, "v64")
        n64 = convert_n64_byte_order(z64, "n64")
        self.assertEqual(detect_n64_byte_order(v64), "v64")
        self.assertEqual(detect_n64_byte_order(n64), "n64")
        self.assertEqual(convert_n64_byte_order(v64, "z64"), z64)
        self.assertEqual(convert_n64_byte_order(n64, "z64"), z64)

    def test_n64_invalid_magic_raises(self) -> None:
        with self.assertRaises(ValueError):
            convert_n64_byte_order(b"ABCD1234", "z64")


def _write_temp_file(name: str, data: bytes) -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp_tests"
    root.mkdir(exist_ok=True)
    path = root / name
    path.write_bytes(data)
    return path
