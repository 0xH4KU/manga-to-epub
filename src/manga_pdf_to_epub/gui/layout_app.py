#!/usr/bin/env python3
"""Small GUI for tuning EPUB blank-page placement before export."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from .layout_background_controller import EpubLayoutBackgroundMixin
from .layout_diagnosis_controller import (
    EpubLayoutDiagnosisMixin,
    initialize_diagnosis_state,
    reset_diagnosis_for_model,
)
from .layout_diagnosis_io_controller import EpubLayoutDiagnosisIOMixin
from .layout_diagnosis_view_controller import EpubLayoutDiagnosisViewMixin
from .layout_command_palette_controller import EpubLayoutCommandPaletteMixin
from .layout_cover_controller import EpubLayoutCoverMixin
from .layout_delete_controller import EpubLayoutDeleteMixin
from .layout_edit_controller import EpubLayoutEditMixin
from .layout_history import DeleteHistory
from .layout_inspector_controller import EpubLayoutInspectorMixin
from .layout_metadata_controller import EpubLayoutMetadataMixin
from .layout_navigation_controller import EpubLayoutNavigationMixin
from .layout_preview import ThumbnailCache
from .layout_preview_controller import EpubLayoutPreviewMixin
from .layout_series_controller import EpubLayoutSeriesMixin
from .layout_series_export_controller import EpubLayoutSeriesExportMixin
from .layout_series_project_controller import EpubLayoutSeriesProjectMixin
from .layout_series_ready_controller import EpubLayoutSeriesReadyMixin
from .layout_spine_controller import EpubLayoutSpineMixin
from .layout_thumbnail_controller import EpubLayoutThumbnailMixin
from .layout_support import event_from_text_input
from .layout_workbench import EpubLayoutWorkbenchMixin
from ..models.layout import LayoutEntry, LayoutModel
from ..models.series import SeriesProject, SeriesVolume


class EpubLayoutApp(
    EpubLayoutBackgroundMixin,
    EpubLayoutWorkbenchMixin,
    EpubLayoutInspectorMixin,
    EpubLayoutNavigationMixin,
    EpubLayoutCommandPaletteMixin,
    EpubLayoutSpineMixin,
    EpubLayoutEditMixin,
    EpubLayoutDeleteMixin,
    EpubLayoutCoverMixin,
    EpubLayoutMetadataMixin,
    EpubLayoutThumbnailMixin,
    EpubLayoutPreviewMixin,
    EpubLayoutDiagnosisViewMixin,
    EpubLayoutDiagnosisIOMixin,
    EpubLayoutDiagnosisMixin,
    EpubLayoutSeriesProjectMixin,
    EpubLayoutSeriesReadyMixin,
    EpubLayoutSeriesExportMixin,
    EpubLayoutSeriesMixin,
):
    def __init__(self, root: tk.Tk):
        self.root = root
        self._configure_window()

        self.model: LayoutModel | None = None
        self.pdf_path: Path | None = None
        self.output_dir = Path.cwd() / "epub_layout_gui_exports"
        self.photo_refs: list[tk.PhotoImage] = []
        self.thumbnail_cache: ThumbnailCache = ThumbnailCache()
        self._thumbnail_render_jobs: set[tuple] = set()
        self._thumbnail_cache_generation = 0
        self._pdf_doc = None
        self._pdf_doc_path: Path | None = None
        self.deleted_history: DeleteHistory[LayoutEntry] = DeleteHistory()
        self.ready_status_undo: list[list[tuple[SeriesVolume, str]]] = []
        self.status = tk.StringVar(value="Open a source file to begin.")
        self.workspace_status = tk.StringVar(value="")
        self.apple_preview = tk.BooleanVar(value=True)
        self.title_var = tk.StringVar(value="")
        self.author_var = tk.StringVar(value="")
        self.language_var = tk.StringVar(value="zh-Hant")
        self.title_label_var = tk.StringVar(value="Title")
        self.author_label_var = tk.StringVar(value="Author")
        self.exclude_cover_var = tk.BooleanVar(value=False)
        self.series_project: SeriesProject | None = None
        self.active_series_volume: SeriesVolume | None = None
        self._busy = False
        self._page_drag_source: int | None = None
        initialize_diagnosis_state(self)

        self._build_ui()
        self._bind_shortcuts()

    def _bind_shortcuts(self) -> None:
        self.root.bind_all("<Command-z>", lambda _event: self.recover_last_deleted())
        self.root.bind_all("<Control-z>", lambda _event: self.recover_last_deleted())
        self.root.bind_all("<Delete>", self._delete_shortcut)
        self.root.bind_all("<BackSpace>", self._delete_shortcut)
        self.root.bind_all("<Command-Shift-E>", lambda _event: self.export_selected_images())
        self.root.bind_all("<Control-Shift-E>", lambda _event: self.export_selected_images())
        self.root.bind_all("<Command-k>", lambda _event: self.open_command_palette())
        self.root.bind_all("<Control-k>", lambda _event: self.open_command_palette())

    def _delete_shortcut(self, event) -> str | None:
        if event_from_text_input(event):
            return "break"
        self.delete_selected_entry()
        return None

    def open_pdf(self) -> None:
        filename = filedialog.askopenfilename(
            title="Open Source",
            filetypes=[("Manga source files", "*.pdf *.cbz *.zip"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not filename:
            return
        self.pdf_path = Path(filename)
        self._run_background(
            "Loading source images...",
            lambda: LayoutModel.from_source(self.pdf_path),
            self._open_pdf_done,
        )

    def _open_pdf_done(self, model: LayoutModel) -> None:
        self.model = model
        reset_diagnosis_for_model(self, model)
        self.series_project = None
        self.active_series_volume = None
        self._sync_navigation_mode()
        self._reset_deleted_history()
        self._reset_preview_cache()
        self._load_metadata_fields()
        self.refresh_spine_views()
        self._select_first_spine_row()
        self.status.set(f"Loaded {self.pdf_path.name}: {len(self.model.entries)} pages")
        self.refresh_workspace_status()
        self.refresh_preview_views()

    def export_epub(self) -> None:
        if self.model is None or self.pdf_path is None:
            return
        self._store_metadata_fields()
        self.output_dir.mkdir(exist_ok=True)
        default = self.pdf_path.with_suffix(".epub").name
        filename = filedialog.asksaveasfilename(
            title="Export EPUB",
            defaultextension=".epub",
            initialdir=str(self.output_dir),
            initialfile=default,
            filetypes=[("EPUB files", "*.epub"), ("All files", "*.*")],
        )
        if not filename:
            return
        epub_path = Path(filename)
        self._run_background(
            "Exporting EPUB...",
            lambda: self.model.export_epub(epub_path, overwrite=True),
            lambda counts: self._export_done(epub_path, counts),
        )

    def save_preset(self) -> None:
        if self.model is None:
            return
        self._store_metadata_fields()
        filename = filedialog.asksaveasfilename(
            title="Save Layout Preset",
            defaultextension=".json",
            initialdir=str(Path.cwd()),
            initialfile="layout-preset.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not filename:
            return
        try:
            self.model.save_preset(Path(filename))
            self.status.set(f"Saved preset: {Path(filename).name}")
        except Exception as exc:
            messagebox.showerror("Save preset failed", str(exc))

    def load_preset(self) -> None:
        if self.model is None:
            return
        filename = filedialog.askopenfilename(
            title="Load Layout Preset",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not filename:
            return
        try:
            preset_path = Path(filename)
            if self.series_project is not None:
                self._load_preset_for_series(preset_path)
            else:
                self._load_preset_for_current_model(preset_path)
        except Exception as exc:
            messagebox.showerror("Load preset failed", str(exc))

    def _load_preset_for_current_model(self, preset_path: Path) -> None:
        if self.model is None:
            return
        self.model.apply_preset(preset_path)
        self._mark_diagnosis_stale()
        self._load_metadata_fields()
        self.refresh_spine_views()
        self.page_list.selection_clear(0, tk.END)
        if self.model.entries:
            self.page_list.selection_set(0)
        self.refresh_preview_views()
        self.status.set(f"Loaded preset: {preset_path.name}")

    def _load_preset_for_series(self, preset_path: Path) -> None:
        if self.series_project is None:
            return
        scope = simpledialog.askstring(
            "Apply Preset to Volumes",
            "Volumes to apply preset to (examples: 1,2,7 or 1-7 or all):",
            parent=getattr(self, "root", None),
        )
        if scope is None or not scope.strip():
            return
        target_volumes = self.series_project.volumes_for_scope(scope)
        if not target_volumes:
            self.status.set("No volumes matched preset scope.")
            return
        active_volume = getattr(self, "active_series_volume", None)
        active_was_updated = False
        for volume in target_volumes:
            model = self.series_project.model_for_volume(volume)
            model.apply_preset(preset_path)
            model.title = self.series_project.generated_title(volume)
            model.author = self.series_project.author
            model.language = self.series_project.language
            volume.status = "Edited"
            volume.error = None
            if volume is active_volume:
                active_was_updated = True
        self.refresh_series_list()
        self._restore_active_series_selection()
        self.refresh_workspace_status()
        if active_was_updated:
            self._mark_diagnosis_stale()
            self._load_metadata_fields()
            self.refresh_spine_views()
            self.page_list.selection_clear(0, tk.END)
            if self.model is not None and self.model.entries:
                self.page_list.selection_set(0)
            self.refresh_preview_views()
        self.status.set(f"Loaded preset for {len(target_volumes)} volumes: {preset_path.name}")

    def _export_done(self, epub_path: Path, counts: dict[str, int]) -> None:
        self.status.set(f"Exported {epub_path.name}: {counts['total']} spine items.")
        messagebox.showinfo("Export complete", f"Exported:\n{epub_path}")

    def _export_failed(self, exc: Exception) -> None:
        self.status.set("Export failed.")
        messagebox.showerror("Export failed", str(exc))


def main() -> int:
    root = tk.Tk()
    EpubLayoutApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
