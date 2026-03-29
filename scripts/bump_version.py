from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "src" / "rompatcher" / "version.py"
PYPROJECT_FILE = ROOT / "pyproject.toml"


def normalize_version(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned.startswith("v"):
        cleaned = cleaned[1:]
    parts = cleaned.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        raise ValueError(f"Version invalide : {value}")
    return ".".join(str(int(part)) for part in parts)


def replace_pattern(path: Path, pattern: str, replacement: str) -> None:
    content = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, content, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Impossible de mettre à jour la version dans {path}")
    path.write_text(updated, encoding="utf-8")


def bump_version(version: str) -> None:
    normalized = normalize_version(version)
    replace_pattern(VERSION_FILE, r'^APP_VERSION = "[^"]+"$', f'APP_VERSION = "{normalized}"')
    replace_pattern(PYPROJECT_FILE, r'^version = "[^"]+"$', f'version = "{normalized}"')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Met à jour la version de RomPatcher Desktop.")
    parser.add_argument("version", help="Nouvelle version sémantique, par exemple 1.0.0")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    bump_version(args.version)
    print(f"Version mise à jour vers {normalize_version(args.version)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
