from __future__ import annotations

import sys
import tkinter as tk
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rompatcher.gui import RomPatcherApp, ScrollableNotebookFrame
from rompatcher.n64 import detect_n64_byte_order


def _ensure_tk_available() -> None:
    try:
        root = tk.Tk()
        root.withdraw()
        root.update_idletasks()
        root.destroy()
    except tk.TclError as exc:
        raise unittest.SkipTest(f"Tk indisponible pour les tests GUI : {exc}") from exc


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _ensure_tk_available()

    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()

        self.showinfo_patcher = patch("rompatcher.gui.messagebox.showinfo")
        self.showwarning_patcher = patch("rompatcher.gui.messagebox.showwarning")
        self.showerror_patcher = patch("rompatcher.gui.messagebox.showerror")
        self.showinfo_mock = self.showinfo_patcher.start()
        self.showwarning_mock = self.showwarning_patcher.start()
        self.showerror_mock = self.showerror_patcher.start()

        self.app = RomPatcherApp(self.root)
        self.app._run_async = self._run_sync
        self.root.update_idletasks()

    def tearDown(self) -> None:
        self.showinfo_patcher.stop()
        self.showwarning_patcher.stop()
        self.showerror_patcher.stop()
        self.root.update_idletasks()
        self.root.destroy()

    def _run_sync(self, action, success_callback) -> None:
        self.app._set_busy(True)
        self.app.progress_var.set(0.0)
        try:
            result = action()
        except Exception as exc:
            self.app._on_failure(exc, traceback.format_exc())
        else:
            success_callback(result)
        self.root.update_idletasks()

    def test_layout_keeps_notebook_visible_and_weighted(self) -> None:
        self.root.update_idletasks()
        self.assertEqual(self.app.shell_frame.grid_rowconfigure(1)["weight"], 5)
        self.assertEqual(self.app.shell_frame.grid_rowconfigure(2)["weight"], 2)
        self.assertEqual(self.app.workspace_notebook.index("end"), 3)
        self.assertIsInstance(self.app.apply_tab, ScrollableNotebookFrame)
        self.assertIsInstance(self.app.create_tab, ScrollableNotebookFrame)
        self.assertIsInstance(self.app.tools_tab, ScrollableNotebookFrame)
        self.assertEqual(self.app.update_button.cget("text"), "Mise à jour")

    def test_apply_output_suggestion_switches_smc_to_sfc(self) -> None:
        self.app.apply_rom_var.set(str(Path("C:/tmp/game.smc")))
        self.root.update_idletasks()
        self.assertTrue(self.app.apply_output_var.get().endswith("game (patched).sfc"))

    def test_create_output_suggestion_uses_selected_extension(self) -> None:
        self.app.create_modified_var.set(str(Path("C:/tmp/modded.bin")))
        self.app.create_format_var.set("rup")
        self.app._on_create_format_changed()
        self.root.update_idletasks()
        self.assertTrue(self.app.create_output_var.get().endswith(".rup"))

    def test_n64_output_suggestion_uses_target_name(self) -> None:
        self.app.n64_input_var.set(str(Path("C:/tmp/zelda.z64")))
        self.app.n64_target_var.set("v64")
        self.root.update_idletasks()
        self.assertTrue(self.app.n64_output_var.get().endswith("zelda (v64).z64"))

    def test_create_help_changes_for_ebp(self) -> None:
        self.app.create_format_var.set("ebp")
        self.app._on_create_format_changed()
        self.assertIn("titre, auteur et description", self.app.create_help_label.cget("text"))

    def test_dropfile_assignment_decodes_first_entry(self) -> None:
        variable = tk.StringVar()
        self.app._assign_dropped_file(variable, [b"C:\\Temp\\rom.smc", b"C:\\Temp\\ignored.ips"])
        self.assertTrue(variable.get().endswith("rom.smc"))

    def test_inspect_patch_updates_info_panel(self) -> None:
        patch_path = _write_temp_file(
            "gui_inspect.ebp",
            b"PATCH" + b"\x00\x00\x01" + b"\x00\x01" + b"X" + b"EOF" + b'{"title":"Hack","author":"Marc"}',
        )
        self.app.apply_patch_var.set(str(patch_path))
        self.app._inspect_patch()
        self.assertIn("Format : EBP", self.app.info_text.get("1.0", "end"))
        self.assertIn("Patch analysé", self.app.status_var.get())

    def test_apply_patch_handler_creates_output(self) -> None:
        rom = _write_temp_file("gui_apply_source.bin", b"ABCDEF")
        patch = _write_temp_file("gui_apply_patch.ips", b"PATCH" + b"\x00\x00\x03" + b"\x00\x01" + b"Z" + b"EOF")
        output = ROOT / ".tmp_tests" / "gui_apply_output.bin"

        self.app.apply_rom_var.set(str(rom))
        self.app.apply_patch_var.set(str(patch))
        self.app.apply_output_var.set(str(output))
        self.app._apply_patch()

        self.assertEqual(output.read_bytes(), b"ABCZEF")
        self.assertIn("Patch appliqué", self.app.status_var.get())
        self.showinfo_mock.assert_called()

    def test_create_patch_handler_creates_patch(self) -> None:
        original = _write_temp_file("gui_create_original.bin", b"HELLO WORLD")
        modified = _write_temp_file("gui_create_modified.bin", b"HELXO WORLD!")
        output = ROOT / ".tmp_tests" / "gui_create_patch.bps"

        self.app.create_original_var.set(str(original))
        self.app.create_modified_var.set(str(modified))
        self.app._create_output_auto = False
        self.app.create_output_var.set(str(output))
        self.app.create_format_var.set("bps")
        self.app.create_description_text.delete("1.0", "end")
        self.app.create_description_text.insert("1.0", "Patch GUI")
        self.app._create_patch()

        self.assertTrue(output.exists())
        self.assertIn("Format : BPS", self.app.info_text.get("1.0", "end"))
        self.showinfo_mock.assert_called()

    def test_convert_n64_handler_creates_output(self) -> None:
        rom = _write_temp_file("gui_n64_source.z64", bytes.fromhex("80371240") + b"\xAA\xBB\xCC\xDD")
        output = ROOT / ".tmp_tests" / "gui_n64_output.v64"

        self.app.n64_input_var.set(str(rom))
        self.app._n64_output_auto = False
        self.app.n64_output_var.set(str(output))
        self.app.n64_target_var.set("v64")
        self.app._convert_n64()

        self.assertEqual(detect_n64_byte_order(output.read_bytes()), "v64")
        self.assertIn("Conversion N64 terminée", self.app.status_var.get())

    def test_missing_inputs_show_warning(self) -> None:
        self.app._apply_patch()
        self.showwarning_mock.assert_called()


def _write_temp_file(name: str, data: bytes) -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp_tests"
    root.mkdir(exist_ok=True)
    path = root / name
    path.write_bytes(data)
    return path
