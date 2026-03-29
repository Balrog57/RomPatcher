from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..binary import BinaryReader
from ..checksums import md5_hex
from ..exceptions import ChecksumMismatchError, PatchFormatError
from ..models import PatchMetadata, ValidationInfo
from .base import BasePatch, ProgressCallback, report_progress


RUP_MAGIC = b"NINJA2"
RUP_COMMAND_END = 0x00
RUP_COMMAND_OPEN_NEW_FILE = 0x01
RUP_COMMAND_XOR_RECORD = 0x02


def read_rup_vlv(reader: BinaryReader) -> int:
    byte_count = reader.read_u8()
    value = 0
    for index in range(byte_count):
        value += reader.read_u8() << (index * 8)
    return value


@dataclass(slots=True)
class RUPXORRecord:
    offset: int
    xor_data: bytes


@dataclass(slots=True)
class RUPFileEntry:
    file_name: str
    rom_type: int
    source_file_size: int
    target_file_size: int
    source_md5: str
    target_md5: str
    overflow_mode: str | None = None
    overflow_data: bytes = b""
    records: list[RUPXORRecord] = field(default_factory=list)


class RUPPatch(BasePatch):
    format_name = "RUP"

    def __init__(
        self,
        *,
        text_encoding: int,
        author: str,
        version: str,
        title: str,
        genre: str,
        language: str,
        date: str,
        web: str,
        description: str,
        files: list[RUPFileEntry],
    ) -> None:
        self.text_encoding = text_encoding
        self.author = author
        self.version = version
        self.title = title
        self.genre = genre
        self.language = language
        self.date = date
        self.web = web
        self.description = description
        self.files = files

    @classmethod
    def from_bytes(cls, data: bytes, path: Path | None = None) -> "RUPPatch":
        del path
        if not data.startswith(RUP_MAGIC):
            raise PatchFormatError("En-tête RUP invalide.")

        reader = BinaryReader(data)
        reader.seek(len(RUP_MAGIC))
        text_encoding = reader.read_u8()
        author = reader.read_text(84).rstrip("\x00")
        version = reader.read_text(11).rstrip("\x00")
        title = reader.read_text(256).rstrip("\x00")
        genre = reader.read_text(48).rstrip("\x00")
        language = reader.read_text(48).rstrip("\x00")
        date = reader.read_text(8).rstrip("\x00")
        web = reader.read_text(512).rstrip("\x00")
        description = reader.read_text(1074).replace("\\n", "\n").rstrip("\x00")

        reader.seek(0x800)
        files: list[RUPFileEntry] = []
        current: RUPFileEntry | None = None

        while not reader.eof():
            command = reader.read_u8()
            if command == RUP_COMMAND_OPEN_NEW_FILE:
                if current is not None:
                    files.append(current)
                file_name = reader.read_text(read_rup_vlv(reader)).rstrip("\x00")
                rom_type = reader.read_u8()
                source_file_size = read_rup_vlv(reader)
                target_file_size = read_rup_vlv(reader)
                source_md5 = reader.read_bytes(16).hex()
                target_md5 = reader.read_bytes(16).hex()
                overflow_mode = None
                overflow_data = b""
                if source_file_size != target_file_size:
                    overflow_mode = reader.read_text(1)
                    if overflow_mode not in {"M", "A"}:
                        raise PatchFormatError("Mode overflow RUP invalide.")
                    overflow_data = reader.read_bytes(read_rup_vlv(reader))

                current = RUPFileEntry(
                    file_name=file_name,
                    rom_type=rom_type,
                    source_file_size=source_file_size,
                    target_file_size=target_file_size,
                    source_md5=source_md5,
                    target_md5=target_md5,
                    overflow_mode=overflow_mode,
                    overflow_data=overflow_data,
                )
            elif command == RUP_COMMAND_XOR_RECORD:
                if current is None:
                    raise PatchFormatError("Enregistrement XOR RUP sans fichier courant.")
                current.records.append(
                    RUPXORRecord(
                        offset=read_rup_vlv(reader),
                        xor_data=reader.read_bytes(read_rup_vlv(reader)),
                    )
                )
            elif command == RUP_COMMAND_END:
                if current is not None:
                    files.append(current)
                break
            else:
                raise PatchFormatError(f"Commande RUP invalide : 0x{command:02X}")

        return cls(
            text_encoding=text_encoding,
            author=author,
            version=version,
            title=title,
            genre=genre,
            language=language,
            date=date,
            web=web,
            description=description,
            files=files,
        )

    def get_metadata(self) -> PatchMetadata:
        return PatchMetadata(
            title=self.title or None,
            author=self.author or None,
            description=self.description or None,
            extra={
                "version": self.version,
                "genre": self.genre,
                "language": self.language,
                "date": self.date,
                "web": self.web,
            },
        )

    def get_validation_info(self) -> ValidationInfo:
        return ValidationInfo("MD5", [entry.source_md5 for entry in self.files])

    def get_notes(self) -> list[str]:
        return [f"{len(self.files)} fichier(s) candidat(s) dans le patch RUP."]

    def supports_undo(self) -> bool:
        return True

    def _select_file(self, source: bytes, force: bool) -> tuple[RUPFileEntry, bool]:
        source_md5 = md5_hex(source)
        for entry in self.files:
            if entry.source_md5 == source_md5:
                return entry, False
            if entry.target_md5 == source_md5:
                return entry, True
        if not force:
            raise ChecksumMismatchError("Aucune entrée RUP ne correspond au MD5 de la source.")
        if not self.files:
            raise PatchFormatError("Le patch RUP ne contient aucune entrée.")
        fallback = self.files[0]
        return fallback, fallback.target_md5 == source_md5

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

        entry, undo = self._select_file(source, force)
        target_size = entry.source_file_size if undo else entry.target_file_size
        target = bytearray(target_size)
        target[: min(len(source), target_size)] = source[:target_size]

        total = max(len(entry.records), 1)
        for index, record in enumerate(entry.records, start=1):
            for offset, xor_byte in enumerate(record.xor_data):
                source_index = record.offset + offset
                source_byte = source[source_index] if source_index < len(source) else 0
                target[source_index] = source_byte ^ xor_byte
            report_progress(progress, index / total, f"RUP : {index}/{total}")

        if entry.overflow_mode == "A" and not undo:
            overflow = bytes(byte ^ 0xFF for byte in entry.overflow_data)
            start = entry.source_file_size
            target[start : start + len(overflow)] = overflow
        elif entry.overflow_mode == "M" and undo:
            overflow = bytes(byte ^ 0xFF for byte in entry.overflow_data)
            start = entry.target_file_size
            target[start : start + len(overflow)] = overflow

        if not force:
            expected_md5 = entry.source_md5 if undo else entry.target_md5
            actual_md5 = md5_hex(target)
            if actual_md5 != expected_md5:
                raise ChecksumMismatchError(
                    f"MD5 cible RUP attendu {expected_md5}, obtenu {actual_md5}."
                )

        return bytes(target)
