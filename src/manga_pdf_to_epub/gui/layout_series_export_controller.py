from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .layout_series_workflow import series_export_preflight


class EpubLayoutSeriesExportMixin:
    def export_ready_series(self) -> None:
        if self.series_project is None:
            return
        if getattr(self, "_busy", False):
            self.status.set("Another operation is already running.")
            return
        self._store_metadata_fields()
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
