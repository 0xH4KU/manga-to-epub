from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from .epub_layout_diagnosis import (
    DiagnosisSession,
    SpreadCandidate,
    read_spread_candidates_csv,
)
from .epub_layout_diagnosis_gui import DiagnosisPanel, DiagnosisPanelCallbacks, diagnosis_summary_texts


class EpubLayoutDiagnosisMixin:
    def refresh_diagnosis_panel(self) -> None:
        refresh_diagnosis_panel(self)

    def _selected_spread_candidate_id(self) -> str | None:
        panel = getattr(self, "diagnosis_panel", None)
        if panel is None:
            return None
        selection = panel.candidate_list.curselection()
        if not selection:
            return None
        candidates = getattr(self, "diagnosis_session", None).spread_candidates()
        index = selection[0]
        return candidates[index].candidate.pair_id if index < len(candidates) else None

    def _load_spread_candidates(self, candidates: list[SpreadCandidate]) -> None:
        self.diagnosis_session.load_spread_candidates(candidates)
        self.spread_damage = []
        self.insert_classification = None
        self.diagnosis_stale = False
        self.spine_markers = {}
        self.refresh_list(preserve_yview=True)
        self.refresh_diagnosis_panel()
        self.status.set(f"Loaded {len(candidates)} spread candidates for review.")

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
        self.diagnosis_stale = True
        self.refresh_diagnosis_panel()
        self.status.set(f"Marked {pair_id} as {status_label}.")

    def _add_missing_spread_pair(self, start_page: int, end_page: int) -> None:
        candidate = self.diagnosis_session.add_manual_spread(start_page, end_page)
        self.diagnosis_stale = True
        self.refresh_diagnosis_panel()
        self.status.set(f"Added confirmed spread {candidate.pair_id}.")

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
    app.spine_markers = {}


def reset_diagnosis_for_model(app, model) -> None:
    source_page_count = getattr(model, "source_page_count", None)
    if source_page_count is None:
        source_page_count = len(getattr(model, "entries", []))
    existing_panel = getattr(app, "diagnosis_panel", None)
    initialize_diagnosis_state(app, source_page_count)
    app.diagnosis_panel = existing_panel
    refresh_diagnosis_panel(app)


def build_diagnosis_tab(app, parent) -> None:
    if not hasattr(parent, "tk"):
        app.diagnosis_panel = None
        return
    app.diagnosis_panel = DiagnosisPanel(parent, diagnosis_callbacks(app))
    refresh_diagnosis_panel(app)


def diagnosis_callbacks(app) -> DiagnosisPanelCallbacks:
    return DiagnosisPanelCallbacks(
        run_spread_diagnosis=lambda: _stub_status(app, "Spread scan will be wired in a later task."),
        import_spread_candidates=app.import_spread_candidates,
        mark_selected_spread_true=app.mark_selected_spread_true,
        mark_selected_spread_false=app.mark_selected_spread_false,
        add_missing_spread=app.add_missing_spread,
        check_confirmed_spread_damage=lambda: _stub_status(app, "Damage checking will be wired in a later task."),
        run_insert_point_scoring=lambda: _stub_status(app, "Insert-point scoring will be wired in a later task."),
        import_insert_scores=lambda: _stub_status(app, "Insert score import will be wired in a later task."),
        insert_selected_diagnosis_blank=lambda: _stub_status(app, "Blank insertion from diagnosis will be wired in a later task."),
        recheck_diagnosis_layout=lambda: _stub_status(app, "Layout recheck will be wired in a later task."),
    )


def refresh_diagnosis_panel(app) -> None:
    panel = getattr(app, "diagnosis_panel", None)
    session = getattr(app, "diagnosis_session", None)
    if panel is None or session is None:
        return
    summary = diagnosis_summary_texts(
        session,
        getattr(app, "spread_damage", []),
        getattr(app, "insert_classification", None),
        getattr(app, "diagnosis_stale", False),
    )
    panel.summary_var.set(summary.candidates)
    panel.damage_var.set(summary.damage)
    panel.insert_var.set(summary.insert_points)
    panel.stale_var.set(summary.staleness)
    _replace_list_preserving_yview(panel.candidate_list, [_candidate_row(item) for item in session.spread_candidates()])
    _replace_list_preserving_yview(panel.damage_list, [_damage_row(item) for item in getattr(app, "spread_damage", [])])
    _replace_list_preserving_yview(panel.insert_list, _insert_rows(getattr(app, "insert_classification", None)))


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
