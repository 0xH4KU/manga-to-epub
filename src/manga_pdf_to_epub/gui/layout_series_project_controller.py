from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from ..models.series import SeriesProject


class EpubLayoutSeriesProjectMixin:
    def import_series(self) -> None:
        filenames = filedialog.askopenfilenames(
            title="Import Series Sources",
            filetypes=[("Manga source files", "*.pdf *.cbz *.zip"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not filenames:
            return
        self.series_project = SeriesProject.from_sources([Path(filename) for filename in filenames])
        self._sync_navigation_mode()
        self._load_metadata_fields()
        self.refresh_series_list()
        self.status.set(f"Imported series with {len(self.series_project.volumes)} volumes.")
        self.refresh_workspace_status()

    def save_project(self) -> None:
        if self.series_project is None:
            return
        if self.model is not None:
            self._store_metadata_fields()
        active_volume = getattr(self, "active_series_volume", None)
        self.series_project.active_volume_number = getattr(active_volume, "volume_number", None)
        filename = filedialog.asksaveasfilename(
            title="Save Series Project",
            defaultextension=".json",
            initialdir=str(Path.cwd()),
            initialfile="series-project.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not filename:
            return
        project_path = Path(filename)
        try:
            payload = self.series_project.to_payload(project_path)
            project_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            self.status.set(f"Saved project: {project_path.name}")
        except Exception as exc:
            messagebox.showerror("Save project failed", str(exc))

    def open_project(self) -> None:
        filename = filedialog.askopenfilename(
            title="Open Series Project",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not filename:
            return
        project_path = Path(filename)
        try:
            payload = json.loads(project_path.read_text(encoding="utf-8"))
            self.series_project = SeriesProject.from_payload(payload, project_path)
            self.model = None
            self.pdf_path = None
            self.active_series_volume = None
            self._reset_deleted_history()
            self.ready_status_undo.clear()
            self._reset_preview_cache()
            self._sync_navigation_mode()
            self._load_metadata_fields()
            self.refresh_series_list()
            self._restore_saved_active_series_selection()
            self.refresh_spine_views()
            self.refresh_preview_views()
            self.status.set(f"Opened project: {project_path.name}")
            self.refresh_workspace_status()
        except Exception as exc:
            messagebox.showerror("Open project failed", str(exc))

    def _restore_saved_active_series_selection(self) -> None:
        if self.series_project is None or not hasattr(self, "series_list"):
            return
        active_number = getattr(self.series_project, "active_volume_number", None)
        if active_number is None:
            return
        for index, volume in enumerate(self.series_project.volumes):
            if volume.volume_number == active_number:
                self.active_series_volume = volume
                self.series_list.selection_clear(0, tk.END)
                self.series_list.selection_set(index)
                return
