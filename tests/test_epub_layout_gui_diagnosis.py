import unittest
import tempfile
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from manga_pdf_to_epub.gui.layout_diagnosis import (
    DiagnosisSession,
    InsertCandidate,
    SpreadCandidate,
    classify_insert_points,
    diagnose_spread_damage,
)
from manga_pdf_to_epub.gui.layout_diagnosis_runner import DiagnosisSettings
from manga_pdf_to_epub.gui.layout_app import EpubLayoutApp
from manga_pdf_to_epub.gui.layout_diagnosis_controller import (
    reset_diagnosis_for_model,
)
from manga_pdf_to_epub.gui.layout_diagnosis_io_controller import (
    _run_insert_scoring_work,
    _run_spread_scan_work,
    diagnosis_output_root_for_current_pdf,
)
from manga_pdf_to_epub.gui.layout_diagnosis_window import (
    DiagnosisPanel,
    DiagnosisPanelCallbacks,
    DiagnosisWindow,
    diagnosis_summary_texts,
)
from tests.gui_helpers import FakeCanvas, FakeDeleteModel, FakeListbox


def page(source_index: int):
    return SimpleNamespace(label=f"Page {source_index}", source_index=source_index, is_blank=False)


class FakeTkWidget:
    def __init__(self, *args, **kwargs):
        self.parent = args[0] if args else None
        self.options = kwargs
        self.items = []
        self.current_yview = (0.0, 0.0)
        self.moved_to = None
        self.bindings = {}
        self.pack_calls = []
        self.pack_forget_count = 0
        self.place_calls = []
        self.raised = False

    def delete(self, *_args):
        self.items.clear()

    def insert(self, _where, value):
        self.items.append(value)

    def yview(self):
        return self.current_yview

    def yview_moveto(self, fraction):
        self.moved_to = fraction
        self.current_yview = (fraction, fraction)

    def bind(self, sequence, callback):
        self.bindings[sequence] = callback

    def pack(self, *args, **kwargs):
        self.pack_calls.append((args, kwargs))

    def pack_forget(self):
        self.pack_forget_count += 1

    def pack_propagate(self, *_args, **_kwargs):
        pass

    def place(self, *args, **kwargs):
        self.place_calls.append((args, kwargs))

    def tkraise(self, *_args, **_kwargs):
        self.raised = True

    def configure(self, **kwargs):
        self.options.update(kwargs)


class DiagnosisGuiTextTests(unittest.TestCase):
    def test_summary_text_counts_manual_review_state(self):
        session = DiagnosisSession(source_page_count=120)
        session.load_spread_candidates(
            [
                SpreadCandidate("037-038", 37, 38, 0.91, 0.88, "review"),
                SpreadCandidate("071-072", 71, 72, 0.72, 0.70, "review"),
            ]
        )
        session.mark_candidate("037-038", "true")
        damage = diagnose_spread_damage([page(index) for index in range(1, 121)], session.confirmed_spreads(), True)
        insert_result = classify_insert_points(
            [page(index) for index in range(1, 121)],
            session.confirmed_spreads(),
            [InsertCandidate("034-035", 34, 35, 0.94, "C scene_change", 0.7, 0.2, ())],
            True,
        )

        summary = diagnosis_summary_texts(session, damage, insert_result, stale=False)

        self.assertEqual("Candidates: 2 total, 1 true, 0 false, 1 pending.", summary.candidates)
        self.assertEqual("Damage: 1 damaged, 0 intact, 0 missing.", summary.damage)
        self.assertEqual("Insert points: 1 suggested, 0 protected, 0 stale.", summary.insert_points)

    def test_stale_summary_requires_manual_recheck(self):
        session = DiagnosisSession(source_page_count=120)

        summary = diagnosis_summary_texts(session, [], None, stale=True)

        self.assertEqual("Results are stale. Click Recheck Layout before using suggestions.", summary.staleness)


