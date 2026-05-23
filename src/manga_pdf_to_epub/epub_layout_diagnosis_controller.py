from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .epub_layout_diagnosis import (
    DiagnosisSession,
    InsertCandidate,
    SpreadCandidate,
    classify_insert_points,
    diagnose_spread_damage,
    read_insert_candidates_csv,
    read_spread_candidates_csv,
)
from .epub_layout_diagnosis_gui import DiagnosisPanel, DiagnosisPanelCallbacks, DiagnosisWindow, diagnosis_summary_texts
from .epub_layout_diagnosis_runner import (
    default_diagnosis_output_dir,
    resolve_insert_score_command,
    resolve_spread_scan_command,
    run_diagnosis_command,
)


class EpubLayoutDiagnosisMixin:
    def refresh_diagnosis_panel(self) -> None:
        refresh_diagnosis_panel(self)

    def open_diagnose_window(self) -> None:
        if getattr(self, "model", None) is None:
            self.status.set("Open a PDF before opening Diagnose.")
            return
        existing = getattr(self, "diagnosis_window", None)
        if existing is not None:
            existing.focus()
            return
        self.diagnosis_window = DiagnosisWindow(self, self.root, diagnosis_callbacks(self))
        self.refresh_diagnosis_panel()

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

    def _selected_spread_candidate_id(self) -> str | None:
        panel = self._active_diagnosis_panel()
        if panel is None:
            return None
        selection = panel.candidate_list.curselection()
        if not selection:
            return None
        candidates = getattr(self, "diagnosis_session", None).spread_candidates()
        index = selection[0]
        return candidates[index].candidate.pair_id if index < len(candidates) else None

    def _selected_insert_suggestion(self):
        classification = getattr(self, "insert_classification", None)
        panel = self._active_diagnosis_panel()
        if classification is None or panel is None:
            return None
        selection = panel.insert_list.curselection()
        if not selection:
            return None
        index = selection[0]
        suggestions = classification.suggestions
        return suggestions[index] if index < len(suggestions) else None

    def _load_spread_candidates(self, candidates: list[SpreadCandidate]) -> None:
        self.diagnosis_session.load_spread_candidates(candidates)
        self.spread_damage = []
        self.insert_classification = None
        self.diagnosis_stale = False
        self.spine_markers = {}
        self.refresh_list(preserve_yview=True)
        self.refresh_diagnosis_panel()
        self.status.set(f"Loaded {len(candidates)} spread candidates for review.")

    def run_spread_diagnosis(self) -> None:
        if getattr(self, "model", None) is None or getattr(self, "pdf_path", None) is None:
            return
        project_root = Path(__file__).resolve().parents[2]
        output_dir = default_diagnosis_output_dir(project_root, self.pdf_path, "spread")
        command = resolve_spread_scan_command(project_root, self.pdf_path, output_dir)
        if command is None:
            messagebox.showerror(
                "Spread scan unavailable",
                "Could not find sibling manga-spread-continuity environment. Use Import Spread Candidates instead.",
            )
            return
        self._run_background(
            "Running cross-page scan. This can take a few minutes.",
            lambda: _run_spread_scan_work(command, self.diagnosis_session.source_page_count),
            self._spread_scan_done,
            on_failure=self._spread_scan_failed,
        )

    def _spread_scan_done(self, candidates: list[SpreadCandidate]) -> None:
        self._load_spread_candidates(candidates)

    def _spread_scan_failed(self, exc: Exception) -> None:
        self.status.set("Cross-page scan failed.")
        messagebox.showerror("Cross-page scan failed", str(exc))

    def _load_insert_candidates(self, candidates: list[InsertCandidate]) -> None:
        if getattr(self, "model", None) is None:
            return
        if not getattr(self, "spread_damage", []):
            self.status.set("Check confirmed spread damage before loading insert scores.")
            return
        if getattr(self, "diagnosis_session", None) is None:
            return
        self.insert_candidates = candidates
        self.insert_classification = classify_insert_points(
            self.model.entries,
            self.diagnosis_session.confirmed_spreads(),
            candidates,
            self.apple_preview.get(),
        )
        self.spine_markers = {}
        for item in self.insert_classification.protected:
            self.spine_markers[item.marker_entry_index] = item
        for item in self.insert_classification.suggestions:
            self.spine_markers[item.marker_entry_index] = item
        self.diagnosis_stale = False
        self.refresh_list(preserve_yview=True)
        self.refresh_diagnosis_panel()
        suggested_count = len(self.insert_classification.suggestions)
        protected_count = len(self.insert_classification.protected)
        self.status.set(
            f"Loaded {len(candidates)} insert scores: {suggested_count} suggested, {protected_count} protected."
        )

    def _marker_text_for_entry(self, row_index: int) -> str:
        marker = getattr(self, "spine_markers", {}).get(row_index)
        if marker is None:
            return ""
        if marker.kind == "suggested":
            return f" [insert +{marker.score:.2f}]"
        return " [protected]"

    def _apply_spine_marker_color(self, row_index: int) -> None:
        marker = getattr(self, "spine_markers", {}).get(row_index)
        if marker is None:
            return
        color = "#0b6b2b" if marker.kind == "suggested" else "#9f1d20"
        try:
            self.page_list.itemconfig(row_index, foreground=color)
        except tk.TclError:
            pass

    def _mark_diagnosis_stale(self, refresh_spine: bool = False) -> None:
        self.diagnosis_stale = True
        self.insert_classification = None
        self.spine_markers = {}
        if refresh_spine:
            self._refresh_spine_preserving_selection()
        self.refresh_diagnosis_panel()

    def _refresh_spine_preserving_selection(self) -> None:
        if not hasattr(self, "page_list"):
            self.refresh_list(preserve_yview=True)
            return
        selected = self.selected_index()
        self.refresh_list(preserve_yview=True)
        if selected is not None and getattr(self, "model", None) is not None and self.model.entries:
            self.page_list.selection_set(min(selected, len(self.model.entries) - 1))

    def import_insert_scores(self) -> None:
        path = filedialog.askopenfilename(
            title="Import insert scores",
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            self._load_insert_candidates(read_insert_candidates_csv(Path(path)))
        except ValueError as exc:
            messagebox.showerror("Import Insert Scores", str(exc))

    def run_insert_point_scoring(self) -> None:
        if getattr(self, "model", None) is None or getattr(self, "pdf_path", None) is None:
            return
        project_root = Path(__file__).resolve().parents[2]
        output_dir = default_diagnosis_output_dir(project_root, self.pdf_path, "insert")
        command = resolve_insert_score_command(project_root, self.pdf_path, output_dir)
        if command is None:
            messagebox.showerror(
                "Insert scoring unavailable",
                "Could not find sibling manga-insert-point-scorer environment. Use Import Insert Scores instead.",
            )
            return
        self._run_background(
            "Running insert-point scoring. This can take a few minutes.",
            lambda: _run_insert_scoring_work(command),
            self._insert_scoring_done,
            on_failure=self._insert_scoring_failed,
        )

    def _insert_scoring_done(self, candidates: list[InsertCandidate]) -> None:
        self._load_insert_candidates(candidates)

    def _insert_scoring_failed(self, exc: Exception) -> None:
        self.status.set("Insert-point scoring failed.")
        messagebox.showerror("Insert-point scoring failed", str(exc))

    def insert_selected_diagnosis_blank(self) -> None:
        suggestion = self._selected_insert_suggestion()
        if suggestion is None:
            self.status.set("Select an insert suggestion first.")
            return
        try:
            self.model.insert_blank(suggestion.insertion_index)
            self.spread_damage = []
            self.insert_classification = None
            self.spine_markers = {}
            self.diagnosis_stale = True
            self._refresh_after_layout_edit(select_index=suggestion.insertion_index)
            self.refresh_diagnosis_panel()
            self.status.set(
                f"Inserted blank for suggested gap {suggestion.gap_id}. Click Recheck Layout before continuing."
            )
        except Exception as exc:
            messagebox.showerror("Diagnosis insert failed", str(exc))

    def check_confirmed_spread_damage(self) -> None:
        if getattr(self, "model", None) is None or getattr(self, "diagnosis_session", None) is None:
            return
        confirmed = self.diagnosis_session.confirmed_spreads()
        if not confirmed:
            self.status.set("Mark at least one true spread before checking damage.")
            return
        self.spread_damage = diagnose_spread_damage(self.model.entries, confirmed, self.apple_preview.get())
        self.insert_classification = None
        self.spine_markers = {}
        self.diagnosis_stale = False
        self.refresh_list(preserve_yview=True)
        self.refresh_diagnosis_panel()
        damaged_count = sum(1 for item in self.spread_damage if item.status == "damaged")
        missing_count = sum(1 for item in self.spread_damage if item.status == "missing")
        self.status.set(
            f"Checked {len(confirmed)} confirmed spreads: {damaged_count} damaged, {missing_count} missing."
        )

    def recheck_diagnosis_layout(self) -> None:
        self.check_confirmed_spread_damage()

    def mark_selected_spread_true(self) -> None:
        self._mark_selected_spread("true", "true spread")

    def mark_selected_spread_false(self) -> None:
        self._mark_selected_spread("false", "false positive")

    def _mark_selected_spread(self, status: str, status_label: str) -> None:
        pair_id = self._selected_spread_candidate_id()
        if pair_id is None:
            self.status.set("Select a spread candidate first.")
            return
        self.diagnosis_session.mark_candidate(pair_id, status)
        self._mark_diagnosis_stale(refresh_spine=True)
        self.status.set(f"Marked {pair_id} as {status_label}.")

    def _add_missing_spread_pair(self, start_page: int, end_page: int) -> None:
        candidate = self.diagnosis_session.add_manual_spread(start_page, end_page)
        self._mark_diagnosis_stale(refresh_spine=True)
        self.status.set(f"Added confirmed spread {candidate.pair_id}.")

    def refresh_preview_after_diagnosis_layout_option_change(self) -> None:
        self._mark_diagnosis_stale(refresh_spine=True)
        self.refresh_preview()

    def import_spread_candidates(self) -> None:
        path = filedialog.askopenfilename(
            title="Import spread candidates",
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            self._load_spread_candidates(read_spread_candidates_csv(Path(path)))
        except ValueError as exc:
            messagebox.showerror("Import Spread Candidates", str(exc))

    def add_missing_spread(self) -> None:
        start_page = simpledialog.askinteger("Add Missing Spread", "Start source page:")
        if start_page is None:
            return
        end_page = simpledialog.askinteger("Add Missing Spread", "End source page:")
        if end_page is None:
            return
        try:
            self._add_missing_spread_pair(start_page, end_page)
        except ValueError as exc:
            messagebox.showerror("Add Missing Spread", str(exc))


def initialize_diagnosis_state(app, source_page_count: int = 0) -> None:
    app.diagnosis_session = DiagnosisSession(source_page_count)
    app.spread_damage = []
    app.insert_candidates = []
    app.insert_classification = None
    app.diagnosis_stale = False
    app.diagnosis_panel = None
    app.diagnosis_window = None
    app.spine_markers = {}


def reset_diagnosis_for_model(app, model) -> None:
    source_page_count = getattr(model, "source_page_count", None)
    if source_page_count is None:
        source_page_count = len(getattr(model, "entries", []))
    existing_panel = getattr(app, "diagnosis_panel", None)
    existing_window = getattr(app, "diagnosis_window", None)
    initialize_diagnosis_state(app, source_page_count)
    app.diagnosis_panel = existing_panel
    app.diagnosis_window = existing_window
    refresh_diagnosis_panel(app)


def build_diagnosis_tab(app, parent) -> None:
    if not hasattr(parent, "tk"):
        app.diagnosis_panel = None
        return
    app.diagnosis_panel = DiagnosisPanel(parent, diagnosis_callbacks(app))
    refresh_diagnosis_panel(app)


def build_diagnosis_entry_tab(app, parent) -> None:
    ttk.Button(parent, text="Open Diagnose Window", command=app.open_diagnose_window).pack(fill=tk.X, pady=(6, 0))


def diagnosis_callbacks(app) -> DiagnosisPanelCallbacks:
    return DiagnosisPanelCallbacks(
        run_spread_diagnosis=app.run_spread_diagnosis,
        import_spread_candidates=app.import_spread_candidates,
        mark_selected_spread_true=app.mark_selected_spread_true,
        mark_selected_spread_false=app.mark_selected_spread_false,
        add_missing_spread=app.add_missing_spread,
        check_confirmed_spread_damage=app.check_confirmed_spread_damage,
        run_insert_point_scoring=app.run_insert_point_scoring,
        import_insert_scores=app.import_insert_scores,
        insert_selected_diagnosis_blank=app.insert_selected_diagnosis_blank,
        recheck_diagnosis_layout=app.recheck_diagnosis_layout,
    )


def refresh_diagnosis_panel(app) -> None:
    panels = _diagnosis_panels(app)
    session = getattr(app, "diagnosis_session", None)
    if not panels or session is None:
        return
    summary = diagnosis_summary_texts(
        session,
        getattr(app, "spread_damage", []),
        getattr(app, "insert_classification", None),
        getattr(app, "diagnosis_stale", False),
    )
    for panel in panels:
        panel.summary_var.set(summary.candidates)
        panel.damage_var.set(summary.damage)
        panel.insert_var.set(summary.insert_points)
        panel.stale_var.set(summary.staleness)
        _replace_list_preserving_yview(panel.candidate_list, [_candidate_row(item) for item in session.spread_candidates()])
        _replace_list_preserving_yview(panel.damage_list, [_damage_row(item) for item in getattr(app, "spread_damage", [])])
        _replace_list_preserving_yview(panel.insert_list, _insert_rows(getattr(app, "insert_classification", None)))


def _diagnosis_panels(app) -> list[DiagnosisPanel]:
    panels = []
    inspector_panel = getattr(app, "diagnosis_panel", None)
    if inspector_panel is not None:
        panels.append(inspector_panel)
    window = getattr(app, "diagnosis_window", None)
    window_panel = getattr(window, "panel", None) if window is not None else None
    if window_panel is not None and window_panel is not inspector_panel:
        panels.append(window_panel)
    return panels


def _replace_list_preserving_yview(listbox, rows: list[str]) -> None:
    yview_start = listbox.yview()[0]
    listbox.delete(0, tk.END)
    for row in rows:
        listbox.insert(tk.END, row)
    listbox.yview_moveto(yview_start)


def _candidate_row(item) -> str:
    candidate = item.candidate
    return (
        f"{candidate.pair_id} [{item.status}] "
        f"score {candidate.score:.3f} review {candidate.review_score:.3f} {candidate.decision}"
    )


def _damage_row(item) -> str:
    return f"{item.pair_id} [{item.status}] {item.reason}"


def _insert_rows(classification) -> list[str]:
    if classification is None:
        return []
    rows = [
        f"{item.gap_id} [suggested] score {item.score:.3f} {item.reason}"
        for item in classification.suggestions
    ]
    rows.extend(
        f"{item.gap_id} [protected] score {item.score:.3f} {item.reason}"
        for item in classification.protected
    )
    rows.extend(f"{gap_id} [stale]" for gap_id in classification.stale_gap_ids)
    return rows


def _stub_status(app, message: str) -> None:
    app.status.set(message)


def _run_spread_scan_work(command, source_page_count: int = 0) -> list[SpreadCandidate]:
    result = run_diagnosis_command(command)
    candidates = read_spread_candidates_csv(result.output_dir / "adjacent_clusters.csv")
    DiagnosisSession(source_page_count).load_spread_candidates(candidates)
    return candidates


def _run_insert_scoring_work(command) -> list[InsertCandidate]:
    result = run_diagnosis_command(command)
    return read_insert_candidates_csv(result.output_dir / "gaps.csv")
