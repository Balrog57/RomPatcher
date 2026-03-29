from __future__ import annotations

import json
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rompatcher.checksums import crc32, md5_hex
from rompatcher.core import apply_patch, create_patch, inspect_patch
from rompatcher.formats import parse_patch_bytes
from rompatcher.models import PatchMetadata


def encode_ups_vlv(value: int) -> bytes:
    output = bytearray()
    while True:
        chunk = value & 0x7F
        value >>= 7
        if value == 0:
            output.append(0x80 | chunk)
            break
        output.append(chunk)
        value -= 1
    return bytes(output)


def encode_bps_vlv(value: int) -> bytes:
    output = bytearray()
    while True:
        chunk = value & 0x7F
        value >>= 7
        if value == 0:
            output.append(0x80 | chunk)
            break
        output.append(chunk)
        value -= 1
    return bytes(output)


def encode_rup_vlv(value: int) -> bytes:
    if value == 0:
        return b"\x00"
    output = bytearray()
    chunks = []
    while value:
        chunks.append(value & 0xFF)
        value >>= 8
    output.append(len(chunks))
    output.extend(chunks)
    return bytes(output)


class PatchFormatTests(unittest.TestCase):
    def test_ips_and_ebp_metadata(self) -> None:
        patch = b"PATCH" + b"\x00\x00\x01" + b"\x00\x01" + b"X" + b"EOF"
        parsed = parse_patch_bytes(patch, Path("demo.ips"))
        output = parsed.apply(b"ABCD")
        self.assertEqual(output, b"AXCD")

        ebp_patch = patch + json.dumps({"title": "Hack", "author": "Marc", "description": "Test"}).encode("utf-8")
        description = inspect_patch(_write_temp_file("demo.ebp", ebp_patch))
        self.assertEqual(description.format_name, "EBP")
        self.assertEqual(description.metadata.title, "Hack")

    def test_ups_patch(self) -> None:
        source = b"ABCDEF"
        target = b"ABzDEF"
        xor_byte = bytes([source[2] ^ target[2]])
        body = bytearray(b"UPS1")
        body += encode_ups_vlv(len(source))
        body += encode_ups_vlv(len(target))
        body += encode_ups_vlv(2)
        body += xor_byte
        body += b"\x00"
        body += struct.pack("<I", crc32(source))
        body += struct.pack("<I", crc32(target))
        body += struct.pack("<I", crc32(bytes(body)))
        parsed = parse_patch_bytes(bytes(body), Path("demo.ups"))
        self.assertEqual(parsed.apply(source), target)

    def test_bps_patch(self) -> None:
        source = b"ABCDE"
        target = b"ABzDE"
        body = bytearray(b"BPS1")
        body += encode_bps_vlv(len(source))
        body += encode_bps_vlv(len(target))
        body += encode_bps_vlv(0)
        body += encode_bps_vlv(((2 - 1) << 2) | 0)
        body += encode_bps_vlv(((1 - 1) << 2) | 1)
        body += b"z"
        body += encode_bps_vlv(((2 - 1) << 2) | 0)
        body += struct.pack("<I", crc32(source))
        body += struct.pack("<I", crc32(target))
        body += struct.pack("<I", crc32(bytes(body)))
        parsed = parse_patch_bytes(bytes(body), Path("demo.bps"))
        self.assertEqual(parsed.apply(source), target)

    def test_ppf_patch(self) -> None:
        source = b"HELLO"
        target = b"HEXXO"
        body = bytearray()
        body += b"PPF"
        body += b"30"
        body += bytes([2])
        body += b"Example PPF".ljust(50, b" ")
        body += bytes([0, 0, 0, 0])
        body += struct.pack("<Q", 2)
        body += bytes([2])
        body += b"XX"
        parsed = parse_patch_bytes(bytes(body), Path("demo.ppf"))
        self.assertEqual(parsed.apply(source), target)

    def test_rup_patch(self) -> None:
        source = b"ABCD"
        target = b"ABXD"
        xor_byte = bytes([source[2] ^ target[2]])
        body = bytearray()
        body += b"NINJA2"
        body += b"\x00"
        body += b"Marc".ljust(84, b"\x00")
        body += b"1.0".ljust(11, b"\x00")
        body += b"Test RUP".ljust(256, b"\x00")
        body += b"ROM Hack".ljust(48, b"\x00")
        body += b"FR".ljust(48, b"\x00")
        body += b"20260329"
        body += b"https://example.com".ljust(512, b"\x00")
        body += b"Patch RUP".ljust(1074, b"\x00")
        body += bytes([1])
        body += encode_rup_vlv(len(b"game.bin"))
        body += b"game.bin"
        body += b"\x00"
        body += encode_rup_vlv(len(source))
        body += encode_rup_vlv(len(target))
        body += bytes.fromhex(md5_hex(source))
        body += bytes.fromhex(md5_hex(target))
        body += bytes([2])
        body += encode_rup_vlv(2)
        body += encode_rup_vlv(1)
        body += xor_byte
        body += b"\x00"
        parsed = parse_patch_bytes(bytes(body), Path("demo.rup"))
        self.assertEqual(parsed.apply(source), target)

    def test_apply_patch_service(self) -> None:
        rom = _write_temp_file("service.rom", b"ABCDEF")
        patch = _write_temp_file(
            "service.ips",
            b"PATCH" + b"\x00\x00\x03" + b"\x00\x01" + b"Z" + b"EOF",
        )
        result = apply_patch(rom, patch)
        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.output_path.read_bytes(), b"ABCZEF")

    def test_create_ips_patch_roundtrip(self) -> None:
        original = _write_temp_file("create_original.bin", b"HELLO WORLD")
        modified = _write_temp_file("create_modified.bin", b"HELXO WORLD!")
        created = create_patch(original, modified, format_name="ips")
        result = apply_patch(original, created.output_path)
        self.assertEqual(result.output_path.read_bytes(), modified.read_bytes())

    def test_create_bps_patch_roundtrip(self) -> None:
        original = _write_temp_file("create_bps_original.bin", b"ABCDEFGHIJKL")
        modified = _write_temp_file("create_bps_modified.bin", b"ABCDzzzzIJKL")
        created = create_patch(original, modified, format_name="bps")
        result = apply_patch(original, created.output_path)
        self.assertEqual(result.output_path.read_bytes(), modified.read_bytes())

    def test_create_ebp_patch_contains_metadata(self) -> None:
        original = _write_temp_file("create_ebp_original.bin", b"ABCDEFGH")
        modified = _write_temp_file("create_ebp_modified.bin", b"ABXDEFGH")
        created = create_patch(
            original,
            modified,
            format_name="ebp",
            metadata=PatchMetadata(title="Titre", author="Marc", description="Desc"),
        )
        description = inspect_patch(created.output_path)
        self.assertEqual(description.format_name, "EBP")
        self.assertEqual(description.metadata.title, "Titre")

    def test_create_rup_patch_roundtrip(self) -> None:
        original = _write_temp_file("create_rup_original.bin", b"ABCDEFGHIJ")
        modified = _write_temp_file("create_rup_modified.bin", b"ABCDefGHIJKLM")
        created = create_patch(
            original,
            modified,
            format_name="rup",
            metadata=PatchMetadata(title="RUP Test", author="Marc", description="RUP creation"),
        )
        result = apply_patch(original, created.output_path)
        self.assertEqual(result.output_path.read_bytes(), modified.read_bytes())

    def test_create_aps_n64_patch_roundtrip(self) -> None:
        original_bytes = bytearray(0x80)
        original_bytes[:4] = bytes.fromhex("80371240")
        original_bytes[0x10:0x18] = b"CRC12345"
        original_bytes[0x3C:0x3F] = b"ABC"
        modified_bytes = bytearray(original_bytes)
        modified_bytes[0x50] = 0x7F
        original = _write_temp_file("create_n64_original.z64", bytes(original_bytes))
        modified = _write_temp_file("create_n64_modified.z64", bytes(modified_bytes))
        created = create_patch(original, modified, format_name="aps-n64")
        result = apply_patch(original, created.output_path)
        self.assertEqual(result.output_path.read_bytes(), modified.read_bytes())

    def test_create_aps_gba_patch_roundtrip(self) -> None:
        original_bytes = bytearray(0x10000)
        modified_bytes = bytearray(original_bytes)
        modified_bytes[1234] = 0x42
        original = _write_temp_file("create_gba_original.gba", bytes(original_bytes))
        modified = _write_temp_file("create_gba_modified.gba", bytes(modified_bytes))
        created = create_patch(original, modified, format_name="aps-gba")
        result = apply_patch(original, created.output_path)
        self.assertEqual(result.output_path.read_bytes(), modified.read_bytes())


def _write_temp_file(name: str, data: bytes) -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp_tests"
    root.mkdir(exist_ok=True)
    path = root / name
    path.write_bytes(data)
    return path
