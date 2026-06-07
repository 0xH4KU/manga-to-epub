from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .layout_diagnosis_panel_controller import _diagnosis_panels, refresh_diagnosis_panel
from .layout_diagnosis_window import DiagnosisPanel, DiagnosisPanelCallbacks, DiagnosisWindow
from .layout_diagnosis_runner import DiagnosisSettings


class EpubLayoutDiagnosisViewMixin:
    def refresh_spine_views(self, preserve_yview: bool = False) -> None:
        self.refresh_list(preserve_yview=preserve_yview)
        self.refresh_diagnosis_spine(preserve_yview=preserve_yview)

    def refresh_preview_views(self) -> None:
        self.refresh_preview()
        self.refresh_diagnosis_preview()

    def refresh_diagnosis_panel(self) -> None:
        refresh_diagnosis_panel(self)

    def refresh_diagnosis_preview(self) -> None:
        window = getattr(self, "diagnosis_window", None)
        if window is None or getattr(window, "preview", None) is None:
            return
        selection = _listbox_selection(window.spine_list)
        if len(selection) >= 2:
            self._refresh_diagnosis_selected_entries(window.preview, window.photo_refs, selection[:2])
            return
        self._refresh_preview_canvas(window.preview, window.photo_refs, _first_selection(window.spine_list))

    def _refresh_diagnosis_selected_entries(self, canvas, photo_refs: list, indexes: tuple[int, ...]) -> None:
        canvas.delete("all")
        photo_refs.clear()
        if self.model is None or not self.model.entries:
            return
        entries = [self.model.entries[index] for index in indexes if 0 <= index < len(self.model.entries)]
        if not entries:
            return

        width = max(400, canvas.winfo_width())
        height = max(300, canvas.winfo_height())
        gap = 12
        page_w = (width - gap * 3) // 2
        page_h = height - gap * 2
        slots = self._spread_slots(2, gap, page_w)
        for entry, (x, y) in zip(entries, slots):
            self._draw_entry_on_canvas(canvas, photo_refs, entry, x, y, page_w, page_h)

    def refresh_diagnosis_spine(self, preserve_yview: bool = False) -> None:
        window = getattr(self, "diagnosis_window", None)
        if window is None or getattr(window, "spine_list", None) is None:
            return
        listbox = window.spine_list
        if getattr(self, "model", None) is None:
            listbox.delete(0, tk.END)
            return
        selected = _listbox_selection(listbox)
        yview_start = listbox.yview()[0] if preserve_yview else None
        listbox.delete(0, tk.END)
        for index, entry in enumerate(self.model.entries, start=1):
            row_index = index - 1
            marker = "[blank]" if entry.is_blank else "[page]"
            cover = " [cover]" if self._is_cover_entry(entry) else ""
            spine_marker = self._marker_text_for_entry(row_index)
            listbox.insert(tk.END, f"{index:04d} {marker}{cover}{spine_marker} {entry.label}")
            self._apply_spine_marker_color_to_listbox(listbox, row_index)
        if yview_start is not None:
            listbox.yview_moveto(yview_start)
        _restore_listbox_selection(listbox, selected, len(self.model.entries))

    def open_diagnose_window(self) -> None:
        if getattr(self, "model", None) is None:
            self.status.set("Open a PDF before opening Diagnose.")
            return
        existing = getattr(self, "diagnosis_window", None)
        if existing is not None:
            existing.focus()
            return
        self.diagnosis_window = DiagnosisWindow(
            self,
            self.root,
            diagnosis_callbacks(self),
            getattr(self, "diagnosis_settings", DiagnosisSettings()),
        )
        self.refresh_diagnosis_spine()
        self.refresh_diagnosis_panel()

    def sync_selection_from_main(self) -> None:
        if getattr(self, "_syncing_spine_selection", False):
            return
        self._syncing_spine_selection = True
        try:
            selected = self.selected_index()
            self._set_diagnosis_selection(selected)
        finally:
            self._syncing_spine_selection = False
        self.refresh_preview()
        self.refresh_diagnosis_preview()

    def sync_selection_from_diagnosis(self) -> None:
        if getattr(self, "_syncing_spine_selection", False):
            return
        window = getattr(self, "diagnosis_window", None)
        if window is None:
            return
        selected = _first_selection(window.spine_list)
        self._syncing_spine_selection = True
        try:
            self._set_main_selection(selected)
        finally:
            self._syncing_spine_selection = False
        self.refresh_preview()
        self.refresh_diagnosis_preview()

    def _set_main_selection(self, selected: int | None) -> None:
        self.page_list.selection_clear(0, tk.END)
        if selected is not None:
            self.page_list.selection_set(selected)
            self.page_list.see(selected)

    def _set_main_selection_range(self, indexes: tuple[int, ...]) -> None:
        self.page_list.selection_clear(0, tk.END)
        for index in indexes:
            self.page_list.selection_set(index)
        if indexes:
            self.page_list.see(indexes[0])

    def _set_diagnosis_selection(self, selected: int | None) -> None:
        window = getattr(self, "diagnosis_window", None)
        if window is None:
            return
        window.spine_list.selection_clear(0, tk.END)
        if selected is not None:
            window.spine_list.selection_set(selected)
            window.spine_list.see(selected)

    def _set_diagnosis_selection_range(self, indexes: tuple[int, ...]) -> None:
        window = getattr(self, "diagnosis_window", None)
        if window is None:
            return
        window.spine_list.selection_clear(0, tk.END)
        for index in indexes:
            window.spine_list.selection_set(index)
        if indexes:
            window.spine_list.see(indexes[0])

    def _select_first_spine_row(self) -> None:
        self.page_list.selection_clear(0, tk.END)
        if getattr(self, "model", None) is not None and self.model.entries:
            self.page_list.selection_set(0)
        self._set_diagnosis_selection(self.selected_index())

    def _diagnose_window_closed(self, closed_window=None) -> None:
        window = closed_window if closed_window is not None else getattr(self, "diagnosis_window", None)
        if closed_window is None or closed_window is getattr(self, "diagnosis_window", None):
            self.diagnosis_window = None
        if window is not None and hasattr(window, "destroy"):
            window.destroy()

    def _active_diagnosis_panel(self):
        window = getattr(self, "diagnosis_window", None)
        if window is not None and getattr(window, "panel", None) is not None:
            return window.panel
        return getattr(self, "diagnosis_panel", None)

    def sync_spine_selection_from_candidate(self) -> None:
        candidate = self._selected_spread_candidate()
        if candidate is None or getattr(self, "model", None) is None:
            return
        source_to_entry = {
            getattr(entry, "source_index", None): index
            for index, entry in enumerate(self.model.entries)
            if getattr(entry, "source_index", None) is not None and not getattr(entry, "is_blank", False)
        }
        indexes = tuple(
            index
            for index in (source_to_entry.get(candidate.start_page), source_to_entry.get(candidate.end_page))
            if index is not None
        )
        if not indexes:
            status = getattr(self, "status", None)
            if status is not None:
                status.set(f"Candidate {candidate.pair_id} is missing from the current layout.")
            return
        self._syncing_spine_selection = True
        try:
            self._set_main_selection_range(indexes)
            self._set_diagnosis_selection_range(indexes)
        finally:
            self._syncing_spine_selection = False
        self.refresh_preview()
        self.refresh_diagnosis_preview()

    def _marker_text_for_entry(self, row_index: int) -> str:
        marker = getattr(self, "spine_markers", {}).get(row_index)
        if marker is None:
            return ""
        if marker.kind == "suggested":
            return f" [insert +{marker.score:.2f}]"
        return " [protected]"

    def _apply_spine_marker_color(self, row_index: int) -> None:
        self._apply_spine_marker_color_to_listbox(self.page_list, row_index)

    def _apply_spine_marker_color_to_listbox(self, listbox, row_index: int) -> None:
        marker = getattr(self, "spine_markers", {}).get(row_index)
        if marker is None:
            return
        color = "#0b6b2b" if marker.kind == "suggested" else "#9f1d20"
        try:
            listbox.itemconfig(row_index, foreground=color)
        except tk.TclError:
            pass

    def _refresh_spine_preserving_selection(self) -> None:
        if not hasattr(self, "page_list"):
            self.refresh_spine_views(preserve_yview=True)
            return
        selected = self.selected_index()
        self.refresh_spine_views(preserve_yview=True)
        if selected is not None and getattr(self, "model", None) is not None and self.model.entries:
            self.page_list.selection_set(min(selected, len(self.model.entries) - 1))

    def apply_diagnosis_settings(self, settings: DiagnosisSettings) -> None:
        self.diagnosis_settings = settings
        for panel in _diagnosis_panels(self):
            panel.set_settings(settings)
        self.status.set("Updated diagnosis settings.")


