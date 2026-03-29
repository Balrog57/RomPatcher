from __future__ import annotations

import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .core import apply_patch, create_patch, inspect_patch
from .dependencies import install_xdelta3
from .exceptions import DependencyMissingError
from .models import PatchMetadata
from .n64 import convert_n64_byte_order, default_n64_output_path
from .updater import (
    download_release_asset,
    find_available_update,
    install_downloaded_update,
    is_frozen_build,
    open_releases_page,
)
from .version import APP_NAME, APP_VERSION

try:
    import windnd  # type: ignore
except ImportError:
    windnd = None


CREATE_FORMAT_HELP = {
    "bps": "Format moderne recommandé pour les ROM hacks importants. Plus compact que IPS dans la plupart des cas.",
    "ups": "Bon format historique pour ROMs, avec CRC32 source et cible intégrés.",
    "ips": "Très compatible, mais limité à 16 Mo et moins efficace pour les gros décalages de données.",
    "ebp": "Variante IPS avec métadonnées JSON. Pratique pour distribuer titre, auteur et description.",
    "ppf": "Format surtout utilisé pour images PlayStation et autres gros binaires proches du monde optique.",
    "aps-gba": "Format bloc par bloc orienté Game Boy Advance. Attendu sur des fichiers de même taille et multiples de 64 Ko.",
    "aps-n64": "Format APS orienté Nintendo 64. Plus pertinent avec une ROM z64 propre.",
    "rup": "Format Ninja 2.0 avec métadonnées et MD5 source/cible. Peut aussi servir à annuler un patch.",
}


class ScrollableNotebookFrame(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, *, background: str = "#eadfce") -> None:
        super().__init__(parent, style="Shell.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, background=background, borderwidth=0, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self._scrollbar_visible = True
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.content = ttk.Frame(self.canvas, padding=(0, 0, 8, 0), style="Shell.TFrame")
        self._window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")

        self.content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)
        self.content.bind("<Enter>", self._bind_mousewheel)
        self.content.bind("<Leave>", self._unbind_mousewheel)

    def _on_content_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._update_scrollbar_visibility()

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)
        self._update_scrollbar_visibility()

    def _bind_mousewheel(self, _event=None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

    def _unbind_mousewheel(self, _event=None) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event) -> None:
        if not self._scrollbar_visible:
            return
        if event.delta:
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _update_scrollbar_visibility(self) -> None:
        bbox = self.canvas.bbox("all")
        if bbox is None:
            return
        content_height = bbox[3] - bbox[1]
        canvas_height = max(self.canvas.winfo_height(), 1)
        needs_scrollbar = content_height > canvas_height + 4
        if needs_scrollbar and not self._scrollbar_visible:
            self.scrollbar.grid()
            self._scrollbar_visible = True
        elif not needs_scrollbar and self._scrollbar_visible:
            self.canvas.yview_moveto(0.0)
            self.scrollbar.grid_remove()
            self._scrollbar_visible = False


class RomPatcherApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self._configure_root_geometry()

        self.apply_rom_var = tk.StringVar()
        self.apply_patch_var = tk.StringVar()
        self.apply_output_var = tk.StringVar()
        self.force_var = tk.BooleanVar(value=False)
        self.strip_snes_var = tk.BooleanVar(value=True)

        self.create_original_var = tk.StringVar()
        self.create_modified_var = tk.StringVar()
        self.create_output_var = tk.StringVar()
        self.create_format_var = tk.StringVar(value="bps")
        self.bps_delta_var = tk.BooleanVar(value=True)
        self.create_title_var = tk.StringVar()
        self.create_author_var = tk.StringVar()

        self.n64_input_var = tk.StringVar()
        self.n64_output_var = tk.StringVar()
        self.n64_target_var = tk.StringVar(value="z64")

        self.status_var = tk.StringVar(value=f"Prêt. Version {APP_VERSION}")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._apply_output_auto = True
        self._create_output_auto = True
        self._n64_output_auto = True
        self._action_buttons: list[ttk.Button] = []

        self._configure_style()
        self._build_ui()
        self._refresh_create_help()
        if is_frozen_build():
            self.root.after(1800, lambda: self._check_for_updates(automatic=True))

    def _configure_root_geometry(self) -> None:
        screen_width = max(self.root.winfo_screenwidth(), 1200)
        screen_height = max(self.root.winfo_screenheight(), 900)
        width = min(max(int(screen_width * 0.82), 1120), 1540)
        height = min(max(int(screen_height * 0.84), 860), 1120)
        min_width = min(width, 1024)
        min_height = min(height, 780)
        pos_x = max((screen_width - width) // 2, 0)
        pos_y = max((screen_height - height) // 3, 0)
        self.root.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
        self.root.minsize(min_width, min_height)

    def _configure_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.root.configure(bg="#eadfce")
        style.configure("Shell.TFrame", background="#eadfce")
        style.configure("Card.TFrame", background="#f9f4ec")
        style.configure("Panel.TFrame", background="#22333b")
        style.configure("Headline.TLabel", background="#eadfce", foreground="#18252c", font=("Bahnschrift", 24, "bold"))
        style.configure("Subhead.TLabel", background="#eadfce", foreground="#4a5b63", font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background="#f9f4ec", foreground="#22333b", font=("Bahnschrift", 12, "bold"))
        style.configure("Body.TLabel", background="#f9f4ec", foreground="#314247", font=("Segoe UI", 10))
        style.configure("Info.TLabel", background="#22333b", foreground="#f1eadb", font=("Segoe UI", 10))
        style.configure("Accent.TButton", font=("Bahnschrift", 10, "bold"))
        style.configure("TNotebook", background="#eadfce", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 10), font=("Bahnschrift", 10))
        style.configure("Workspace.TNotebook", background="#eadfce", borderwidth=0, tabmargins=(0, 8, 0, 0))
        style.configure(
            "Workspace.TNotebook.Tab",
            padding=(22, 12, 22, 12),
            width=12,
            font=("Bahnschrift", 11, "bold"),
            background="#c9bba3",
            foreground="#22333b",
            borderwidth=0,
        )
        style.map(
            "Workspace.TNotebook.Tab",
            background=[("selected", "#f9f4ec"), ("active", "#ddcfb8")],
            foreground=[("selected", "#18252c"), ("active", "#18252c")],
            padding=[("selected", (22, 12, 22, 12)), ("active", (22, 12, 22, 12))],
        )
        style.configure("TLabelframe", background="#f9f4ec")
        style.configure("TLabelframe.Label", background="#f9f4ec", foreground="#22333b", font=("Bahnschrift", 10, "bold"))

    def _build_ui(self) -> None:
        shell = ttk.Frame(self.root, padding=18, style="Shell.TFrame")
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=5)
        shell.rowconfigure(2, weight=2, minsize=200)
        shell.rowconfigure(3, weight=0)
        self.shell_frame = shell

        header = ttk.Frame(shell, style="Shell.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(header, text=APP_NAME, style="Headline.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Patcher Windows autonome pour appliquer, créer, analyser et convertir des patchs de ROMs et de binaires.",
            style="Subhead.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        ttk.Label(
            header,
            text="Astuce : glissez-déposez vos fichiers directement sur les champs.",
            style="Subhead.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        self.workspace_frame = ttk.Frame(shell, style="Shell.TFrame")
        self.workspace_frame.grid(row=1, column=0, sticky="nsew")
        self.workspace_frame.columnconfigure(0, weight=1)
        self.workspace_frame.rowconfigure(0, weight=1)

        self.workspace_notebook = ttk.Notebook(self.workspace_frame, style="Workspace.TNotebook")
        self.workspace_notebook.grid(row=0, column=0, sticky="nsew")

        self.apply_tab = ttk.Frame(self.workspace_notebook, style="Shell.TFrame")
        self.create_tab = ttk.Frame(self.workspace_notebook, style="Shell.TFrame")
        self.tools_tab = ttk.Frame(self.workspace_notebook, style="Shell.TFrame")
        self.workspace_notebook.add(self.apply_tab, text="Appliquer")
        self.workspace_notebook.add(self.create_tab, text="Créer")
        self.workspace_notebook.add(self.tools_tab, text="Outils")

        self._build_apply_tab(self.apply_tab)
        self._build_create_tab(self.create_tab)
        self._build_tools_tab(self.tools_tab)

        self.bottom_frame = ttk.Frame(shell, style="Shell.TFrame")
        self.bottom_frame.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        self.bottom_frame.columnconfigure(0, weight=1, uniform="bottom-split")
        self.bottom_frame.columnconfigure(1, weight=1, uniform="bottom-split")
        self.bottom_frame.rowconfigure(0, weight=1)

        info_card = ttk.Frame(self.bottom_frame, padding=16, style="Card.TFrame")
        info_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        info_card.columnconfigure(0, weight=1)
        info_card.rowconfigure(1, weight=1)
        ttk.Label(info_card, text="Analyse et détails", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.info_text = ScrolledText(
            info_card,
            wrap="word",
            font=("Consolas", 10),
            height=8,
            bg="#fffdf8",
            fg="#22333b",
            insertbackground="#22333b",
            relief="flat",
        )
        self.info_text.grid(row=1, column=0, sticky="nsew")
        self.info_text.configure(state="disabled")

        log_card = ttk.Frame(self.bottom_frame, padding=16, style="Panel.TFrame")
        log_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        log_card.columnconfigure(0, weight=1)
        log_card.rowconfigure(1, weight=1)
        ttk.Label(log_card, text="Journal", style="Info.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.log_text = ScrolledText(
            log_card,
            wrap="word",
            font=("Consolas", 10),
            height=8,
            bg="#1d2b31",
            fg="#f4efe4",
            insertbackground="#f4efe4",
            relief="flat",
        )
        self.log_text.grid(row=1, column=0, sticky="nsew")
        self.log_text.configure(state="disabled")

        footer = ttk.Frame(shell, style="Shell.TFrame")
        footer.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        footer.columnconfigure(0, weight=1)
        self.footer_frame = footer
        ttk.Label(footer, textvariable=self.status_var, style="Subhead.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(footer, text=f"v{APP_VERSION}", style="Subhead.TLabel").grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.update_button = ttk.Button(footer, text="Mise à jour", command=lambda: self._check_for_updates(automatic=False))
        self.update_button.grid(row=0, column=2, sticky="e", padx=(12, 0))
        self.progress_bar = ttk.Progressbar(footer, variable=self.progress_var, maximum=1.0, length=220)
        self.progress_bar.grid(row=0, column=3, sticky="e", padx=(12, 0))
        self._action_buttons.append(self.update_button)

    def _build_apply_tab(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1, uniform="tab-split")
        parent.columnconfigure(1, weight=1, uniform="tab-split")

        form = ttk.Frame(parent, padding=16, style="Card.TFrame")
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        form.columnconfigure(0, weight=1)

        ttk.Label(form, text="Appliquer un patch", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        self._file_picker_row(form, 1, "ROM source", self.apply_rom_var, self._pick_apply_rom)
        self._file_picker_row(form, 2, "Patch", self.apply_patch_var, self._pick_apply_patch)
        self._file_picker_row(
            form,
            3,
            "Sortie",
            self.apply_output_var,
            self._pick_apply_output,
            save=True,
            manual_override=self._mark_apply_output_manual,
        )

        ttk.Checkbutton(
            form,
            text="Retirer automatiquement l'en-tête SNES copier de 512 octets",
            variable=self.strip_snes_var,
            command=self._refresh_apply_output_suggestion,
        ).grid(row=4, column=0, sticky="w", pady=(12, 4))
        ttk.Checkbutton(
            form,
            text="Forcer l'application même si les checksums ne correspondent pas",
            variable=self.force_var,
        ).grid(row=5, column=0, sticky="w", pady=(0, 12))

        bar = ttk.Frame(form, style="Card.TFrame")
        bar.grid(row=6, column=0, sticky="ew")
        bar.columnconfigure(0, weight=1)
        bar.columnconfigure(1, weight=1)
        self.inspect_button = ttk.Button(bar, text="Analyser le patch", command=self._inspect_patch)
        self.inspect_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.apply_button = ttk.Button(bar, text="Appliquer le patch", style="Accent.TButton", command=self._apply_patch)
        self.apply_button.grid(row=0, column=1, sticky="ew")
        self._action_buttons.extend([self.inspect_button, self.apply_button])

        side = ttk.Frame(parent, padding=16, style="Panel.TFrame")
        side.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        side.columnconfigure(0, weight=1)
        ttk.Label(side, text="Conseils", style="Info.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        ttk.Label(
            side,
            text=(
                "Choisissez la ROM source propre et le patch.\n\n"
                "Le logiciel détecte automatiquement le format, vérifie les checksums quand le patch le permet, "
                "et retire l'en-tête SNES copier si nécessaire."
            ),
            style="Info.TLabel",
            justify="left",
            wraplength=420,
        ).grid(row=1, column=0, sticky="nw")

        self.apply_rom_var.trace_add("write", lambda *_: self._refresh_apply_output_suggestion())
        self.apply_patch_var.trace_add("write", lambda *_: self._refresh_apply_output_suggestion())

    def _build_create_tab(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1, uniform="tab-split")
        parent.columnconfigure(1, weight=1, uniform="tab-split")

        form = ttk.Frame(parent, padding=16, style="Card.TFrame")
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        form.columnconfigure(0, weight=1)

        ttk.Label(form, text="Créer un patch", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        self._file_picker_row(form, 1, "Fichier original", self.create_original_var, self._pick_create_original)
        self._file_picker_row(form, 2, "Fichier modifié", self.create_modified_var, self._pick_create_modified)
        self._file_picker_row(
            form,
            3,
            "Patch de sortie",
            self.create_output_var,
            self._pick_create_output,
            save=True,
            manual_override=self._mark_create_output_manual,
        )

        format_row = ttk.Frame(form, style="Card.TFrame")
        format_row.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        format_row.columnconfigure(1, weight=1)
        ttk.Label(format_row, text="Format", style="Body.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.create_format_combo = ttk.Combobox(
            format_row,
            textvariable=self.create_format_var,
            values=["bps", "ups", "ips", "ebp", "ppf", "aps-gba", "aps-n64", "rup"],
            state="readonly",
        )
        self.create_format_combo.grid(row=0, column=1, sticky="ew")
        self.create_format_combo.bind("<<ComboboxSelected>>", lambda *_: self._on_create_format_changed())

        ttk.Checkbutton(
            form,
            text="BPS en mode delta (recommandé)",
            variable=self.bps_delta_var,
        ).grid(row=5, column=0, sticky="w", pady=(12, 4))

        meta = ttk.LabelFrame(form, text="Métadonnées", padding=12)
        meta.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        meta.columnconfigure(1, weight=1)
        ttk.Label(meta, text="Titre").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(meta, textvariable=self.create_title_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(meta, text="Auteur").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(meta, textvariable=self.create_author_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(meta, text="Description").grid(row=2, column=0, sticky="nw", padx=(0, 8), pady=4)
        self.create_description_text = tk.Text(
            meta,
            height=4,
            wrap="word",
            font=("Segoe UI", 10),
            bg="#fffdf8",
            fg="#22333b",
            insertbackground="#22333b",
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
        )
        self.create_description_text.grid(row=2, column=1, sticky="ew", pady=4)

        self.create_button = ttk.Button(form, text="Créer le patch", style="Accent.TButton", command=self._create_patch)
        self.create_button.grid(row=7, column=0, sticky="ew", pady=(14, 0))
        self._action_buttons.append(self.create_button)

        side = ttk.Frame(parent, padding=16, style="Panel.TFrame")
        side.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        side.columnconfigure(0, weight=1)
        ttk.Label(side, text="Guide format", style="Info.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.create_help_label = ttk.Label(side, text="", style="Info.TLabel", justify="left", wraplength=420)
        self.create_help_label.grid(row=1, column=0, sticky="nw")

        self.create_original_var.trace_add("write", lambda *_: self._refresh_create_output_suggestion())
        self.create_modified_var.trace_add("write", lambda *_: self._refresh_create_output_suggestion())
        self.create_format_var.trace_add("write", lambda *_: self._refresh_create_output_suggestion())

    def _build_tools_tab(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1, uniform="tab-split")
        parent.columnconfigure(1, weight=1, uniform="tab-split")

        form = ttk.Frame(parent, padding=16, style="Card.TFrame")
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        form.columnconfigure(0, weight=1)
        ttk.Label(form, text="Outils N64", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        self._file_picker_row(form, 1, "ROM N64", self.n64_input_var, self._pick_n64_input)
        self._file_picker_row(
            form,
            2,
            "Sortie",
            self.n64_output_var,
            self._pick_n64_output,
            save=True,
            manual_override=self._mark_n64_output_manual,
        )

        row = ttk.Frame(form, style="Card.TFrame")
        row.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text="Ordre cible", style="Body.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Combobox(row, textvariable=self.n64_target_var, values=["z64", "v64", "n64"], state="readonly").grid(
            row=0, column=1, sticky="ew"
        )

        self.n64_button = ttk.Button(form, text="Convertir le byte order", style="Accent.TButton", command=self._convert_n64)
        self.n64_button.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        self._action_buttons.append(self.n64_button)

        side = ttk.Frame(parent, padding=16, style="Panel.TFrame")
        side.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        side.columnconfigure(0, weight=1)
        ttk.Label(side, text="Rappel", style="Info.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        ttk.Label(
            side,
            text=(
                "Certaines ROMs Nintendo 64 existent en trois ordres d'octets.\n\n"
                "z64 : big-endian canonique\n"
                "v64 : byte-swapped\n"
                "n64 : little-endian"
            ),
            style="Info.TLabel",
            justify="left",
            wraplength=420,
        ).grid(row=1, column=0, sticky="nw")

        self.n64_input_var.trace_add("write", lambda *_: self._refresh_n64_output_suggestion())
        self.n64_target_var.trace_add("write", lambda *_: self._refresh_n64_output_suggestion())

    def _file_picker_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command,
        save: bool = False,
        manual_override=None,
    ) -> None:
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.grid(row=row, column=0, sticky="ew", pady=6)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=label, style="Body.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        entry = ttk.Entry(frame, textvariable=variable)
        entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="Parcourir", command=command).grid(row=1, column=1, sticky="ew")
        self._hook_dropfiles(entry, lambda files: self._assign_dropped_file(variable, files))
        if save and manual_override is not None:
            entry.bind("<KeyRelease>", manual_override)
            entry.bind("<<Paste>>", lambda *_: self.root.after_idle(manual_override))

    def _mark_apply_output_manual(self, _event=None) -> None:
        if self.apply_output_var.get().strip():
            self._apply_output_auto = False

    def _mark_create_output_manual(self, _event=None) -> None:
        if self.create_output_var.get().strip():
            self._create_output_auto = False

    def _mark_n64_output_manual(self, _event=None) -> None:
        if self.n64_output_var.get().strip():
            self._n64_output_auto = False

    def _hook_dropfiles(self, widget, callback) -> None:
        if windnd is None:
            return
        try:
            windnd.hook_dropfiles(widget, func=callback)
        except Exception:
            pass

    def _decode_drop_path(self, raw_value) -> str:
        if isinstance(raw_value, bytes):
            for encoding in ("utf-8", "mbcs", "latin-1"):
                try:
                    return raw_value.decode(encoding)
                except UnicodeDecodeError:
                    continue
            return raw_value.decode(errors="ignore")
        return str(raw_value)

    def _assign_dropped_file(self, variable: tk.StringVar, dropped_files) -> None:
        if not dropped_files:
            return
        value = self._decode_drop_path(dropped_files[0]).strip()
        if value:
            variable.set(value)

    def _pick_apply_rom(self) -> None:
        filename = filedialog.askopenfilename(title="Choisir la ROM source")
        if filename:
            self.apply_rom_var.set(filename)

    def _pick_apply_patch(self) -> None:
        filename = filedialog.askopenfilename(title="Choisir le patch")
        if filename:
            self.apply_patch_var.set(filename)

    def _pick_apply_output(self) -> None:
        filename = filedialog.asksaveasfilename(title="Choisir la sortie du patch")
        if filename:
            self._apply_output_auto = False
            self.apply_output_var.set(filename)

    def _pick_create_original(self) -> None:
        filename = filedialog.askopenfilename(title="Choisir le fichier original")
        if filename:
            self.create_original_var.set(filename)

    def _pick_create_modified(self) -> None:
        filename = filedialog.askopenfilename(title="Choisir le fichier modifié")
        if filename:
            self.create_modified_var.set(filename)

    def _pick_create_output(self) -> None:
        filename = filedialog.asksaveasfilename(title="Choisir le patch de sortie")
        if filename:
            self._create_output_auto = False
            self.create_output_var.set(filename)

    def _pick_n64_input(self) -> None:
        filename = filedialog.askopenfilename(title="Choisir la ROM N64")
        if filename:
            self.n64_input_var.set(filename)

    def _pick_n64_output(self) -> None:
        filename = filedialog.asksaveasfilename(title="Choisir le fichier de sortie N64")
        if filename:
            self._n64_output_auto = False
            self.n64_output_var.set(filename)

    def _refresh_apply_output_suggestion(self) -> None:
        if not self._apply_output_auto and self.apply_output_var.get():
            return
        rom_value = self.apply_rom_var.get().strip()
        if not rom_value:
            return
        rom_path = Path(rom_value)
        suffix = ".sfc" if self.strip_snes_var.get() and rom_path.suffix.lower() == ".smc" else rom_path.suffix
        self.apply_output_var.set(str(rom_path.with_name(f"{rom_path.stem} (patched){suffix}")))
        self._apply_output_auto = True

    def _refresh_create_output_suggestion(self) -> None:
        if not self._create_output_auto and self.create_output_var.get():
            return
        modified_value = self.create_modified_var.get().strip()
        if not modified_value:
            return
        modified_path = Path(modified_value)
        ext = {
            "bps": ".bps",
            "ups": ".ups",
            "ips": ".ips",
            "ebp": ".ebp",
            "ppf": ".ppf",
            "aps-gba": ".aps",
            "aps-n64": ".aps",
            "rup": ".rup",
        }[self.create_format_var.get()]
        self.create_output_var.set(str(modified_path.with_suffix(ext)))
        self._create_output_auto = True

    def _refresh_n64_output_suggestion(self) -> None:
        if not self._n64_output_auto and self.n64_output_var.get():
            return
        input_value = self.n64_input_var.get().strip()
        if not input_value:
            return
        input_path = Path(input_value)
        self.n64_output_var.set(str(default_n64_output_path(input_path, self.n64_target_var.get())))
        self._n64_output_auto = True

    def _refresh_create_help(self) -> None:
        fmt = self.create_format_var.get()
        text = CREATE_FORMAT_HELP.get(fmt, "")
        if fmt == "ebp":
            text += "\n\nLes champs titre, auteur et description seront intégrés au patch."
        elif fmt == "bps":
            text += "\n\nLe mode delta produit souvent de meilleurs patchs."
        self.create_help_label.configure(text=text)

    def _on_create_format_changed(self) -> None:
        self._refresh_create_output_suggestion()
        self._refresh_create_help()

    def _check_for_updates(self, *, automatic: bool) -> None:
        self.status_var.set("Vérification des mises à jour...")
        if not automatic:
            self._append_log("[INFO] Vérification des mises à jour demandée.")

        def action():
            try:
                return {
                    "release": find_available_update(force_refresh=not automatic),
                    "error": None,
                }
            except Exception as exc:
                return {"release": None, "error": str(exc)}

        self._run_async(action, lambda result: self._on_update_check_success(result, automatic))

    def _on_update_check_success(self, result: dict[str, object], automatic: bool) -> None:
        self._set_busy(False)
        self.progress_var.set(0.0)

        error = result.get("error")
        if isinstance(error, str) and error:
            self.status_var.set("Vérification des mises à jour indisponible.")
            self._append_log(f"[INFO] {error}")
            if not automatic:
                messagebox.showerror("Mise à jour impossible", error)
            return

        release = result.get("release")
        if release is None:
            self.status_var.set(f"Version actuelle : {APP_VERSION}")
            self._append_log("[INFO] Aucune mise à jour disponible.")
            if not automatic:
                messagebox.showinfo("Aucune mise à jour", f"Vous utilisez déjà la dernière version ({APP_VERSION}).")
            return

        self.status_var.set(f"Mise à jour disponible : v{release.version}")
        self._append_log(f"[INFO] Nouvelle version détectée : v{release.version}")

        prompt = (
            f"La version v{release.version} est disponible.\n\n"
            "Voulez-vous la télécharger et l'installer maintenant ?"
        )
        if is_frozen_build() and getattr(release, "asset", None) is not None:
            if messagebox.askyesno("Mise à jour disponible", prompt):
                self._download_and_install_update(release)
            return

        prompt = (
            f"La version v{release.version} est disponible.\n\n"
            "L'installation automatique fonctionne depuis l'exécutable Windows packagé.\n"
            "Voulez-vous ouvrir la page des releases ?"
        )
        if not automatic and messagebox.askyesno("Mise à jour disponible", prompt):
            open_releases_page(release.html_url)

    def _download_and_install_update(self, release) -> None:
        self.status_var.set(f"Téléchargement de la version v{release.version}...")
        self._append_log(f"[INFO] Téléchargement de la mise à jour v{release.version}.")

        def action():
            try:
                path = download_release_asset(
                    release,
                    progress=lambda value, message=None: self.root.after(0, self._on_progress, value, message),
                )
                return {"path": path, "error": None}
            except Exception as exc:
                return {"path": None, "error": str(exc)}

        self._run_async(action, self._on_update_downloaded)

    def _on_update_downloaded(self, result: dict[str, object]) -> None:
        error = result.get("error")
        if isinstance(error, str) and error:
            self._set_busy(False)
            self.progress_var.set(0.0)
            self.status_var.set("Téléchargement de la mise à jour échoué.")
            self._append_log(f"[ERREUR] {error}")
            messagebox.showerror("Mise à jour échouée", error)
            return

        downloaded_path = result.get("path")
        if not isinstance(downloaded_path, Path):
            self._set_busy(False)
            self.progress_var.set(0.0)
            self.status_var.set("Téléchargement de la mise à jour échoué.")
            messagebox.showerror("Mise à jour échouée", "Le fichier téléchargé est introuvable.")
            return

        try:
            script_path = install_downloaded_update(downloaded_path)
        except Exception as exc:
            self._on_failure(exc, traceback.format_exc())
            return

        self._set_busy(False)
        self.progress_var.set(1.0)
        self.status_var.set("Mise à jour prête. Redémarrage en cours...")
        self._append_log(f"[OK] Mise à jour téléchargée : {downloaded_path}")
        self._append_log(f"[INFO] Script d'installation lancé : {script_path}")
        messagebox.showinfo(
            "Mise à jour prête",
            "La nouvelle version a été téléchargée. L'application va se fermer puis redémarrer.",
        )
        self.root.after(350, self.root.destroy)

    def _set_text(self, widget: ScrolledText, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text.rstrip() + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _render_description(self, description) -> None:
        lines = [f"Format : {description.format_name}"]
        if description.validation:
            lines.append(f"Validation : {description.validation.algorithm} {description.validation.display_expected()}")
        if not description.metadata.is_empty():
            lines.append("")
            if description.metadata.title:
                lines.append(f"Titre : {description.metadata.title}")
            if description.metadata.author:
                lines.append(f"Auteur : {description.metadata.author}")
            if description.metadata.description:
                lines.append(f"Description : {description.metadata.description}")
            for key, value in description.metadata.extra.items():
                lines.append(f"{key} : {value}")
        if description.notes:
            lines.append("")
            lines.append("Notes :")
            lines.extend(f"- {note}" for note in description.notes)
        if description.can_undo:
            lines.append("")
            lines.append("Ce format peut aussi servir à annuler le patch si la cible correspond.")
        self._set_text(self.info_text, "\n".join(lines))

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for button in self._action_buttons:
            button.configure(state=state)

    def _on_progress(self, value: float, message: str | None) -> None:
        self.progress_var.set(value)
        if message:
            self.status_var.set(message)

    def _run_async(self, action, success_callback) -> None:
        self._set_busy(True)
        self.progress_var.set(0.0)

        def worker() -> None:
            try:
                result = action()
            except Exception as exc:
                trace = traceback.format_exc()
                self.root.after(0, self._on_failure, exc, trace)
                return
            self.root.after(0, success_callback, result)

        threading.Thread(target=worker, daemon=True).start()

    def _inspect_patch(self) -> None:
        patch_value = self.apply_patch_var.get().strip()
        if not patch_value:
            messagebox.showwarning("Patch manquant", "Choisissez un fichier de patch.")
            return
        try:
            description = inspect_patch(Path(patch_value))
        except Exception as exc:
            self._append_log(f"[ERREUR] Analyse : {exc}")
            messagebox.showerror("Analyse impossible", str(exc))
            return
        self._render_description(description)
        self.status_var.set(f"Patch analysé : {description.format_name}")
        self._append_log(f"[INFO] Patch analysé : {Path(patch_value).name} ({description.format_name})")

    def _apply_patch(self) -> None:
        rom_value = self.apply_rom_var.get().strip()
        patch_value = self.apply_patch_var.get().strip()
        output_value = self.apply_output_var.get().strip()
        if not rom_value or not patch_value:
            messagebox.showwarning("Fichiers manquants", "Choisissez une ROM source et un patch.")
            return

        self.status_var.set("Application du patch en cours...")
        self._append_log("[INFO] Application du patch démarrée.")

        def action():
            return apply_patch(
                Path(rom_value),
                Path(patch_value),
                output_path=Path(output_value) if output_value else None,
                force=self.force_var.get(),
                strip_snes_header=self.strip_snes_var.get(),
                progress=lambda value, message=None: self.root.after(0, self._on_progress, value, message),
            )

        self._run_async(action, self._on_apply_success)

    def _create_patch(self) -> None:
        original_value = self.create_original_var.get().strip()
        modified_value = self.create_modified_var.get().strip()
        output_value = self.create_output_var.get().strip()
        if not original_value or not modified_value:
            messagebox.showwarning("Fichiers manquants", "Choisissez un original et un fichier modifié.")
            return

        self.status_var.set("Création du patch en cours...")
        self._append_log(f"[INFO] Création du patch {self.create_format_var.get().upper()} démarrée.")

        metadata = PatchMetadata(
            title=self.create_title_var.get().strip() or None,
            author=self.create_author_var.get().strip() or None,
            description=self.create_description_text.get("1.0", "end").strip() or None,
        )

        def action():
            return create_patch(
                Path(original_value),
                Path(modified_value),
                format_name=self.create_format_var.get(),
                output_path=Path(output_value) if output_value else None,
                metadata=metadata,
                bps_delta_mode=self.bps_delta_var.get(),
                progress=lambda value, message=None: self.root.after(0, self._on_progress, value, message),
            )

        self._run_async(action, self._on_create_success)

    def _convert_n64(self) -> None:
        input_value = self.n64_input_var.get().strip()
        output_value = self.n64_output_var.get().strip()
        if not input_value:
            messagebox.showwarning("Fichier manquant", "Choisissez une ROM N64.")
            return

        self.status_var.set("Conversion N64 en cours...")
        self._append_log("[INFO] Conversion du byte order N64 démarrée.")

        def action():
            source_path = Path(input_value)
            output_path = Path(output_value) if output_value else default_n64_output_path(source_path, self.n64_target_var.get())
            converted = convert_n64_byte_order(source_path.read_bytes(), self.n64_target_var.get())
            output_path.write_bytes(converted)
            return output_path

        self._run_async(action, self._on_n64_success)

    def _on_apply_success(self, result) -> None:
        self._set_busy(False)
        self.progress_var.set(1.0)
        self.status_var.set(f"Patch appliqué : {result.output_path.name}")
        self._append_log(f"[OK] Patch appliqué : {result.output_path}")
        for note in result.notes:
            self._append_log(f"  - {note}")
        messagebox.showinfo(
            "Patch appliqué",
            f"Fichier généré :\n{result.output_path}\n\nFormat : {result.format_name}\nTaille : {result.output_size} octets",
        )

    def _on_create_success(self, result) -> None:
        self._set_busy(False)
        self.progress_var.set(1.0)
        self.status_var.set(f"Patch créé : {result.output_path.name}")
        self._append_log(f"[OK] Patch créé : {result.output_path}")
        for note in result.notes:
            self._append_log(f"  - {note}")
        try:
            description = inspect_patch(result.output_path)
            self._render_description(description)
        except Exception:
            pass
        messagebox.showinfo(
            "Patch créé",
            f"Patch généré :\n{result.output_path}\n\nFormat : {result.format_name}\nTaille : {result.patch_size} octets",
        )

    def _on_n64_success(self, output_path: Path) -> None:
        self._set_busy(False)
        self.progress_var.set(1.0)
        self.status_var.set(f"Conversion N64 terminée : {output_path.name}")
        self._append_log(f"[OK] ROM N64 convertie : {output_path}")
        messagebox.showinfo("Conversion terminée", f"Fichier généré :\n{output_path}")

    def _handle_missing_dependency(self, exc: Exception) -> bool:
        if not isinstance(exc, DependencyMissingError):
            return False
        if "xdelta" not in str(exc).lower():
            return False

        self._set_busy(False)
        self.progress_var.set(0.0)
        self.status_var.set("xdelta3 requis pour ce patch.")
        self._append_log(f"[INFO] {exc}")

        install_now = messagebox.askyesno(
            "xdelta3 manquant",
            "Ce patch requiert xdelta3.exe.\n\n"
            "Voulez-vous le télécharger et l'installer automatiquement maintenant ?",
        )
        if not install_now:
            messagebox.showerror(
                "xdelta3 manquant",
                "Installez xdelta3.exe dans le PATH, à côté de l'application, ou dans un dossier tools/.",
            )
            return True

        self.status_var.set("Installation de xdelta3 en cours...")
        self._append_log("[INFO] Téléchargement de xdelta3 depuis la release officielle.")

        def action():
            return install_xdelta3(
                progress=lambda value, message=None: self.root.after(0, self._on_progress, value, message),
            )

        def success(installed_path: Path) -> None:
            self._set_busy(False)
            self.progress_var.set(1.0)
            self.status_var.set("xdelta3 installé. Nouvelle tentative...")
            self._append_log(f"[OK] xdelta3 installé : {installed_path}")
            self.root.after(100, self._apply_patch)

        self._run_async(action, success)
        return True

    def _on_failure(self, exc: Exception, trace: str) -> None:
        if self._handle_missing_dependency(exc):
            return
        self._set_busy(False)
        self.progress_var.set(0.0)
        self.status_var.set("Opération échouée.")
        self._append_log(f"[ERREUR] {exc}")
        self._append_log(trace)
        messagebox.showerror("Échec", str(exc))


def launch() -> None:
    root = tk.Tk()
    icon_path = Path(__file__).resolve().parents[2] / "assets" / "rompatcher.ico"
    if icon_path.exists():
        try:
            root.iconbitmap(default=str(icon_path))
        except tk.TclError:
            pass
    RomPatcherApp(root)
    root.mainloop()
