from __future__ import annotations

import hashlib
import zlib


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def md5_hex(data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def format_crc32(value: int) -> str:
    return f"{value:08X}"


def format_crc16(value: int) -> str:
    return f"{value:04X}"
