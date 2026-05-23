import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from manga_pdf_to_epub.epub_layout_gui import EpubLayoutApp

from tests.gui_helpers import (
    FakeDeleteModel,
    FakeListbox,
    FakeRoot,
    FakeStatus,
    entry,
)


class EpubLayoutGuiCommandTests(unittest.TestCase):
    def test_bind_shortcuts_registers_safe_layout_actions(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = FakeRoot()
        app.recover_last_deleted = lambda: setattr(app, "recovered", True)
        app.delete_selected_entry = lambda: setattr(app, "deleted", True)
        app.export_selected_images = lambda: setattr(app, "exported", True)
        app.open_command_palette = lambda: setattr(app, "palette_opened", True)

        app._bind_shortcuts()
        app.root.bindings["<Delete>"](None)
        app.root.bindings["<Command-Shift-E>"](None)
        app.root.bindings["<Command-k>"](None)

        self.assertIn("<Command-z>", app.root.bindings)
        self.assertIn("<Control-z>", app.root.bindings)
        self.assertIn("<Command-k>", app.root.bindings)
        self.assertIn("<Control-k>", app.root.bindings)
        self.assertTrue(app.deleted)
        self.assertTrue(app.exported)
        self.assertTrue(app.palette_opened)

    def test_delete_shortcut_ignores_textentry_focus(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = FakeRoot()
        app.delete_selected_entry = lambda: setattr(app, "deleted", True)
        app.recover_last_deleted = lambda: None
        app.export_selected_images = lambda: None
        app.open_command_palette = lambda: None

        app._bind_shortcuts()
        result = app.root.bindings["<Delete>"](SimpleNamespace(widget=SimpleNamespace(winfo_class=lambda: "TEntry")))

        self.assertEqual("break", result)
        self.assertFalse(hasattr(app, "deleted"))

    def test_backspace_shortcut_ignores_textentry_focus(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = FakeRoot()
        app.delete_selected_entry = lambda: setattr(app, "deleted", True)
        app.recover_last_deleted = lambda: None
        app.export_selected_images = lambda: None
        app.open_command_palette = lambda: None

        app._bind_shortcuts()
        result = app.root.bindings["<BackSpace>"](SimpleNamespace(widget=SimpleNamespace(winfo_class=lambda: "Entry")))

        self.assertEqual("break", result)
        self.assertFalse(hasattr(app, "deleted"))

    def test_command_palette_queries_match_action_labels(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)

        labels = [command.label for command in app._matching_commands("cover")]

        self.assertIn("Set Selected As Cover", labels)
        self.assertNotIn("Export EPUB", labels)

    def test_command_palette_omits_legacy_and_status_only_actions(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)

        labels = [command.label for command in app._commands()]

        self.assertNotIn("Batch Apply", labels)
        self.assertNotIn("Normalize Export Order", labels)
        self.assertNotIn("Validate Batch", labels)
        self.assertNotIn("Export Ready Batch", labels)
        self.assertNotIn("Export All Batch", labels)

    def test_command_palette_keeps_bulk_delete_actions_searchable(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)

        labels = [command.label for command in app._matching_commands("delete")]

        self.assertIn("Delete Selected Page", labels)
        self.assertIn("Delete First...", labels)
        self.assertIn("Delete Last...", labels)
        self.assertIn("Delete Range...", labels)

    def test_command_palette_includes_project_save_load_actions(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)

        labels = [command.label for command in app._matching_commands("project")]

        self.assertIn("Save Project", labels)
        self.assertIn("Open Project", labels)

    def test_command_palette_includes_validate_series_action(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)

        labels = [command.label for command in app._matching_commands("validate")]

        self.assertIn("Validate Series", labels)

    def test_command_palette_dispatches_bulk_delete_actions(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.ask_delete_range = lambda: setattr(app, "range_delete_opened", True)

        app._execute_command("Delete Range...")

        self.assertTrue(app.range_delete_opened)

    def test_command_palette_dispatches_to_existing_app_method(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.insert_blank = lambda before: setattr(app, "insert_before", before)

        app._execute_command("Insert Blank Before")

        self.assertTrue(app.insert_before)

    def test_workspace_summary_reports_empty_workspace(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = None
        app.series_project = None

        self.assertEqual("No PDF loaded | Series: 0", app._workspace_summary())

    def test_workspace_summary_reports_pages_and_series_counts(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[entry("Page 1"), entry("Page 2")])
        app.series_project = SimpleNamespace(volumes=[
            SimpleNamespace(status="Ready"),
            SimpleNamespace(status="Edited"),
            SimpleNamespace(status="Failed"),
            SimpleNamespace(status="Unreviewed"),
        ])

        self.assertEqual("Pages: 2 | Series: 4 | Ready: 1 | Edited: 1 | Failed: 1", app._workspace_summary())

    def test_run_background_sets_and_clears_busy_state(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = FakeRoot()
        app.status = FakeStatus()
        app._busy = False
        app.done_value = None

        with patch("manga_pdf_to_epub.epub_layout_gui.threading.Thread") as thread:
            thread.side_effect = lambda target, daemon: SimpleNamespace(start=target)
            started = app._run_background("Working...", lambda: 42, lambda value: setattr(app, "done_value", value))

        self.assertTrue(started)
        self.assertFalse(app._busy)
        self.assertEqual(42, app.done_value)
        self.assertEqual("Working...", app.status.value)

    def test_run_background_uses_custom_failure_handler(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = FakeRoot()
        app.status = FakeStatus()
        app._busy = False

        with patch("manga_pdf_to_epub.epub_layout_gui.threading.Thread") as thread:
            thread.side_effect = lambda target, daemon: SimpleNamespace(start=target)
            started = app._run_background(
                "Working...",
                lambda: (_ for _ in ()).throw(ValueError("bad")),
                lambda value: None,
                on_failure=lambda exc: setattr(app, "failure_message", str(exc)),
            )

        self.assertTrue(started)
        self.assertFalse(app._busy)
        self.assertEqual("bad", app.failure_message)

    def test_run_background_rejects_reentrant_work(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = FakeRoot()
        app.status = FakeStatus()
        app._busy = True

        started = app._run_background("Working...", lambda: 42, lambda value: None)

        self.assertFalse(started)
        self.assertEqual("Another operation is already running.", app.status.value)

    def test_open_pdf_uses_background_loader(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app._run_background = lambda status, work, on_success: setattr(app, "background_call", (status, work, on_success)) or True

        with patch("manga_pdf_to_epub.epub_layout_gui.filedialog.askopenfilename", return_value="/tmp/book.pdf"):
            app.open_pdf()

        self.assertEqual(Path("/tmp/book.pdf"), app.pdf_path)
        self.assertEqual("Loading PDF images...", app.background_call[0])

    def test_thumbnail_cache_key_uses_stableentry_identity(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        entry = SimpleNamespace(page=SimpleNamespace(item_id="inserted-0001"), source_index=None)

        self.assertEqual(("entry", "inserted-0001", 100, 200), app._thumbnail_cache_key(entry, 100, 200))

    def test_thumbnail_for_page_reuses_open_pdf_document(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.pdf_path = Path("/tmp/book.pdf")
        app.thumbnail_cache = {}
        fake_page = SimpleNamespace(
            rect=SimpleNamespace(width=100, height=200),
            get_pixmap=lambda matrix, alpha: SimpleNamespace(tobytes=lambda fmt: b"PNG"),
        )

        class FakeDoc:
            def __getitem__(self, index):
                return fake_page

            def close(self):
                app.closed_doc = True

        app._pdf_doc = FakeDoc()
        app._pdf_doc_path = app.pdf_path

        with patch("manga_pdf_to_epub.epub_layout_gui.tk.PhotoImage", return_value=SimpleNamespace(width=lambda: 10, height=lambda: 20)) as photo:
            first = app._thumbnail_for_page(1, 120, 180)
            second = app._thumbnail_for_page(1, 121, 181)

        self.assertIs(first, second)
        photo.assert_called_once()

    def test_reset_preview_cache_closes_open_document_and_clears_thumbnails(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.thumbnail_cache = {"old": object()}
        app._pdf_doc_path = Path("/tmp/book.pdf")
        app.closed = False
        app._pdf_doc = SimpleNamespace(close=lambda: setattr(app, "closed", True))

        app._reset_preview_cache()

        self.assertEqual({}, app.thumbnail_cache)
        self.assertIsNone(app._pdf_doc)
        self.assertIsNone(app._pdf_doc_path)
        self.assertTrue(app.closed)

    def test_refresh_list_can_preserve_scroll_position(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[entry(f"Page {index}") for index in range(1, 8)])
        app.page_list = FakeListbox(yview=(0.5, 0.8))

        app.refresh_list(preserve_yview=True)

        self.assertEqual(0.5, app.page_list.moved_to)

    def test_refresh_list_marks_cover_entry(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1"), entry("Page 2")])
        app.model.cover_source_index = 2
        app.page_list = FakeListbox(yview=(0.5, 0.8))

        app.refresh_list()

        self.assertEqual("0002 [page] [cover] Page 2", app.page_list.items[1])

if __name__ == "__main__":
    unittest.main()
