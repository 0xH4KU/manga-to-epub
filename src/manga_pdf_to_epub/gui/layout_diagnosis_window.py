from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk
from typing import Callable

from .layout_diagnosis import DiagnosisSession, InsertClassification, SpreadDamage
from .layout_diagnosis_runner import DiagnosisSettings


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
    sync_spine_selection_from_candidate: Callable[[], None]
    mark_selected_spread_true: Callable[[], None]
    mark_selected_spread_false: Callable[[], None]
    add_selected_spread: Callable[[], None]
    check_confirmed_spread_damage: Callable[[], None]
    run_insert_point_scoring: Callable[[], None]
    import_insert_scores: Callable[[], None]
    insert_selected_diagnosis_blank: Callable[[], None]
    recheck_diagnosis_layout: Callable[[], None]
    apply_settings: Callable[[DiagnosisSettings], None]
    clear_diagnostics_output: Callable[[], None]


class DiagnosisPanel:
    WORKFLOW_TABS = ("Candidates", "Damage", "Insert Points", "Settings")

    def __init__(
        self,
        parent: ttk.Frame,
        callbacks: DiagnosisPanelCallbacks,
        settings: DiagnosisSettings | None = None,
    ):
        self.callbacks = callbacks
        self.settings = settings or DiagnosisSettings()
        self.summary_var = tk.StringVar(
            master=parent,
            value="Run scan, then review or add spreads from Spine order.",
        )
        self.damage_var = tk.StringVar(master=parent, value="")
        self.insert_var = tk.StringVar(master=parent, value="")
        self.stale_var = tk.StringVar(master=parent, value="")
        self.candidate_list = None
        self.damage_list = None
        self.insert_list = None
        self._candidate_rows: list[str] = []
        self._damage_rows: list[str] = []
        self._insert_rows: list[str] = []
        self.workers_var = tk.StringVar(master=parent, value=str(self.settings.spread_workers))
        self.threshold_var = tk.StringVar(master=parent, value=str(self.settings.spread_threshold))
        self.debug_limit_var = tk.StringVar(master=parent, value=str(self.settings.spread_debug_limit))
        self.max_height_var = tk.StringVar(master=parent, value=str(self.settings.spread_max_height))
        self.insert_thumb_height_var = tk.StringVar(master=parent, value=str(self.settings.insert_thumb_height))
        self.workflow_tabs: dict[str, ttk.Frame] = {}
        self.workflow_tab_buttons: dict[str, ttk.Button] = {}
        self.active_workflow_tab = "Candidates"
        self._build(parent)

    def _build(self, parent: ttk.Frame) -> None:
        tabbar = ttk.Frame(parent)
        tabbar.pack(fill=tk.X)
        for title in self.WORKFLOW_TABS:
            button = ttk.Button(tabbar, text=title, command=lambda tab=title: self._show_workflow_tab(tab))
            button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)
            self.workflow_tab_buttons[title] = button

        content = ttk.Frame(parent)
        content.pack(fill=tk.BOTH, expand=True)
        tab_builders = {
            "Candidates": self._build_candidates_tab,
            "Damage": self._build_damage_tab,
            "Insert Points": self._build_insert_tab,
            "Settings": self._build_settings_tab,
        }
        self._workflow_tab_builders = tab_builders
        for title in self.WORKFLOW_TABS:
            tab = ttk.Frame(content, padding=(12, 12))
            self.workflow_tabs[title] = tab
        self._build_workflow_tab("Candidates")
        self._show_workflow_tab("Candidates")

    def _show_workflow_tab(self, title: str) -> None:
        if title not in self.workflow_tabs:
            return
        self._build_workflow_tab(title)
        self.active_workflow_tab = title
        for tab_title, tab in self.workflow_tabs.items():
            if tab_title == title:
                tab.pack(fill=tk.BOTH, expand=True)
            else:
                tab.pack_forget()
        for tab_title, button in self.workflow_tab_buttons.items():
            state = tk.DISABLED if tab_title == title else tk.NORMAL
            try:
                button.configure(state=state)
            except tk.TclError:
                pass

    def _build_workflow_tab(self, title: str) -> None:
        tab = self.workflow_tabs[title]
        if getattr(tab, "_diagnosis_built", False):
            return
        self._workflow_tab_builders[title](tab)
        setattr(tab, "_diagnosis_built", True)

    def _build_candidates_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Spread Candidates").pack(anchor=tk.W)
        ttk.Label(parent, textvariable=self.summary_var).pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(
            parent,
            text="Run Cross-Page Scan",
            command=self.callbacks.run_spread_diagnosis,
        ).pack(fill=tk.X, pady=(6, 0))
        self.candidate_list = tk.Listbox(parent, exportselection=False, height=16)
        self.candidate_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.candidate_list.bind(
            "<<ListboxSelect>>",
            lambda _event: self.callbacks.sync_spine_selection_from_candidate(),
        )
        self._replace_list_rows(self.candidate_list, self._candidate_rows)
        ttk.Button(
            parent,
            text="Mark Selected True",
            command=self.callbacks.mark_selected_spread_true,
        ).pack(fill=tk.X, pady=(6, 0))
        ttk.Button(
            parent,
            text="Mark Selected False",
            command=self.callbacks.mark_selected_spread_false,
        ).pack(fill=tk.X, pady=(6, 0))
        ttk.Button(parent, text="Add Selected As Spread", command=self.callbacks.add_selected_spread).pack(
            fill=tk.X,
            pady=(6, 0),
        )

    def _build_damage_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Damage Check").pack(anchor=tk.W)
        ttk.Label(parent, textvariable=self.damage_var).pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(
            parent,
            text="Check Damage Against Current Layout",
            command=self.callbacks.check_confirmed_spread_damage,
        ).pack(
            fill=tk.X,
            pady=(6, 0),
        )
        self.damage_list = tk.Listbox(parent, exportselection=False, height=6)
        self.damage_list.pack(fill=tk.X, pady=(6, 0))
        self._replace_list_rows(self.damage_list, self._damage_rows)

    def _build_insert_tab(self, parent: ttk.Frame) -> None:
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
        self.insert_list = tk.Listbox(parent, exportselection=False, height=6)
        self.insert_list.pack(fill=tk.X, pady=(6, 0))
        self._replace_list_rows(self.insert_list, self._insert_rows)
        ttk.Button(parent, text="Insert Selected Blank", command=self.callbacks.insert_selected_diagnosis_blank).pack(
            fill=tk.X,
            pady=(6, 0),
        )
        ttk.Button(
            parent,
            text="Recheck Layout",
            command=self.callbacks.recheck_diagnosis_layout,
        ).pack(fill=tk.X, pady=(6, 0))

    def _build_settings_tab(self, parent: ttk.Frame) -> None:
        fields = (
            ("Spread scan workers", self.workers_var),
            ("Spread threshold", self.threshold_var),
            ("Debug image limit", self.debug_limit_var),
            ("Spread render max height", self.max_height_var),
            ("Insert thumbnail height", self.insert_thumb_height_var),
        )
        for label, variable in fields:
            ttk.Label(parent, text=label).pack(anchor=tk.W, pady=(8, 0))
            ttk.Entry(parent, textvariable=variable).pack(fill=tk.X)
        ttk.Button(parent, text="Apply Settings", command=self.apply_settings).pack(fill=tk.X, pady=(14, 0))
        ttk.Button(
            parent,
            text="Clear Current Diagnostics Output",
            command=self.callbacks.clear_diagnostics_output,
        ).pack(fill=tk.X, pady=(6, 0))

    def apply_settings(self) -> None:
        try:
            spread_workers = int(self.workers_var.get())
            spread_threshold = float(self.threshold_var.get())
            spread_debug_limit = int(self.debug_limit_var.get())
            spread_max_height = int(self.max_height_var.get())
            insert_thumb_height = int(self.insert_thumb_height_var.get())
        except ValueError:
            messagebox.showerror("Diagnosis Settings", "Diagnosis settings must use numeric values.")
            return
        try:
            settings = DiagnosisSettings(
                spread_workers=spread_workers,
                spread_threshold=spread_threshold,
                spread_debug_limit=spread_debug_limit,
                spread_max_height=spread_max_height,
                insert_thumb_height=insert_thumb_height,
            )
        except ValueError as exc:
            messagebox.showerror("Diagnosis Settings", str(exc))
            return
        self.callbacks.apply_settings(settings)

    def set_settings(self, settings: DiagnosisSettings) -> None:
        self.settings = settings
        self.workers_var.set(str(settings.spread_workers))
        self.threshold_var.set(str(settings.spread_threshold))
        self.debug_limit_var.set(str(settings.spread_debug_limit))
        self.max_height_var.set(str(settings.spread_max_height))
        self.insert_thumb_height_var.set(str(settings.insert_thumb_height))

    def set_candidate_rows(self, rows: list[str]) -> None:
        self._candidate_rows = rows
        if self.candidate_list is not None:
            self._replace_list_rows(self.candidate_list, rows)

    def set_damage_rows(self, rows: list[str]) -> None:
        self._damage_rows = rows
        if self.damage_list is not None:
            self._replace_list_rows(self.damage_list, rows)

    def set_insert_rows(self, rows: list[str]) -> None:
        self._insert_rows = rows
        if self.insert_list is not None:
            self._replace_list_rows(self.insert_list, rows)

    @staticmethod
    def _replace_list_rows(listbox, rows: list[str]) -> None:
        try:
            yview_start = listbox.yview()[0]
        except tk.TclError:
            yview_start = 0.0
        listbox.delete(0, tk.END)
        for row in rows:
            listbox.insert(tk.END, row)
        listbox.yview_moveto(yview_start)


class DiagnosisWindow:
    def __init__(
        self,
        app,
        parent,
        callbacks: DiagnosisPanelCallbacks,
        settings: DiagnosisSettings | None = None,
    ):
        self.app = app
        self.settings = settings or DiagnosisSettings()
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
        self.spine_list.bind(
            "<<ListboxSelect>>",
            lambda _event: self._invoke_app_callback("sync_selection_from_diagnosis"),
        )
        ttk.Label(self.center, text="RTL spread preview").pack(anchor=tk.W)
        self.preview = tk.Canvas(self.center, background="#202020", highlightthickness=0)
        self.preview.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.preview.bind("<Configure>", lambda _event: self._invoke_app_callback("refresh_diagnosis_preview"))
        self.panel = DiagnosisPanel(self.right, callbacks, self.settings)

    def _invoke_app_callback(self, name: str) -> None:
        callback = getattr(self.app, name, None)
        if callback is not None:
            callback()

    def focus(self) -> None:
        self.window.lift()
        self.window.focus_force()

    def destroy(self) -> None:
        self.window.destroy()
