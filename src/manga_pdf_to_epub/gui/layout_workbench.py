from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .layout_inspector_controller import build_diagnosis_inspector_entry


class EpubLayoutWorkbenchMixin:
    def _configure_window(self) -> None:
        self.root.title("EPUB Layout Lab")
        self.root.geometry("1280x760")
        self.root.minsize(1100, 680)

    def _build_ui(self) -> None:
        self._build_toolbar()
        main = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)

        self._build_navigation(main)
        self._build_preview_pane(main)
        self._build_inspector(main)
        self._build_statusbar()

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        toolbar_row = ttk.Frame(toolbar)
        toolbar_row.pack(anchor=tk.CENTER)
        toolbar_buttons = (
            ("Import Series...", self.import_series),
            ("Open Source", self.open_pdf),
            ("Export EPUB", self.export_epub),
            ("Export Ready Series...", self.export_ready_series),
            ("Open Project...", self.open_project),
            ("Save Project...", self.save_project),
            ("Save Preset", self.save_preset),
            ("Load Preset", self.load_preset),
            ("Command Palette...", self.open_command_palette),
        )
        last_index = len(toolbar_buttons) - 1
        for index, (text, command) in enumerate(toolbar_buttons):
            padx = (0, 0) if index == last_index else (0, 8)
            ttk.Button(toolbar_row, text=text, command=command).pack(side=tk.LEFT, padx=padx)

    def _build_navigation(self, main) -> None:
        left = ttk.Frame(main, padding=8)
        main.add(left, weight=1)
        navigation = ttk.Frame(left)
        navigation.pack(fill=tk.BOTH, expand=True)
        navigation.bind("<Configure>", lambda event: self._sync_navigation_mode(available_width=event.width))
        self.series_pane = ttk.Frame(navigation, padding=(0, 0, 6, 0))
        self.series_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Label(self.series_pane, text="Series volumes").pack(anchor=tk.W)
        self.series_list = tk.Listbox(
            self.series_pane,
            exportselection=False,
            activestyle="dotbox",
            selectmode=tk.EXTENDED,
            width=34,
        )
        self.series_list.pack(fill=tk.BOTH, expand=True, pady=(6, 12))
        self.series_list.bind("<<ListboxSelect>>", lambda _event: self.select_series_volume())
        self.spine_pane = ttk.Frame(navigation, padding=(6, 0, 0, 0))
        self.spine_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Label(self.spine_pane, text="Spine order").pack(anchor=tk.W)
        self.page_list = tk.Listbox(self.spine_pane, exportselection=False, activestyle="dotbox", selectmode=tk.EXTENDED)
        self.page_list.pack(fill=tk.BOTH, expand=True, pady=(6, 12))
        self.page_list.bind("<<ListboxSelect>>", lambda _event: self.sync_selection_from_main())
        self.page_list.bind("<ButtonPress-1>", self._page_drag_start)
        self.page_list.bind("<ButtonRelease-1>", self._page_drag_release)
        self._sync_navigation_mode()

    def _build_preview_pane(self, main) -> None:
        center = ttk.Frame(main, padding=8)
        main.add(center, weight=3)
        preview_header = ttk.Frame(center)
        preview_header.pack(fill=tk.X)
        ttk.Label(preview_header, text="RTL spread preview").pack(side=tk.LEFT)
        ttk.Checkbutton(
            preview_header,
            text="Preview Apple Books cover gap",
            variable=self.apple_preview,
            command=self.refresh_preview_after_diagnosis_layout_option_change,
        ).pack(side=tk.RIGHT)
        self.preview = tk.Canvas(center, background="#202020", highlightthickness=0)
        self.preview.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.preview.bind("<Configure>", lambda _event: self.refresh_preview())

    def _build_inspector(self, main) -> None:
        inspector = ttk.Frame(main, width=320)
        main.add(inspector, weight=1)
        inspector.pack_propagate(False)
        self.inspector_tabs: dict[str, ttk.Frame] = {}
        self.inspector_tab_buttons: dict[str, ttk.Button] = {}
        self.active_inspector_tab = "Edit"
        self._build_inspector_tab_bar(inspector)
        content = ttk.Frame(inspector)
        content.pack(fill=tk.BOTH, expand=True)
        edit_tab = self._add_inspector_tab(content, "Edit")
        diagnose_tab = self._add_inspector_tab(content, "Diagnose")
        book_tab = self._add_inspector_tab(content, "Book")
        series_tab = self._add_inspector_tab(content, "Series")
        self._build_edit_tab(edit_tab)
        build_diagnosis_inspector_entry(self, diagnose_tab)
        self._build_book_tab(book_tab)
        self._build_series_tab(series_tab)
        self._show_inspector_tab("Edit")

    def _build_statusbar(self) -> None:
        statusbar = ttk.Frame(self.root, padding=(8, 4))
        statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(statusbar, textvariable=self.status).pack(side=tk.LEFT)
        ttk.Label(statusbar, textvariable=self.workspace_status).pack(side=tk.RIGHT)
        self.refresh_workspace_status()
