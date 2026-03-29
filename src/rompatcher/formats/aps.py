from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..binary import BinaryReader
from ..checksums import crc16_ccitt_false, format_crc16
from ..exceptions import ChecksumMismatchError, PatchFormatError
from ..models import ValidationInfo
from .base import BasePatch, ProgressCallback, report_progress


APS_N64_MAGIC = b"APS10"
APS_GBA_MAGIC = b"APS1"
APS_GBA_BLOCK_SIZE = 0x10000
APS_N64_MODE = 0x01


@dataclass(slots=True)
class APSGBARecord:
    offset: int
    source_crc16: int
    target_crc16: int
    xor_bytes: bytes


class APSGBAPatch(BasePatch):
    format_name = "APS (GBA)"

    def __init__(self, *, source_size: int, target_size: int, records: list[APSGBARecord]) -> None:
        self.source_size = source_size
        self.target_size = target_size
        self.records = records

    @classmethod
    def from_bytes(cls, data: bytes, path: Path | None = None) -> "APSGBAPatch":
        del path
        if not data.startswith(APS_GBA_MAGIC):
            raise PatchFormatError("En-tête APS GBA invalide.")
        if len(data) < 12 or (len(data) - 12) % (4 + 2 + 2 + APS_GBA_BLOCK_SIZE) != 0:
            raise PatchFormatError("Taille APS GBA invalide.")

        reader = BinaryReader(data)
        reader.seek(len(APS_GBA_MAGIC))
        source_size = reader.read_u32_le()
        target_size = reader.read_u32_le()
        records: list[APSGBARecord] = []
        while not reader.eof():
            records.append(
                APSGBARecord(
                    offset=reader.read_u32_le(),
                    source_crc16=reader.read_u16_le(),
                    target_crc16=reader.read_u16_le(),
                    xor_bytes=reader.read_bytes(APS_GBA_BLOCK_SIZE),
                )
            )
        return cls(source_size=source_size, target_size=target_size, records=records)

    def get_validation_info(self) -> ValidationInfo:
        expected = [f"{format_crc16(record.source_crc16)}@0x{record.offset:X}" for record in self.records]
        return ValidationInfo("CRC16/CCITT-FALSE", expected)

    def get_notes(self) -> list[str]:
        return [
            f"{len(self.records)} bloc(s) APS GBA de {APS_GBA_BLOCK_SIZE} octets.",
            f"Taille source : {self.source_size} octets.",
            f"Taille cible : {self.target_size} octets.",
        ]

    def apply(
        self,
        source: bytes,
        *,
        source_path: Path | None = None,
        patch_path: Path | None = None,
        force: bool = False,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        del source_path, patch_path

        if not force and len(source) != self.source_size:
            raise ChecksumMismatchError(
                f"Taille source APS GBA attendue {self.source_size}, obtenue {len(source)}."
            )

        target = bytearray(self.target_size)
        target[: min(len(source), self.target_size)] = source[: self.target_size]
        total = max(len(self.records), 1)
        for index, record in enumerate(self.records, start=1):
            block = source[record.offset : record.offset + APS_GBA_BLOCK_SIZE]
            if len(block) != APS_GBA_BLOCK_SIZE:
                raise PatchFormatError("Bloc source APS GBA incomplet.")
            if not force and crc16_ccitt_false(block) != record.source_crc16:
                raise ChecksumMismatchError(
                    f"CRC16 source APS GBA invalide au bloc 0x{record.offset:X}."
                )

            for block_index, xor_byte in enumerate(record.xor_bytes):
                target[record.offset + block_index] = block[block_index] ^ xor_byte

            if not force:
                target_block = target[record.offset : record.offset + APS_GBA_BLOCK_SIZE]
                if crc16_ccitt_false(target_block) != record.target_crc16:
                    raise ChecksumMismatchError(
                        f"CRC16 cible APS GBA invalide au bloc 0x{record.offset:X}."
                    )

            report_progress(progress, index / total, f"APS GBA : {index}/{total}")

        return bytes(target)


@dataclass(slots=True)
class APSN64Record:
    offset: int
    data: bytes = b""
    fill_byte: int | None = None
    length: int = 0

    @property
    def is_rle(self) -> bool:
        return self.fill_byte is not None


class APSN64Patch(BasePatch):
    format_name = "APS (N64)"

    def __init__(
        self,
        *,
        header_type: int,
        encoding_method: int,
        description: str,
        original_format: int | None,
        cart_id: str | None,
        crc_bytes: bytes | None,
        size_output: int,
        records: list[APSN64Record],
    ) -> None:
        self.header_type = header_type
        self.encoding_method = encoding_method
        self.description = description
        self.original_format = original_format
        self.cart_id = cart_id
        self.crc_bytes = crc_bytes
        self.size_output = size_output
        self.records = records

    @classmethod
    def from_bytes(cls, data: bytes, path: Path | None = None) -> "APSN64Patch":
        del path
        if not data.startswith(APS_N64_MAGIC):
            raise PatchFormatError("En-tête APS N64 invalide.")

        reader = BinaryReader(data)
        reader.seek(len(APS_N64_MAGIC))
        header_type = reader.read_u8()
        encoding_method = reader.read_u8()
        description = reader.read_text(50).rstrip("\x00 ")

        original_format = None
        cart_id = None
        crc_bytes = None
        if header_type == APS_N64_MODE:
            original_format = reader.read_u8()
            cart_id = reader.read_text(3)
            crc_bytes = reader.read_bytes(8)
            reader.read_bytes(5)

        size_output = reader.read_u32_le()
        records: list[APSN64Record] = []
        while not reader.eof():
            offset = reader.read_u32_le()
            length = reader.read_u8()
            if length == 0:
                fill_byte = reader.read_u8()
                rle_length = reader.read_u8()
                records.append(APSN64Record(offset=offset, fill_byte=fill_byte, length=rle_length))
            else:
                records.append(APSN64Record(offset=offset, data=reader.read_bytes(length), length=length))

        return cls(
            header_type=header_type,
            encoding_method=encoding_method,
            description=description,
            original_format=original_format,
            cart_id=cart_id,
            crc_bytes=crc_bytes,
            size_output=size_output,
            records=records,
        )

    def get_validation_info(self) -> ValidationInfo | None:
        if self.header_type != APS_N64_MODE or not self.cart_id or not self.crc_bytes:
            return None
        return ValidationInfo("Cart ID / CRC", f"{self.cart_id} ({self.crc_bytes.hex().upper()})")

    def get_notes(self) -> list[str]:
        notes = [f"{len(self.records)} enregistrement(s) APS N64."]
        if self.description:
            notes.append(self.description)
        if self.original_format is not None:
            notes.append("Format d'origine attendu : v64." if self.original_format == 0 else "Format d'origine attendu : z64.")
        return notes

    def apply(
        self,
        source: bytes,
        *,
        source_path: Path | None = None,
        patch_path: Path | None = None,
        force: bool = False,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        del source_path, patch_path

        if not force and self.header_type == APS_N64_MODE and self.cart_id and self.crc_bytes:
            if source[0x3C:0x3F].decode("latin-1", errors="replace") != self.cart_id or source[0x10:0x18] != self.crc_bytes:
                raise ChecksumMismatchError("Cart ID ou CRC N64 non conforme pour ce patch APS.")

        target = bytearray(self.size_output)
        target[: min(len(source), self.size_output)] = source[: self.size_output]
        total = max(len(self.records), 1)
        for index, record in enumerate(self.records, start=1):
            if record.is_rle:
                target[record.offset : record.offset + record.length] = bytes([record.fill_byte]) * record.length
            else:
                target[record.offset : record.offset + record.length] = record.data
            report_progress(progress, index / total, f"APS N64 : {index}/{total}")
        return bytes(target)
