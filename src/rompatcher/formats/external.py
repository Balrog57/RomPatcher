from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..exceptions import DependencyMissingError
from .base import BasePatch, ProgressCallback, report_progress


class BSDiffPatch(BasePatch):
    format_name = "BSDiff"

    def __init__(self, patch_data: bytes) -> None:
        self.patch_data = patch_data

    @classmethod
    def from_bytes(cls, data: bytes, path: Path | None = None) -> "BSDiffPatch":
        del path
        return cls(data)

    def get_notes(self) -> list[str]:
        return ["Support BSDiff via dépendance optionnelle `bsdiff4`."]

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
        report_progress(progress, 0.2, "BSDiff : chargement de la dépendance")
        try:
            import bsdiff4  # type: ignore
        except ImportError as exc:
            raise DependencyMissingError(
                "Le support BSDiff requiert `python -m pip install bsdiff4`."
            ) from exc
        report_progress(progress, 0.7, "BSDiff : application du patch")
        output = bsdiff4.patch(source, self.patch_data)
        report_progress(progress, 1.0, "BSDiff : terminé")
        return output


class VCDiffPatch(BasePatch):
    format_name = "VCDiff / xdelta"

    def __init__(self, patch_data: bytes) -> None:
        self.patch_data = patch_data

    @classmethod
    def from_bytes(cls, data: bytes, path: Path | None = None) -> "VCDiffPatch":
        del path
        return cls(data)

    def get_notes(self) -> list[str]:
        return ["Support via `xdelta3.exe` ou `xdelta3` présent dans le PATH."]

    def _resolve_executable(self) -> str:
        candidates = [
            shutil.which("xdelta3"),
            shutil.which("xdelta"),
            str((Path.cwd() / "tools" / "xdelta3.exe").resolve()),
            str((Path.cwd() / "tools" / "xdelta3").resolve()),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        raise DependencyMissingError(
            "Le support xdelta/VCDiff requiert `xdelta3` dans le PATH ou `tools/xdelta3.exe`."
        )

    def apply(
        self,
        source: bytes,
        *,
        source_path: Path | None = None,
        patch_path: Path | None = None,
        force: bool = False,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        del force
        exe = self._resolve_executable()
        report_progress(progress, 0.1, "xdelta : préparation des fichiers temporaires")
        with tempfile.TemporaryDirectory(prefix="rompatcher_xdelta_") as temp_dir:
            temp_root = Path(temp_dir)
            source_file = temp_root / "source.bin"
            patch_file = temp_root / "patch.xdelta"
            output_file = temp_root / "output.bin"

            if source_path is None:
                source_file.write_bytes(source)
            else:
                source_file = source_path

            if patch_path is None:
                patch_file.write_bytes(self.patch_data)
            else:
                patch_file = patch_path

            report_progress(progress, 0.5, "xdelta : application du patch")
            result = subprocess.run(
                [exe, "-d", "-s", str(source_file), str(patch_file), str(output_file)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip() or result.stdout.strip() or "Erreur inconnue xdelta."
                raise RuntimeError(stderr)

            report_progress(progress, 1.0, "xdelta : terminé")
            return output_file.read_bytes()
