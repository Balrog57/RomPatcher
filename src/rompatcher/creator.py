from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .checksums import crc32, md5_hex
from .exceptions import RomPatcherError
from .models import CreateResult, PatchMetadata

ProgressCallback = Callable[[float, str | None], None]


def _report(callback, fraction: float, message: str | None = None) -> None:
    if callback is not None:
        callback(max(0.0, min(1.0, float(fraction))), message)


def _encode_ups_vlv(value: int) -> bytes:
    output = bytearray()
    while True:
        chunk = value & 0x7F
        value >>= 7
        if value == 0:
            output.append(0x80 | chunk)
            return bytes(output)
        output.append(chunk)
        value -= 1


def _encode_bps_vlv(value: int) -> bytes:
    output = bytearray()
    while True:
        chunk = value & 0x7F
        value >>= 7
        if value == 0:
            output.append(0x80 | chunk)
            return bytes(output)
        output.append(chunk)
        value -= 1


def _encode_signed_bps_offset(relative: int) -> bytes:
    return _encode_bps_vlv((abs(relative) << 1) | (1 if relative < 0 else 0))


def _encode_rup_vlv(value: int) -> bytes:
    if isinstance(value, str):
        value = len(value.encode("latin-1", errors="replace"))
    if value == 0:
        return b"\x00"
    chunks: list[int] = []
    while value:
        chunks.append(value & 0xFF)
        value >>= 8
    return bytes([len(chunks), *chunks])


@dataclass(slots=True)
class IPSRecordBuild:
    offset: int
    data: bytes
    fill_byte: int | None = None

    @property
    def length(self) -> int:
        return len(self.data) if self.fill_byte is None else len(self.data)

    @property
    def is_rle(self) -> bool:
        return self.fill_byte is not None


@dataclass(slots=True)
class UPSRecordBuild:
    relative_offset: int
    xor_data: bytes


@dataclass(slots=True)
class BPSActionBuild:
    action_type: int
    length: int
    data: bytes = b""
    relative_offset: int = 0


def _default_patch_path(modified_path: Path, fmt: str) -> Path:
    ext = {
        "ips": ".ips",
        "ebp": ".ebp",
        "ups": ".ups",
        "bps": ".bps",
        "ppf": ".ppf",
        "aps-gba": ".aps",
        "aps-n64": ".aps",
        "rup": ".rup",
    }[fmt]
    return modified_path.with_suffix(ext)


def _iter_diff_spans(source: bytes, target: bytes) -> Iterable[tuple[int, bytes]]:
    index = 0
    target_size = len(target)
    while index < target_size:
        source_byte = source[index] if index < len(source) else 0
        target_byte = target[index]
        if source_byte == target_byte:
            index += 1
            continue

        start = index
        buffer = bytearray()
        while index < target_size:
            source_byte = source[index] if index < len(source) else 0
            target_byte = target[index]
            if source_byte == target_byte and len(buffer) > 0:
                break
            if source_byte != target_byte:
                buffer.append(target_byte)
            index += 1
            if len(buffer) >= 0xFFFF:
                break
        yield start, bytes(buffer)


