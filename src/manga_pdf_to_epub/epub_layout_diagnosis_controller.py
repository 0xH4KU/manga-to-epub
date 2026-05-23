from __future__ import annotations

import tkinter as tk

from .epub_layout_diagnosis import DiagnosisSession
from .epub_layout_diagnosis_gui import DiagnosisPanel, DiagnosisPanelCallbacks, diagnosis_summary_texts


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
        run_spread_scan=lambda: _stub_status(app, "Spread scan will be wired in a later task."),
        import_spread_candidates=lambda: _stub_status(app, "Spread candidate import will be wired in a later task."),
        mark_true=lambda: _stub_status(app, "Spread review marking will be wired in a later task."),
        mark_false=lambda: _stub_status(app, "Spread review marking will be wired in a later task."),
        add_missing_spread=lambda: _stub_status(app, "Manual spread entry will be wired in a later task."),
        check_damage=lambda: _stub_status(app, "Damage checking will be wired in a later task."),
        run_insert_scores=lambda: _stub_status(app, "Insert-point scoring will be wired in a later task."),
        import_insert_scores=lambda: _stub_status(app, "Insert score import will be wired in a later task."),
        insert_selected=lambda: _stub_status(app, "Blank insertion from diagnosis will be wired in a later task."),
        recheck_layout=lambda: _stub_status(app, "Layout recheck will be wired in a later task."),
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
    _replace_list(panel.candidate_list, [])
    _replace_list(panel.damage_list, [])
    _replace_list(panel.insert_list, [])


def _replace_list(listbox, rows: list[str]) -> None:
    listbox.delete(0, tk.END)
    for row in rows:
        listbox.insert(tk.END, row)


def _stub_status(app, message: str) -> None:
    app.status.set(message)
