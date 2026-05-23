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
    run_spread_diagnosis: Callable[[], None]
    import_spread_candidates: Callable[[], None]
    mark_selected_spread_true: Callable[[], None]
    mark_selected_spread_false: Callable[[], None]
    add_selected_spread: Callable[[], None]
    check_confirmed_spread_damage: Callable[[], None]
    run_insert_point_scoring: Callable[[], None]
    import_insert_scores: Callable[[], None]
    insert_selected_diagnosis_blank: Callable[[], None]
    recheck_diagnosis_layout: Callable[[], None]


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
        ttk.Button(parent, text="Run Cross-Page Scan", command=self.callbacks.run_spread_diagnosis).pack(fill=tk.X, pady=(6, 0))
        ttk.Button(parent, text="Import Spread Candidates...", command=self.callbacks.import_spread_candidates).pack(
            fill=tk.X,
            pady=(6, 0),
        )
        self.candidate_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        ttk.Button(parent, text="Mark Selected True", command=self.callbacks.mark_selected_spread_true).pack(fill=tk.X, pady=(6, 0))
        ttk.Button(parent, text="Mark Selected False", command=self.callbacks.mark_selected_spread_false).pack(fill=tk.X, pady=(6, 0))
        ttk.Button(parent, text="Add Selected As Spread", command=self.callbacks.add_selected_spread).pack(
            fill=tk.X,
            pady=(6, 0),
        )
        ttk.Separator(parent).pack(fill=tk.X, pady=14)
        ttk.Label(parent, text="Damage Check").pack(anchor=tk.W)
        ttk.Label(parent, textvariable=self.damage_var).pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(parent, text="Check Damage Against Current Layout", command=self.callbacks.check_confirmed_spread_damage).pack(
            fill=tk.X,
            pady=(6, 0),
        )
        self.damage_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        ttk.Separator(parent).pack(fill=tk.X, pady=14)
        ttk.Label(parent, text="Insert Points").pack(anchor=tk.W)
        ttk.Label(parent, textvariable=self.insert_var).pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(parent, textvariable=self.stale_var).pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(parent, text="Run Insert-Point Scoring", command=self.callbacks.run_insert_point_scoring).pack(
            fill=tk.X,
            pady=(6, 0),
        )
        ttk.Button(parent, text="Import Insert Scores...", command=self.callbacks.import_insert_scores).pack(
            fill=tk.X,
            pady=(6, 0),
        )
        self.insert_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        ttk.Button(parent, text="Insert Selected Blank", command=self.callbacks.insert_selected_diagnosis_blank).pack(
            fill=tk.X,
            pady=(6, 0),
        )
        ttk.Button(parent, text="Recheck Layout", command=self.callbacks.recheck_diagnosis_layout).pack(fill=tk.X, pady=(6, 0))


class DiagnosisWindow:
    def __init__(self, app, parent, callbacks: DiagnosisPanelCallbacks):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("Diagnose Spreads")
        self.window.geometry("1180x760")
        self.window.minsize(980, 620)
        self.window.protocol("WM_DELETE_WINDOW", lambda: app._diagnose_window_closed(self))
        self.photo_refs = []
        self.spine_list = None
        self.preview = None
        self.panel = None
        self._build(callbacks)

    def _build(self, callbacks: DiagnosisPanelCallbacks) -> None:
        main = ttk.Panedwindow(self.window, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)
        self.left = ttk.Frame(main, padding=8)
        self.center = ttk.Frame(main, padding=8)
        self.right = ttk.Frame(main, padding=8)
        main.add(self.left, weight=1)
        main.add(self.center, weight=3)
        main.add(self.right, weight=1)
        ttk.Label(self.left, text="Spine order").pack(anchor=tk.W)
        self.spine_list = tk.Listbox(self.left, exportselection=False, activestyle="dotbox", selectmode=tk.EXTENDED)
        self.spine_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.spine_list.bind("<<ListboxSelect>>", lambda _event: self._invoke_app_callback("sync_selection_from_diagnosis"))
        ttk.Label(self.center, text="RTL spread preview").pack(anchor=tk.W)
        self.preview = tk.Canvas(self.center, background="#202020", highlightthickness=0)
        self.preview.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.preview.bind("<Configure>", lambda _event: self._invoke_app_callback("refresh_diagnosis_preview"))
        self.panel = DiagnosisPanel(self.right, callbacks)

    def _invoke_app_callback(self, name: str) -> None:
        callback = getattr(self.app, name, None)
        if callback is not None:
            callback()

    def focus(self) -> None:
        self.window.lift()
        self.window.focus_force()

    def destroy(self) -> None:
        self.window.destroy()
