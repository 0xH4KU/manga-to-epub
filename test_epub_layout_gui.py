import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from epub_layout_gui import EpubLayoutApp


class _FakeBool:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _FakeCanvas:
    def delete(self, *_args):
        pass

    def winfo_width(self):
        return 400

    def winfo_height(self):
        return 300


class _FakeListbox:
    def __init__(self, selection=0, yview=(0.4, 0.7)):
        self.items = []
        self.selection = selection
        self.current_yview = yview
        self.moved_to = None

    def curselection(self):
        return () if self.selection is None else (self.selection,)

    def delete(self, *_args):
        self.items.clear()
        self.current_yview = (0.0, 0.0)

    def insert(self, _where, value):
        self.items.append(value)

    def selection_clear(self, *_args):
        self.selection = None

    def selection_set(self, index):
        self.selection = index

    def yview(self):
        return self.current_yview

    def yview_moveto(self, fraction):
        self.moved_to = fraction
        self.current_yview = (fraction, fraction)

    def nearest(self, y):
        if not self.items:
            return 0
        return min(max(int(y), 0), len(self.items) - 1)


class _FakeStatus:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class _FakeRoot:
    def __init__(self):
        self.bindings = {}
        self.after_calls = []
        self.title_value = None
        self.geometry_value = None
        self.minsize_value = None

    def title(self, value):
        self.title_value = value

    def geometry(self, value):
        self.geometry_value = value

    def minsize(self, width, height):
        self.minsize_value = (width, height)

    def bind_all(self, sequence, callback):
        self.bindings[sequence] = callback

    def after(self, delay, callback):
        self.after_calls.append((delay, callback))
        callback()

    def update_idletasks(self):
        pass


class _FakeWidget:
    def __init__(self, *_args, **_kwargs):
        self.children = []
        self.options = {}
        self.pack_args = []

    def add(self, child, **_kwargs):
        self.children.append(child)

    def pack(self, *args, **kwargs):
        self.pack_args.append((args, kwargs))

    def pack_propagate(self, *_args, **_kwargs):
        pass

    def place(self, *_args, **_kwargs):
        pass

    def set(self, *_args, **_kwargs):
        pass

    def bind(self, *_args, **_kwargs):
        pass

    def tkraise(self, *_args, **_kwargs):
        pass

    def configure(self, **kwargs):
        self.options.update(kwargs)


class _FakeDeleteModel:
    def __init__(self, entries):
        self.entries = entries
        self.deleted = []
        self.cover_source_index = 1
        self.exclude_cover_from_reading = False

    def delete_entry(self, index):
        self.deleted.append(index)
        del self.entries[index]

    def delete_first(self, count):
        deleted = []
        for offset in range(count):
            entry = self.entries.pop(0)
            deleted.append((offset, entry))
        return deleted

    def delete_last(self, count):
        start = len(self.entries) - count
        deleted = [(start + offset, entry) for offset, entry in enumerate(self.entries[start:])]
        del self.entries[start:]
        return deleted

    def delete_range(self, start, end):
        deleted = [(index, self.entries[index]) for index in range(start, end + 1)]
        del self.entries[start : end + 1]
        return deleted

    def set_cover(self, source_index):
        self.cover_source_index = source_index

    def set_cover_entry(self, entry):
        if entry.source_index is None:
            self.cover_entry_id = entry.label
        else:
            self.set_cover(entry.source_index)

    def insert_image(self, index, image_path):
        self.entries.insert(index, _entry(f"Image {index + 1}"))

    def export_selected_images(self, indexes, output_dir):
        return [output_dir / f"{index + 1:04d}.jpg" for index in indexes], 0

    def move_entry(self, from_index, to_index):
        entry = self.entries.pop(from_index)
        self.entries.insert(to_index, entry)
        return to_index


class _FakeBatchProject:
    def __init__(self):
        self.items = []
        self.validated_dir = None
        self.exported_all_dir = None

    def add_pdf(self, path):
        item = SimpleNamespace(pdf_path=path, status="Pending", warnings=[], error=None)
        self.items.append(item)
        return item

    def validate_all(self, output_dir):
        self.validated_dir = output_dir
        for item in self.items:
            item.status = "Ready"

    def export_ready(self, output_dir):
        return {"exported": len(self.items), "failed": 0, "skipped": 0}

    def export_all(self, output_dir):
        self.exported_all_dir = output_dir
        return {"exported": len(self.items), "failed": 0, "skipped": 0}


