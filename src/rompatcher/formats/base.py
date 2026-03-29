from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from ..models import PatchDescription, PatchMetadata, ValidationInfo

ProgressCallback = Callable[[float, str | None], None]


def report_progress(callback: ProgressCallback | None, fraction: float, message: str | None = None) -> None:
    if callback is None:
        return
    callback(max(0.0, min(1.0, float(fraction))), message)


class BasePatch(ABC):
    format_name = "Unknown"

    def get_metadata(self) -> PatchMetadata:
        return PatchMetadata()

    def get_validation_info(self) -> ValidationInfo | None:
        return None

    def get_notes(self) -> list[str]:
        return []

    def supports_undo(self) -> bool:
        return False

    def describe(self) -> PatchDescription:
        return PatchDescription(
            format_name=self.format_name,
            metadata=self.get_metadata(),
            validation=self.get_validation_info(),
            notes=self.get_notes(),
            can_undo=self.supports_undo(),
        )

    @abstractmethod
    def apply(
        self,
        source: bytes,
        *,
        source_path: Path | None = None,
        patch_path: Path | None = None,
        force: bool = False,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        raise NotImplementedError
