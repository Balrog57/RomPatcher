from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..binary import BinaryReader
from ..checksums import crc32, format_crc32
from ..exceptions import ChecksumMismatchError, PatchFormatError
from ..models import PatchMetadata, ValidationInfo
from .base import BasePatch, ProgressCallback, report_progress


BPS_MAGIC = b"BPS1"
BPS_SOURCE_READ = 0
BPS_TARGET_READ = 1
BPS_SOURCE_COPY = 2
BPS_TARGET_COPY = 3


def read_bps_vlv(reader: BinaryReader) -> int:
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
class BPSAction:
    action_type: int
    length: int
    literal: bytes = b""
    relative_offset: int = 0


class BPSPatch(BasePatch):
    format_name = "BPS"

    def __init__(
        self,
        *,
        source_size: int,
        target_size: int,
        metadata_text: str,
        actions: list[BPSAction],
        source_checksum: int,
        target_checksum: int,
        patch_checksum: int,
    ) -> None:
        self.source_size = source_size
        self.target_size = target_size
        self.metadata_text = metadata_text
        self.actions = actions
        self.source_checksum = source_checksum
        self.target_checksum = target_checksum
        self.patch_checksum = patch_checksum

    @classmethod
    def from_bytes(cls, data: bytes, path: Path | None = None) -> "BPSPatch":
        del path
        if not data.startswith(BPS_MAGIC):
            raise PatchFormatError("En-tête BPS invalide.")

        reader = BinaryReader(data)
        reader.seek(len(BPS_MAGIC))

        source_size = read_bps_vlv(reader)
        target_size = read_bps_vlv(reader)
        metadata_length = read_bps_vlv(reader)
        metadata_text = reader.read_text(metadata_length, encoding="utf-8") if metadata_length else ""

        actions: list[BPSAction] = []
        while reader.tell() < len(data) - 12:
            raw = read_bps_vlv(reader)
            action_type = raw & 0x03
            length = (raw >> 2) + 1
            if action_type == BPS_TARGET_READ:
                actions.append(BPSAction(action_type=action_type, length=length, literal=reader.read_bytes(length)))
            elif action_type in {BPS_SOURCE_COPY, BPS_TARGET_COPY}:
                relative = read_bps_vlv(reader)
                signed_relative = (-1 if relative & 1 else 1) * (relative >> 1)
                actions.append(BPSAction(action_type=action_type, length=length, relative_offset=signed_relative))
            else:
                actions.append(BPSAction(action_type=action_type, length=length))

        source_checksum = reader.read_u32_le()
        target_checksum = reader.read_u32_le()
        patch_checksum = reader.read_u32_le()
        if patch_checksum != crc32(data[:-4]):
            raise PatchFormatError("Checksum interne BPS invalide.")

        return cls(
            source_size=source_size,
            target_size=target_size,
            metadata_text=metadata_text,
            actions=actions,
            source_checksum=source_checksum,
            target_checksum=target_checksum,
            patch_checksum=patch_checksum,
        )

    def get_metadata(self) -> PatchMetadata:
        if not self.metadata_text:
            return PatchMetadata()
        return PatchMetadata(description=self.metadata_text, extra={"metadata": self.metadata_text})

    def get_validation_info(self) -> ValidationInfo:
        return ValidationInfo("CRC32", format_crc32(self.source_checksum))

    def get_notes(self) -> list[str]:
        return [
            f"{len(self.actions)} action(s) BPS.",
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
                f"CRC32 source BPS attendu {format_crc32(self.source_checksum)}, obtenu {format_crc32(source_crc)}."
            )

        target = bytearray(self.target_size)
        target_pos = 0
        source_relative = 0
        target_relative = 0
        total = max(len(self.actions), 1)

        for index, action in enumerate(self.actions, start=1):
            if action.action_type == BPS_SOURCE_READ:
                chunk = source[target_pos : target_pos + action.length]
                if len(chunk) != action.length:
                    raise PatchFormatError("Lecture BPS hors de la ROM source.")
                target[target_pos : target_pos + action.length] = chunk
                target_pos += action.length
            elif action.action_type == BPS_TARGET_READ:
                target[target_pos : target_pos + action.length] = action.literal
                target_pos += action.length
            elif action.action_type == BPS_SOURCE_COPY:
                source_relative += action.relative_offset
                for _ in range(action.length):
                    if source_relative < 0 or source_relative >= len(source):
                        raise PatchFormatError("Copie BPS source hors limites.")
                    target[target_pos] = source[source_relative]
                    target_pos += 1
                    source_relative += 1
            elif action.action_type == BPS_TARGET_COPY:
                target_relative += action.relative_offset
                for _ in range(action.length):
                    if target_relative < 0 or target_relative >= len(target):
                        raise PatchFormatError("Copie BPS cible hors limites.")
                    target[target_pos] = target[target_relative]
                    target_pos += 1
                    target_relative += 1
            else:
                raise PatchFormatError(f"Action BPS inconnue : {action.action_type}")

            report_progress(progress, index / total, f"BPS : {index}/{total}")

        if not force:
            target_crc = crc32(target)
            if target_crc != self.target_checksum:
                raise ChecksumMismatchError(
                    f"CRC32 cible BPS attendu {format_crc32(self.target_checksum)}, obtenu {format_crc32(target_crc)}."
                )

        return bytes(target)