class DiagnosisPanelTests(unittest.TestCase):
    def test_callback_contract_uses_future_action_names(self):
        self.assertEqual(
            [
                "run_spread_diagnosis",
                "sync_spine_selection_from_candidate",
                "mark_selected_spread_true",
                "mark_selected_spread_false",
                "add_selected_spread",
                "check_confirmed_spread_damage",
                "run_insert_point_scoring",
                "import_insert_scores",
                "insert_selected_diagnosis_blank",
                "recheck_diagnosis_layout",
                "apply_settings",
                "clear_diagnostics_output",
            ],
            list(DiagnosisPanelCallbacks.__dataclass_fields__),
        )

    def test_panel_binds_string_vars_to_parent_and_buttons_to_callbacks(self):
        calls = []
        parent = object()
        string_var_kwargs = []
        buttons = []

        def callback(name):
            return lambda: calls.append(name)

        callbacks = DiagnosisPanelCallbacks(
            run_spread_diagnosis=callback("scan"),
            sync_spine_selection_from_candidate=callback("candidate_select"),
            mark_selected_spread_true=callback("true"),
            mark_selected_spread_false=callback("false"),
            add_selected_spread=callback("manual"),
            check_confirmed_spread_damage=callback("damage"),
            run_insert_point_scoring=callback("score"),
            import_insert_scores=callback("import_scores"),
            insert_selected_diagnosis_blank=callback("insert"),
            recheck_diagnosis_layout=callback("recheck"),
            apply_settings=lambda settings: calls.append(("settings", settings)),
            clear_diagnostics_output=callback("clear_cache"),
        )

        class FakeStringVar:
            def __init__(self, *_args, **kwargs):
                string_var_kwargs.append(kwargs)
                self.value = kwargs.get("value", "")

            def set(self, value):
                self.value = value

            def get(self):
                return self.value

        class FakeButton(FakeTkWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                buttons.append(self)

        class FakeNotebook(FakeTkWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.tabs = []

            def add(self, child, **kwargs):
                self.tabs.append((child, kwargs.get("text")))

        with patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.StringVar", FakeStringVar), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.Listbox", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Label", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Button", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Entry", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Frame", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Notebook", FakeNotebook), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Separator", FakeTkWidget):
            panel = DiagnosisPanel(parent, callbacks)
            panel._show_workflow_tab("Insert Points")
            panel._show_workflow_tab("Settings")

        self.assertEqual(9, len(string_var_kwargs))
        self.assertTrue(all(kwargs.get("master") is parent for kwargs in string_var_kwargs))
        button_by_text = {button.options["text"]: button for button in buttons}

        button_by_text["Run Cross-Page Scan"].options["command"]()
        button_by_text["Recheck Layout"].options["command"]()
        button_by_text["Add Selected As Spread"].options["command"]()
        button_by_text["Clear Current Diagnostics Output"].options["command"]()
        panel.candidate_list.bindings["<<ListboxSelect>>"](None)

        self.assertEqual(["scan", "recheck", "manual", "clear_cache", "candidate_select"], calls)

    def test_panel_uses_main_window_style_workflow_tabs(self):
        buttons = []
        parent = object()

        class FakeVar:
            def __init__(self, *_args, **kwargs):
                self.value = kwargs.get("value", "")

            def set(self, value):
                self.value = value

            def get(self):
                return self.value

        class StrictFakeWidget(FakeTkWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

            def place(self, *args, **kwargs):
                raise AssertionError("Workflow tab panes should not be stacked with place.")

            def tkraise(self, *_args, **_kwargs):
                raise AssertionError("Workflow tab panes should not rely on tkraise.")

        class FakeButton(StrictFakeWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                buttons.append(self)

        callbacks = DiagnosisPanelCallbacks(
            run_spread_diagnosis=lambda: None,
            sync_spine_selection_from_candidate=lambda: None,
            mark_selected_spread_true=lambda: None,
            mark_selected_spread_false=lambda: None,
            add_selected_spread=lambda: None,
            check_confirmed_spread_damage=lambda: None,
            run_insert_point_scoring=lambda: None,
            import_insert_scores=lambda: None,
            insert_selected_diagnosis_blank=lambda: None,
            recheck_diagnosis_layout=lambda: None,
            apply_settings=lambda _settings: None,
            clear_diagnostics_output=lambda: None,
        )

        with patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.StringVar", FakeVar), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.Listbox", StrictFakeWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Label", StrictFakeWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Button", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Entry", StrictFakeWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Frame", StrictFakeWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Notebook", side_effect=AssertionError("Notebook should not be used")), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Separator", StrictFakeWidget):
            panel = DiagnosisPanel(parent, callbacks)

            tab_buttons = buttons[:4]
            self.assertEqual(["Candidates", "Damage", "Insert Points", "Settings"], [button.options["text"] for button in tab_buttons])
            self.assertTrue(all(button.pack_calls[-1][1] == {"side": tk.LEFT, "fill": tk.X, "expand": True, "padx": 3} for button in tab_buttons))
            self.assertEqual("disabled", tab_buttons[0].options["state"])
            self.assertEqual("normal", tab_buttons[1].options["state"])
            self.assertEqual(1, len(panel.workflow_tabs["Candidates"].pack_calls))
            self.assertEqual(1, panel.workflow_tabs["Damage"].pack_forget_count)

            tab_buttons[3].options["command"]()

            self.assertEqual("Settings", panel.active_workflow_tab)
            self.assertEqual("normal", tab_buttons[0].options["state"])
            self.assertEqual("disabled", tab_buttons[3].options["state"])
            self.assertEqual(1, panel.workflow_tabs["Candidates"].pack_forget_count)
            self.assertEqual(1, len(panel.workflow_tabs["Settings"].pack_calls))

    def test_panel_builds_only_visible_workflow_tab_content(self):
        listboxes = []
        parent = object()

        class FakeVar:
            def __init__(self, *_args, **kwargs):
                self.value = kwargs.get("value", "")

            def set(self, value):
                self.value = value

            def get(self):
                return self.value

        class FakeListbox(FakeTkWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                listboxes.append(self)

        callbacks = DiagnosisPanelCallbacks(
            run_spread_diagnosis=lambda: None,
            sync_spine_selection_from_candidate=lambda: None,
            mark_selected_spread_true=lambda: None,
            mark_selected_spread_false=lambda: None,
            add_selected_spread=lambda: None,
            check_confirmed_spread_damage=lambda: None,
            run_insert_point_scoring=lambda: None,
            import_insert_scores=lambda: None,
            insert_selected_diagnosis_blank=lambda: None,
            recheck_diagnosis_layout=lambda: None,
            apply_settings=lambda _settings: None,
            clear_diagnostics_output=lambda: None,
        )

        with patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.StringVar", FakeVar), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.Listbox", FakeListbox), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Label", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Button", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Entry", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Frame", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Notebook", side_effect=AssertionError("Notebook should not be used")), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Separator", FakeTkWidget):
            panel = DiagnosisPanel(parent, callbacks)

            self.assertEqual(1, len(listboxes))
            self.assertIsNotNone(panel.candidate_list)
            self.assertIsNone(panel.damage_list)
            self.assertIsNone(panel.insert_list)

            panel._show_workflow_tab("Damage")

            self.assertEqual(2, len(listboxes))
            self.assertIs(panel.workflow_tabs["Damage"], panel.damage_list.parent)
            self.assertIsNone(panel.insert_list)

    def test_panel_listboxes_belong_to_their_workflow_tabs(self):
        parent = object()

        class FakeVar:
            def __init__(self, *_args, **kwargs):
                self.value = kwargs.get("value", "")

            def set(self, value):
                self.value = value

            def get(self):
                return self.value

        callbacks = DiagnosisPanelCallbacks(
            run_spread_diagnosis=lambda: None,
            sync_spine_selection_from_candidate=lambda: None,
            mark_selected_spread_true=lambda: None,
            mark_selected_spread_false=lambda: None,
            add_selected_spread=lambda: None,
            check_confirmed_spread_damage=lambda: None,
            run_insert_point_scoring=lambda: None,
            import_insert_scores=lambda: None,
            insert_selected_diagnosis_blank=lambda: None,
            recheck_diagnosis_layout=lambda: None,
            apply_settings=lambda _settings: None,
            clear_diagnostics_output=lambda: None,
        )

        with patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.StringVar", FakeVar), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.Listbox", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Label", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Button", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Entry", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Frame", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Notebook", side_effect=AssertionError("Notebook should not be used")), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Separator", FakeTkWidget):
            panel = DiagnosisPanel(parent, callbacks)

            panel._show_workflow_tab("Damage")
            panel._show_workflow_tab("Insert Points")

            self.assertIs(panel.workflow_tabs["Candidates"], panel.candidate_list.parent)
            self.assertIs(panel.workflow_tabs["Damage"], panel.damage_list.parent)
            self.assertIs(panel.workflow_tabs["Insert Points"], panel.insert_list.parent)

    def test_panel_listboxes_keep_buttons_visible_in_workflow_tabs(self):
        parent = object()

        class FakeVar:
            def __init__(self, *_args, **kwargs):
                self.value = kwargs.get("value", "")

            def set(self, value):
                self.value = value

            def get(self):
                return self.value

        callbacks = DiagnosisPanelCallbacks(
            run_spread_diagnosis=lambda: None,
            sync_spine_selection_from_candidate=lambda: None,
            mark_selected_spread_true=lambda: None,
            mark_selected_spread_false=lambda: None,
            add_selected_spread=lambda: None,
            check_confirmed_spread_damage=lambda: None,
            run_insert_point_scoring=lambda: None,
            import_insert_scores=lambda: None,
            insert_selected_diagnosis_blank=lambda: None,
            recheck_diagnosis_layout=lambda: None,
            apply_settings=lambda _settings: None,
            clear_diagnostics_output=lambda: None,
        )

        with patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.StringVar", FakeVar), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.Listbox", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Label", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Button", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Entry", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Frame", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Notebook", side_effect=AssertionError("Notebook should not be used")), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Separator", FakeTkWidget):
            panel = DiagnosisPanel(parent, callbacks)

            panel._show_workflow_tab("Damage")
            self.assertNotIn("expand", panel.damage_list.pack_calls[-1][1])
            panel._show_workflow_tab("Insert Points")
            self.assertNotIn("expand", panel.insert_list.pack_calls[-1][1])

    def test_panel_candidate_list_expands_for_long_scan_results(self):
        parent = object()

        class FakeVar:
            def __init__(self, *_args, **kwargs):
                self.value = kwargs.get("value", "")

            def set(self, value):
                self.value = value

            def get(self):
                return self.value

        callbacks = DiagnosisPanelCallbacks(
            run_spread_diagnosis=lambda: None,
            sync_spine_selection_from_candidate=lambda: None,
            mark_selected_spread_true=lambda: None,
            mark_selected_spread_false=lambda: None,
            add_selected_spread=lambda: None,
            check_confirmed_spread_damage=lambda: None,
            run_insert_point_scoring=lambda: None,
            import_insert_scores=lambda: None,
            insert_selected_diagnosis_blank=lambda: None,
            recheck_diagnosis_layout=lambda: None,
            apply_settings=lambda _settings: None,
            clear_diagnostics_output=lambda: None,
        )

        with patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.StringVar", FakeVar), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.Listbox", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Label", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Button", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Entry", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Frame", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Notebook", side_effect=AssertionError("Notebook should not be used")), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Separator", FakeTkWidget):
            panel = DiagnosisPanel(parent, callbacks)

            self.assertGreaterEqual(panel.candidate_list.options["height"], 14)
            self.assertEqual({"fill": tk.BOTH, "expand": True, "pady": (6, 0)}, panel.candidate_list.pack_calls[-1][1])

    def test_panel_initializes_settings_from_current_app_settings(self):
        parent = object()
        settings = DiagnosisSettings(
            spread_workers=7,
            spread_threshold=0.72,
            spread_debug_limit=18,
            spread_max_height=1500,
            insert_thumb_height=640,
        )

        class FakeVar:
            def __init__(self, *_args, **kwargs):
                self.value = kwargs.get("value", "")

            def set(self, value):
                self.value = value

            def get(self):
                return self.value

        class FakeNotebook(FakeTkWidget):
            def add(self, *_args, **_kwargs):
                pass

        callbacks = DiagnosisPanelCallbacks(
            run_spread_diagnosis=lambda: None,
            sync_spine_selection_from_candidate=lambda: None,
            mark_selected_spread_true=lambda: None,
            mark_selected_spread_false=lambda: None,
            add_selected_spread=lambda: None,
            check_confirmed_spread_damage=lambda: None,
            run_insert_point_scoring=lambda: None,
            import_insert_scores=lambda: None,
            insert_selected_diagnosis_blank=lambda: None,
            recheck_diagnosis_layout=lambda: None,
            apply_settings=lambda _settings: None,
            clear_diagnostics_output=lambda: None,
        )

        with patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.StringVar", FakeVar), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.Listbox", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Label", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Button", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Entry", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Frame", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Notebook", FakeNotebook), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Separator", FakeTkWidget):
            panel = DiagnosisPanel(parent, callbacks, settings)

        self.assertEqual("7", panel.workers_var.get())
        self.assertEqual("0.72", panel.threshold_var.get())
        self.assertEqual("18", panel.debug_limit_var.get())
        self.assertEqual("1500", panel.max_height_var.get())
        self.assertEqual("640", panel.insert_thumb_height_var.get())

    def test_panel_default_summary_points_to_scan_or_spine_selection(self):
        parent = object()

        class FakeVar:
            def __init__(self, *_args, **kwargs):
                self.value = kwargs.get("value", "")

            def set(self, value):
                self.value = value

            def get(self):
                return self.value

        class FakeNotebook(FakeTkWidget):
            def add(self, *_args, **_kwargs):
                pass

        callbacks = DiagnosisPanelCallbacks(
            run_spread_diagnosis=lambda: None,
            sync_spine_selection_from_candidate=lambda: None,
            mark_selected_spread_true=lambda: None,
            mark_selected_spread_false=lambda: None,
            add_selected_spread=lambda: None,
            check_confirmed_spread_damage=lambda: None,
            run_insert_point_scoring=lambda: None,
            import_insert_scores=lambda: None,
            insert_selected_diagnosis_blank=lambda: None,
            recheck_diagnosis_layout=lambda: None,
            apply_settings=lambda _settings: None,
            clear_diagnostics_output=lambda: None,
        )

        with patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.StringVar", FakeVar), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.Listbox", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Label", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Button", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Entry", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Frame", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Notebook", FakeNotebook), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Separator", FakeTkWidget):
            panel = DiagnosisPanel(parent, callbacks)

        self.assertNotIn("import spread", panel.summary_var.get().lower())
        self.assertIn("Spine order", panel.summary_var.get())

    def test_panel_settings_apply_validates_and_calls_callback(self):
        received = []
        panel = DiagnosisPanel.__new__(DiagnosisPanel)
        panel.callbacks = SimpleNamespace(apply_settings=lambda settings: received.append(settings))
        panel.workers_var = SimpleNamespace(get=lambda: "6")
        panel.threshold_var = SimpleNamespace(get=lambda: "0.61")
        panel.debug_limit_var = SimpleNamespace(get=lambda: "12")
        panel.max_height_var = SimpleNamespace(get=lambda: "1400")
        panel.insert_thumb_height_var = SimpleNamespace(get=lambda: "800")

        panel.apply_settings()

        self.assertEqual(
            DiagnosisSettings(
                spread_workers=6,
                spread_threshold=0.61,
                spread_debug_limit=12,
                spread_max_height=1400,
                insert_thumb_height=800,
            ),
            received[0],
        )

    def test_panel_settings_apply_reports_invalid_input_without_callback(self):
        received = []
        panel = DiagnosisPanel.__new__(DiagnosisPanel)
        panel.callbacks = SimpleNamespace(apply_settings=lambda settings: received.append(settings))
        panel.workers_var = SimpleNamespace(get=lambda: "many")
        panel.threshold_var = SimpleNamespace(get=lambda: "0.61")
        panel.debug_limit_var = SimpleNamespace(get=lambda: "12")
        panel.max_height_var = SimpleNamespace(get=lambda: "1400")
        panel.insert_thumb_height_var = SimpleNamespace(get=lambda: "800")

        with patch("manga_pdf_to_epub.gui.layout_diagnosis_window.messagebox.showerror") as showerror:
            panel.apply_settings()

        self.assertEqual([], received)
        self.assertEqual("Diagnosis Settings", showerror.call_args.args[0])
        self.assertIn("numeric", showerror.call_args.args[1])

    def test_panel_settings_apply_reports_out_of_range_input_without_callback(self):
        received = []
        panel = DiagnosisPanel.__new__(DiagnosisPanel)
        panel.callbacks = SimpleNamespace(apply_settings=lambda settings: received.append(settings))
        panel.workers_var = SimpleNamespace(get=lambda: "0")
        panel.threshold_var = SimpleNamespace(get=lambda: "0.61")
        panel.debug_limit_var = SimpleNamespace(get=lambda: "12")
        panel.max_height_var = SimpleNamespace(get=lambda: "1400")
        panel.insert_thumb_height_var = SimpleNamespace(get=lambda: "800")

        with patch("manga_pdf_to_epub.gui.layout_diagnosis_window.messagebox.showerror") as showerror:
            panel.apply_settings()

        self.assertEqual([], received)
        self.assertEqual("Diagnosis Settings", showerror.call_args.args[0])
        self.assertIn("workers", showerror.call_args.args[1])


