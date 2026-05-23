import unittest
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
from manga_pdf_to_epub.epub_layout_diagnosis_gui import (
    DiagnosisPanel,
    DiagnosisPanelCallbacks,
    diagnosis_summary_texts,
)


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
    def test_panel_binds_string_vars_to_parent_and_buttons_to_callbacks(self):
        calls = []
        parent = object()
        string_var_kwargs = []
        buttons = []

        def callback(name):
            return lambda: calls.append(name)

        callbacks = DiagnosisPanelCallbacks(
            callback("scan"),
            callback("import_spreads"),
            callback("true"),
            callback("false"),
            callback("manual"),
            callback("damage"),
            callback("score"),
            callback("import_scores"),
            callback("insert"),
            callback("recheck"),
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


if __name__ == "__main__":
    unittest.main()
