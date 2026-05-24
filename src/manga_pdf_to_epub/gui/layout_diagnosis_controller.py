from __future__ import annotations

from tkinter import messagebox

from .layout_diagnosis import (
    DiagnosisSession,
    InsertCandidate,
    SpreadCandidate,
    classify_insert_points,
    diagnose_spread_damage,
)
from .layout_diagnosis_panel_controller import refresh_diagnosis_panel
from .layout_diagnosis_runner import DiagnosisSettings


class EpubLayoutDiagnosisMixin:
    def _selected_spread_candidate_id(self) -> str | None:
        candidate = self._selected_spread_candidate()
        return candidate.pair_id if candidate is not None else None

    def _selected_spread_candidate(self) -> SpreadCandidate | None:
        panel = self._active_diagnosis_panel()
        if panel is None:
            return None
        selection = panel.candidate_list.curselection()
        if not selection:
            return None
        candidates = getattr(self, "diagnosis_session", None).spread_candidates()
        index = selection[0]
        return candidates[index].candidate if index < len(candidates) else None

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
        self.refresh_spine_views(preserve_yview=True)
        self.refresh_diagnosis_panel()
        self.status.set(f"Loaded {len(candidates)} spread candidates for review.")

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
        self.spine_markers = {
            item.marker_entry_index: item
            for item in [*self.insert_classification.protected, *self.insert_classification.suggestions]
        }
        self.diagnosis_stale = False
        self.refresh_spine_views(preserve_yview=True)
        self.refresh_diagnosis_panel()
        suggested_count = len(self.insert_classification.suggestions)
        protected_count = len(self.insert_classification.protected)
        self.status.set(
            f"Loaded {len(candidates)} insert scores: {suggested_count} suggested, {protected_count} protected."
        )

    def _mark_diagnosis_stale(self, refresh_spine: bool = False) -> None:
        self.diagnosis_stale = True
        self.insert_classification = None
        self.spine_markers = {}
        if refresh_spine:
            self._refresh_spine_preserving_selection()
        self.refresh_diagnosis_panel()

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
        self.refresh_spine_views(preserve_yview=True)
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

    def add_selected_spread_from_diagnosis_spine(self) -> None:
        window = getattr(self, "diagnosis_window", None)
        if window is None or getattr(self, "model", None) is None:
            self._reject_selected_spread()
            return
        selection = list(window.spine_list.curselection())
        if len(selection) != 2:
            self._reject_selected_spread()
            return
        first_index, second_index = sorted(selection)
        entries = self.model.entries
        if first_index < 0 or second_index >= len(entries) or second_index != first_index + 1:
            self._reject_selected_spread()
            return
        first = entries[first_index]
        second = entries[second_index]
        first_source = getattr(first, "source_index", None)
        second_source = getattr(second, "source_index", None)
        if getattr(first, "is_blank", False) or getattr(second, "is_blank", False):
            self._reject_selected_spread()
            return
        if first_source is None or second_source is None or second_source != first_source + 1:
            self._reject_selected_spread()
            return
        self._add_missing_spread_pair(first_source, second_source)

    def _reject_selected_spread(self) -> None:
        self.status.set("Select exactly two adjacent real pages.")

    def refresh_preview_after_diagnosis_layout_option_change(self) -> None:
        self._mark_diagnosis_stale(refresh_spine=True)
        self.refresh_preview_views()


def initialize_diagnosis_state(app, source_page_count: int = 0) -> None:
    app.diagnosis_session = DiagnosisSession(source_page_count)
    if not hasattr(app, "diagnosis_settings"):
        app.diagnosis_settings = DiagnosisSettings()
    app.spread_damage = []
    app.insert_candidates = []
    app.insert_classification = None
    app.diagnosis_stale = False
    app.diagnosis_panel = None
    app.diagnosis_window = None
    app.spine_markers = {}
    app._syncing_spine_selection = False


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
