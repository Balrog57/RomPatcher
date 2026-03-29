from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..binary import BinaryReader
from ..exceptions import PatchFormatError
from ..models import PatchMetadata
from .base import BasePatch, ProgressCallback, report_progress


IPS_MAGIC = b"PATCH"
IPS_EOF = 0x454F46


@dataclass(slots=True)
class IPSRecord:
    offset: int
    length: int
    data: bytes = b""
    fill_byte: int | None = None

    @property
    def is_rle(self) -> bool:
        return self.fill_byte is not None


class IPSPatch(BasePatch):
    def __init__(
        self,
        records: list[IPSRecord],
        *,
        truncate_size: int | None = None,
        ebp_metadata: dict[str, str] | None = None,
    ) -> None:
        self.records = records
        self.truncate_size = truncate_size
        self.ebp_metadata = ebp_metadata

    @property
    def format_name(self) -> str:
        return "EBP" if self.ebp_metadata else "IPS"

    @classmethod
    def from_bytes(cls, data: bytes, path: Path | None = None) -> "IPSPatch":
        if not data.startswith(IPS_MAGIC):
            raise PatchFormatError("En-tête IPS invalide.")

        reader = BinaryReader(data)
        reader.seek(len(IPS_MAGIC))
        records: list[IPSRecord] = []
        truncate_size: int | None = None
        ebp_metadata: dict[str, str] | None = None

        while not reader.eof():
            offset = reader.read_u24_be()
            if offset == IPS_EOF:
                if reader.eof():
                    break

                remaining = data[reader.tell() :]
                stripped = remaining.lstrip()
                if len(remaining) == 3:
                    truncate_size = int.from_bytes(remaining, "big")
                    break
                if stripped.startswith(b"{"):
                    try:
                        raw = json.loads(remaining.decode("utf-8"))
                    except json.JSONDecodeError as exc:
                        raise PatchFormatError("Bloc JSON EBP invalide.") from exc
                    ebp_metadata = {str(key): str(value) for key, value in raw.items()}
                    break
                raise PatchFormatError("Bloc de fin IPS invalide.")

            length = reader.read_u16_be()
            if length == 0:
                rle_length = reader.read_u16_be()
                fill_byte = reader.read_u8()
                records.append(IPSRecord(offset=offset, length=rle_length, fill_byte=fill_byte))
            else:
                records.append(IPSRecord(offset=offset, length=length, data=reader.read_bytes(length)))

        return cls(records, truncate_size=truncate_size, ebp_metadata=ebp_metadata)

    def get_metadata(self) -> PatchMetadata:
        if not self.ebp_metadata:
            return PatchMetadata()
        lowered = {key.lower(): value for key, value in self.ebp_metadata.items()}
        extra = dict(self.ebp_metadata)
        extra.pop("patcher", None)
        return PatchMetadata(
            title=lowered.get("title"),
            author=lowered.get("author"),
            description=lowered.get("description"),
            extra=extra,
        )

    def get_notes(self) -> list[str]:
        notes = [f"{len(self.records)} enregistrement(s) IPS."]
        if self.truncate_size is not None and not self.ebp_metadata:
            notes.append(f"Taille cible imposée : {self.truncate_size} octets.")
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
        del source_path, patch_path, force

        if self.truncate_size is not None and not self.ebp_metadata:
            target = bytearray(self.truncate_size)
            target[: min(len(source), self.truncate_size)] = source[: self.truncate_size]
        else:
            target_size = len(source)
            for record in self.records:
                target_size = max(target_size, record.offset + record.length)
            target = bytearray(target_size)
            target[: len(source)] = source

        total = max(len(self.records), 1)
        for index, record in enumerate(self.records, start=1):
            if record.offset + record.length > len(target):
                target.extend(b"\x00" * (record.offset + record.length - len(target)))
            if record.is_rle:
                target[record.offset : record.offset + record.length] = bytes([record.fill_byte]) * record.length
            else:
                target[record.offset : record.offset + record.length] = record.data
            report_progress(progress, index / total, f"IPS/EBP : {index}/{total}")

        return bytes(target)
