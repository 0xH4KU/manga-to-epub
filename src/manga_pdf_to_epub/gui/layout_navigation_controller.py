from __future__ import annotations

import tkinter as tk


class EpubLayoutNavigationMixin:
    def _workspace_summary(self) -> str:
        if self.model is None:
            page_summary = "No source loaded"
        else:
            page_summary = f"Pages: {len(self.model.entries)}"
        if self.series_project is None:
            return f"{page_summary} | Series: 0"
        volumes = self.series_project.volumes
        counts = {"Ready": 0, "Edited": 0, "Failed": 0}
        for volume in volumes:
            if volume.status in counts:
                counts[volume.status] += 1
        return (
            f"{page_summary} | Series: {len(volumes)} | "
            f"Ready: {counts['Ready']} | Edited: {counts['Edited']} | Failed: {counts['Failed']}"
        )

    def refresh_workspace_status(self) -> None:
        if hasattr(self, "workspace_status"):
            self.workspace_status.set(self._workspace_summary())

    def _sync_navigation_mode(self, available_width: int | None = None) -> None:
        if not hasattr(self, "series_pane") or not hasattr(self, "spine_pane"):
            return
        series_mode = getattr(self, "series_project", None) is not None
        if series_mode:
            if self._navigation_uses_columns(available_width):
                self._pack_navigation_pane(self.series_pane, side=tk.LEFT, fill=tk.BOTH, expand=True)
                self._pack_navigation_pane(self.spine_pane, side=tk.LEFT, fill=tk.BOTH, expand=True)
            else:
                self._pack_navigation_pane(self.series_pane, side=tk.TOP, fill=tk.BOTH, expand=True)
                self._pack_navigation_pane(self.spine_pane, side=tk.TOP, fill=tk.BOTH, expand=True)
        else:
            self.series_pane.pack_forget()
            self._pack_navigation_pane(self.spine_pane, side=tk.LEFT, fill=tk.BOTH, expand=True)

    @staticmethod
    def _navigation_uses_columns(available_width: int | None) -> bool:
        if available_width is None:
            return False
        return available_width >= 680

    @staticmethod
    def _pack_navigation_pane(pane, **kwargs) -> None:
        try:
            pane.pack_forget()
        except Exception:
            pass
        pane.pack(**kwargs)
