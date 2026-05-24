from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog


class EpubLayoutEditMixin:
    def insert_blank(self, before: bool) -> None:
        if self.model is None:
            return
        selected = self.selected_index()
        index = selected if selected is not None else len(self.model.entries)
        if not before:
            index += 1
        try:
            self.model.insert_blank(index)
            self._refresh_after_layout_edit(select_index=index)
            self.status.set(f"Inserted blank page at position {index + 1}.")
        except Exception as exc:
            messagebox.showerror("Insert blank failed", str(exc))

    def insert_image(self, before: bool) -> None:
        if self.model is None:
            return
        filename = filedialog.askopenfilename(
            title="Insert Image",
            filetypes=[("Image files", "*.jpg *.jpeg *.png"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not filename:
            return
        selected = self.selected_index()
        index = selected if selected is not None else len(self.model.entries)
        if not before:
            index += 1
        try:
            self.model.insert_image(index, Path(filename))
            self._refresh_after_layout_edit(select_index=index)
            self.status.set(f"Inserted image: {Path(filename).name}")
        except Exception as exc:
            messagebox.showerror("Insert image failed", str(exc))

    def quick_blank_before_cover(self) -> None:
        if self.model is None:
            return
        index = self._cover_entry_index()
        if index is None:
            index = 0
        self.model.insert_blank(index)
        self._refresh_after_layout_edit(select_index=index)
        self.status.set("Inserted one blank page before cover.")

    def quick_blank_after_cover(self) -> None:
        if self.model is None:
            return
        index = self._cover_entry_index()
        if index is None:
            index = 0
        index += 1
        self.model.insert_blank(index)
        self._refresh_after_layout_edit(select_index=index)
        self.status.set("Inserted one blank page after cover.")

    def _refresh_after_layout_edit(
        self,
        select_index: int | None = None,
        preserve_yview: bool = True,
        mark_edited: bool = True,
    ) -> None:
        if mark_edited:
            self._mark_diagnosis_stale()
        self.refresh_spine_views(preserve_yview=preserve_yview)
        self.page_list.selection_clear(0, tk.END)
        if select_index is not None:
            self.page_list.selection_set(select_index)
        self.refresh_preview_views()
        if mark_edited:
            self._mark_active_volume_edited()

    def _ask_positive_integer(self, title: str, prompt: str) -> int | None:
        return simpledialog.askinteger(title, prompt, minvalue=1, parent=self.root)
