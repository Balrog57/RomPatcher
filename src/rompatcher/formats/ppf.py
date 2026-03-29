from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..binary import BinaryReader
from ..exceptions import PatchFormatError
from ..models import PatchMetadata
from .base import BasePatch, ProgressCallback, report_progress


PPF_MAGIC = b"PPF"
PPF_BEGIN_DIZ = b"@BEGIN_FILE_ID.DIZ"
PPF_END_DIZ = b"@END_FILE_ID.DIZ"


@dataclass(slots=True)
class PPFRecord:
    offset: int
    data: bytes
    undo_data: bytes | None = None


class PPFPatch(BasePatch):
    format_name = "PPF"

    def __init__(
        self,
        *,
        version: int,
        description: str,
        image_type: int,
        block_check: bytes | None,
        undo_enabled: bool,
        file_id_diz: str | None,
        records: list[PPFRecord],
    ) -> None:
        self.version = version
        self.description = description
        self.image_type = image_type
        self.block_check = block_check
        self.undo_enabled = undo_enabled
        self.file_id_diz = file_id_diz
        self.records = records

    @classmethod
    def from_bytes(cls, data: bytes, path: Path | None = None) -> "PPFPatch":
        del path
        if not data.startswith(PPF_MAGIC):
            raise PatchFormatError("En-tête PPF invalide.")

        reader = BinaryReader(data)
        reader.seek(3)
        version_text = reader.read_text(2)
        version_marker = reader.read_u8() + 1
        try:
            version_from_text = int(version_text) // 10
        except ValueError as exc:
            raise PatchFormatError("Version PPF invalide.") from exc
        if version_from_text != version_marker or version_from_text not in {1, 2, 3}:
            raise PatchFormatError("Version PPF non supportée.")

        version = version_from_text
        description = reader.read_text(50).rstrip(" \x00")
        image_type = 0
        block_check: bytes | None = None
        undo_enabled = False

        if version == 3:
            image_type = reader.read_u8()
            block_check_enabled = reader.read_u8() != 0
            undo_enabled = reader.read_u8() != 0
            reader.read_u8()
            if block_check_enabled:
                block_check = reader.read_bytes(1024)
        elif version == 2:
            reader.read_u32_be()
            block_check = reader.read_bytes(1024)

        records: list[PPFRecord] = []
        file_id_diz: str | None = None
        while not reader.eof():
            if reader.remaining() >= len(PPF_BEGIN_DIZ) and reader.peek_bytes(len(PPF_BEGIN_DIZ)) == PPF_BEGIN_DIZ:
                reader.read_bytes(len(PPF_BEGIN_DIZ))
                remaining = reader.read_bytes(reader.remaining())
                end_index = remaining.find(PPF_END_DIZ)
                if end_index != -1:
                    file_id_diz = remaining[:end_index].decode("latin-1", errors="replace")
                else:
                    file_id_diz = remaining.decode("latin-1", errors="replace")
                break

            if version == 3:
                offset = reader.read_u64_le()
            else:
                offset = reader.read_u32_le()
            length = reader.read_u8()
            record_data = reader.read_bytes(length)
            undo_data = reader.read_bytes(length) if undo_enabled else None
            records.append(PPFRecord(offset=offset, data=record_data, undo_data=undo_data))

        return cls(
            version=version,
            description=description,
            image_type=image_type,
            block_check=block_check,
            undo_enabled=undo_enabled,
            file_id_diz=file_id_diz,
            records=records,
        )

    def get_metadata(self) -> PatchMetadata:
        description = self.description or None
        extra: dict[str, str] = {}
        if self.file_id_diz:
            extra["file_id_diz"] = self.file_id_diz
        return PatchMetadata(description=description, extra=extra)

    def get_notes(self) -> list[str]:
        notes = [f"PPF v{self.version} avec {len(self.records)} enregistrement(s)."]
        if self.undo_enabled:
            notes.append("Le patch contient aussi les données d'annulation.")
        if self.file_id_diz:
            notes.append("FILE_ID.DIZ détecté.")
        return notes

    def supports_undo(self) -> bool:
        return self.undo_enabled

    def apply(
        self,
        source: bytes,
        *,
        source_path: Path | None = None,
        patch_path: Path | None = None,
        force: bool = False,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        del source_path, patch_path, force

        target_size = len(source)
        for record in self.records:
            target_size = max(target_size, record.offset + len(record.data))

        target = bytearray(target_size)
        target[: len(source)] = source

        undoing = False
        if self.undo_enabled and self.records:
            first = self.records[0]
            current = target[first.offset : first.offset + len(first.data)]
            undoing = current == first.data

        total = max(len(self.records), 1)
        for index, record in enumerate(self.records, start=1):
            payload = record.undo_data if undoing and record.undo_data is not None else record.data
            target[record.offset : record.offset + len(payload)] = payload
            report_progress(progress, index / total, f"PPF : {index}/{total}")

        return bytes(target)
