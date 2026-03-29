from __future__ import annotations

from pathlib import Path
from typing import Callable

from .creator import create_patch
from .formats import parse_patch_bytes
from .headers import strip_known_header
from .models import ApplyResult, CreateResult, HeaderAction, PatchDescription

ProgressCallback = Callable[[float, str | None], None]


def parse_patch_file(patch_path: str | Path):
    patch_path = Path(patch_path)
    return parse_patch_bytes(patch_path.read_bytes(), patch_path)


def inspect_patch(patch_path: str | Path) -> PatchDescription:
    patch = parse_patch_file(patch_path)
    return patch.describe()


def default_output_path(rom_path: Path, header_action: HeaderAction) -> Path:
    suffix = header_action.new_extension or rom_path.suffix
    return rom_path.with_name(f"{rom_path.stem} (patched){suffix}")


def apply_patch(
    rom_path: str | Path,
    patch_path: str | Path,
    *,
    output_path: str | Path | None = None,
    force: bool = False,
    strip_snes_header: bool = True,
    progress: ProgressCallback | None = None,
) -> ApplyResult:
    rom_path = Path(rom_path)
    patch_path = Path(patch_path)

    patch = parse_patch_file(patch_path)
    description = patch.describe()

    original_source = rom_path.read_bytes()
    source_bytes = original_source
    header_action = HeaderAction()
    if strip_snes_header:
        source_bytes, header_action = strip_known_header(rom_path, original_source)

    if output_path is None:
        final_output_path = default_output_path(rom_path, header_action)
    else:
        final_output_path = Path(output_path)
        if header_action.removed and final_output_path.suffix.lower() == ".smc":
            final_output_path = final_output_path.with_suffix(".sfc")

    source_path_for_patch = rom_path if source_bytes == original_source else None
    output_bytes = patch.apply(
        source_bytes,
        source_path=source_path_for_patch,
        patch_path=patch_path,
        force=force,
        progress=progress,
    )

    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_bytes(output_bytes)

    notes = list(description.notes)
    if header_action.note:
        notes.append(header_action.note)
    if force:
        notes.append("Application forcée sans bloquer sur les checksums.")

    return ApplyResult(
        output_path=final_output_path,
        format_name=description.format_name,
        metadata=description.metadata,
        output_size=len(output_bytes),
        notes=notes,
        header_action=header_action,
    )


__all__ = [
    "apply_patch",
    "create_patch",
    "inspect_patch",
    "parse_patch_file",
    "ApplyResult",
    "CreateResult",
]
