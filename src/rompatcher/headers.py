from __future__ import annotations

from pathlib import Path

from .models import HeaderAction


SNES_COPIER_EXTENSIONS = {".sfc", ".smc", ".swc", ".fig"}


def is_snes_copier_headered(path: Path, data: bytes) -> bool:
    extension = path.suffix.lower()
    if extension not in SNES_COPIER_EXTENSIONS:
        return False
    if len(data) > 0x600200 or len(data) % 1024 == 0:
        return False
    return (len(data) - 512) % 262144 == 0


def strip_known_header(path: Path, data: bytes) -> tuple[bytes, HeaderAction]:
    if is_snes_copier_headered(path, data):
        return (
            data[512:],
            HeaderAction(
                removed=True,
                header_bytes=data[:512],
                new_extension=".sfc",
                note="En-tête SNES copier de 512 octets retiré automatiquement.",
            ),
        )
    return data, HeaderAction()
