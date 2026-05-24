from __future__ import annotations

import tkinter as tk

from .layout_diagnosis_window import DiagnosisPanel, diagnosis_summary_texts


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
        _set_panel_rows(
            panel,
            "candidate",
            panel.candidate_list,
            [_candidate_row(item) for item in session.spread_candidates()],
        )
        _set_panel_rows(
            panel,
            "damage",
            panel.damage_list,
            [_damage_row(item) for item in getattr(app, "spread_damage", [])],
        )
        _set_panel_rows(panel, "insert", panel.insert_list, _insert_rows(getattr(app, "insert_classification", None)))


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


def _set_panel_rows(panel, name: str, listbox, rows: list[str]) -> None:
    setter = getattr(panel, f"set_{name}_rows", None)
    if setter is not None:
        setter(rows)
    elif listbox is not None:
        _replace_list_preserving_yview(listbox, rows)


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