class DiagnosisImportUxTests(unittest.TestCase):
    def test_spread_scan_unavailable_points_to_manual_spine_review(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2)])
        app.pdf_path = Path("/tmp/book.pdf")
        app.diagnosis_session = DiagnosisSession(source_page_count=2)

        with patch("manga_pdf_to_epub.gui.layout_diagnosis_io_controller.resolve_spread_scan_command", return_value=None), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_io_controller.messagebox.showerror") as showerror:
            app.run_spread_diagnosis()

        title, message = showerror.call_args.args
        self.assertEqual("Spread scan unavailable", title)
        self.assertIn("Use Add Selected As Spread", message)
        self.assertNotIn("Use Import Spread Candidates", message)

    def test_spread_scan_reports_pdf_only_for_archive_sources(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2)])
        app.pdf_path = Path("/tmp/book.cbz")
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        app.run_spread_diagnosis()

        self.assertEqual("Cross-page scan is available for PDF sources only.", app.status_value)

    def test_primary_panel_has_no_import_spread_candidates_button(self):
        labels = []
        parent = object()

        class FakeStringVar:
            def __init__(self, *_args, **kwargs):
                self.value = kwargs.get("value", "")

            def set(self, value):
                self.value = value

        class FakeButton(FakeTkWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                labels.append(kwargs.get("text"))

        class FakeNotebook(FakeTkWidget):
            def add(self, *_args, **_kwargs):
                pass

        callbacks = DiagnosisPanelCallbacks(
            run_spread_diagnosis=lambda: None,
            sync_spine_selection_from_candidate=lambda: None,
            mark_selected_spread_true=lambda: None,
            mark_selected_spread_false=lambda: None,
            add_selected_spread=lambda: None,
            check_confirmed_spread_damage=lambda: None,
            run_insert_point_scoring=lambda: None,
            import_insert_scores=lambda: None,
            insert_selected_diagnosis_blank=lambda: None,
            recheck_diagnosis_layout=lambda: None,
            apply_settings=lambda _settings: None,
            clear_diagnostics_output=lambda: None,
        )
        with patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.StringVar", FakeStringVar), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.tk.Listbox", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Label", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Button", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Entry", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Frame", FakeTkWidget), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Notebook", FakeNotebook), \
            patch("manga_pdf_to_epub.gui.layout_diagnosis_window.ttk.Separator", FakeTkWidget):
            DiagnosisPanel(parent, callbacks)

        self.assertNotIn("Import Spread Candidates...", labels)
        self.assertIn("Add Selected As Spread", labels)