def build_diagnosis_tab(app, parent) -> None:
    if not hasattr(parent, "tk"):
        app.diagnosis_panel = None
        return
    app.diagnosis_panel = DiagnosisPanel(
        parent,
        diagnosis_callbacks(app),
        getattr(app, "diagnosis_settings", DiagnosisSettings()),
    )
    refresh_diagnosis_panel(app)


def build_diagnosis_entry_tab(app, parent) -> None:
    ttk.Button(parent, text="Open Diagnose Window", command=app.open_diagnose_window).pack(fill=tk.X, pady=(6, 0))


def diagnosis_callbacks(app) -> DiagnosisPanelCallbacks:
    return DiagnosisPanelCallbacks(
        run_spread_diagnosis=app.run_spread_diagnosis,
        sync_spine_selection_from_candidate=app.sync_spine_selection_from_candidate,
        mark_selected_spread_true=app.mark_selected_spread_true,
        mark_selected_spread_false=app.mark_selected_spread_false,
        add_selected_spread=app.add_selected_spread_from_diagnosis_spine,
        check_confirmed_spread_damage=app.check_confirmed_spread_damage,
        run_insert_point_scoring=app.run_insert_point_scoring,
        import_insert_scores=app.import_insert_scores,
        insert_selected_diagnosis_blank=app.insert_selected_diagnosis_blank,
        recheck_diagnosis_layout=app.recheck_diagnosis_layout,
        apply_settings=app.apply_diagnosis_settings,
        clear_diagnostics_output=app.clear_current_diagnostics_output,
    )


def _first_selection(listbox) -> int | None:
    selection = listbox.curselection()
    return selection[0] if selection else None


def _listbox_selection(listbox) -> tuple[int, ...]:
    return tuple(listbox.curselection())


def _restore_listbox_selection(listbox, selection: tuple[int, ...], entry_count: int) -> None:
    if not selection or entry_count <= 0:
        return
    for index in selection:
        listbox.selection_set(min(index, entry_count - 1))
