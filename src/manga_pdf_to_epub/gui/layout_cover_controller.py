from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

from .layout_history import CoverState
from ..models.layout import LayoutEntry


class EpubLayoutCoverMixin:
    def set_selected_as_cover(self) -> None:
        if self.model is None:
            return
        index = self.selected_index()
        if index is None:
            return
        entry = self.model.entries[index]
        if entry.is_blank:
            messagebox.showerror("Set cover failed", "Cover must be an image page.")
            return
        try:
            self.model.set_cover_entry(entry)
            self.refresh_spine_views(preserve_yview=True)
            self.status.set(f"Set {entry.label} as cover.")
            self._mark_active_volume_edited()
        except Exception as exc:
            messagebox.showerror("Set cover failed", str(exc))

    def export_selected_images(self) -> None:
        if self.model is None:
            return
        indexes = self.selected_indexes()
        if not indexes:
            return
        output_dir_name = filedialog.askdirectory(title="Export selected images", initialdir=str(Path.cwd()))
        if not output_dir_name:
            return
        try:
            exported, skipped = self.model.export_selected_images(indexes, Path(output_dir_name))
            self.status.set(f"Exported {len(exported)} images; skipped {skipped} blank pages.")
            if not exported:
                messagebox.showinfo("Export selected images", "No exportable images selected.")
        except Exception as exc:
            messagebox.showerror("Export selected images failed", str(exc))

    def _capture_cover_state(self) -> CoverState:
        if self.model is None:
            return CoverState(None, None)
        return CoverState(
            getattr(self.model, "cover_source_index", None),
            getattr(self.model, "cover_entry_id", None),
        )

    def _restore_cover_state(self, state: CoverState | None) -> None:
        if self.model is None or state is None:
            return
        self.model.cover_source_index = state.source_index
        self.model.cover_entry_id = state.entry_id

    def _cover_entry_index(self) -> int | None:
        if self.model is None:
            return None
        for index, entry in enumerate(self.model.entries):
            if self._is_cover_entry(entry):
                return index
        return None

    def _is_cover_entry(self, entry: LayoutEntry) -> bool:
        if self.model is None:
            return False
        if entry.is_blank:
            return False
        cover_entry_id = getattr(self.model, "cover_entry_id", None)
        if cover_entry_id is not None:
            return entry.page.item_id == cover_entry_id
        return entry.source_index == getattr(self.model, "cover_source_index", None)