class DiagnosisSettingsTests(unittest.TestCase):
    def test_diagnosis_state_initializes_default_settings(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)

        from manga_pdf_to_epub.gui.layout_diagnosis_controller import initialize_diagnosis_state

        initialize_diagnosis_state(app, source_page_count=10)

        self.assertEqual(2, app.diagnosis_settings.spread_workers)
        self.assertEqual(0.53, app.diagnosis_settings.spread_threshold)

    def test_run_spread_diagnosis_passes_current_settings(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2)])
        app.pdf_path = Path("/tmp/book.pdf")
        app.diagnosis_session = DiagnosisSession(source_page_count=2)
        app.diagnosis_settings = SimpleNamespace(spread_workers=6)
        app._run_background = lambda *_args, **_kwargs: setattr(app, "background_started", True)

        with patch("manga_pdf_to_epub.gui.layout_diagnosis_io_controller.resolve_spread_scan_command") as resolve:
            resolve.return_value = SimpleNamespace()
            app.run_spread_diagnosis()

        self.assertIs(app.diagnosis_settings, resolve.call_args.args[3])
        self.assertTrue(app.background_started)

    def test_apply_diagnosis_settings_updates_open_panels(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        settings = DiagnosisSettings(spread_workers=5)
        received = []
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.diagnosis_panel = SimpleNamespace(set_settings=lambda value: received.append(("main", value)))
        app.diagnosis_window = SimpleNamespace(
            panel=SimpleNamespace(set_settings=lambda value: received.append(("window", value)))
        )

        app.apply_diagnosis_settings(settings)

        self.assertIs(settings, app.diagnosis_settings)
        self.assertEqual([("main", settings), ("window", settings)], received)
        self.assertEqual("Updated diagnosis settings.", app.status_value)

    def test_clear_current_diagnostics_removes_current_pdf_output_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = EpubLayoutApp.__new__(EpubLayoutApp)
            app.pdf_path = Path(tmp) / "book.pdf"
            app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
            output_root = Path(tmp) / "diagnostics" / "book"
            (output_root / "spread").mkdir(parents=True)
            (output_root / "spread" / "scores.csv").write_text("old", encoding="utf-8")

            with patch(
                "manga_pdf_to_epub.gui.layout_diagnosis_io_controller.diagnosis_output_root_for_current_pdf",
                return_value=output_root,
            ):
                app.clear_current_diagnostics_output()

            self.assertFalse(output_root.exists())
            self.assertEqual("Cleared diagnostics output for book.", app.status_value)

    def test_clear_current_diagnostics_reports_when_no_cache_exists(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.pdf_path = Path("/tmp/book.pdf")
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        with tempfile.TemporaryDirectory() as tmp, patch(
            "manga_pdf_to_epub.gui.layout_diagnosis_io_controller.diagnosis_output_root_for_current_pdf",
            return_value=Path(tmp) / "missing",
        ):
            app.clear_current_diagnostics_output()

        self.assertEqual("No diagnostics output to clear for book.", app.status_value)

    def test_diagnosis_output_root_for_current_pdf_groups_spread_and_insert_outputs(self):
        root = diagnosis_output_root_for_current_pdf(Path("/repo/manga-pdf-to-epub"), Path("/books/Vol 01.pdf"))

        self.assertEqual(Path("/repo/manga-pdf-to-epub/epub_layout_gui_exports/diagnostics/Vol 01"), root)


class DiagnosisManualSpreadSelectionTests(unittest.TestCase):
    def test_add_selected_spread_uses_two_selected_real_adjacent_pages(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2), page(3)])
        app.diagnosis_session = DiagnosisSession(source_page_count=3)
        app.diagnosis_window = SimpleNamespace(spine_list=FakeListbox(selection=(0, 1)))
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)
        app.refresh_list = lambda preserve_yview=False: setattr(app, "main_list_refreshed", preserve_yview)
        app.refresh_diagnosis_spine = lambda preserve_yview=False: setattr(app, "diagnose_list_refreshed", preserve_yview)
        app.insert_classification = object()
        app.spine_markers = {0: object()}

        app.add_selected_spread_from_diagnosis_spine()

        self.assertEqual([(1, 2)], [(item.start_page, item.end_page) for item in app.diagnosis_session.confirmed_spreads()])
        self.assertTrue(app.diagnosis_stale)
        self.assertIsNone(app.insert_classification)
        self.assertEqual({}, app.spine_markers)
        self.assertEqual("Added confirmed spread 001-002.", app.status_value)
        self.assertTrue(app.main_list_refreshed)
        self.assertTrue(app.diagnose_list_refreshed)
        self.assertTrue(app.panel_refreshed)

    def test_add_selected_spread_rejects_wrong_selection_count(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2), page(3)])
        app.diagnosis_session = DiagnosisSession(source_page_count=3)
        app.diagnosis_window = SimpleNamespace(spine_list=FakeListbox(selection=(0, 1, 2)))
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        app.add_selected_spread_from_diagnosis_spine()

        self.assertEqual([], app.diagnosis_session.confirmed_spreads())
        self.assertEqual("Select exactly two adjacent real pages.", app.status_value)

    def test_add_selected_spread_rejects_blank_or_inserted_rows(self):
        blank = SimpleNamespace(label="Blank", source_index=None, is_blank=True)
        inserted = SimpleNamespace(label="Inserted Image", source_index=None, is_blank=False)
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), blank])
        app.diagnosis_session = DiagnosisSession(source_page_count=2)
        app.diagnosis_window = SimpleNamespace(spine_list=FakeListbox(selection=(0, 1)))
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        app.add_selected_spread_from_diagnosis_spine()

        self.assertEqual([], app.diagnosis_session.confirmed_spreads())
        self.assertEqual("Select exactly two adjacent real pages.", app.status_value)

        app.model = SimpleNamespace(entries=[page(1), inserted])
        app.status_value = ""
        app.add_selected_spread_from_diagnosis_spine()

        self.assertEqual([], app.diagnosis_session.confirmed_spreads())
        self.assertEqual("Select exactly two adjacent real pages.", app.status_value)

    def test_add_selected_spread_rejects_without_diagnose_window(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2)])
        app.diagnosis_session = DiagnosisSession(source_page_count=2)
        app.diagnosis_window = None
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        app.add_selected_spread_from_diagnosis_spine()

        self.assertEqual([], app.diagnosis_session.confirmed_spreads())
        self.assertEqual("Select exactly two adjacent real pages.", app.status_value)

    def test_add_selected_spread_rejects_without_model(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = None
        app.diagnosis_session = DiagnosisSession(source_page_count=2)
        app.diagnosis_window = SimpleNamespace(spine_list=FakeListbox(selection=(0, 1)))
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        app.add_selected_spread_from_diagnosis_spine()

        self.assertEqual([], app.diagnosis_session.confirmed_spreads())
        self.assertEqual("Select exactly two adjacent real pages.", app.status_value)

    def test_add_selected_spread_rejects_non_adjacent_source_pages(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(3)])
        app.diagnosis_session = DiagnosisSession(source_page_count=3)
        app.diagnosis_window = SimpleNamespace(spine_list=FakeListbox(selection=(0, 1)))
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        app.add_selected_spread_from_diagnosis_spine()

        self.assertEqual([], app.diagnosis_session.confirmed_spreads())
        self.assertEqual("Select exactly two adjacent real pages.", app.status_value)

    def test_add_selected_spread_rejects_non_adjacent_spine_rows(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), SimpleNamespace(label="Inserted Image", source_index=None, is_blank=False), page(2)])
        app.diagnosis_session = DiagnosisSession(source_page_count=2)
        app.diagnosis_window = SimpleNamespace(spine_list=FakeListbox(selection=(0, 2)))
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        app.add_selected_spread_from_diagnosis_spine()

        self.assertEqual([], app.diagnosis_session.confirmed_spreads())
        self.assertEqual("Select exactly two adjacent real pages.", app.status_value)


class DiagnosisViewRefreshTests(unittest.TestCase):
    def test_loading_candidates_refreshes_main_and_diagnose_spines(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.diagnosis_session = DiagnosisSession(source_page_count=50)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.refresh_list = lambda preserve_yview=False: setattr(app, "main_refreshed", preserve_yview)
        app.refresh_diagnosis_spine = lambda preserve_yview=False: setattr(app, "diagnose_refreshed", preserve_yview)
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)
        app.spine_markers = {0: object()}

        app._load_spread_candidates([SpreadCandidate("003-004", 3, 4, 0.9, 0.8, "review")])

        self.assertTrue(app.main_refreshed)
        self.assertTrue(getattr(app, "diagnose_refreshed", False))
        self.assertTrue(app.panel_refreshed)

    def test_layout_edit_refreshes_diagnose_spine_when_window_open(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.page_list = FakeListbox(selection=0)
        app.diagnosis_stale = False
        app.insert_classification = object()
        app.spine_markers = {0: object()}
        app.refresh_list = lambda preserve_yview=False: setattr(app, "main_refreshed", preserve_yview)
        app.refresh_diagnosis_spine = lambda preserve_yview=False: setattr(app, "diagnose_refreshed", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)
        app.refresh_diagnosis_preview = lambda: setattr(app, "diagnosis_preview_refreshed", True)
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)
        app._mark_active_volume_edited = lambda: None

        app._refresh_after_layout_edit(select_index=0)

        self.assertTrue(app.main_refreshed)
        self.assertTrue(getattr(app, "diagnose_refreshed", False))
        self.assertTrue(app.preview_refreshed)
        self.assertTrue(getattr(app, "diagnosis_preview_refreshed", False))