def build_ips_patch(
    source: bytes,
    target: bytes,
    *,
    as_ebp: bool = False,
    metadata: PatchMetadata | None = None,
) -> bytes:
    records: list[IPSRecordBuild] = []
    for offset, payload in _iter_diff_spans(source, target):
        if offset >= 0x1000000:
            raise RomPatcherError("Le format IPS/EBP est limité à 16 Mo.")
        if len(set(payload)) == 1 and len(payload) > 2:
            records.append(IPSRecordBuild(offset=offset, data=payload, fill_byte=payload[0]))
        else:
            records.append(IPSRecordBuild(offset=offset, data=payload))

    if len(target) > len(source):
        last_end = 0
        if records:
            last = records[-1]
            last_end = last.offset + len(last.data)
        if last_end < len(target):
            if len(target) - 1 >= 0x1000000:
                raise RomPatcherError("Le format IPS/EBP est limité à 16 Mo.")
            records.append(IPSRecordBuild(offset=len(target) - 1, data=b"\x00"))

    body = bytearray(b"PATCH")
    for record in records:
        body += record.offset.to_bytes(3, "big")
        if record.is_rle:
            body += (0).to_bytes(2, "big")
            body += len(record.data).to_bytes(2, "big")
            body.append(record.fill_byte)
        else:
            body += len(record.data).to_bytes(2, "big")
            body += record.data

    body += b"EOF"
    if as_ebp:
        metadata_dict = {
            "patcher": "EBPatcher",
            "title": metadata.title or "Untitled",
            "author": metadata.author or "Unknown",
            "description": metadata.description or "No description",
        }
        body += json.dumps(metadata_dict, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    elif len(target) < len(source):
        body += len(target).to_bytes(3, "big")
    return bytes(body)


def build_ups_patch(source: bytes, target: bytes) -> bytes:
    records: list[UPSRecordBuild] = []
    previous_seek = 1
    index = 0
    while index < len(target):
        source_byte = source[index] if index < len(source) else 0
        target_byte = target[index]
        if source_byte == target_byte:
            index += 1
            continue

        current_seek = index + 1
        xor_data = bytearray()
        while index < len(target):
            source_byte = source[index] if index < len(source) else 0
            target_byte = target[index]
            if source_byte == target_byte and xor_data:
                break
            if source_byte != target_byte:
                xor_data.append(source_byte ^ target_byte)
            index += 1
            if index >= len(target):
                break
        records.append(UPSRecordBuild(relative_offset=current_seek - previous_seek, xor_data=bytes(xor_data)))
        previous_seek = current_seek + len(xor_data) + 1

    body = bytearray(b"UPS1")
    body += _encode_ups_vlv(len(source))
    body += _encode_ups_vlv(len(target))
    for record in records:
        body += _encode_ups_vlv(record.relative_offset)
        body += record.xor_data
        body.append(0)
    body += struct.pack("<I", crc32(source))
    body += struct.pack("<I", crc32(target))
    body += struct.pack("<I", crc32(bytes(body)))
    return bytes(body)


def _create_bps_linear_actions(source: bytes, target: bytes) -> list[BPSActionBuild]:
    actions: list[BPSActionBuild] = []
    target_relative_offset = 0
    output_offset = 0
    target_read_length = 0

    def flush_target_read() -> None:
        nonlocal target_read_length
        if target_read_length:
            start = output_offset - target_read_length
            actions.append(BPSActionBuild(action_type=1, length=target_read_length, data=target[start:output_offset]))
            target_read_length = 0

    while output_offset < len(target):
        source_length = 0
        while output_offset + source_length < min(len(source), len(target)):
            if source[output_offset + source_length] != target[output_offset + source_length]:
                break
            source_length += 1

        rle_length = 0
        while output_offset + 1 + rle_length < len(target):
            if target[output_offset] != target[output_offset + 1 + rle_length]:
                break
            rle_length += 1

        if rle_length >= 4:
            target_read_length += 1
            output_offset += 1
            flush_target_read()
            relative_offset = (output_offset - 1) - target_relative_offset
            actions.append(BPSActionBuild(action_type=3, length=rle_length, relative_offset=relative_offset))
            output_offset += rle_length
            target_relative_offset = output_offset - 1
        elif source_length >= 4:
            flush_target_read()
            actions.append(BPSActionBuild(action_type=0, length=source_length))
            output_offset += source_length
        else:
            target_read_length += 1
            output_offset += 1

    flush_target_read()
    return actions


def _create_bps_delta_actions(source: bytes, target: bytes) -> list[BPSActionBuild]:
    source_map: dict[int, list[int]] = {}
    target_map: dict[int, list[int]] = {}
    for offset in range(len(source)):
        symbol = source[offset]
        if offset < len(source) - 1:
            symbol |= source[offset + 1] << 8
        source_map.setdefault(symbol, []).append(offset)

    actions: list[BPSActionBuild] = []
    source_relative_offset = 0
    target_relative_offset = 0
    output_offset = 0
    target_read_length = 0

    def flush_target_read() -> None:
        nonlocal target_read_length
        if target_read_length:
            start = output_offset - target_read_length
            actions.append(BPSActionBuild(action_type=1, length=target_read_length, data=target[start:output_offset]))
            target_read_length = 0

    while output_offset < len(target):
        max_length = 0
        max_offset = 0
        mode = 1

        symbol = target[output_offset]
        if output_offset < len(target) - 1:
            symbol |= target[output_offset + 1] << 8

        length = 0
        while output_offset + length < min(len(source), len(target)) and source[output_offset + length] == target[output_offset + length]:
            length += 1
        if length > max_length:
            max_length = length
            mode = 0

        for source_offset in source_map.get(symbol, []):
            length = 0
            x = source_offset
            y = output_offset
            while x < len(source) and y < len(target) and source[x] == target[y]:
                length += 1
                x += 1
                y += 1
            if length > max_length:
                max_length = length
                max_offset = source_offset
                mode = 2

        for target_offset in target_map.get(symbol, []):
            length = 0
            x = target_offset
            y = output_offset
            while y < len(target) and x < len(target) and target[x] == target[y]:
                length += 1
                x += 1
                y += 1
            if length > max_length:
                max_length = length
                max_offset = target_offset
                mode = 3

        target_map.setdefault(symbol, []).append(output_offset)

        if max_length < 4:
            max_length = min(1, len(target) - output_offset)
            mode = 1

        if mode != 1:
            flush_target_read()

        if mode == 0:
            actions.append(BPSActionBuild(action_type=0, length=max_length))
        elif mode == 1:
            target_read_length += max_length
        elif mode == 2:
            relative_offset = max_offset - source_relative_offset
            source_relative_offset = max_offset + max_length
            actions.append(BPSActionBuild(action_type=2, length=max_length, relative_offset=relative_offset))
        elif mode == 3:
            relative_offset = max_offset - target_relative_offset
            target_relative_offset = max_offset + max_length
            actions.append(BPSActionBuild(action_type=3, length=max_length, relative_offset=relative_offset))

        output_offset += max_length

    flush_target_read()
    return actions


def build_bps_patch(source: bytes, target: bytes, *, delta_mode: bool = True, metadata_text: str = "") -> bytes:
    actions = _create_bps_delta_actions(source, target) if delta_mode else _create_bps_linear_actions(source, target)
    body = bytearray(b"BPS1")
    metadata_bytes = metadata_text.encode("utf-8")
    body += _encode_bps_vlv(len(source))
    body += _encode_bps_vlv(len(target))
    body += _encode_bps_vlv(len(metadata_bytes))
    body += metadata_bytes

    for action in actions:
        body += _encode_bps_vlv(((action.length - 1) << 2) | action.action_type)
        if action.action_type == 1:
            body += action.data
        elif action.action_type in {2, 3}:
            body += _encode_signed_bps_offset(action.relative_offset)

    body += struct.pack("<I", crc32(source))
    body += struct.pack("<I", crc32(target))
    body += struct.pack("<I", crc32(bytes(body)))
    return bytes(body)


def build_ppf_patch(source: bytes, target: bytes, *, description: str = "Patch description") -> bytes:
    if len(source) > len(target):
        target = target + (b"\x00" * (len(source) - len(target)))

    records: list[tuple[int, bytes]] = []
    index = 0
    while index < len(target):
        source_byte = source[index] if index < len(source) else 0
        target_byte = target[index]
        if source_byte == target_byte:
            index += 1
            continue

        start = index
        payload = bytearray()
        while index < len(target):
            source_byte = source[index] if index < len(source) else 0
            target_byte = target[index]
            if source_byte == target_byte and payload:
                break
            if source_byte != target_byte:
                payload.append(target_byte)
            index += 1
            if len(payload) >= 0xFF:
                break
        records.append((start, bytes(payload)))

    if len(target) > len(source) and target and target[-1] == 0:
        records.append((len(target) - 1, b"\x00"))

    body = bytearray()
    body += b"PPF"
    body += b"30"
    body.append(2)
    body += description.encode("latin-1", errors="replace")[:50].ljust(50, b" ")
    body += b"\x00\x00\x00\x00"
    for offset, payload in records:
        body += struct.pack("<Q", offset)
        body.append(len(payload))
        body += payload
    return bytes(body)


def build_aps_gba_patch(source: bytes, target: bytes) -> bytes:
    block_size = 0x10000
    if len(source) != len(target):
        raise RomPatcherError("APS GBA nécessite actuellement un original et un modifié de même taille.")
    if len(source) % block_size != 0:
        raise RomPatcherError("APS GBA nécessite actuellement une taille multiple de 64 Ko.")

    body = bytearray(b"APS1")
    body += struct.pack("<I", len(source))
    body += struct.pack("<I", len(target))

    for offset in range(0, len(source), block_size):
        source_block = source[offset : offset + block_size]
        target_block = target[offset : offset + block_size]
        if source_block == target_block:
            continue
        xor_bytes = bytes(a ^ b for a, b in zip(source_block, target_block))
        body += struct.pack("<I", offset)
        body += struct.pack("<H", _crc16(source_block))
        body += struct.pack("<H", _crc16(target_block))
        body += xor_bytes

    if len(body) == 12:
        raise RomPatcherError("Aucune différence détectée pour créer un patch APS GBA.")
    return bytes(body)


def _crc16(data: bytes) -> int:
    from .checksums import crc16_ccitt_false

    return crc16_ccitt_false(data)


def build_aps_n64_patch(source: bytes, target: bytes, *, original_path: Path, description: str = "no description") -> bytes:
    header_type = 1 if source[:4] == bytes.fromhex("80371240") else 0
    body = bytearray(b"APS10")
    body.append(header_type)
    body.append(0)
    body += description.encode("latin-1", errors="replace")[:50].ljust(50, b"\x00")

    if header_type == 1:
        original_format = 0 if original_path.suffix.lower() == ".v64" else 1
        body.append(original_format)
        body += source[0x3C:0x3F]
        body += source[0x10:0x18]
        body += b"\x00" * 5

    body += struct.pack("<I", len(target))

    index = 0
    while index < len(target):
        source_byte = source[index] if index < len(source) else 0
        target_byte = target[index]
        if source_byte == target_byte:
            index += 1
            continue

        start = index
        buffer = bytearray()
        rle = True
        first = target_byte
        while index < len(target):
            source_byte = source[index] if index < len(source) else 0
            target_byte = target[index]
            if source_byte == target_byte and buffer:
                break
            if source_byte != target_byte:
                buffer.append(target_byte)
                if target_byte != first:
                    rle = False
            index += 1
            if len(buffer) >= 0xFF:
                break

        body += struct.pack("<I", start)
        if rle and len(buffer) > 2:
            body.append(0)
            body.append(first)
            body.append(len(buffer))
        else:
            body.append(len(buffer))
            body += buffer

    return bytes(body)


def build_rup_patch(source: bytes, target: bytes, *, modified_path: Path, metadata: PatchMetadata | None = None) -> bytes:
    from datetime import date

    metadata = metadata or PatchMetadata()
    today = date.today()
    file_name = modified_path.name

    source_work = source
    target_work = target
    overflow_mode = None
    overflow_data = b""

    if len(source) < len(target):
        overflow_mode = "A"
        overflow_data = bytes(byte ^ 0xFF for byte in target[len(source) :])
        target_work = target[: len(source)]
    elif len(source) > len(target):
        overflow_mode = "M"
        overflow_data = bytes(byte ^ 0xFF for byte in source[len(target) :])
        source_work = source[: len(target)]

    records: list[tuple[int, bytes]] = []
    index = 0
    while index < len(target_work):
        source_byte = source_work[index] if index < len(source_work) else 0
        target_byte = target_work[index]
        if source_byte == target_byte:
            index += 1
            continue

        start = index
        xor_data = bytearray()
        while index < len(target_work):
            source_byte = source_work[index] if index < len(source_work) else 0
            target_byte = target_work[index]
            if source_byte == target_byte and xor_data:
                break
            if source_byte != target_byte:
                xor_data.append(source_byte ^ target_byte)
            index += 1
            if index >= len(target_work):
                break
        records.append((start, bytes(xor_data)))

    body = bytearray()
    body += b"NINJA2"
    body.append(0)
    body += (metadata.author or "").encode("latin-1", errors="replace")[:84].ljust(84, b"\x00")
    body += b"1.0".ljust(11, b"\x00")
    body += (metadata.title or "").encode("latin-1", errors="replace")[:256].ljust(256, b"\x00")
    body += b"ROM Hack".ljust(48, b"\x00")
    body += b"Multi".ljust(48, b"\x00")
    body += f"{today.year:04d}{today.month:02d}{today.day:02d}".encode("ascii")
    body += b"".ljust(512, b"\x00")
    body += (metadata.description or "").replace("\n", "\\n").encode("latin-1", errors="replace")[:1074].ljust(1074, b"\x00")

    body.append(1)
    body += _encode_rup_vlv(len(file_name.encode("latin-1", errors="replace")))
    body += file_name.encode("latin-1", errors="replace")
    body.append(0)
    body += _encode_rup_vlv(len(source))
    body += _encode_rup_vlv(len(target))
    body += bytes.fromhex(md5_hex(source))
    body += bytes.fromhex(md5_hex(target))

    if overflow_mode is not None:
        body += overflow_mode.encode("ascii")
        body += _encode_rup_vlv(len(overflow_data))
        body += overflow_data

    for offset, xor_data in records:
        body.append(2)
        body += _encode_rup_vlv(offset)
        body += _encode_rup_vlv(len(xor_data))
        body += xor_data

    body.append(0)
    return bytes(body)


def create_patch(
    original_path: str | Path,
    modified_path: str | Path,
    *,
    format_name: str,
    output_path: str | Path | None = None,
    metadata: PatchMetadata | None = None,
    bps_delta_mode: bool = True,
    progress=None,
) -> CreateResult:
    original_path = Path(original_path)
    modified_path = Path(modified_path)
    metadata = metadata or PatchMetadata()

    original = original_path.read_bytes()
    _report(progress, 0.15, "Lecture du fichier original")
    modified = modified_path.read_bytes()
    _report(progress, 0.3, "Lecture du fichier modifié")

    fmt = format_name.lower()
    fmt = fmt.replace("_", "-")
    if fmt not in {"ips", "ebp", "ups", "bps", "ppf", "aps-gba", "aps-n64", "rup"}:
        raise RomPatcherError(f"Création non supportée pour le format {format_name}.")

    if fmt == "ips":
        patch_bytes = build_ips_patch(original, modified)
        notes = ["Patch IPS créé nativement en Python."]
    elif fmt == "ebp":
        patch_bytes = build_ips_patch(original, modified, as_ebp=True, metadata=metadata)
        notes = ["Patch EBP créé à partir d'une base IPS avec métadonnées JSON."]
    elif fmt == "ups":
        patch_bytes = build_ups_patch(original, modified)
        notes = ["Patch UPS créé nativement en Python."]
    elif fmt == "bps":
        metadata_text = metadata.description or ""
        patch_bytes = build_bps_patch(original, modified, delta_mode=bps_delta_mode, metadata_text=metadata_text)
        notes = [f"Patch BPS créé en mode {'delta' if bps_delta_mode else 'linear'}."]
    elif fmt == "aps-gba":
        patch_bytes = build_aps_gba_patch(original, modified)
        notes = ["Patch APS GBA créé bloc par bloc sur 64 Ko."]
    elif fmt == "aps-n64":
        patch_bytes = build_aps_n64_patch(
            original,
            modified,
            original_path=original_path,
            description=metadata.description or "no description",
        )
        notes = ["Patch APS N64 créé nativement en Python."]
    elif fmt == "rup":
        patch_bytes = build_rup_patch(original, modified, modified_path=modified_path, metadata=metadata)
        notes = ["Patch RUP créé nativement en Python."]
    else:
        patch_bytes = build_ppf_patch(original, modified, description=metadata.description or "Patch description")
        notes = ["Patch PPF v3 créé nativement en Python."]

    _report(progress, 0.9, "Écriture du patch")

    final_output_path = Path(output_path) if output_path is not None else _default_patch_path(modified_path, fmt)
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_bytes(patch_bytes)
    _report(progress, 1.0, "Patch créé")

    return CreateResult(
        output_path=final_output_path,
        format_name=fmt.upper(),
        patch_size=len(patch_bytes),
        notes=notes,
        metadata=metadata,
    )
