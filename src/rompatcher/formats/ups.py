from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..binary import BinaryReader
from ..checksums import crc32, format_crc32
from ..exceptions import ChecksumMismatchError, PatchFormatError
from ..models import ValidationInfo
from .base import BasePatch, ProgressCallback, report_progress


UPS_MAGIC = b"UPS1"


def read_ups_vlv(reader: BinaryReader) -> int:
    data = 0
    shift = 1
    while True:
        value = reader.read_u8()
        data += (value & 0x7F) * shift
        if value & 0x80:
            break
        shift <<= 7
        data += shift
    return data


@dataclass(slots=True)
class UPSRecord:
    relative_offset: int
    xor_data: bytes


class UPSPatch(BasePatch):
    format_name = "UPS"

    def __init__(
        self,
        *,
        source_size: int,
        target_size: int,
        source_checksum: int,
        target_checksum: int,
        patch_checksum: int,
        records: list[UPSRecord],
    ) -> None:
        self.source_size = source_size
        self.target_size = target_size
        self.source_checksum = source_checksum
        self.target_checksum = target_checksum
        self.patch_checksum = patch_checksum
        self.records = records

    @classmethod
    def from_bytes(cls, data: bytes, path: Path | None = None) -> "UPSPatch":
        del path
        if not data.startswith(UPS_MAGIC):
            raise PatchFormatError("En-tête UPS invalide.")

        reader = BinaryReader(data)
        reader.seek(len(UPS_MAGIC))
        source_size = read_ups_vlv(reader)
        target_size = read_ups_vlv(reader)
        records: list[UPSRecord] = []

        while reader.tell() < len(data) - 12:
            relative_offset = read_ups_vlv(reader)
            xor_bytes = bytearray()
            while True:
                byte = reader.read_u8()
                if byte == 0:
                    break
                xor_bytes.append(byte)
            records.append(UPSRecord(relative_offset=relative_offset, xor_data=bytes(xor_bytes)))

        source_checksum = reader.read_u32_le()
        target_checksum = reader.read_u32_le()
        patch_checksum = reader.read_u32_le()
        if patch_checksum != crc32(data[:-4]):
            raise PatchFormatError("Checksum interne UPS invalide.")

        return cls(
            source_size=source_size,
            target_size=target_size,
            source_checksum=source_checksum,
            target_checksum=target_checksum,
            patch_checksum=patch_checksum,
            records=records,
        )

    def get_validation_info(self) -> ValidationInfo:
        return ValidationInfo("CRC32", format_crc32(self.source_checksum))

    def get_notes(self) -> list[str]:
        return [
            f"{len(self.records)} enregistrement(s) UPS.",
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

        source_crc = crc32(source)
        if not force and source_crc != self.source_checksum:
            raise ChecksumMismatchError(
                f"CRC32 source UPS attendu {format_crc32(self.source_checksum)}, obtenu {format_crc32(source_crc)}."
            )

        effective_source_size = self.source_size
        effective_target_size = self.target_size
        if force and len(source) > self.source_size:
            effective_source_size = len(source)
            effective_target_size = max(effective_target_size, effective_source_size)

        target = bytearray(effective_target_size)
        target[: min(len(source), effective_source_size)] = source[:effective_source_size]

        read_pos = 0
        write_pos = 0
        total = max(len(self.records), 1)
        for index, record in enumerate(self.records, start=1):
            read_pos += record.relative_offset
            write_pos += record.relative_offset

            for xor_byte in record.xor_data:
                source_byte = source[read_pos] if read_pos < len(source) else 0
                target[write_pos] = source_byte ^ xor_byte
                read_pos += 1
                write_pos += 1

            read_pos += 1
            write_pos += 1
            report_progress(progress, index / total, f"UPS : {index}/{total}")

        if not force:
            target_crc = crc32(target)
            if target_crc != self.target_checksum:
                raise ChecksumMismatchError(
                    f"CRC32 cible UPS attendu {format_crc32(self.target_checksum)}, obtenu {format_crc32(target_crc)}."
                )

        return bytes(target)
