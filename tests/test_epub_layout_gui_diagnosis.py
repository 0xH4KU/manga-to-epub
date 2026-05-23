import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from manga_pdf_to_epub.epub_layout_diagnosis import (
    DiagnosisSession,
    InsertCandidate,
    SpreadCandidate,
    classify_insert_points,
    diagnose_spread_damage,
)
from manga_pdf_to_epub.epub_layout_gui import EpubLayoutApp
from manga_pdf_to_epub.epub_layout_diagnosis_controller import (
    _run_insert_scoring_work,
    _run_spread_scan_work,
    reset_diagnosis_for_model,
)
from manga_pdf_to_epub.epub_layout_diagnosis_gui import (
    DiagnosisPanel,
    DiagnosisPanelCallbacks,
    DiagnosisWindow,
    diagnosis_summary_texts,
)
from tests.gui_helpers import FakeDeleteModel, FakeListbox


def page(source_index: int):
    return SimpleNamespace(label=f"Page {source_index}", source_index=source_index, is_blank=False)


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
                "import_spread_candidates",
                "mark_selected_spread_true",
                "mark_selected_spread_false",
                "add_missing_spread",
                "check_confirmed_spread_damage",
                "run_insert_point_scoring",
                "import_insert_scores",
                "insert_selected_diagnosis_blank",
                "recheck_diagnosis_layout",
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
            import_spread_candidates=callback("import_spreads"),
            mark_selected_spread_true=callback("true"),
            mark_selected_spread_false=callback("false"),
            add_missing_spread=callback("manual"),
            check_confirmed_spread_damage=callback("damage"),
            run_insert_point_scoring=callback("score"),
            import_insert_scores=callback("import_scores"),
            insert_selected_diagnosis_blank=callback("insert"),
            recheck_diagnosis_layout=callback("recheck"),
        )

        class FakeStringVar:
            def __init__(self, *_args, **kwargs):
                string_var_kwargs.append(kwargs)
                self.value = kwargs.get("value", "")

            def set(self, value):
                self.value = value

            def get(self):
                return self.value

        class FakeWidget:
            def __init__(self, *args, **kwargs):
                self.parent = args[0] if args else None
                self.options = kwargs

            def pack(self, *_args, **_kwargs):
                pass

        class FakeButton(FakeWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                buttons.append(self)

        with patch("manga_pdf_to_epub.epub_layout_diagnosis_gui.tk.StringVar", FakeStringVar), \
            patch("manga_pdf_to_epub.epub_layout_diagnosis_gui.tk.Listbox", FakeWidget), \
            patch("manga_pdf_to_epub.epub_layout_diagnosis_gui.ttk.Label", FakeWidget), \
            patch("manga_pdf_to_epub.epub_layout_diagnosis_gui.ttk.Button", FakeButton), \
            patch("manga_pdf_to_epub.epub_layout_diagnosis_gui.ttk.Separator", FakeWidget):
            DiagnosisPanel(parent, callbacks)

        self.assertEqual([parent, parent, parent, parent], [kwargs.get("master") for kwargs in string_var_kwargs])
        button_by_text = {button.options["text"]: button for button in buttons}

        button_by_text["Run Cross-Page Scan"].options["command"]()
        button_by_text["Recheck Layout"].options["command"]()

        self.assertEqual(["scan", "recheck"], calls)


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
        app.refresh_list = lambda: None
        app.refresh_workspace_status = lambda: None
        app.refresh_preview = lambda: None
        app.page_list = SimpleNamespace(selection_clear=lambda *_args: None, selection_set=lambda *_args: None)
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


class DiagnosisSpineViewTests(unittest.TestCase):
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
        created = []

        class FakeDiagnosisWindow:
            def __init__(self, app_arg, parent, callbacks):
                self.app_arg = app_arg
                self.parent = parent
                self.callbacks = callbacks
                self.focus_count = 0
                created.append(self)

            def focus(self):
                self.focus_count += 1

        with patch("manga_pdf_to_epub.epub_layout_diagnosis_controller.DiagnosisWindow", FakeDiagnosisWindow):
            app.open_diagnose_window()
            app.open_diagnose_window()

        self.assertIs(created[0], app.diagnosis_window)
        self.assertEqual(1, len(created))
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
                "manga_pdf_to_epub.epub_layout_diagnosis_controller.run_diagnosis_command",
                return_value=SimpleNamespace(output_dir=output_dir),
            ):
                candidates = _run_spread_scan_work(SimpleNamespace(), source_page_count=50)

        self.assertEqual(["037-038"], [candidate.pair_id for candidate in candidates])

    def test_spread_scan_work_validates_candidates_in_background_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / "adjacent_clusters.csv").write_text(
                "start_page,end_page,decision,spread,review_score\n37,39,review,0.91,0.88\n",
                encoding="utf-8",
            )

            with patch(
                "manga_pdf_to_epub.epub_layout_diagnosis_controller.run_diagnosis_command",
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

        with patch("manga_pdf_to_epub.epub_layout_diagnosis_controller.messagebox.showerror") as showerror:
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
                "manga_pdf_to_epub.epub_layout_diagnosis_controller.filedialog.askopenfilename",
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
                "manga_pdf_to_epub.epub_layout_diagnosis_controller.run_diagnosis_command",
                return_value=SimpleNamespace(output_dir=output_dir),
            ):
                candidates = _run_insert_scoring_work(SimpleNamespace())

        self.assertEqual(["034-035"], [candidate.gap_id for candidate in candidates])

    def test_insert_scoring_failure_uses_scoring_specific_status_and_dialog(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        with patch("manga_pdf_to_epub.epub_layout_diagnosis_controller.messagebox.showerror") as showerror:
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
