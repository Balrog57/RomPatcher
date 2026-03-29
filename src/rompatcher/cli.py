from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import apply_patch, create_patch, inspect_patch
from .gui import launch
from .models import PatchMetadata
from .n64 import convert_n64_byte_order, default_n64_output_path


def _print_description(path: Path) -> None:
    description = inspect_patch(path)
    print(f"Format : {description.format_name}")
    if description.validation:
        print(f"Validation : {description.validation.algorithm} {description.validation.display_expected()}")
    if not description.metadata.is_empty():
        if description.metadata.title:
            print(f"Titre : {description.metadata.title}")
        if description.metadata.author:
            print(f"Auteur : {description.metadata.author}")
        if description.metadata.description:
            print(f"Description : {description.metadata.description}")
    if description.notes:
        print("Notes :")
        for note in description.notes:
            print(f"- {note}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RomPatcher Desktop")
    subparsers = parser.add_subparsers(dest="command")

    inspect_parser = subparsers.add_parser("inspect", help="Analyser un patch")
    inspect_parser.add_argument("patch", type=Path)

    apply_parser = subparsers.add_parser("apply", help="Appliquer un patch")
    apply_parser.add_argument("rom", type=Path)
    apply_parser.add_argument("patch", type=Path)
    apply_parser.add_argument("-o", "--output", type=Path)
    apply_parser.add_argument("--force", action="store_true", help="Ignore les checksums source/cible.")
    apply_parser.add_argument(
        "--keep-snes-header",
        action="store_true",
        help="Ne retire pas automatiquement l'en-tête SNES copier.",
    )

    create_parser = subparsers.add_parser("create", help="Créer un patch à partir d'un original et d'un fichier modifié")
    create_parser.add_argument("original", type=Path)
    create_parser.add_argument("modified", type=Path)
    create_parser.add_argument(
        "--format",
        choices=["ips", "ebp", "ups", "bps", "ppf", "aps-gba", "aps-n64", "rup"],
        default="bps",
        help="Format du patch à générer.",
    )
    create_parser.add_argument("-o", "--output", type=Path)
    create_parser.add_argument("--title", help="Titre du patch, surtout utile pour EBP.")
    create_parser.add_argument("--author", help="Auteur du patch, surtout utile pour EBP.")
    create_parser.add_argument("--description", help="Description ou notes du patch.")
    create_parser.add_argument(
        "--bps-linear",
        action="store_true",
        help="Utilise le mode linear au lieu du mode delta pour les patchs BPS.",
    )

    gui_parser = subparsers.add_parser("gui", help="Lancer l'interface graphique")
    gui_parser.set_defaults(command="gui")

    n64_parser = subparsers.add_parser("n64-byteswap", help="Convertir l'ordre des octets d'une ROM N64")
    n64_parser.add_argument("rom", type=Path)
    n64_parser.add_argument("--target", choices=["z64", "v64", "n64"], required=True)
    n64_parser.add_argument("-o", "--output", type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect":
        _print_description(args.patch)
        return 0

    if args.command == "apply":
        result = apply_patch(
            args.rom,
            args.patch,
            output_path=args.output,
            force=args.force,
            strip_snes_header=not args.keep_snes_header,
        )
        print(f"Patch appliqué : {result.output_path}")
        print(f"Format : {result.format_name}")
        print(f"Taille de sortie : {result.output_size} octets")
        for note in result.notes:
            print(f"- {note}")
        return 0

    if args.command == "create":
        result = create_patch(
            args.original,
            args.modified,
            format_name=args.format,
            output_path=args.output,
            metadata=PatchMetadata(
                title=args.title,
                author=args.author,
                description=args.description,
            ),
            bps_delta_mode=not args.bps_linear,
        )
        print(f"Patch créé : {result.output_path}")
        print(f"Format : {result.format_name}")
        print(f"Taille du patch : {result.patch_size} octets")
        for note in result.notes:
            print(f"- {note}")
        return 0

    if args.command == "gui":
        launch()
        return 0

    if args.command == "n64-byteswap":
        output = args.output or default_n64_output_path(args.rom, args.target)
        converted = convert_n64_byte_order(args.rom.read_bytes(), args.target)
        output.write_bytes(converted)
        print(f"ROM convertie : {output}")
        return 0

    parser.print_help(sys.stderr)
    return 1