def _entry(label, is_blank=False):
    source_index = None if is_blank else int(label.split()[-1])
    return SimpleNamespace(label=label, is_blank=is_blank, source_index=source_index)


def _inserted_entry(label):
    return SimpleNamespace(label=label, is_blank=False, source_index=None)


def _app_for_preview(entries, selected):
    app = EpubLayoutApp.__new__(EpubLayoutApp)
    app.preview = _FakeCanvas()
    app.photo_refs = []
    app.model = SimpleNamespace(entries=entries)
    app.apple_preview = _FakeBool(True)
    app.selected_index = lambda: selected
    app.draws = []
    app._draw_entry = lambda entry, x, y, width, height: app.draws.append((entry.label, x))
    return app


class EpubLayoutGuiPreviewTests(unittest.TestCase):
    def test_apple_cover_gap_is_drawn_on_right_of_cover(self):
        app = _app_for_preview([_entry("Page 1"), _entry("Page 2")], selected=0)

        app.refresh_preview()

        self.assertEqual(
            [("Page 1", 12), ("Virtual Apple Books cover gap", 206)],
            app.draws,
        )

    def test_selected_pages_after_cover_map_past_virtual_apple_gap(self):
        app = _app_for_preview([_entry("Page 1"), _entry("Page 2"), _entry("Page 3")], selected=1)

        app.refresh_preview()

        self.assertEqual(
            [("Page 2", 206), ("Page 3", 12)],
            app.draws,
        )

    def test_blank_before_cover_does_not_remove_virtual_apple_gap(self):
        app = _app_for_preview([_entry("Blank 1", is_blank=True), _entry("Page 1"), _entry("Page 2")], selected=0)

        app.refresh_preview()

        self.assertEqual(
            [("Blank 1", 12), ("Virtual Apple Books cover gap", 206)],
            app.draws,
        )

    def test_cover_after_inserted_blank_maps_past_virtual_apple_gap(self):
        app = _app_for_preview([_entry("Blank 1", is_blank=True), _entry("Page 1"), _entry("Page 2")], selected=1)

        app.refresh_preview()

        self.assertEqual(
            [("Page 1", 206), ("Page 2", 12)],
            app.draws,
        )