class DiagnosisCandidateNavigationTests(unittest.TestCase):
    def test_selected_candidate_jumps_to_matching_source_pages_and_refreshes_previews(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(index) for index in range(1, 13)])
        app.diagnosis_session = DiagnosisSession(source_page_count=12)
        app.diagnosis_session.load_spread_candidates(
            [
                SpreadCandidate("009-010", 9, 10, 0.74, 0.73, "auto"),
                SpreadCandidate("005-006", 5, 6, 0.64, 0.63, "auto"),
            ]
        )
        app.page_list = FakeListbox(selection=None)
        app.diagnosis_window = SimpleNamespace(
            spine_list=FakeListbox(selection=None),
            panel=SimpleNamespace(candidate_list=FakeListbox(selection=0)),
        )
        app.refresh_preview = lambda: setattr(app, "main_preview_selection", app.selected_indexes())
        app.refresh_diagnosis_preview = lambda: setattr(app, "diagnosis_preview_selection", app.diagnosis_window.spine_list.curselection())
        app._syncing_spine_selection = False

        app.sync_spine_selection_from_candidate()

        self.assertEqual((8, 9), app.page_list.curselection())
        self.assertEqual((8, 9), app.diagnosis_window.spine_list.curselection())
        self.assertEqual([8], app.page_list.seen)
        self.assertEqual([8], app.diagnosis_window.spine_list.seen)
        self.assertEqual([8, 9], app.main_preview_selection)
        self.assertEqual((8, 9), app.diagnosis_preview_selection)

    def test_selected_candidate_uses_current_layout_entry_indexes_after_insertions(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(
            entries=[
                page(1),
                SimpleNamespace(label="Inserted", source_index=None, is_blank=False),
                page(2),
                page(3),
                page(4),
            ]
        )
        app.diagnosis_session = DiagnosisSession(source_page_count=4)
        app.diagnosis_session.load_spread_candidates([SpreadCandidate("002-003", 2, 3, 0.9, 0.8, "auto")])
        app.page_list = FakeListbox(selection=None)
        app.diagnosis_window = SimpleNamespace(
            spine_list=FakeListbox(selection=None),
            panel=SimpleNamespace(candidate_list=FakeListbox(selection=0)),
        )
        app.refresh_preview = lambda: None
        app.refresh_diagnosis_preview = lambda: None
        app._syncing_spine_selection = False

        app.sync_spine_selection_from_candidate()

        self.assertEqual((2, 3), app.page_list.curselection())
        self.assertEqual((2, 3), app.diagnosis_window.spine_list.curselection())


class DiagnosisGuiIntegrationTests(unittest.TestCase):
    def test_new_pdf_resets_diagnosis_state(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = None
        app.series_project = "old"
        app.active_series_volume = "old"
        app._sync_navigation_mode = lambda: None
        app._reset_deleted_history = lambda: None
        app._reset_preview_cache = lambda: None
        app._load_metadata_fields = lambda: None
        app.refresh_list = lambda preserve_yview=False: None
        app.refresh_workspace_status = lambda: None
        app.refresh_preview = lambda: None
        app.page_list = FakeListbox(selection=None)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.pdf_path = Path("/tmp/book.pdf")
        app.diagnosis_session = None
        app.spread_damage = ["old"]
        app.insert_classification = "old"
        app.diagnosis_stale = True

        app._open_pdf_done(SimpleNamespace(entries=[page(1), page(2)], source_page_count=2))

        self.assertEqual(2, app.diagnosis_session.source_page_count)
        self.assertEqual([], app.spread_damage)
        self.assertIsNone(app.insert_classification)
        self.assertFalse(app.diagnosis_stale)

    def test_new_pdf_refreshes_open_diagnose_window_from_new_model(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = None
        app.series_project = "old"
        app.active_series_volume = "old"
        app._sync_navigation_mode = lambda: None
        app._reset_deleted_history = lambda: None
        app._reset_preview_cache = lambda: None
        app._load_metadata_fields = lambda: None
        app.refresh_workspace_status = lambda: None
        app.refresh_preview = lambda: setattr(app, "main_preview_refreshed", True)
        app.refresh_diagnosis_preview = lambda: setattr(app, "diagnosis_preview_refreshed", True)
        app.page_list = FakeListbox(selection=None)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.pdf_path = Path("/tmp/book.pdf")
        app.diagnosis_window = SimpleNamespace(
            spine_list=FakeListbox(selection=None),
            preview=FakeCanvas(),
            photo_refs=[],
        )
        app.diagnosis_window.spine_list.items = ["old row"]
        app._is_cover_entry = lambda _entry: False

        app._open_pdf_done(SimpleNamespace(entries=[page(1), page(2)], source_page_count=2))

        self.assertEqual(["0001 [page] Page 1", "0002 [page] Page 2"], app.diagnosis_window.spine_list.items)
        self.assertEqual(0, app.diagnosis_window.spine_list.selection)
        self.assertTrue(app.main_preview_refreshed)
        self.assertTrue(app.diagnosis_preview_refreshed)


class DiagnosisSpineViewTests(unittest.TestCase):
    def test_open_diagnose_window_refreshes_spine_rows(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = object()
        app.model = SimpleNamespace(entries=[page(1), page(2)])
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)
        app._is_cover_entry = lambda _entry: False

        class FakeDiagnosisWindow:
            def __init__(self, *_args):
                self.spine_list = FakeListbox(selection=None)

        with patch("manga_pdf_to_epub.gui.layout_diagnosis_view_controller.DiagnosisWindow", FakeDiagnosisWindow):
            app.open_diagnose_window()

        self.assertEqual(["0001 [page] Page 1", "0002 [page] Page 2"], app.diagnosis_window.spine_list.items)

    def test_refresh_diagnosis_spine_uses_current_model_rows_and_markers(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2), page(3)])
        app.spine_markers = {1: SimpleNamespace(kind="suggested", score=0.91)}
        app.diagnosis_window = SimpleNamespace(spine_list=FakeListbox(selection=1, yview=(0.5, 0.8)))
        app.refresh_workspace_status = lambda: None
        app._is_cover_entry = lambda _entry: False

        app.refresh_diagnosis_spine(preserve_yview=True)

        self.assertEqual("0001 [page] Page 1", app.diagnosis_window.spine_list.items[0])
        self.assertIn("[insert +0.91]", app.diagnosis_window.spine_list.items[1])
        self.assertEqual({"foreground": "#0b6b2b"}, app.diagnosis_window.spine_list.item_options[1])
        self.assertEqual(0.5, app.diagnosis_window.spine_list.moved_to)
        self.assertEqual(1, app.diagnosis_window.spine_list.selection)

    def test_refresh_diagnosis_spine_preserves_multiple_selected_rows(self):
        class SelectionClearingListbox(FakeListbox):
            def delete(self, *args):
                super().delete(*args)
                self.selection = None

            def selection_set(self, index):
                if self.selection is None:
                    self.selection = (index,)
                else:
                    self.selection = (*self.curselection(), index)

        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2), page(3)])
        app.spine_markers = {}
        app.diagnosis_window = SimpleNamespace(spine_list=SelectionClearingListbox(selection=(0, 1)))
        app._is_cover_entry = lambda _entry: False

        app.refresh_diagnosis_spine()

        self.assertEqual((0, 1), app.diagnosis_window.spine_list.selection)

    def test_refresh_diagnosis_spine_uses_protected_marker_color(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2)])
        app.spine_markers = {0: SimpleNamespace(kind="protected", score=0.99)}
        app.diagnosis_window = SimpleNamespace(spine_list=FakeListbox(selection=0))
        app._is_cover_entry = lambda _entry: False

        app.refresh_diagnosis_spine()

        self.assertIn("[protected]", app.diagnosis_window.spine_list.items[0])
        self.assertEqual({"foreground": "#9f1d20"}, app.diagnosis_window.spine_list.item_options[0])

    def test_refresh_diagnosis_spine_noops_when_window_closed(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1)])
        app.diagnosis_window = None

        app.refresh_diagnosis_spine()

        self.assertIsNone(app.diagnosis_window)


