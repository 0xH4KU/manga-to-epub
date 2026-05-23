from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Callable

from .epub_layout_diagnosis import DiagnosisSession, InsertClassification, SpreadDamage


@dataclass(frozen=True)
class DiagnosisSummaryTexts:
    candidates: str
    damage: str
    insert_points: str
    staleness: str


def diagnosis_summary_texts(
    session: DiagnosisSession,
    damage: list[SpreadDamage],
    insert_result: InsertClassification | None,
    stale: bool,
) -> DiagnosisSummaryTexts:
    candidates = session.spread_candidates()
    true_count = sum(1 for item in candidates if item.status == "true")
    false_count = sum(1 for item in candidates if item.status == "false")
    pending_count = sum(1 for item in candidates if item.status == "pending")
    damaged = sum(1 for item in damage if item.status == "damaged")
    intact = sum(1 for item in damage if item.status == "intact")
    missing = sum(1 for item in damage if item.status == "missing")
    suggested = len(insert_result.suggestions) if insert_result is not None else 0
    protected = len(insert_result.protected) if insert_result is not None else 0
    stale_gaps = len(insert_result.stale_gap_ids) if insert_result is not None else 0
    return DiagnosisSummaryTexts(
        f"Candidates: {len(candidates)} total, {true_count} true, {false_count} false, {pending_count} pending.",
        f"Damage: {damaged} damaged, {intact} intact, {missing} missing.",
        f"Insert points: {suggested} suggested, {protected} protected, {stale_gaps} stale.",
        "Results are stale. Click Recheck Layout before using suggestions." if stale else "",
    )


@dataclass(frozen=True)
class DiagnosisPanelCallbacks:
    run_spread_scan: Callable[[], None]
    import_spread_candidates: Callable[[], None]
    mark_true: Callable[[], None]
    mark_false: Callable[[], None]
    add_missing_spread: Callable[[], None]
    check_damage: Callable[[], None]
    run_insert_scores: Callable[[], None]
    import_insert_scores: Callable[[], None]
    insert_selected: Callable[[], None]
    recheck_layout: Callable[[], None]


class DiagnosisPanel:
    def __init__(self, parent: ttk.Frame, callbacks: DiagnosisPanelCallbacks):
        self.callbacks = callbacks
        self.summary_var = tk.StringVar(master=parent, value="Run or import spread candidates to begin.")
        self.damage_var = tk.StringVar(master=parent, value="")
        self.insert_var = tk.StringVar(master=parent, value="")
        self.stale_var = tk.StringVar(master=parent, value="")
        self.candidate_list = tk.Listbox(parent, exportselection=False, height=8)
        self.damage_list = tk.Listbox(parent, exportselection=False, height=6)
        self.insert_list = tk.Listbox(parent, exportselection=False, height=6)
        self._build(parent)

    def _build(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Spread Candidates").pack(anchor=tk.W)
        ttk.Label(parent, textvariable=self.summary_var).pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(parent, text="Run Cross-Page Scan", command=self.callbacks.run_spread_scan).pack(fill=tk.X, pady=(6, 0))
        ttk.Button(parent, text="Import Spread Candidates...", command=self.callbacks.import_spread_candidates).pack(
            fill=tk.X,
            pady=(6, 0),
        )
        self.candidate_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        ttk.Button(parent, text="Mark Selected True", command=self.callbacks.mark_true).pack(fill=tk.X, pady=(6, 0))
        ttk.Button(parent, text="Mark Selected False", command=self.callbacks.mark_false).pack(fill=tk.X, pady=(6, 0))
        ttk.Button(parent, text="Add Missing Spread...", command=self.callbacks.add_missing_spread).pack(
            fill=tk.X,
            pady=(6, 0),
        )
        ttk.Separator(parent).pack(fill=tk.X, pady=14)
        ttk.Label(parent, text="Damage Check").pack(anchor=tk.W)
        ttk.Label(parent, textvariable=self.damage_var).pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(parent, text="Check Damage Against Current Layout", command=self.callbacks.check_damage).pack(
            fill=tk.X,
            pady=(6, 0),
        )
        self.damage_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        ttk.Separator(parent).pack(fill=tk.X, pady=14)
        ttk.Label(parent, text="Insert Points").pack(anchor=tk.W)
        ttk.Label(parent, textvariable=self.insert_var).pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(parent, textvariable=self.stale_var).pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(parent, text="Run Insert-Point Scoring", command=self.callbacks.run_insert_scores).pack(
            fill=tk.X,
            pady=(6, 0),
        )
        ttk.Button(parent, text="Import Insert Scores...", command=self.callbacks.import_insert_scores).pack(
            fill=tk.X,
            pady=(6, 0),
        )
        self.insert_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        ttk.Button(parent, text="Insert Selected Blank", command=self.callbacks.insert_selected).pack(
            fill=tk.X,
            pady=(6, 0),
        )
        ttk.Button(parent, text="Recheck Layout", command=self.callbacks.recheck_layout).pack(fill=tk.X, pady=(6, 0))