class EpubLayoutGuiListTests(unittest.TestCase):
    def test_configure_window_sets_workbench_geometry_and_minimum_size(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = _FakeRoot()

        app._configure_window()

        self.assertEqual("EPUB Layout Lab", app.root.title_value)
        self.assertEqual("1280x760", app.root.geometry_value)
        self.assertEqual((1100, 680), app.root.minsize_value)

    def test_inspector_tabs_group_workbench_controls(self):
        self.assertEqual(("Edit", "Book", "Batch"), EpubLayoutApp._inspector_tab_titles())

    def test_edit_inspector_sections_follow_layout_workflow(self):
        self.assertEqual(("Insert", "Delete", "Repair"), EpubLayoutApp._edit_section_titles())

    def test_batch_inspector_sections_follow_batch_workflow(self):
        self.assertEqual(("Template", "Queue", "Preflight", "Export"), EpubLayoutApp._batch_section_titles())

    def test_inspector_tab_state_switches_active_tab(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.inspector_tabs = {
            "Edit": SimpleNamespace(raise_count=0, tkraise=lambda: None),
            "Batch": SimpleNamespace(raise_count=0, tkraise=lambda: None),
        }
        app.inspector_tab_buttons = {}

        app._show_inspector_tab("Batch")

        self.assertEqual("Batch", app.active_inspector_tab)

    def test_preview_checkbox_label_is_explicitly_preview_only(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = _FakeRoot()
        app.apple_preview = _FakeBool(True)
        app.title_var = SimpleNamespace()
        app.author_var = SimpleNamespace()
        app.language_var = SimpleNamespace()
        app.exclude_cover_var = _FakeBool(False)
        app.inspector_tabs = {}
        app.inspector_tab_buttons = {}
        app.status = _FakeStatus()
        app.workspace_status = _FakeStatus()
        app.refresh_preview = lambda: None
        app.refresh_workspace_status = lambda: None
        widgets = []

        class FakeFrame(_FakeWidget):
            pass

        class FakePanedwindow(_FakeWidget):
            pass

        class FakeButton(_FakeWidget):
            def __init__(self, *_args, **kwargs):
                super().__init__()
                self.options = kwargs

        class FakeLabel(FakeButton):
            pass

        class FakeCheckbutton(FakeButton):
            def __init__(self, *_args, **kwargs):
                super().__init__(*_args, **kwargs)
                widgets.append(self)

        class FakeListbox(_FakeWidget):
            def __init__(self, *_args, **_kwargs):
                super().__init__()

            def bind(self, *_args, **_kwargs):
                pass

            def pack_propagate(self, *_args, **_kwargs):
                pass

            def yview(self, *_args, **_kwargs):
                pass

        class FakeCanvas(FakeListbox):
            def create_window(self, *_args, **_kwargs):
                return 1

            def configure(self, **kwargs):
                self.options.update(kwargs)

            def itemconfigure(self, *_args, **_kwargs):
                pass

            def bbox(self, *_args, **_kwargs):
                return (0, 0, 1, 1)

        with patch("epub_layout_gui.ttk.Frame", FakeFrame), \
            patch("epub_layout_gui.ttk.Panedwindow", FakePanedwindow), \
            patch("epub_layout_gui.ttk.Button", FakeButton), \
            patch("epub_layout_gui.ttk.Label", FakeLabel), \
            patch("epub_layout_gui.ttk.Checkbutton", FakeCheckbutton), \
            patch("epub_layout_gui.ttk.Scrollbar", FakeButton), \
            patch("epub_layout_gui.ttk.Separator", FakeButton), \
            patch("epub_layout_gui.ttk.Entry", FakeButton), \
            patch("epub_layout_gui.tk.Listbox", FakeListbox), \
            patch("epub_layout_gui.tk.Canvas", FakeCanvas):
            app._build_ui()

        labels = [widget.options.get("text") for widget in widgets]
        self.assertIn("Preview Apple Books cover gap", labels)
        self.assertNotIn("Apple Books-like cover-right gap", labels)

    def test_batch_queue_is_scoped_to_batch_tab(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = _FakeRoot()
        app.apple_preview = _FakeBool(True)
        app.title_var = SimpleNamespace()
        app.author_var = SimpleNamespace()
        app.language_var = SimpleNamespace()
        app.exclude_cover_var = _FakeBool(False)
        app.inspector_tabs = {}
        app.inspector_tab_buttons = {}
        app.status = _FakeStatus()
        app.workspace_status = _FakeStatus()
        app.refresh_preview = lambda: None
        app.refresh_workspace_status = lambda: None
        widgets = []

        class FakeFrame(_FakeWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.parent = args[0] if args else None
                self.options = kwargs
                widgets.append(self)

        class FakePanedwindow(FakeFrame):
            pass

        class FakeButton(FakeFrame):
            pass

        class FakeLabel(FakeFrame):
            pass

        class FakeCheckbutton(FakeFrame):
            pass

        class FakeListbox(FakeFrame):
            def bind(self, *_args, **_kwargs):
                pass

            def yview(self, *_args, **_kwargs):
                pass

        class FakeCanvas(FakeListbox):
            def create_window(self, *_args, **_kwargs):
                return 1

            def itemconfigure(self, *_args, **_kwargs):
                pass

            def bbox(self, *_args, **_kwargs):
                return (0, 0, 1, 1)

        with patch("epub_layout_gui.ttk.Frame", FakeFrame), \
            patch("epub_layout_gui.ttk.Panedwindow", FakePanedwindow), \
            patch("epub_layout_gui.ttk.Button", FakeButton), \
            patch("epub_layout_gui.ttk.Label", FakeLabel), \
            patch("epub_layout_gui.ttk.Checkbutton", FakeCheckbutton), \
            patch("epub_layout_gui.ttk.Scrollbar", FakeButton), \
            patch("epub_layout_gui.ttk.Separator", FakeButton), \
            patch("epub_layout_gui.ttk.Entry", FakeButton), \
            patch("epub_layout_gui.tk.Listbox", FakeListbox), \
            patch("epub_layout_gui.tk.Canvas", FakeCanvas):
            app._build_ui()

        labels = [widget.options.get("text") for widget in widgets]
        self.assertNotIn("Batch queue", labels)
        self.assertNotIn("Delete First...", labels)
        self.assertNotIn("Delete Last...", labels)
        self.assertNotIn("Delete Range...", labels)

        batch_queue_parent = app.batch_list.parent
        parent_labels = [
            widget.options.get("text")
            for widget in widgets
            if widget.parent is batch_queue_parent
        ]
        self.assertIn("Queue", parent_labels)
        self.assertIn("Add PDFs...", parent_labels)

    def test_import_series_toolbar_and_series_list_are_visible(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = _FakeRoot()
        app.apple_preview = _FakeBool(True)
        app.title_var = SimpleNamespace()
        app.author_var = SimpleNamespace()
        app.language_var = SimpleNamespace()
        app.exclude_cover_var = _FakeBool(False)
        app.inspector_tabs = {}
        app.inspector_tab_buttons = {}
        app.status = _FakeStatus()
        app.workspace_status = _FakeStatus()
        app.refresh_preview = lambda: None
        app.refresh_workspace_status = lambda: None
        widgets = []

        class FakeFrame(_FakeWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.options = kwargs
                widgets.append(self)

        class FakePanedwindow(FakeFrame):
            pass

        class FakeButton(FakeFrame):
            pass

        class FakeLabel(FakeFrame):
            pass

        class FakeCheckbutton(FakeFrame):
            pass

        class FakeListbox(FakeFrame):
            def bind(self, *_args, **_kwargs):
                pass

            def yview(self, *_args, **_kwargs):
                pass

        class FakeCanvas(FakeListbox):
            def create_window(self, *_args, **_kwargs):
                return 1

            def itemconfigure(self, *_args, **_kwargs):
                pass

            def bbox(self, *_args, **_kwargs):
                return (0, 0, 1, 1)

        with patch("epub_layout_gui.ttk.Frame", FakeFrame), \
            patch("epub_layout_gui.ttk.Panedwindow", FakePanedwindow), \
            patch("epub_layout_gui.ttk.Button", FakeButton), \
            patch("epub_layout_gui.ttk.Label", FakeLabel), \
            patch("epub_layout_gui.ttk.Checkbutton", FakeCheckbutton), \
            patch("epub_layout_gui.ttk.Scrollbar", FakeButton), \
            patch("epub_layout_gui.ttk.Separator", FakeButton), \
            patch("epub_layout_gui.ttk.Entry", FakeButton), \
            patch("epub_layout_gui.tk.Listbox", FakeListbox), \
            patch("epub_layout_gui.tk.Canvas", FakeCanvas):
            app._build_ui()

        labels = [widget.options.get("text") for widget in widgets]
        self.assertIn("Import Series...", labels)
        self.assertIn("Series volumes", labels)
        self.assertIsNot(app.series_list, app.page_list)

    def test_import_series_creates_project_and_populates_volume_list(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.series_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.workspace_status = _FakeStatus()
        app.refresh_workspace_status = lambda: None

        with patch(
            "epub_layout_gui.filedialog.askopenfilenames",
            return_value=("/tmp/晚安,布布 淺野一二O Vol.02.pdf", "/tmp/晚安,布布 淺野一二O Vol.01.pdf"),
        ):
            app.import_series()

        self.assertEqual("晚安,布布 淺野一二O", app.series_project.title)
        self.assertEqual(
            [
                "Unreviewed Vol.01 晚安,布布 淺野一二O Vol.01.pdf",
                "Unreviewed Vol.02 晚安,布布 淺野一二O Vol.02.pdf",
            ],
            app.series_list.items,
        )
        self.assertEqual("Imported series with 2 volumes.", app.status.value)

    def test_select_series_volume_loads_existing_editor_model(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        first = SimpleNamespace(
            pdf_path=Path("/tmp/vol01.pdf"),
            volume_number=1,
            status="Unreviewed",
            layout_model=_FakeDeleteModel([_entry("Page 1")]),
        )
        project = SimpleNamespace(
            volumes=[first],
            generated_title=lambda volume: f"Series Vol.{volume.volume_number:02d}",
            model_for_volume=lambda volume: volume.layout_model,
        )
        app.series_project = project
        app.series_list = _FakeListbox(selection=0)
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.deleted_entries = []
        app.thumbnail_cache = {}
        app._load_metadata_fields = lambda: setattr(app, "metadata_loaded", True)
        app.refresh_list = lambda: setattr(app, "list_refreshed", True)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)
        app.refresh_workspace_status = lambda: None

        app.select_series_volume()

        self.assertIs(first.layout_model, app.model)
        self.assertEqual(Path("/tmp/vol01.pdf"), app.pdf_path)
        self.assertTrue(app.metadata_loaded)
        self.assertTrue(app.list_refreshed)
        self.assertTrue(app.preview_refreshed)
        self.assertEqual("Loaded Series Vol.01.", app.status.value)

    def test_bind_shortcuts_registers_safe_layout_actions(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = _FakeRoot()
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

    def test_delete_shortcut_ignores_text_entry_focus(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = _FakeRoot()
        app.delete_selected_entry = lambda: setattr(app, "deleted", True)
        app.recover_last_deleted = lambda: None
        app.export_selected_images = lambda: None
        app.open_command_palette = lambda: None

        app._bind_shortcuts()
        result = app.root.bindings["<Delete>"](SimpleNamespace(widget=SimpleNamespace(winfo_class=lambda: "TEntry")))

        self.assertEqual("break", result)
        self.assertFalse(hasattr(app, "deleted"))

    def test_backspace_shortcut_ignores_text_entry_focus(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = _FakeRoot()
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

    def test_command_palette_keeps_bulk_delete_actions_searchable(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)

        labels = [command.label for command in app._matching_commands("delete")]

        self.assertIn("Delete Selected Page", labels)
        self.assertIn("Delete First...", labels)
        self.assertIn("Delete Last...", labels)
        self.assertIn("Delete Range...", labels)

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
        app.batch_project = None

        self.assertEqual("No PDF loaded | Queue: 0", app._workspace_summary())

    def test_workspace_summary_reports_pages_and_batch_counts(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[_entry("Page 1"), _entry("Page 2")])
        app.batch_project = _FakeBatchProject()
        app.batch_project.items = [
            SimpleNamespace(status="Ready"),
            SimpleNamespace(status="Warning"),
            SimpleNamespace(status="Failed"),
            SimpleNamespace(status="Pending"),
        ]

        self.assertEqual("Pages: 2 | Queue: 4 | Ready: 1 | Warning: 1 | Failed: 1", app._workspace_summary())

    def test_run_background_sets_and_clears_busy_state(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = _FakeRoot()
        app.status = _FakeStatus()
        app._busy = False
        app.done_value = None

        with patch("epub_layout_gui.threading.Thread") as thread:
            thread.side_effect = lambda target, daemon: SimpleNamespace(start=target)
            started = app._run_background("Working...", lambda: 42, lambda value: setattr(app, "done_value", value))

        self.assertTrue(started)
        self.assertFalse(app._busy)
        self.assertEqual(42, app.done_value)
        self.assertEqual("Working...", app.status.value)

    def test_run_background_rejects_reentrant_work(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = _FakeRoot()
        app.status = _FakeStatus()
        app._busy = True

        started = app._run_background("Working...", lambda: 42, lambda value: None)

        self.assertFalse(started)
        self.assertEqual("Another operation is already running.", app.status.value)

    def test_open_pdf_uses_background_loader(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app._run_background = lambda status, work, on_success: setattr(app, "background_call", (status, work, on_success)) or True

        with patch("epub_layout_gui.filedialog.askopenfilename", return_value="/tmp/book.pdf"):
            app.open_pdf()

        self.assertEqual(Path("/tmp/book.pdf"), app.pdf_path)
        self.assertEqual("Loading PDF images...", app.background_call[0])

    def test_thumbnail_cache_key_uses_stable_entry_identity(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        entry = SimpleNamespace(page=SimpleNamespace(item_id="inserted-0001"), source_index=None)

        self.assertEqual(("entry", "inserted-0001", 100, 200), app._thumbnail_cache_key(entry, 100, 200))

    def test_refresh_list_can_preserve_scroll_position(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[_entry(f"Page {index}") for index in range(1, 8)])
        app.page_list = _FakeListbox(yview=(0.5, 0.8))

        app.refresh_list(preserve_yview=True)

        self.assertEqual(0.5, app.page_list.moved_to)

    def test_refresh_list_marks_cover_entry(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2")])
        app.model.cover_source_index = 2
        app.page_list = _FakeListbox(yview=(0.5, 0.8))

        app.refresh_list()

        self.assertEqual("0002 [page] [cover] Page 2", app.page_list.items[1])

    def test_delete_selected_entry_uses_common_delete_for_blank(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Blank 1", is_blank=True), _entry("Page 1")])
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.deleted_entries = []
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app.delete_selected_entry()

        self.assertEqual([0], app.model.deleted)
        self.assertEqual([[(0, "Blank 1")]], [[(index, entry.label) for index, entry in group] for group in app.deleted_entries])
        self.assertEqual(0, app.page_list.selection)
        self.assertTrue(app.preserved_yview)
        self.assertTrue(app.preview_refreshed)
        self.assertEqual("Removed Blank 1 from layout.", app.status.value)

    def test_delete_selected_entry_confirms_real_pages(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2")])
        app.page_list = _FakeListbox(selection=1)
        app.status = _FakeStatus()
        app.deleted_entries = []
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        with patch("epub_layout_gui.messagebox.askyesno", return_value=True) as askyesno:
            app.delete_selected_entry()

        askyesno.assert_called_once()
        self.assertEqual([1], app.model.deleted)
        self.assertEqual(0, app.page_list.selection)
        self.assertTrue(app.preserved_yview)

    def test_recover_last_deleted_restores_entry_to_original_position(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        page_1 = _entry("Page 1")
        page_2 = _entry("Page 2")
        page_3 = _entry("Page 3")
        app.model = _FakeDeleteModel([page_1, page_3])
        app.deleted_entries = [[(1, page_2)]]
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app.recover_last_deleted()

        self.assertEqual(["Page 1", "Page 2", "Page 3"], [entry.label for entry in app.model.entries])
        self.assertEqual([], app.deleted_entries)
        self.assertEqual(1, app.page_list.selection)
        self.assertTrue(app.preserved_yview)
        self.assertTrue(app.preview_refreshed)
        self.assertEqual("Recovered Page 2 at position 2.", app.status.value)

    def test_recover_last_deleted_is_lifo_and_clamps_position(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        page_1 = _entry("Page 1")
        page_2 = _entry("Page 2")
        page_9 = _entry("Page 9")
        app.model = _FakeDeleteModel([page_1])
        app.deleted_entries = [[(1, page_2)], [(8, page_9)]]
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.refresh_list = lambda preserve_yview=False: None
        app.refresh_preview = lambda: None

        app.recover_last_deleted()

        self.assertEqual(["Page 1", "Page 9"], [entry.label for entry in app.model.entries])
        self.assertEqual([[(1, "Page 2")]], [[(index, entry.label) for index, entry in group] for group in app.deleted_entries])
        self.assertEqual(1, app.page_list.selection)

    def test_quick_delete_first_records_one_undo_group(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2"), _entry("Page 3")])
        app.page_list = _FakeListbox(selection=2)
        app.status = _FakeStatus()
        app.deleted_entries = []
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        with patch("epub_layout_gui.messagebox.askyesno", return_value=True):
            app.quick_delete_first(2)

        self.assertEqual(["Page 3"], [entry.label for entry in app.model.entries])
        self.assertEqual([[(0, "Page 1"), (1, "Page 2")]], [[(index, entry.label) for index, entry in group] for group in app.deleted_entries])
        self.assertEqual(0, app.page_list.selection)
        self.assertEqual("Deleted 2 entries: 2 images, 0 blanks.", app.status.value)

    def test_recover_last_deleted_restores_grouped_delete(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        page_1 = _entry("Page 1")
        page_2 = _entry("Page 2")
        page_3 = _entry("Page 3")
        app.model = _FakeDeleteModel([page_3])
        app.deleted_entries = [[(0, page_1), (1, page_2)]]
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app.recover_last_deleted()

        self.assertEqual(["Page 1", "Page 2", "Page 3"], [entry.label for entry in app.model.entries])
        self.assertEqual([], app.deleted_entries)
        self.assertEqual(0, app.page_list.selection)
        self.assertEqual("Recovered 2 pages.", app.status.value)

    def test_set_selected_as_cover_updates_model_and_status(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2")])
        app.page_list = _FakeListbox(selection=1)
        app.status = _FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)

        app.set_selected_as_cover()

        self.assertEqual(2, app.model.cover_source_index)
        self.assertTrue(app.preserved_yview)
        self.assertEqual("Set Page 2 as cover.", app.status.value)

    def test_set_selected_as_cover_accepts_inserted_images(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        inserted = _inserted_entry("Extra Cover")
        app.model = _FakeDeleteModel([_entry("Page 1"), inserted])
        app.model.set_cover_entry = lambda entry: setattr(app, "cover_entry", entry)
        app.page_list = _FakeListbox(selection=1)
        app.status = _FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)

        app.set_selected_as_cover()

        self.assertIs(inserted, app.cover_entry)
        self.assertTrue(app.preserved_yview)
        self.assertEqual("Set Extra Cover as cover.", app.status.value)

    def test_set_selected_as_cover_rejects_blank_pages(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Blank 1", is_blank=True)])
        app.page_list = _FakeListbox(selection=1)
        app.status = _FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)

        with patch("epub_layout_gui.messagebox.showerror") as showerror:
            app.set_selected_as_cover()

        showerror.assert_called_once_with("Set cover failed", "Cover must be an image page.")
        self.assertEqual(1, app.model.cover_source_index)
        self.assertFalse(hasattr(app, "preserved_yview"))

    def test_selected_indexes_support_multi_selection(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.page_list = _FakeListbox(selection=None)
        app.page_list.curselection = lambda: (0, 2)

        self.assertEqual([0, 2], app.selected_indexes())

    def test_drag_release_moves_pressed_row_to_target_row(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2"), _entry("Page 3")])
        app.page_list = _FakeListbox(selection=0)
        app.page_list.items = ["Page 1", "Page 2", "Page 3"]
        app.status = _FakeStatus()
        app.workspace_status = _FakeStatus()
        app.batch_project = None
        app._page_drag_source = None
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app._page_drag_start(SimpleNamespace(y=0))
        app._page_drag_release(SimpleNamespace(y=2))

        self.assertEqual(["Page 2", "Page 3", "Page 1"], [entry.label for entry in app.model.entries])
        self.assertEqual(2, app.page_list.selection)
        self.assertTrue(app.preview_refreshed)
        self.assertEqual("Moved Page 1 to position 3.", app.status.value)

    def test_drag_release_on_same_row_does_not_move(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2")])
        app.page_list = _FakeListbox(selection=0)
        app.page_list.items = ["Page 1", "Page 2"]
        app.status = _FakeStatus()
        app.workspace_status = _FakeStatus()
        app.batch_project = None
        app._page_drag_source = None
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app._page_drag_start(SimpleNamespace(y=1))
        app._page_drag_release(SimpleNamespace(y=1))

        self.assertEqual(["Page 1", "Page 2"], [entry.label for entry in app.model.entries])
        self.assertFalse(hasattr(app, "preview_refreshed"))
        self.assertIsNone(app.status.value)

    def test_drag_uses_pressed_row_when_selection_differs(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2"), _entry("Page 3")])
        app.page_list = _FakeListbox(selection=0)
        app.page_list.items = ["Page 1", "Page 2", "Page 3"]
        app.status = _FakeStatus()
        app.workspace_status = _FakeStatus()
        app.batch_project = None
        app._page_drag_source = None
        app.refresh_preview = lambda: None

        app._page_drag_start(SimpleNamespace(y=1))
        app._page_drag_release(SimpleNamespace(y=2))

        self.assertEqual(["Page 1", "Page 3", "Page 2"], [entry.label for entry in app.model.entries])
        self.assertEqual(2, app.page_list.selection)

    def test_insert_image_after_selected_page_calls_model(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1")])
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        with patch("epub_layout_gui.filedialog.askopenfilename", return_value="/tmp/extra.png"):
            app.insert_image(before=False)

        self.assertEqual(["Page 1", "Image 2"], [entry.label for entry in app.model.entries])
        self.assertTrue(app.preserved_yview)
        self.assertEqual("Inserted image: extra.png", app.status.value)

    def test_batch_add_pdfs_updates_queue_list(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.batch_project = _FakeBatchProject()
        app.batch_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()

        with patch("epub_layout_gui.filedialog.askopenfilenames", return_value=["/tmp/a.pdf", "/tmp/b.pdf"]):
            app.add_batch_pdfs()

        self.assertEqual(["Pending a.pdf", "Pending b.pdf"], app.batch_list.items)
        self.assertEqual("Added 2 PDFs to batch.", app.status.value)

    def test_batch_validate_uses_selected_output_dir(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.batch_project = _FakeBatchProject()
        app.batch_project.add_pdf(Path("/tmp/a.pdf"))
        app.batch_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.root = _FakeRoot()

        with patch("epub_layout_gui.filedialog.askdirectory", return_value="/tmp/out"):
            with patch("epub_layout_gui.threading.Thread") as thread:
                thread.side_effect = lambda target, daemon: SimpleNamespace(start=target)
                app.validate_batch()

        self.assertEqual(Path("/tmp/out"), app.batch_project.validated_dir)
        self.assertEqual(["Ready a.pdf"], app.batch_list.items)
        self.assertEqual("Batch validation complete: 1 ready, 0 warning, 0 failed.", app.status.value)

    def test_batch_validate_reports_status_counts(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.batch_project = _FakeBatchProject()
        app.batch_project.items = [
            SimpleNamespace(pdf_path=Path("/tmp/ready.pdf"), status="Ready", warnings=[], error=None),
            SimpleNamespace(pdf_path=Path("/tmp/warn.pdf"), status="Warning", warnings=["Page count differs"], error=None),
            SimpleNamespace(pdf_path=Path("/tmp/bad.pdf"), status="Failed", warnings=[], error="bad pdf"),
        ]
        app.batch_project.validate_all = lambda output_dir: setattr(app.batch_project, "validated_dir", output_dir)
        app.batch_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.root = _FakeRoot()

        with patch("epub_layout_gui.filedialog.askdirectory", return_value="/tmp/out"):
            with patch("epub_layout_gui.threading.Thread") as thread:
                thread.side_effect = lambda target, daemon: SimpleNamespace(start=target)
                app.validate_batch()

        self.assertEqual("Batch validation complete: 1 ready, 1 warning, 1 failed.", app.status.value)

    def test_hidden_legacy_gui_actions_are_removed(self):
        removed_method_names = (
            "normalize" + "_export_order",
            "batch" + "_apply_preset",
            "_batch" + "_apply_work",
            "_batch_done",
        )
        for method_name in removed_method_names:
            self.assertFalse(hasattr(EpubLayoutApp, method_name), method_name)

    def test_quick_delete_status_reports_deleted_mix(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Blank 1", is_blank=True), _entry("Page 1"), _entry("Page 2")])
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.deleted_entries = []
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        with patch("epub_layout_gui.messagebox.askyesno", return_value=True):
            app.quick_delete_first(2)

        self.assertEqual("Deleted 2 entries: 1 image, 1 blank.", app.status.value)

    def test_load_batch_template_from_preset_creates_batch_project(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.batch_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()

        with patch("epub_layout_gui.filedialog.askopenfilename", return_value="/tmp/layout.json"):
            with patch("epub_layout_gui.BatchProject.from_preset", return_value=_FakeBatchProject()) as from_preset:
                app.load_batch_template_from_preset()

        from_preset.assert_called_once_with(Path("/tmp/layout.json"))
        self.assertIsInstance(app.batch_project, _FakeBatchProject)
        self.assertEqual("Batch template loaded from preset: layout.json", app.status.value)

    def test_export_all_batch_uses_warnings_included_export(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.batch_project = _FakeBatchProject()
        app.batch_project.add_pdf(Path("/tmp/a.pdf"))
        app.batch_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.root = SimpleNamespace(update_idletasks=lambda: None, after=lambda _delay, callback: callback())

        with patch("epub_layout_gui.filedialog.askdirectory", return_value="/tmp/out"):
            with patch("epub_layout_gui.threading.Thread") as thread:
                thread.side_effect = lambda target, daemon: SimpleNamespace(start=target)
                with patch("epub_layout_gui.messagebox.showinfo"):
                    app.export_all_batch()

        self.assertEqual(Path("/tmp/out"), app.batch_project.exported_all_dir)
        self.assertEqual("Batch exported 1 EPUB files; 0 failed, 0 skipped.", app.status.value)

    def test_batch_export_confirms_existing_output_files(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.batch_project = _FakeBatchProject()
        item = app.batch_project.add_pdf(Path("/tmp/a.pdf"))
        item.output_path = Path("/tmp/out/a.epub")
        app.batch_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.root = SimpleNamespace(update_idletasks=lambda: None, after=lambda _delay, callback: callback())

        with patch("epub_layout_gui.filedialog.askdirectory", return_value="/tmp/out"):
            with patch("epub_layout_gui.Path.exists", return_value=True):
                with patch("epub_layout_gui.messagebox.askyesno", return_value=False) as askyesno:
                    with patch("epub_layout_gui.messagebox.showinfo"):
                        app.export_ready_batch()

        askyesno.assert_called_once()
        self.assertIsNone(app.batch_project.exported_all_dir)
        self.assertEqual("Batch export cancelled.", app.status.value)

    def test_store_metadata_fields_updates_cover_only_option(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2")])
        app.title_var = SimpleNamespace(get=lambda: "Book")
        app.author_var = SimpleNamespace(get=lambda: "")
        app.language_var = SimpleNamespace(get=lambda: "zh-Hant")
        app.exclude_cover_var = _FakeBool(True)

        app._store_metadata_fields()

        self.assertTrue(app.model.exclude_cover_from_reading)

    def test_load_metadata_fields_reads_cover_only_option(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2")])
        app.model.title = "Book"
        app.model.author = ""
        app.model.language = "zh-Hant"
        app.model.exclude_cover_from_reading = True
        app.title_var = SimpleNamespace(set=lambda value: setattr(app, "title_value", value))
        app.author_var = SimpleNamespace(set=lambda value: setattr(app, "author_value", value))
        app.language_var = SimpleNamespace(set=lambda value: setattr(app, "language_value", value))
        app.exclude_cover_var = _FakeBool(False)

        app._load_metadata_fields()

        self.assertTrue(app.exclude_cover_var.get())


if __name__ == "__main__":
    unittest.main()
