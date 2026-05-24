from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .epub_layout_diagnosis_controller import reset_diagnosis_for_model
from .epub_layout_series_workflow import series_export_preflight
from .epub_series_model import SeriesProject, SeriesVolume


class EpubLayoutSeriesMixin:
    def import_series(self) -> None:
        filenames = filedialog.askopenfilenames(
            title="Import Series PDFs",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not filenames:
            return
        self.series_project = SeriesProject.from_pdfs([Path(filename) for filename in filenames])
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

    def mark_selected_series_volume_ready(self) -> None:
        if self.series_project is None or not hasattr(self, "series_list"):
            return
        selection = self.series_list.curselection()
        if not selection:
            return
        selected_volumes = [self.series_project.volumes[index] for index in selection]
        self._record_ready_status_undo(selected_volumes)
        for volume in selected_volumes:
            self.series_project.mark_ready(volume)
        self.refresh_series_list()
        self.refresh_workspace_status()
        if len(selected_volumes) == 1:
            self.status.set(f"Marked Vol.{selected_volumes[0].volume_number:02d} ready.")
        else:
            self.status.set(f"Marked {len(selected_volumes)} volumes ready.")

    def _record_ready_status_undo(self, volumes: list[SeriesVolume]) -> None:
        if not hasattr(self, "ready_status_undo"):
            self.ready_status_undo = []
        self.ready_status_undo.append([(volume, volume.status) for volume in volumes])

    def unready_selected(self) -> bool:
        undo_stack = getattr(self, "ready_status_undo", [])
        if not undo_stack:
            return False
        selected_volumes = self._selected_series_volumes()
        if selected_volumes:
            return self._unready_selected_volumes(selected_volumes)
        return self._unready_latest_batch()

    def undo_ready_mark(self) -> bool:
        return self.unready_selected()

    def _selected_series_volumes(self) -> list[SeriesVolume]:
        if self.series_project is None or not hasattr(self, "series_list"):
            return []
        selection = self.series_list.curselection()
        return [
            self.series_project.volumes[index]
            for index in selection
            if 0 <= index < len(self.series_project.volumes)
        ]

    def _unready_selected_volumes(self, selected_volumes: list[SeriesVolume]) -> bool:
        undo_stack = getattr(self, "ready_status_undo", [])
        pending_volume_ids = {id(volume) for volume in selected_volumes}
        restored_statuses: list[tuple[SeriesVolume, str]] = []
        revised_stack = [list(batch) for batch in undo_stack]

        for batch_index in range(len(revised_stack) - 1, -1, -1):
            batch = revised_stack[batch_index]
            remaining_statuses: list[tuple[SeriesVolume, str]] = []
            for volume, previous_status in batch:
                if id(volume) in pending_volume_ids:
                    volume.status = previous_status
                    volume.error = None
                    restored_statuses.append((volume, previous_status))
                    pending_volume_ids.remove(id(volume))
                else:
                    remaining_statuses.append((volume, previous_status))
            revised_stack[batch_index] = remaining_statuses
            if not pending_volume_ids:
                break

        if not restored_statuses:
            self.status.set("No selected ready marks to undo.")
            return False

        self.ready_status_undo = [batch for batch in revised_stack if batch]
        self.refresh_series_list()
        self.refresh_workspace_status()
        if len(restored_statuses) == 1:
            volume = restored_statuses[0][0]
            self.status.set(f"Restored Vol.{volume.volume_number:02d} status.")
        else:
            self.status.set(f"Restored {len(restored_statuses)} selected volume statuses.")
        return True

    def _unready_latest_batch(self) -> bool:
        undo_stack = getattr(self, "ready_status_undo", [])
        if not undo_stack:
            return False
        previous_statuses = undo_stack.pop()
        for volume, previous_status in previous_statuses:
            volume.status = previous_status
            volume.error = None
        self.refresh_series_list()
        self.refresh_workspace_status()
        if len(previous_statuses) == 1:
            volume = previous_statuses[0][0]
            self.status.set(f"Restored Vol.{volume.volume_number:02d} status.")
        else:
            self.status.set(f"Restored {len(previous_statuses)} volume statuses.")
        return True

    def export_ready_series(self) -> None:
        if self.series_project is None:
            return
        if getattr(self, "_busy", False):
            self.status.set("Another operation is already running.")
            return
        output_dir_name = filedialog.askdirectory(
            title="Series output directory",
            initialdir=str(getattr(self, "output_dir", Path.cwd())),
        )
        if not output_dir_name:
            return
        output_dir = Path(output_dir_name)
        preflight = series_export_preflight(self.series_project, output_dir)
        warning_lines = preflight.message_lines
        if warning_lines:
            messagebox.showwarning("Series export preflight", "\n".join(warning_lines))
        self._open_series_export_progress()
        self._run_background(
            "Exporting ready series...",
            lambda: self._export_ready_series_work(output_dir),
            self._series_export_done,
        )

    def validate_series(self) -> None:
        if self.series_project is None:
            return
        output_dir = Path(getattr(self, "output_dir", Path.cwd()))
        summary = self.series_project.validate_all(output_dir)
        self.refresh_series_list()
        self.refresh_workspace_status()
        warning_lines = self._series_warning_lines()
        if warning_lines:
            messagebox.showwarning("Series validation warnings", "\n".join(warning_lines))
        self.status.set(
            f"Series validation: {summary['ready']} ready, {summary['failed']} failed, "
            f"{summary['warnings']} warnings."
        )

    def _series_warning_lines(self) -> list[str]:
        if self.series_project is None:
            return []
        lines: list[str] = []
        for volume in self.series_project.volumes:
            for warning in volume.warnings:
                lines.append(f"Vol.{volume.volume_number:02d}: {warning}")
        return lines[:20]

    def _export_ready_series_work(self, output_dir: Path) -> dict[str, int]:
        summary = {"exported": 0, "failed": 0, "skipped": 0, "warnings": 0}
        if self.series_project is None:
            return summary
        for event in self.series_project.export_ready_iter(output_dir):
            if event["status"] == "summary":
                summary = {
                    "exported": event["exported"],
                    "failed": event["failed"],
                    "skipped": event["skipped"],
                    "warnings": event["warnings"],
                }
                continue
            self.root.after(0, lambda event=event: self._series_export_progress(event))
        return summary

    def _open_series_export_progress(self) -> None:
        self.series_export_progress = {
            "current": "Exporting ready series...",
            "summary": "",
            "close_text": "Exporting...",
        }
        try:
            window = tk.Toplevel(self.root)
            window.title("Series Export")
            window.resizable(False, False)
            current_var = tk.StringVar(value=self.series_export_progress["current"])
            summary_var = tk.StringVar(value="")
            close_text_var = tk.StringVar(value="Exporting...")
            ttk.Label(window, textvariable=current_var, padding=(12, 12, 12, 4)).pack(fill=tk.X)
            ttk.Label(window, textvariable=summary_var, padding=(12, 0, 12, 8)).pack(fill=tk.X)
            close_button = ttk.Button(window, textvariable=close_text_var, command=window.destroy, state=tk.DISABLED)
            close_button.pack(padx=12, pady=(0, 12))
            self.series_export_progress.update(
                {
                    "window": window,
                    "current_var": current_var,
                    "summary_var": summary_var,
                    "close_text_var": close_text_var,
                    "close_button": close_button,
                }
            )
        except Exception:
            pass

    def _set_series_export_progress(self, current: str | None = None, summary: str | None = None) -> None:
        progress = getattr(self, "series_export_progress", None)
        if progress is None:
            return
        if current is not None:
            progress["current"] = current
            current_var = progress.get("current_var")
            if current_var is not None:
                current_var.set(current)
        if summary is not None:
            progress["summary"] = summary
            summary_var = progress.get("summary_var")
            if summary_var is not None:
                summary_var.set(summary)

    def _series_export_progress(self, event: dict) -> None:
        volume_number = event.get("volume_number")
        if volume_number is None:
            return
        status = event.get("status")
        if status == "exported":
            self.status.set(f"Exported Vol.{volume_number:02d}.")
            self._set_series_export_progress(current=f"Exported Vol.{volume_number:02d}.")
            self.refresh_series_list()
        elif status == "failed":
            self.status.set(f"Failed Vol.{volume_number:02d}.")
            self._set_series_export_progress(current=f"Failed Vol.{volume_number:02d}.")
            self.refresh_series_list()
        elif status == "skipped":
            self.status.set(f"Skipped Vol.{volume_number:02d}.")
            self._set_series_export_progress(current=f"Skipped Vol.{volume_number:02d}.")
            self.refresh_series_list()
        elif status == "started":
            self.status.set(f"Exporting Vol.{volume_number:02d}.")
            self._set_series_export_progress(current=f"Exporting Vol.{volume_number:02d}.")

    def _series_export_done(self, summary: dict[str, int]) -> None:
        self.refresh_series_list()
        self.refresh_workspace_status()
        self._finish_series_export_progress(summary)
        self.status.set(
            f"Series exported {summary['exported']} volumes; "
            f"{summary['failed']} failed, {summary['skipped']} skipped, "
            f"{summary.get('warnings', 0)} warnings."
        )

    def _finish_series_export_progress(self, summary: dict[str, int]) -> None:
        text = (
            f"{summary['exported']} exported, {summary['failed']} failed, "
            f"{summary['skipped']} skipped, {summary.get('warnings', 0)} warnings"
        )
        self._set_series_export_progress(current="Series export complete.", summary=text)
        progress = getattr(self, "series_export_progress", None)
        if progress is None:
            return
        progress["close_text"] = "Close"
        close_text_var = progress.get("close_text_var")
        if close_text_var is not None:
            close_text_var.set("Close")
        close_button = progress.get("close_button")
        if close_button is not None:
            close_button.configure(state=tk.NORMAL)

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
