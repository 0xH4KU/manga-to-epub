from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from .layout_diagnosis_controller import reset_diagnosis_for_model
from ..models.series import SeriesVolume


class EpubLayoutSeriesMixin:
    def refresh_series_list(self) -> None:
        if not hasattr(self, "series_list"):
            return
        self._sync_navigation_mode()
        self.series_list.delete(0, tk.END)
        if self.series_project is None:
            return
        for volume in self.series_project.volumes:
            self.series_list.insert(
                tk.END,
                f"{volume.status} Vol.{volume.volume_number:02d} {volume.pdf_path.name}",
            )

    def select_series_volume(self) -> None:
        if self.series_project is None or not hasattr(self, "series_list"):
            return
        selection = self.series_list.curselection()
        if not selection:
            return
        volume = self.series_project.volumes[selection[0]]
        try:
            self._load_series_volume(volume)
        except Exception as exc:
            volume.status = "Failed"
            volume.error = str(exc)
            self.refresh_series_list()
            messagebox.showerror("Load series volume failed", str(exc))

    def _load_series_volume(self, volume: SeriesVolume) -> None:
        self.pdf_path = volume.pdf_path
        self.model = self.series_project.model_for_volume(volume) if self.series_project is not None else None
        reset_diagnosis_for_model(self, self.model)
        self.active_series_volume = volume
        self._reset_deleted_history()
        self._reset_preview_cache()
        self._load_metadata_fields()
        self.refresh_spine_views()
        self._select_first_spine_row()
        self.status.set(f"Loaded {self.series_project.generated_title(volume)}.")
        self.refresh_workspace_status()
        self.refresh_preview_views()

    def _mark_active_volume_edited(self) -> None:
        volume = getattr(self, "active_series_volume", None)
        if getattr(self, "series_project", None) is None or volume is None:
            return
        volume.status = "Edited"
        volume.error = None
        self.refresh_series_list()
        self._restore_active_series_selection()
        self.refresh_workspace_status()

    def _restore_active_series_selection(self) -> None:
        if self.series_project is None or not hasattr(self, "series_list"):
            return
        volume = getattr(self, "active_series_volume", None)
        if volume is None:
            return
        try:
            index = self.series_project.volumes.index(volume)
        except ValueError:
            return
        self.series_list.selection_clear(0, tk.END)
        self.series_list.selection_set(index)
