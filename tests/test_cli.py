from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rompatcher.cli import main
from rompatcher.core import create_patch
from rompatcher.models import PatchMetadata
from rompatcher.n64 import detect_n64_byte_order


class CLITests(unittest.TestCase):
    def test_no_command_returns_error(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([])
        self.assertEqual(code, 1)
        self.assertIn("usage:", stderr.getvalue().lower())

    def test_gui_command_calls_launch(self) -> None:
        with patch("rompatcher.cli.launch") as launch_mock:
            code = main(["gui"])
        self.assertEqual(code, 0)
        launch_mock.assert_called_once_with()

    def test_version_option_prints_current_version(self) -> None:
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as exit_info:
            with redirect_stdout(stdout):
                main(["--version"])
        self.assertEqual(exit_info.exception.code, 0)
        self.assertIn("0.2.0", stdout.getvalue())

    def test_inspect_command_prints_metadata(self) -> None:
        original = _write_temp_file("cli_inspect_original.bin", b"ABCDEFGH")
        modified = _write_temp_file("cli_inspect_modified.bin", b"ABCXEFGH")
        created = create_patch(
            original,
            modified,
            format_name="ebp",
            metadata=PatchMetadata(title="CLI Test", author="Marc", description="Inspection"),
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = main(["inspect", str(created.output_path)])

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Format : EBP", output)
        self.assertIn("Titre : CLI Test", output)

    def test_create_and_apply_commands_roundtrip(self) -> None:
        original = _write_temp_file("cli_create_original.bin", b"HELLO WORLD")
        modified = _write_temp_file("cli_create_modified.bin", b"HELXO WORLD!")
        patch_path = ROOT / ".tmp_tests" / "cli_roundtrip.bps"
        output_path = ROOT / ".tmp_tests" / "cli_roundtrip.bin"

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            create_code = main(["create", str(original), str(modified), "--format", "bps", "-o", str(patch_path)])
            apply_code = main(["apply", str(original), str(patch_path), "-o", str(output_path)])

        self.assertEqual(create_code, 0)
        self.assertEqual(apply_code, 0)
        self.assertTrue(patch_path.exists())
        self.assertEqual(output_path.read_bytes(), modified.read_bytes())

    def test_n64_byteswap_command_creates_output(self) -> None:
        rom = _write_temp_file("cli_n64_source.z64", bytes.fromhex("80371240") + b"\xAA\xBB\xCC\xDD")
        output = ROOT / ".tmp_tests" / "cli_n64_output.v64"

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = main(["n64-byteswap", str(rom), "--target", "v64", "-o", str(output)])

        self.assertEqual(code, 0)
        self.assertEqual(detect_n64_byte_order(output.read_bytes()), "v64")


def _write_temp_file(name: str, data: bytes) -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp_tests"
    root.mkdir(exist_ok=True)
    path = root / name
    path.write_bytes(data)
    return path
