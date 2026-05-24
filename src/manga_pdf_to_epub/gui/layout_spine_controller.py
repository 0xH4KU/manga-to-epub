from __future__ import annotations

import tkinter as tk


class EpubLayoutSpineMixin:
    def refresh_list(self, preserve_yview: bool = False) -> None:
        if self.model is None:
            if hasattr(self, "page_list"):
                self.page_list.delete(0, tk.END)
            self.refresh_workspace_status()
            return
        yview_start = self.page_list.yview()[0] if preserve_yview else None
        self.page_list.delete(0, tk.END)
        for i, entry in enumerate(self.model.entries, start=1):
            marker = "[blank]" if entry.is_blank else "[page]"
            cover = " [cover]" if self._is_cover_entry(entry) else ""
            row_index = i - 1
            spine_marker = self._marker_text_for_entry(row_index)
            self.page_list.insert(tk.END, f"{i:04d} {marker}{cover}{spine_marker} {entry.label}")
            self._apply_spine_marker_color(row_index)
        if yview_start is not None:
            self.page_list.yview_moveto(yview_start)
        self.refresh_workspace_status()

    def selected_index(self) -> int | None:
        selection = self.page_list.curselection()
        return selection[0] if selection else None

    def selected_indexes(self) -> list[int]:
        return list(self.page_list.curselection())

    def _page_drag_start(self, event) -> None:
        if self.model is None or not self.model.entries:
            self._page_drag_source = None
            return
        index = self.page_list.nearest(event.y)
        if index < 0 or index >= len(self.model.entries):
            self._page_drag_source = None
            return
        self._page_drag_source = index

    def _page_drag_release(self, event) -> None:
        if self.model is None or self._page_drag_source is None:
            return
        from_index = self._page_drag_source
        self._page_drag_source = None
        if not self.model.entries:
            return
        to_index = self.page_list.nearest(event.y)
        to_index = min(max(to_index, 0), len(self.model.entries) - 1)
        if from_index == to_index:
            return
        try:
            label = self.model.entries[from_index].label
            final_index = self.model.move_entry(from_index, to_index)
            self._refresh_after_layout_edit(select_index=final_index)
            self.status.set(f"Moved {label} to position {final_index + 1}.")
        except Exception as exc:
            self._show_spine_error("Move page failed", exc)

    def _show_spine_error(self, title: str, exc: Exception) -> None:
        from tkinter import messagebox

        messagebox.showerror(title, str(exc))
