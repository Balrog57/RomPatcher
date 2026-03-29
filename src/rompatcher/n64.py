from __future__ import annotations

from pathlib import Path


N64_Z64_MAGIC = bytes.fromhex("80371240")
N64_V64_MAGIC = bytes.fromhex("37804012")
N64_N64_MAGIC = bytes.fromhex("40123780")


def detect_n64_byte_order(data: bytes) -> str | None:
    header = data[:4]
    if header == N64_Z64_MAGIC:
        return "z64"
    if header == N64_V64_MAGIC:
        return "v64"
    if header == N64_N64_MAGIC:
        return "n64"
    return None


def _swap_pairs(data: bytes) -> bytes:
    if len(data) % 2 != 0:
        raise ValueError("La taille du fichier doit être multiple de 2 pour convertir en v64.")
    output = bytearray(len(data))
    output[0::2] = data[1::2]
    output[1::2] = data[0::2]
    return bytes(output)


def _swap_words(data: bytes) -> bytes:
    if len(data) % 4 != 0:
        raise ValueError("La taille du fichier doit être multiple de 4 pour convertir en n64.")
    output = bytearray(len(data))
    for index in range(0, len(data), 4):
        output[index : index + 4] = data[index : index + 4][::-1]
    return bytes(output)


def convert_n64_byte_order(data: bytes, target: str) -> bytes:
    current = detect_n64_byte_order(data)
    if current is None:
        raise ValueError("Le fichier ne ressemble pas à une ROM Nintendo 64 reconnue.")
    if current == target:
        return data

    if current == "v64":
        data = _swap_pairs(data)
    elif current == "n64":
        data = _swap_words(data)

    if target == "z64":
        return data
    if target == "v64":
        return _swap_pairs(data)
    if target == "n64":
        return _swap_words(data)
    raise ValueError(f"Ordre de bytes N64 inconnu : {target}")


def default_n64_output_path(path: Path, target: str) -> Path:
    return path.with_name(f"{path.stem} ({target}){path.suffix}")