class DiagnosisPreviewTests(unittest.TestCase):
    def test_refresh_diagnosis_preview_draws_selected_spread(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        diagnosis_canvas = FakeCanvas()
        diagnosis_refs = ["old"]
        app.photo_refs = ["main"]
        app.model = SimpleNamespace(entries=[page(1), page(2), page(3)])
        app.apple_preview = SimpleNamespace(get=lambda: False)
        app.diagnosis_window = SimpleNamespace(
            spine_list=FakeListbox(selection=1),
            preview=diagnosis_canvas,
            photo_refs=diagnosis_refs,
        )
        app.draws = []

        def draw(canvas, photo_refs, entry, *_args):
            app.draws.append((canvas, photo_refs, entry.label))
            photo_refs.append(entry.label)

        app._draw_entry_on_canvas = draw

        app.refresh_diagnosis_preview()

        self.assertEqual([(diagnosis_canvas, diagnosis_refs, "Page 1"), (diagnosis_canvas, diagnosis_refs, "Page 2")], app.draws)
        self.assertEqual(["Page 1", "Page 2"], diagnosis_refs)
        self.assertEqual(["main"], app.photo_refs)

    def test_refresh_diagnosis_preview_uses_two_selected_candidate_pages(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        diagnosis_canvas = FakeCanvas()
        diagnosis_refs = []
        app.model = SimpleNamespace(entries=[page(index) for index in range(1, 74)])
        app.apple_preview = SimpleNamespace(get=lambda: True)
        app.diagnosis_window = SimpleNamespace(
            spine_list=FakeListbox(selection=(70, 71)),
            preview=diagnosis_canvas,
            photo_refs=diagnosis_refs,
        )
        app.draws = []

        def draw(canvas, photo_refs, entry, *_args):
            app.draws.append((canvas, photo_refs, entry.label))
            photo_refs.append(entry.label)

        app._draw_entry_on_canvas = draw

        app.refresh_diagnosis_preview()

        self.assertEqual([(diagnosis_canvas, diagnosis_refs, "Page 71"), (diagnosis_canvas, diagnosis_refs, "Page 72")], app.draws)
        self.assertEqual(["Page 71", "Page 72"], diagnosis_refs)

    def test_refresh_diagnosis_preview_noops_when_window_closed(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.diagnosis_window = None

        app.refresh_diagnosis_preview()

        self.assertIsNone(app.diagnosis_window)


class DiagnosisSelectionSyncTests(unittest.TestCase):
    def test_main_selection_updates_diagnose_selection_and_preview(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2), page(3)])
        app.page_list = FakeListbox(selection=2)
        app.diagnosis_window = SimpleNamespace(spine_list=FakeListbox(selection=None))
        app.refresh_preview = lambda: setattr(app, "main_preview_refreshed", True)
        app.refresh_diagnosis_preview = lambda: setattr(app, "diagnosis_preview_refreshed", True)
        app._syncing_spine_selection = False

        app.sync_selection_from_main()

        self.assertEqual(2, app.diagnosis_window.spine_list.selection)
        self.assertTrue(app.main_preview_refreshed)
        self.assertTrue(app.diagnosis_preview_refreshed)

    def test_diagnose_selection_updates_main_selection_and_preview(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2), page(3)])
        app.page_list = FakeListbox(selection=None)
        app.diagnosis_window = SimpleNamespace(spine_list=FakeListbox(selection=1))
        app.refresh_preview = lambda: setattr(app, "main_preview_refreshed", app.selected_index())
        app.refresh_diagnosis_preview = lambda: setattr(app, "diagnosis_preview_refreshed", True)
        app._syncing_spine_selection = False

        app.sync_selection_from_diagnosis()

        self.assertEqual(1, app.page_list.selection)
        self.assertEqual(1, app.main_preview_refreshed)
        self.assertTrue(app.diagnosis_preview_refreshed)

    def test_selection_sync_guard_prevents_recursion(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.page_list = FakeListbox(selection=1)
        app.diagnosis_window = SimpleNamespace(spine_list=FakeListbox(selection=None))
        app._syncing_spine_selection = True
        app.refresh_preview = lambda: setattr(app, "main_preview_refreshed", True)
        app.refresh_diagnosis_preview = lambda: setattr(app, "diagnosis_preview_refreshed", True)

        app.sync_selection_from_main()

        self.assertEqual(None, app.diagnosis_window.spine_list.selection)
        self.assertFalse(hasattr(app, "main_preview_refreshed"))
        self.assertFalse(hasattr(app, "diagnosis_preview_refreshed"))

    def test_diagnosis_selection_sync_guard_prevents_recursion(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.page_list = FakeListbox(selection=None)
        app.diagnosis_window = SimpleNamespace(spine_list=FakeListbox(selection=1))
        app._syncing_spine_selection = True
        app.refresh_preview = lambda: setattr(app, "main_preview_refreshed", True)
        app.refresh_diagnosis_preview = lambda: setattr(app, "diagnosis_preview_refreshed", True)

        app.sync_selection_from_diagnosis()

        self.assertEqual(None, app.page_list.selection)
        self.assertFalse(hasattr(app, "main_preview_refreshed"))
        self.assertFalse(hasattr(app, "diagnosis_preview_refreshed"))

    def test_sync_selection_from_main_works_without_diagnosis_window(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.page_list = FakeListbox(selection=0)
        app.diagnosis_window = None
        app.refresh_preview = lambda: setattr(app, "main_preview_refreshed", True)
        app._syncing_spine_selection = False

        app.sync_selection_from_main()

        self.assertTrue(app.main_preview_refreshed)

    def test_selection_sync_guard_blocks_reentrant_selection_callbacks(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.page_list = FakeListbox(selection=2)
        app.reentrant_calls = 0

        class ReentrantListbox(FakeListbox):
            def selection_set(self, index):
                super().selection_set(index)
                app.reentrant_calls += 1
                app.sync_selection_from_diagnosis()

        app.diagnosis_window = SimpleNamespace(spine_list=ReentrantListbox(selection=None))
        app.refresh_preview = lambda: setattr(app, "main_preview_refreshed", True)
        app.refresh_diagnosis_preview = lambda: setattr(app, "diagnosis_preview_refreshed", True)
        app._syncing_spine_selection = False

        app.sync_selection_from_main()

        self.assertEqual(2, app.diagnosis_window.spine_list.selection)
        self.assertEqual(1, app.reentrant_calls)
        self.assertTrue(app.main_preview_refreshed)
        self.assertTrue(app.diagnosis_preview_refreshed)


class DiagnosisWindowLifecycleTests(unittest.TestCase):
    def _panel(self, candidate_selection=None):
        class Var:
            def __init__(self):
                self.value = None

            def set(self, value):
                self.value = value

        return SimpleNamespace(
            summary_var=Var(),
            damage_var=Var(),
            insert_var=Var(),
            stale_var=Var(),
            candidate_list=FakeListbox(selection=candidate_selection),
            damage_list=FakeListbox(selection=None),
            insert_list=FakeListbox(selection=None),
        )

    def test_open_diagnose_window_requires_loaded_model(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = None
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        app.open_diagnose_window()

        self.assertEqual("Open a PDF before opening Diagnose.", app.status_value)
        self.assertIsNone(getattr(app, "diagnosis_window", None))

    def test_open_diagnose_window_creates_and_focuses_toplevel(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = object()
        app.model = SimpleNamespace(entries=[page(1), page(2)])
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)
        app.diagnosis_settings = DiagnosisSettings(spread_workers=8)
        created = []

        class FakeDiagnosisWindow:
            def __init__(self, app_arg, parent, callbacks, settings):
                self.app_arg = app_arg
                self.parent = parent
                self.callbacks = callbacks
                self.settings = settings
                self.focus_count = 0
                created.append(self)

            def focus(self):
                self.focus_count += 1

        with patch("manga_pdf_to_epub.gui.layout_diagnosis_view_controller.DiagnosisWindow", FakeDiagnosisWindow):
            app.open_diagnose_window()
            app.open_diagnose_window()

        self.assertIs(created[0], app.diagnosis_window)
        self.assertEqual(1, len(created))
        self.assertIs(app.diagnosis_settings, created[0].settings)
        self.assertEqual(1, created[0].focus_count)
        self.assertTrue(app.panel_refreshed)

    def test_close_diagnose_window_clears_window_reference_only(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.diagnosis_session = DiagnosisSession(source_page_count=20)
        app.diagnosis_session.add_manual_spread(3, 4)
        app.diagnosis_window = object()

        app._diagnose_window_closed()

        self.assertIsNone(app.diagnosis_window)
        self.assertEqual(
            [(3, 4)],
            [(item.start_page, item.end_page) for item in app.diagnosis_session.confirmed_spreads()],
        )

    def test_close_stale_diagnose_window_does_not_clear_current_window(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        destroyed = []
        current = SimpleNamespace(destroy=lambda: destroyed.append("current"))
        stale = SimpleNamespace(destroy=lambda: destroyed.append("stale"))
        app.diagnosis_window = current

        app._diagnose_window_closed(stale)

        self.assertIs(current, app.diagnosis_window)
        self.assertEqual(["stale"], destroyed)

    def test_reset_diagnosis_for_model_keeps_open_window_linked(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        window = SimpleNamespace(panel=self._panel())
        app.diagnosis_window = window
        app.diagnosis_panel = None
        app.spread_damage = ["old"]
        app.insert_classification = "old"
        app.diagnosis_stale = True

        reset_diagnosis_for_model(app, SimpleNamespace(entries=[page(1), page(2)], source_page_count=2))

        self.assertIs(window, app.diagnosis_window)
        self.assertEqual(2, app.diagnosis_session.source_page_count)
        self.assertEqual("Candidates: 0 total, 0 true, 0 false, 0 pending.", window.panel.summary_var.value)

    def test_window_callback_hook_noops_until_later_sync_methods_exist(self):
        window = DiagnosisWindow.__new__(DiagnosisWindow)
        window.app = SimpleNamespace()

        window._invoke_app_callback("sync_selection_from_diagnosis")

        window.app = SimpleNamespace(refresh_diagnosis_preview=lambda: setattr(window, "preview_refreshed", True))
        window._invoke_app_callback("refresh_diagnosis_preview")
        self.assertTrue(window.preview_refreshed)

    def test_refresh_and_selection_use_diagnose_window_panel_when_open(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.diagnosis_session = DiagnosisSession(source_page_count=20)
        app.diagnosis_session.load_spread_candidates([SpreadCandidate("003-004", 3, 4, 0.91, 0.88, "review")])
        inspector_panel = self._panel(candidate_selection=None)
        window_panel = self._panel(candidate_selection=0)
        app.diagnosis_panel = inspector_panel
        app.diagnosis_window = SimpleNamespace(panel=window_panel)
        app.spread_damage = []
        app.insert_classification = None
        app.diagnosis_stale = False

        app.refresh_diagnosis_panel()

        self.assertEqual("003-004", app._selected_spread_candidate_id())
        self.assertEqual(window_panel.summary_var.value, inspector_panel.summary_var.value)
        self.assertEqual(window_panel.candidate_list.items, inspector_panel.candidate_list.items)


class DiagnosisReviewWorkflowTests(unittest.TestCase):
    def test_imported_candidates_replace_existing_session_candidates(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.diagnosis_session = DiagnosisSession(source_page_count=200)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)
        app.refresh_list = lambda preserve_yview=False: setattr(app, "list_preserved", preserve_yview)
        app.spread_damage = ["old"]
        app.insert_classification = "old"
        app.diagnosis_stale = True
        app.spine_markers = {0: object()}

        app._load_spread_candidates(
            [
                SpreadCandidate("037-038", 37, 38, 0.91, 0.88, "review"),
                SpreadCandidate("115-116", 115, 116, 0.90, 0.89, "review"),
            ]
        )

        self.assertEqual(2, len(app.diagnosis_session.spread_candidates()))
        self.assertEqual([], app.spread_damage)
        self.assertIsNone(app.insert_classification)
        self.assertFalse(app.diagnosis_stale)
        self.assertEqual({}, app.spine_markers)
        self.assertEqual("Loaded 2 spread candidates for review.", app.status_value)
        self.assertTrue(app.panel_refreshed)
        self.assertTrue(app.list_preserved)

    def test_mark_selected_candidate_true_updates_session(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.diagnosis_session = DiagnosisSession(source_page_count=200)
        app.diagnosis_session.load_spread_candidates([SpreadCandidate("037-038", 37, 38, 0.91, 0.88, "review")])
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app._selected_spread_candidate_id = lambda: "037-038"
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)
        app.refresh_list = lambda preserve_yview=False: setattr(app, "list_preserved", preserve_yview)
        app.insert_classification = object()
        app.spine_markers = {0: object()}

        app.mark_selected_spread_true()

        self.assertEqual([(37, 38)], [(item.start_page, item.end_page) for item in app.diagnosis_session.confirmed_spreads()])
        self.assertTrue(app.diagnosis_stale)
        self.assertIsNone(app.insert_classification)
        self.assertEqual({}, app.spine_markers)
        self.assertEqual("Marked 037-038 as true spread.", app.status_value)
        self.assertTrue(app.panel_refreshed)
        self.assertTrue(app.list_preserved)

    def test_mark_selected_candidate_false_clears_insert_suggestions(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.diagnosis_session = DiagnosisSession(source_page_count=200)
        app.diagnosis_session.load_spread_candidates([SpreadCandidate("037-038", 37, 38, 0.91, 0.88, "review")])
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app._selected_spread_candidate_id = lambda: "037-038"
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)
        app.refresh_list = lambda preserve_yview=False: setattr(app, "list_preserved", preserve_yview)
        app.insert_classification = object()
        app.spine_markers = {0: object()}

        app.mark_selected_spread_false()

        self.assertEqual([], app.diagnosis_session.confirmed_spreads())
        self.assertTrue(app.diagnosis_stale)
        self.assertIsNone(app.insert_classification)
        self.assertEqual({}, app.spine_markers)
        self.assertEqual("Marked 037-038 as false positive.", app.status_value)
        self.assertTrue(app.panel_refreshed)
        self.assertTrue(app.list_preserved)

    def test_manual_missing_spread_is_confirmed(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.diagnosis_session = DiagnosisSession(source_page_count=200)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.refresh_diagnosis_panel = lambda: None
        app.refresh_list = lambda preserve_yview=False: setattr(app, "list_preserved", preserve_yview)
        app.insert_classification = object()
        app.spine_markers = {0: object()}

        app._add_missing_spread_pair(173, 174)

        self.assertEqual([(173, 174)], [(item.start_page, item.end_page) for item in app.diagnosis_session.confirmed_spreads()])
        self.assertTrue(app.diagnosis_stale)
        self.assertIsNone(app.insert_classification)
        self.assertEqual({}, app.spine_markers)
        self.assertEqual("Added confirmed spread 173-174.", app.status_value)
        self.assertTrue(app.list_preserved)

    def test_preview_layout_option_change_marks_diagnosis_stale(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.diagnosis_stale = False
        app.insert_classification = object()
        app.spine_markers = {0: object()}
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)
        app.refresh_list = lambda preserve_yview=False: setattr(app, "list_preserved", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app.refresh_preview_after_diagnosis_layout_option_change()

        self.assertTrue(app.diagnosis_stale)
        self.assertIsNone(app.insert_classification)
        self.assertEqual({}, app.spine_markers)
        self.assertTrue(app.panel_refreshed)
        self.assertTrue(app.list_preserved)
        self.assertTrue(app.preview_refreshed)

    def test_preview_layout_option_change_preserves_spine_selection(self):
        class SelectionClearingListbox(FakeListbox):
            def delete(self, *args):
                super().delete(*args)
                self.selection = None

        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(index) for index in range(1, 8)])
        app.page_list = SelectionClearingListbox(selection=4, yview=(0.5, 0.8))
        app.diagnosis_stale = False
        app.insert_classification = object()
        app.spine_markers = {0: object()}
        app.refresh_workspace_status = lambda: None
        app.refresh_diagnosis_panel = lambda: None
        app.refresh_preview = lambda: setattr(app, "preview_selection", app.selected_index())
        app._is_cover_entry = lambda _entry: False

        app.refresh_preview_after_diagnosis_layout_option_change()

        self.assertEqual(4, app.page_list.selection)
        self.assertEqual(4, app.preview_selection)


class DiagnosisDamageWorkflowTests(unittest.TestCase):
    def test_damage_check_uses_confirmed_spreads_and_apple_preview_flag(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(index) for index in range(1, 41)])
        app.apple_preview = SimpleNamespace(get=lambda: True)
        app.diagnosis_session = DiagnosisSession(source_page_count=40)
        app.diagnosis_session.add_manual_spread(37, 38)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)
        app.refresh_list = lambda preserve_yview=False: setattr(app, "list_preserved", preserve_yview)
        app.spine_markers = {0: object()}
        app.insert_classification = "old"
        app.diagnosis_stale = True

        app.check_confirmed_spread_damage()

        self.assertEqual("damaged", app.spread_damage[0].status)
        self.assertIsNone(app.insert_classification)
        self.assertEqual({}, app.spine_markers)
        self.assertFalse(app.diagnosis_stale)
        self.assertEqual("Checked 1 confirmed spreads: 1 damaged, 0 missing.", app.status_value)
        self.assertTrue(app.panel_refreshed)
        self.assertTrue(app.list_preserved)

    def test_damage_check_requires_confirmed_spreads(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2)])
        app.apple_preview = SimpleNamespace(get=lambda: False)
        app.diagnosis_session = DiagnosisSession(source_page_count=2)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        app.check_confirmed_spread_damage()

        self.assertEqual("Mark at least one true spread before checking damage.", app.status_value)

    def test_recheck_layout_runs_damage_check_from_stale_state(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(index) for index in range(1, 41)])
        app.apple_preview = SimpleNamespace(get=lambda: True)
        app.diagnosis_session = DiagnosisSession(source_page_count=40)
        app.diagnosis_session.add_manual_spread(37, 38)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)
        app.refresh_list = lambda preserve_yview=False: setattr(app, "list_preserved", preserve_yview)
        app.spread_damage = []
        app.insert_classification = "old"
        app.spine_markers = {0: object()}
        app.diagnosis_stale = True

        app.recheck_diagnosis_layout()

        self.assertEqual("damaged", app.spread_damage[0].status)
        self.assertFalse(app.diagnosis_stale)
        self.assertEqual("Checked 1 confirmed spreads: 1 damaged, 0 missing.", app.status_value)


class DiagnosisSpreadScanWorkflowTests(unittest.TestCase):
    def test_spread_scan_work_reads_candidates_in_background_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / "adjacent_clusters.csv").write_text(
                "start_page,end_page,decision,spread,review_score\n37,38,review,0.91,0.88\n",
                encoding="utf-8",
            )

            with patch(
                "manga_pdf_to_epub.gui.layout_diagnosis_io_controller.run_diagnosis_command",
                return_value=SimpleNamespace(output_dir=output_dir),
            ):
                candidates = _run_spread_scan_work(SimpleNamespace(), source_page_count=50)

        self.assertEqual(["037-038"], [candidate.pair_id for candidate in candidates])

    def test_spread_scan_work_forwards_progress_callback(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / "adjacent_clusters.csv").write_text(
                "start_page,end_page,decision,spread,review_score\n37,38,review,0.91,0.88\n",
                encoding="utf-8",
            )
            def callback(event):
                return None

            with patch(
                "manga_pdf_to_epub.gui.layout_diagnosis_io_controller.run_diagnosis_command",
                return_value=SimpleNamespace(output_dir=output_dir),
            ) as run:
                _run_spread_scan_work(SimpleNamespace(), source_page_count=50, progress_callback=callback)

        self.assertIs(callback, run.call_args.kwargs["progress_callback"])

    def test_spread_scan_work_validates_candidates_in_background_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / "adjacent_clusters.csv").write_text(
                "start_page,end_page,decision,spread,review_score\n37,39,review,0.91,0.88\n",
                encoding="utf-8",
            )

            with patch(
                "manga_pdf_to_epub.gui.layout_diagnosis_io_controller.run_diagnosis_command",
                return_value=SimpleNamespace(output_dir=output_dir),
            ):
                with self.assertRaisesRegex(ValueError, "adjacent"):
                    _run_spread_scan_work(SimpleNamespace(), source_page_count=50)

    def test_spread_scan_done_loads_parsed_candidates(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.diagnosis_session = DiagnosisSession(source_page_count=50)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.refresh_diagnosis_panel = lambda: None
        app.refresh_list = lambda preserve_yview=False: None
        app.spine_markers = {}

        app._spread_scan_done([SpreadCandidate("037-038", 37, 38, 0.91, 0.88, "review")])

        self.assertEqual(["037-038"], [item.candidate.pair_id for item in app.diagnosis_session.spread_candidates()])
        self.assertEqual("Loaded 1 spread candidates for review.", app.status_value)

    def test_spread_scan_failure_uses_scan_specific_status_and_dialog(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        with patch("manga_pdf_to_epub.gui.layout_diagnosis_io_controller.messagebox.showerror") as showerror:
            app._spread_scan_failed(ValueError("bad csv"))

        self.assertEqual("Cross-page scan failed.", app.status_value)
        showerror.assert_called_once_with("Cross-page scan failed", "bad csv")


class DiagnosisInsertWorkflowTests(unittest.TestCase):
    def test_insert_scores_classify_and_refresh_spine_markers(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(index) for index in range(1, 41)])
        app.apple_preview = SimpleNamespace(get=lambda: True)
        app.diagnosis_session = DiagnosisSession(source_page_count=40)
        app.diagnosis_session.add_manual_spread(37, 38)
        app.spread_damage = diagnose_spread_damage(app.model.entries, app.diagnosis_session.confirmed_spreads(), True)
        app.page_list = FakeListbox(selection=0)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)
        app.refresh_workspace_status = lambda: None
        app._is_cover_entry = lambda _entry: False

        app._load_insert_candidates(
            [
                InsertCandidate("034-035", 34, 35, 0.94, "C scene_change", 0.7, 0.2, ("scene change",)),
                InsertCandidate("037-038", 37, 38, 0.99, "B low_content_pause", 0.8, 0.1, ("low content",)),
            ]
        )

        self.assertEqual(1, len(app.insert_classification.suggestions))
        self.assertIn("insert +0.94", app.page_list.items[33])
        self.assertIn("protected", app.page_list.items[36])
        self.assertEqual({"foreground": "#0b6b2b"}, app.page_list.item_options[33])
        self.assertEqual({"foreground": "#9f1d20"}, app.page_list.item_options[36])
        self.assertEqual("Loaded 2 insert scores: 1 suggested, 1 protected.", app.status_value)
        self.assertTrue(app.panel_refreshed)

    def test_insert_score_import_requires_damage_check_first(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2)])
        app.spread_damage = []
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        app._load_insert_candidates([InsertCandidate("001-002", 1, 2, 0.9, "C scene_change", 0.7, 0.2, ())])

        self.assertEqual("Check confirmed spread damage before loading insert scores.", app.status_value)

    def test_import_insert_scores_reads_csv_and_loads_candidates(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.loaded = None

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gaps.csv"
            path.write_text(
                "gap,after_page,before_page,safe_insert_score,label,visual_difference,continuity_risk,reasons\n"
                "034-035,34,35,0.94,C scene_change,0.7,0.2,scene change\n",
                encoding="utf-8",
            )

            with patch(
                "manga_pdf_to_epub.gui.layout_diagnosis_io_controller.filedialog.askopenfilename",
                return_value=str(path),
            ):
                app._load_insert_candidates = lambda candidates: setattr(app, "loaded", candidates)
                app.import_insert_scores()

        self.assertEqual(["034-035"], [candidate.gap_id for candidate in app.loaded])

    def test_run_insert_scoring_work_reads_gaps_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / "gaps.csv").write_text(
                "gap,after_page,before_page,safe_insert_score,label,visual_difference,continuity_risk,reasons\n"
                "034-035,34,35,0.94,C scene_change,0.7,0.2,scene change\n",
                encoding="utf-8",
            )

            with patch(
                "manga_pdf_to_epub.gui.layout_diagnosis_io_controller.run_diagnosis_command",
                return_value=SimpleNamespace(output_dir=output_dir),
            ):
                candidates = _run_insert_scoring_work(SimpleNamespace())

        self.assertEqual(["034-035"], [candidate.gap_id for candidate in candidates])

    def test_insert_scoring_failure_uses_scoring_specific_status_and_dialog(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        with patch("manga_pdf_to_epub.gui.layout_diagnosis_io_controller.messagebox.showerror") as showerror:
            app._insert_scoring_failed(ValueError("bad gaps"))

        self.assertEqual("Insert-point scoring failed.", app.status_value)
        showerror.assert_called_once_with("Insert-point scoring failed", "bad gaps")


class DiagnosisInsertionExecutionTests(unittest.TestCase):
    def test_insert_selected_suggestion_calls_layout_model_once_and_marks_results_stale(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([page(index) for index in range(1, 41)])
        app.apple_preview = SimpleNamespace(get=lambda: True)
        app.diagnosis_session = DiagnosisSession(source_page_count=40)
        app.diagnosis_session.add_manual_spread(37, 38)
        app.spread_damage = diagnose_spread_damage(app.model.entries, app.diagnosis_session.confirmed_spreads(), True)
        app.page_list = FakeListbox(selection=0)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)
        app.refresh_workspace_status = lambda: None
        app._is_cover_entry = lambda _entry: False
        app._load_insert_candidates(
            [InsertCandidate("034-035", 34, 35, 0.94, "C scene_change", 0.7, 0.2, ("scene change",))]
        )
        app.diagnosis_panel = SimpleNamespace(insert_list=FakeListbox(selection=0))
        app._refresh_after_layout_edit = lambda select_index: setattr(app, "selected_after_insert", select_index)

        app.insert_selected_diagnosis_blank()

        self.assertEqual("Blank 35", app.model.entries[34].label)
        self.assertTrue(app.diagnosis_stale)
        self.assertEqual([], app.spread_damage)
        self.assertIsNone(app.insert_classification)
        self.assertEqual({}, app.spine_markers)
        self.assertEqual(34, app.selected_after_insert)
        self.assertEqual("Inserted blank for suggested gap 034-035. Click Recheck Layout before continuing.", app.status_value)
        self.assertTrue(app.panel_refreshed)

    def test_insert_selected_requires_suggested_row(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = None
        app.insert_classification = None
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        app.insert_selected_diagnosis_blank()

        self.assertEqual("Select an insert suggestion first.", app.status_value)


if __name__ == "__main__":
    unittest.main()
