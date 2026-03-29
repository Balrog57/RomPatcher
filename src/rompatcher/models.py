from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class PatchMetadata:
    title: str | None = None
    author: str | None = None
    description: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not any([self.title, self.author, self.description, self.extra])


@dataclass(slots=True)
class ValidationInfo:
    algorithm: str
    expected: str | list[str]

    def display_expected(self) -> str:
        if isinstance(self.expected, list):
            return ", ".join(self.expected)
        return self.expected


@dataclass(slots=True)
class PatchDescription:
    format_name: str
    metadata: PatchMetadata = field(default_factory=PatchMetadata)
    validation: ValidationInfo | None = None
    notes: list[str] = field(default_factory=list)
    can_undo: bool = False


@dataclass(slots=True)
class HeaderAction:
    removed: bool = False
    header_bytes: bytes = b""
    new_extension: str | None = None
    note: str | None = None


@dataclass(slots=True)
class ApplyResult:
    output_path: Path
    format_name: str
    metadata: PatchMetadata
    output_size: int
    notes: list[str] = field(default_factory=list)
    header_action: HeaderAction = field(default_factory=HeaderAction)


@dataclass(slots=True)
class CreateResult:
    output_path: Path
    format_name: str
    patch_size: int
    notes: list[str] = field(default_factory=list)
    metadata: PatchMetadata = field(default_factory=PatchMetadata)
