from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .layout_diagnosis_view_controller import build_diagnosis_entry_tab


class EpubLayoutInspectorMixin:
    @staticmethod
    def _inspector_tab_titles() -> tuple[str, str, str, str]:
        return ("Edit", "Diagnose", "Book", "Series")

    @staticmethod
    def _edit_section_titles() -> tuple[str, str, str]:
        return ("Insert", "Delete", "Repair")

    @staticmethod
    def _series_section_titles() -> tuple[str, str]:
        return ("Review", "Export")

    def _build_inspector_tab_bar(self, parent: ttk.Frame) -> None:
        tabbar = ttk.Frame(parent, padding=(8, 8, 8, 4))
        tabbar.pack(fill=tk.X)
        for title in self._inspector_tab_titles():
            button = ttk.Button(tabbar, text=title, command=lambda tab=title: self._show_inspector_tab(tab))
            button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)
            self.inspector_tab_buttons[title] = button

    def _add_inspector_tab(self, container: ttk.Frame, title: str) -> ttk.Frame:
        outer = ttk.Frame(container)
        outer.place(relx=0, rely=0, relwidth=1, relheight=1)
        outer.pack_propagate(False)
        canvas = tk.Canvas(outer, highlightthickness=0, width=300)
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        content = ttk.Frame(canvas, padding=(12, 12))
        window_id = canvas.create_window((0, 0), window=content, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        self.inspector_tabs[title] = outer
        return content

    def _show_inspector_tab(self, title: str) -> None:
        if title not in self.inspector_tabs:
            return
        if getattr(self, "active_inspector_tab", None) == "Book" and title != "Book":
            self._store_metadata_fields()
        self.active_inspector_tab = title
        self.inspector_tabs[title].tkraise()
        for tab_title, button in getattr(self, "inspector_tab_buttons", {}).items():
            state = tk.DISABLED if tab_title == title else tk.NORMAL
            try:
                button.configure(state=state)
            except tk.TclError:
                pass

    def _build_edit_tab(self, parent: ttk.Frame) -> None:
        self._add_section_label(parent, "Insert")
        self._add_panel_button(parent, "Insert Blank Before", lambda: self.insert_blank(before=True))
        self._add_panel_button(parent, "Insert Blank After", lambda: self.insert_blank(before=False))
        self._add_panel_button(parent, "Quick: Blank Before Cover", self.quick_blank_before_cover)
        self._add_panel_button(parent, "Quick: Blank After Cover", self.quick_blank_after_cover)
        self._add_panel_button(parent, "Insert Image Before", lambda: self.insert_image(before=True))
        self._add_panel_button(parent, "Insert Image After", lambda: self.insert_image(before=False))
        self._add_section_gap(parent)
        self._add_section_label(parent, "Delete")
        self._add_panel_button(parent, "Delete Selected Page", self.delete_selected_entry)
        self._add_section_gap(parent)
        self._add_section_label(parent, "Repair")
        self._add_panel_button(parent, "Recover Last Deleted", self.recover_last_deleted)

    def _build_book_tab(self, parent: ttk.Frame) -> None:
        self._ensure_metadata_label_vars()
        self._add_section_label(parent, "Metadata")
        ttk.Label(parent, textvariable=self.title_label_var).pack(anchor=tk.W, pady=(8, 0))
        ttk.Entry(parent, textvariable=self.title_var).pack(fill=tk.X)
        ttk.Label(parent, textvariable=self.author_label_var).pack(anchor=tk.W, pady=(8, 0))
        ttk.Entry(parent, textvariable=self.author_var).pack(fill=tk.X)
        ttk.Label(parent, text="Language").pack(anchor=tk.W, pady=(8, 0))
        ttk.Entry(parent, textvariable=self.language_var).pack(fill=tk.X)
        self._add_panel_button(parent, "Set Selected As Cover", self.set_selected_as_cover)
        ttk.Checkbutton(
            parent,
            text="Cover only, exclude from pages",
            variable=self.exclude_cover_var,
        ).pack(anchor=tk.W, pady=(8, 0))
        self._add_panel_button(parent, "Export Selected Images...", self.export_selected_images)

    def _build_series_tab(self, parent: ttk.Frame) -> None:
        self._add_section_label(parent, "Review")
        self._add_panel_button(parent, "Mark Selected Volume Ready", self.mark_selected_series_volume_ready)
        self._add_panel_button(parent, "Unready Selected", self.unready_selected)
        self._add_section_gap(parent)
        self._add_section_label(parent, "Export")
        self._add_panel_button(parent, "Export Ready Series...", self.export_ready_series)

    def _add_section_label(self, parent: ttk.Frame, text: str) -> None:
        ttk.Label(parent, text=text).pack(anchor=tk.W, pady=(0, 4))

    def _add_section_gap(self, parent: ttk.Frame) -> None:
        ttk.Separator(parent).pack(fill=tk.X, pady=14)

    def _add_panel_button(self, parent: ttk.Frame, text: str, command) -> None:
        ttk.Button(parent, text=text, command=command).pack(fill=tk.X, pady=(6, 0))


def build_diagnosis_inspector_entry(app, parent) -> None:
    build_diagnosis_entry_tab(app, parent)
