import unittest
import json
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
        if self.selection is None:
            return ()
        if isinstance(self.selection, tuple):
            return self.selection
        if isinstance(self.selection, list):
            return tuple(self.selection)
        return (self.selection,)

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
        self.packed = False

    def add(self, child, **_kwargs):
        self.children.append(child)

    def pack(self, *args, **kwargs):
        self.pack_args.append((args, kwargs))
        self.packed = True

    def pack_forget(self):
        self.packed = False

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

    def insert_blank(self, index):
        self.entries.insert(index, _entry(f"Blank {index + 1}", is_blank=True))

    def export_selected_images(self, indexes, output_dir):
        return [output_dir / f"{index + 1:04d}.jpg" for index in indexes], 0

    def move_entry(self, from_index, to_index):
        entry = self.entries.pop(from_index)
        self.entries.insert(to_index, entry)
        return to_index


class _FakePresetModel(_FakeDeleteModel):
    def __init__(self, entries):
        super().__init__(entries)
        self.applied_presets = []
        self.title = "Book"
        self.author = ""
        self.language = "zh-Hant"
        self.source_path = Path("/tmp/book.pdf")
        self.exclude_cover_from_reading = False

    def apply_preset(self, preset_path):
        self.applied_presets.append(Path(preset_path))


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
        self.assertEqual(("Edit", "Book", "Series"), EpubLayoutApp._inspector_tab_titles())

    def test_edit_inspector_sections_follow_layout_workflow(self):
        self.assertEqual(("Insert", "Delete", "Repair"), EpubLayoutApp._edit_section_titles())

    def test_series_inspector_sections_follow_series_workflow(self):
        self.assertEqual(("Review", "Export"), EpubLayoutApp._series_section_titles())

    def test_metadata_labels_switch_between_single_pdf_and_series_modes(self):
        self.assertEqual(("Title", "Author"), EpubLayoutApp._metadata_label_texts(series_mode=False))
        self.assertEqual(("Series Title", "Series Author"), EpubLayoutApp._metadata_label_texts(series_mode=True))

    def test_inspector_tab_state_switches_active_tab(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.inspector_tabs = {
            "Edit": SimpleNamespace(raise_count=0, tkraise=lambda: None),
            "Series": SimpleNamespace(raise_count=0, tkraise=lambda: None),
        }
        app.inspector_tab_buttons = {}

        app._show_inspector_tab("Series")

        self.assertEqual("Series", app.active_inspector_tab)

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

    def test_series_tab_omits_old_batch_template_workflow(self):
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
        self.assertNotIn("Use Current Layout As Template", labels)
        self.assertNotIn("Load Template Preset...", labels)
        self.assertNotIn("Validate Batch...", labels)
        self.assertNotIn("Export Ready...", labels)
        self.assertNotIn("Export All...", labels)
        self.assertIn("Mark Selected Volume Ready", labels)
        self.assertIn("Unready Selected", labels)
        self.assertIn("Export Ready Series...", labels)
        self.assertNotIn("Delete First...", labels)
        self.assertNotIn("Delete Last...", labels)
        self.assertNotIn("Delete Range...", labels)

    def test_toolbar_buttons_use_even_left_to_right_spacing(self):
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
        frames = []
        buttons = []

        class FakeFrame(_FakeWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.parent = args[0] if args else None
                self.options = kwargs
                frames.append(self)

        class FakePanedwindow(FakeFrame):
            pass

        class FakeButton(_FakeWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.parent = args[0] if args else None
                self.options = kwargs
                buttons.append(self)

        class FakeLabel(FakeButton):
            pass

        class FakeCheckbutton(FakeButton):
            pass

        class FakeListbox(_FakeWidget):
            def bind(self, *_args, **_kwargs):
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

        toolbar = frames[0]
        toolbar_rows = [frame for frame in frames if frame.parent is toolbar]

        self.assertEqual(1, len(toolbar_rows))
        toolbar_row = toolbar_rows[0]
        self.assertEqual("center", toolbar_row.pack_args[-1][1].get("anchor"))
        toolbar_buttons = [button for button in buttons if button.parent is toolbar_row]

        self.assertEqual(
            [
                "Import Series...",
                "Open PDF",
                "Export EPUB",
                "Export Ready Series...",
                "Open Project...",
                "Save Project...",
                "Save Preset",
                "Load Preset",
                "Command Palette...",
            ],
            [button.options.get("text") for button in toolbar_buttons],
        )
        for button in toolbar_buttons[:-1]:
            pack_kwargs = button.pack_args[-1][1]
            self.assertEqual("left", pack_kwargs.get("side"))
            self.assertEqual((0, 8), pack_kwargs.get("padx"))
        last_pack_kwargs = toolbar_buttons[-1].pack_args[-1][1]
        self.assertEqual("left", last_pack_kwargs.get("side"))
        self.assertEqual((0, 0), last_pack_kwargs.get("padx"))

    def test_single_pdf_navigation_hides_series_volumes_by_default(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = _FakeRoot()
        app.apple_preview = _FakeBool(True)
        app.series_project = None
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
        self.assertIsNot(app.series_list, app.page_list)
        self.assertFalse(app.series_pane.packed)
        self.assertTrue(app.spine_pane.packed)

    def test_left_navigation_places_series_volumes_beside_spine_order(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = _FakeRoot()
        app.apple_preview = _FakeBool(True)
        app.series_project = SimpleNamespace(volumes=[])
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

        class FakeFrame(_FakeWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.parent = args[0] if args else None
                self.options = kwargs

        class FakePanedwindow(FakeFrame):
            pass

        class FakeButton(FakeFrame):
            pass

        class FakeLabel(FakeFrame):
            pass

        class FakeCheckbutton(FakeFrame):
            pass

        class FakeListbox(FakeFrame):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.options = kwargs

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

        self.assertEqual(app.series_list.parent, app.series_pane)
        self.assertEqual(app.page_list.parent, app.spine_pane)
        self.assertTrue(app.series_pane.packed)
        self.assertTrue(app.spine_pane.packed)
        self.assertIsNot(app.series_list.parent, app.page_list.parent)
        self.assertEqual("extended", app.series_list.options.get("selectmode"))

    def test_series_navigation_stacks_when_default_width_is_too_narrow(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.series_project = SimpleNamespace(volumes=[])
        app.series_pane = _FakeWidget()
        app.spine_pane = _FakeWidget()

        app._sync_navigation_mode(available_width=520)

        self.assertTrue(app.series_pane.packed)
        self.assertTrue(app.spine_pane.packed)
        self.assertEqual("top", app.series_pane.pack_args[-1][1]["side"])
        self.assertEqual("top", app.spine_pane.pack_args[-1][1]["side"])

    def test_series_navigation_uses_columns_when_width_allows(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.series_project = SimpleNamespace(volumes=[])
        app.series_pane = _FakeWidget()
        app.spine_pane = _FakeWidget()

        app._sync_navigation_mode(available_width=760)

        self.assertEqual("left", app.series_pane.pack_args[-1][1]["side"])
        self.assertEqual("left", app.spine_pane.pack_args[-1][1]["side"])

    def test_import_series_reveals_series_navigation(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.series_pane = _FakeWidget()
        app.spine_pane = _FakeWidget()
        app.series_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.workspace_status = _FakeStatus()
        app._load_metadata_fields = lambda: setattr(app, "metadata_loaded", True)
        app.refresh_workspace_status = lambda: None

        with patch(
            "epub_layout_gui.filedialog.askopenfilenames",
            return_value=("/tmp/[晚安,布布][淺野一二O] Vol.02.pdf", "/tmp/[晚安,布布][淺野一二O] Vol.01.pdf"),
        ):
            app.import_series()

        self.assertTrue(app.series_pane.packed)
        self.assertTrue(app.spine_pane.packed)

    def test_import_series_creates_project_and_populates_volume_list(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.series_list = _FakeListbox(selection=0)
        app.series_pane = _FakeWidget()
        app.spine_pane = _FakeWidget()
        app.status = _FakeStatus()
        app.workspace_status = _FakeStatus()
        app._load_metadata_fields = lambda: setattr(app, "metadata_loaded", True)
        app.refresh_workspace_status = lambda: None

        with patch(
            "epub_layout_gui.filedialog.askopenfilenames",
            return_value=("/tmp/[晚安,布布][淺野一二O] Vol.02.pdf", "/tmp/[晚安,布布][淺野一二O] Vol.01.pdf"),
        ):
            app.import_series()

        self.assertEqual("晚安,布布", app.series_project.title)
        self.assertEqual("淺野一二O", app.series_project.author)
        self.assertTrue(app.metadata_loaded)
        self.assertEqual(
            [
                "Unreviewed Vol.01 [晚安,布布][淺野一二O] Vol.01.pdf",
                "Unreviewed Vol.02 [晚安,布布][淺野一二O] Vol.02.pdf",
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
        self.assertIs(first, app.active_series_volume)
        self.assertTrue(app.metadata_loaded)
        self.assertTrue(app.list_refreshed)
        self.assertTrue(app.preview_refreshed)
        self.assertEqual("Loaded Series Vol.01.", app.status.value)

    def test_mark_selected_series_volume_ready_updates_series_list(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        volume = SimpleNamespace(status="Edited", volume_number=1, pdf_path=Path("/tmp/vol01.pdf"))
        project = SimpleNamespace(
            volumes=[volume],
            mark_ready=lambda selected: setattr(selected, "status", "Ready"),
        )
        app.series_project = project
        app.series_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app.mark_selected_series_volume_ready()

        self.assertEqual("Ready", volume.status)
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)
        self.assertEqual("Marked Vol.01 ready.", app.status.value)

    def test_mark_selected_series_volume_ready_updates_all_selected_volumes(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        volumes = [
            SimpleNamespace(status="Edited", volume_number=1, pdf_path=Path("/tmp/vol01.pdf")),
            SimpleNamespace(status="Edited", volume_number=2, pdf_path=Path("/tmp/vol02.pdf")),
            SimpleNamespace(status="Unreviewed", volume_number=7, pdf_path=Path("/tmp/vol07.pdf")),
        ]
        project = SimpleNamespace(
            volumes=volumes,
            mark_ready=lambda selected: setattr(selected, "status", "Ready"),
        )
        app.series_project = project
        app.series_list = _FakeListbox(selection=(0, 1, 2))
        app.status = _FakeStatus()
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app.mark_selected_series_volume_ready()

        self.assertEqual(["Ready", "Ready", "Ready"], [volume.status for volume in volumes])
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)
        self.assertEqual("Marked 3 volumes ready.", app.status.value)

    def test_unready_selected_restores_only_selected_volume_status(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        volumes = [
            SimpleNamespace(status="Edited", volume_number=index + 1, pdf_path=Path(f"/tmp/vol{index + 1:02d}.pdf"))
            for index in range(13)
        ]
        volumes[6].status = "Unreviewed"
        project = SimpleNamespace(
            volumes=volumes,
            mark_ready=lambda selected: setattr(selected, "status", "Ready"),
        )
        app.series_project = project
        app.series_list = _FakeListbox(selection=tuple(range(13)))
        app.status = _FakeStatus()
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app.mark_selected_series_volume_ready()
        app.series_list.selection = (6,)
        restored = app.unready_selected()

        self.assertTrue(restored)
        self.assertEqual("Unreviewed", volumes[6].status)
        self.assertEqual(["Ready"] * 12, [volume.status for index, volume in enumerate(volumes) if index != 6])
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)
        self.assertEqual("Restored Vol.07 status.", app.status.value)

    def test_unready_selected_without_selection_restores_latest_ready_batch(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        volumes = [
            SimpleNamespace(status="Edited", volume_number=1, pdf_path=Path("/tmp/vol01.pdf")),
            SimpleNamespace(status="Unreviewed", volume_number=2, pdf_path=Path("/tmp/vol02.pdf")),
        ]
        project = SimpleNamespace(
            volumes=volumes,
            mark_ready=lambda selected: setattr(selected, "status", "Ready"),
        )
        app.series_project = project
        app.series_list = _FakeListbox(selection=(0, 1))
        app.status = _FakeStatus()
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app.mark_selected_series_volume_ready()
        app.series_list.selection = None
        app.unready_selected()

        self.assertEqual(["Edited", "Unreviewed"], [volume.status for volume in volumes])
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)
        self.assertEqual("Restored 2 volume statuses.", app.status.value)

    def test_recover_last_deleted_falls_back_to_unready_selected(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        volume = SimpleNamespace(status="Edited", volume_number=1, pdf_path=Path("/tmp/vol01.pdf"))
        project = SimpleNamespace(
            volumes=[volume],
            mark_ready=lambda selected: setattr(selected, "status", "Ready"),
        )
        app.model = _FakeDeleteModel([_entry("Page 1")])
        app.deleted_entries = []
        app.series_project = project
        app.series_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app.mark_selected_series_volume_ready()
        app.recover_last_deleted()

        self.assertEqual("Edited", volume.status)
        self.assertEqual("Restored Vol.01 status.", app.status.value)

    def test_unready_selected_without_history_is_noop(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = _FakeStatus()

        restored = app.unready_selected()

        self.assertFalse(restored)
        self.assertIsNone(app.status.value)

    def test_unready_selected_with_unmatched_selection_keeps_ready_history(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        volumes = [
            SimpleNamespace(status="Edited", volume_number=1, pdf_path=Path("/tmp/vol01.pdf")),
            SimpleNamespace(status="Edited", volume_number=2, pdf_path=Path("/tmp/vol02.pdf")),
        ]
        project = SimpleNamespace(
            volumes=volumes,
            mark_ready=lambda selected: setattr(selected, "status", "Ready"),
        )
        app.series_project = project
        app.series_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app.mark_selected_series_volume_ready()
        app.series_list.selection = (1,)
        restored = app.unready_selected()

        self.assertFalse(restored)
        self.assertEqual(["Ready", "Edited"], [volume.status for volume in volumes])
        self.assertEqual("No selected ready marks to undo.", app.status.value)
        self.assertEqual(1, len(app.ready_status_undo))

    def test_export_ready_series_uses_series_project(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = _FakeStatus()
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)
        app.root = _FakeRoot()
        events = [{"status": "summary", "exported": 1, "failed": 0, "skipped": 2, "warnings": 3}]
        project = SimpleNamespace(
            exported_to=None,
            volumes=[],
            validate_ready=lambda output_dir: {"ready": 1, "failed": 0, "warnings": 0},
            export_ready_iter=lambda output_dir: setattr(project, "exported_to", output_dir) or iter(events),
        )
        app.series_project = project
        app._run_background = lambda _status, work, on_success: on_success(work()) or True

        with patch("epub_layout_gui.filedialog.askdirectory", return_value="/tmp/out"):
            app.export_ready_series()

        self.assertEqual(Path("/tmp/out"), project.exported_to)
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)
        self.assertEqual("Series exported 1 volumes; 0 failed, 2 skipped, 3 warnings.", app.status.value)

    def test_export_ready_series_runs_in_background(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = _FakeStatus()
        app.refresh_series_list = lambda: None
        app.refresh_workspace_status = lambda: None
        app.root = _FakeRoot()
        events = [{"status": "summary", "exported": 1, "failed": 0, "skipped": 0, "warnings": 0}]
        project = SimpleNamespace(
            volumes=[],
            validate_ready=lambda output_dir: {"ready": 1, "failed": 0, "warnings": 0},
            export_ready_iter=lambda output_dir: iter(events),
        )
        app.series_project = project
        app._run_background = lambda status, work, on_success: setattr(app, "background_call", (status, work, on_success)) or True

        with patch("epub_layout_gui.filedialog.askdirectory", return_value="/tmp/out"):
            app.export_ready_series()

        self.assertEqual("Exporting ready series...", app.background_call[0])
        self.assertEqual({"exported": 1, "failed": 0, "skipped": 0, "warnings": 0}, app.background_call[1]())

    def test_export_ready_series_background_work_consumes_progress_events(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = _FakeRoot()
        app.status = _FakeStatus()
        app.refresh_series_list = lambda: setattr(app, "series_refresh_count", getattr(app, "series_refresh_count", 0) + 1)
        app.refresh_workspace_status = lambda: None
        app._open_series_export_progress = lambda: setattr(app, "progress_opened", True)
        app._finish_series_export_progress = lambda summary: setattr(app, "finished_summary", summary)
        events = [
            {"volume_number": 1, "status": "started", "output_path": Path("/tmp/out/Series Vol.01.epub")},
            {"volume_number": 1, "status": "exported", "output_path": Path("/tmp/out/Series Vol.01.epub")},
            {"status": "summary", "exported": 1, "failed": 0, "skipped": 0, "warnings": 0},
        ]
        project = SimpleNamespace(
            volumes=[],
            validate_ready=lambda output_dir: {"ready": 1, "failed": 0, "warnings": 0},
            export_ready_iter=lambda output_dir: iter(events),
        )
        app.series_project = project
        app._run_background = lambda status, work, on_success: setattr(app, "background_call", (status, work, on_success)) or True

        with patch("epub_layout_gui.filedialog.askdirectory", return_value="/tmp/out"):
            app.export_ready_series()

        summary = app.background_call[1]()

        self.assertEqual({"exported": 1, "failed": 0, "skipped": 0, "warnings": 0}, summary)
        self.assertEqual("Exported Vol.01.", app.status.value)
        self.assertEqual(1, app.series_refresh_count)

    def test_series_export_opens_and_finishes_progress_state(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = _FakeStatus()
        app.refresh_series_list = lambda: None
        app.refresh_workspace_status = lambda: None
        app.root = _FakeRoot()
        events = [{"status": "summary", "exported": 1, "failed": 0, "skipped": 0, "warnings": 0}]
        app.series_project = SimpleNamespace(
            volumes=[],
            validate_ready=lambda output_dir: {"ready": 1, "failed": 0, "warnings": 0},
            export_ready_iter=lambda output_dir: iter(events),
        )
        app._run_background = lambda status, work, on_success: setattr(app, "background_call", (status, work, on_success)) or True

        with patch("epub_layout_gui.filedialog.askdirectory", return_value="/tmp/out"):
            app.export_ready_series()

        self.assertEqual("Exporting ready series...", app.series_export_progress["current"])
        app.background_call[2](app.background_call[1]())
        self.assertEqual("Close", app.series_export_progress["close_text"])
        self.assertEqual("1 exported, 0 failed, 0 skipped, 0 warnings", app.series_export_progress["summary"])

    def test_series_export_progress_reports_started_volume(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = _FakeStatus()
        app.series_export_progress = {}

        app._series_export_progress({"volume_number": 2, "status": "started"})

        self.assertEqual("Exporting Vol.02.", app.status.value)
        self.assertEqual("Exporting Vol.02.", app.series_export_progress["current"])

    def test_export_ready_series_busy_state_blocks_second_export(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = _FakeStatus()
        app.series_project = SimpleNamespace(export_ready_iter=lambda output_dir: iter([]))
        app._busy = True

        with patch("epub_layout_gui.filedialog.askdirectory", return_value="/tmp/out"):
            app.export_ready_series()

        self.assertEqual("Another operation is already running.", app.status.value)

    def test_export_ready_series_shows_warning_summary_before_background_export(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = _FakeStatus()
        app.root = _FakeRoot()
        app.output_dir = Path("/tmp")
        volume = SimpleNamespace(volume_number=1, status="Ready", warnings=["check page count"], error=None)
        project = SimpleNamespace(
            volumes=[volume],
            validate_ready=lambda output_dir: {"ready": 1, "failed": 0, "warnings": 1},
            export_ready_iter=lambda output_dir: iter([{"status": "summary", "exported": 1, "failed": 0, "skipped": 0, "warnings": 1}]),
        )
        app.series_project = project
        app._run_background = lambda status, work, on_success: setattr(app, "background_call", (status, work, on_success)) or True
        app._open_series_export_progress = lambda: setattr(app, "progress_opened", True)

        with patch("epub_layout_gui.filedialog.askdirectory", return_value="/tmp/out"):
            with patch("epub_layout_gui.messagebox.showwarning") as showwarning:
                app.export_ready_series()

        showwarning.assert_called_once()
        self.assertIn("Vol.01: check page count", showwarning.call_args.args[1])
        self.assertTrue(app.progress_opened)
        self.assertEqual("Exporting ready series...", app.background_call[0])

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
        app.model = SimpleNamespace(entries=[_entry("Page 1"), _entry("Page 2")])
        app.series_project = SimpleNamespace(volumes=[
            SimpleNamespace(status="Ready"),
            SimpleNamespace(status="Edited"),
            SimpleNamespace(status="Failed"),
            SimpleNamespace(status="Unreviewed"),
        ])

        self.assertEqual("Pages: 2 | Series: 4 | Ready: 1 | Edited: 1 | Failed: 1", app._workspace_summary())

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

        with patch("epub_layout_gui.tk.PhotoImage", return_value=SimpleNamespace(width=lambda: 10, height=lambda: 20)) as photo:
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

    def test_insert_blank_marks_active_series_volume_edited(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1")])
        volume = SimpleNamespace(status="Unreviewed", volume_number=1)
        app.active_series_volume = volume
        app.series_project = SimpleNamespace(volumes=[volume])
        app.series_list = _FakeListbox(selection=0)
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app.insert_blank(before=False)

        self.assertEqual("Edited", volume.status)
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)

    def test_insert_blank_in_single_pdf_mode_does_not_require_series_state(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1")])
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app.insert_blank(before=False)

        self.assertEqual(["Page 1", "Blank 2"], [entry.label for entry in app.model.entries])
        self.assertFalse(hasattr(app, "series_refreshed"))

    def test_refresh_after_layout_edit_centralizes_selection_preview_and_edit_state(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2")])
        volume = SimpleNamespace(status="Ready", volume_number=1)
        app.active_series_volume = volume
        app.series_project = SimpleNamespace(volumes=[volume])
        app.series_list = _FakeListbox(selection=0)
        app.page_list = _FakeListbox(selection=0)
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app._refresh_after_layout_edit(select_index=1)

        self.assertTrue(app.preserved_yview)
        self.assertEqual(1, app.page_list.selection)
        self.assertTrue(app.preview_refreshed)
        self.assertEqual("Edited", volume.status)
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)

    def test_set_selected_as_cover_marks_ready_series_volume_edited(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2")])
        volume = SimpleNamespace(status="Ready", volume_number=1)
        app.active_series_volume = volume
        app.series_project = SimpleNamespace(volumes=[volume])
        app.series_list = _FakeListbox(selection=0)
        app.page_list = _FakeListbox(selection=1)
        app.status = _FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app.set_selected_as_cover()

        self.assertEqual("Edited", volume.status)
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)

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
        app.series_project = None
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
        app.series_project = None
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
        app.series_project = None
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

    def test_hidden_legacy_gui_actions_are_removed(self):
        removed_method_names = (
            "normalize" + "_export_order",
            "use_current_layout_as" + "_batch_template",
            "load_batch_template" + "_from_preset",
            "add_batch" + "_pdfs",
            "validate" + "_batch",
            "export_ready" + "_batch",
            "export_all" + "_batch",
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

    def test_store_metadata_fields_updates_cover_only_option(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2")])
        app.series_project = None
        app.title_var = SimpleNamespace(get=lambda: "Book")
        app.author_var = SimpleNamespace(get=lambda: "")
        app.language_var = SimpleNamespace(get=lambda: "zh-Hant")
        app.exclude_cover_var = _FakeBool(True)

        app._store_metadata_fields()

        self.assertTrue(app.model.exclude_cover_from_reading)

    def test_store_metadata_fields_updates_series_metadata_in_series_mode(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1")])
        app.model.source_path = Path("/tmp/[晚安,布布][淺野一二O] Vol.01.pdf")
        app.model.title = "晚安,布布 Vol.01"
        app.model.author = "淺野一二O"
        app.model.language = "ja"
        app.model.exclude_cover_from_reading = False
        app.series_project = SimpleNamespace(title="Old", author="", language="zh-Hant")
        app.title_var = SimpleNamespace(get=lambda: "晚安,布布")
        app.author_var = SimpleNamespace(get=lambda: "淺野一二O")
        app.language_var = SimpleNamespace(get=lambda: "ja")
        app.exclude_cover_var = _FakeBool(True)

        app._store_metadata_fields()

        self.assertEqual("晚安,布布", app.series_project.title)
        self.assertEqual("淺野一二O", app.series_project.author)
        self.assertEqual("ja", app.series_project.language)
        self.assertEqual("晚安,布布 Vol.01", app.model.title)
        self.assertTrue(app.model.exclude_cover_from_reading)

    def test_load_metadata_fields_reads_cover_only_option(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2")])
        app.model.title = "Book"
        app.model.author = ""
        app.model.language = "zh-Hant"
        app.model.exclude_cover_from_reading = True
        app.series_project = None
        app.title_var = SimpleNamespace(set=lambda value: setattr(app, "title_value", value))
        app.author_var = SimpleNamespace(set=lambda value: setattr(app, "author_value", value))
        app.language_var = SimpleNamespace(set=lambda value: setattr(app, "language_value", value))
        app.exclude_cover_var = _FakeBool(False)

        app._load_metadata_fields()

        self.assertTrue(app.exclude_cover_var.get())

    def test_load_metadata_fields_reads_series_metadata_in_series_mode(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1")])
        app.model.title = "晚安,布布 Vol.01"
        app.model.author = "淺野一二O"
        app.model.language = "ja"
        app.model.exclude_cover_from_reading = True
        app.series_project = SimpleNamespace(title="晚安,布布", author="淺野一二O", language="ja")
        app.title_var = SimpleNamespace(set=lambda value: setattr(app, "title_value", value))
        app.author_var = SimpleNamespace(set=lambda value: setattr(app, "author_value", value))
        app.language_var = SimpleNamespace(set=lambda value: setattr(app, "language_value", value))
        app.exclude_cover_var = _FakeBool(False)

        app._load_metadata_fields()

        self.assertEqual("晚安,布布", app.title_value)
        self.assertEqual("淺野一二O", app.author_value)
        self.assertEqual("ja", app.language_value)
        self.assertTrue(app.exclude_cover_var.get())

    def test_load_preset_single_pdf_mode_applies_to_current_model_without_scope_prompt(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakePresetModel([_entry("Page 1")])
        app.series_project = None
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app._load_metadata_fields = lambda: setattr(app, "metadata_loaded", True)
        app.refresh_list = lambda: setattr(app, "list_refreshed", True)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        with patch("epub_layout_gui.filedialog.askopenfilename", return_value="/tmp/layout.json"), \
            patch("epub_layout_gui.simpledialog.askstring") as askstring:
            app.load_preset()

        self.assertEqual([Path("/tmp/layout.json")], app.model.applied_presets)
        askstring.assert_not_called()
        self.assertEqual("Loaded preset: layout.json", app.status.value)

    def test_load_preset_series_mode_prompts_scope_and_applies_to_matching_volumes(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        active_model = _FakePresetModel([_entry("Page 1")])
        inactive_model = _FakePresetModel([_entry("Page 1")])
        volumes = [
            SimpleNamespace(volume_number=1, status="Ready", layout_model=active_model),
            SimpleNamespace(volume_number=2, status="Unreviewed", layout_model=inactive_model),
            SimpleNamespace(volume_number=7, status="Unreviewed", layout_model=_FakePresetModel([_entry("Page 1")])),
        ]
        project = SimpleNamespace(
            volumes=volumes,
            model_for_volume=lambda volume: volume.layout_model,
            volumes_for_scope=lambda scope: [volumes[0], volumes[2]] if scope == "1,7" else [],
            generated_title=lambda volume: f"Series Vol.{volume.volume_number:02d}",
            title="Series",
            author="Author",
            language="ja",
        )
        app.model = active_model
        app.series_project = project
        app.active_series_volume = volumes[0]
        app.series_list = _FakeListbox(selection=0)
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app._load_metadata_fields = lambda: setattr(app, "metadata_loaded", True)
        app.refresh_list = lambda: setattr(app, "list_refreshed", True)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        with patch("epub_layout_gui.filedialog.askopenfilename", return_value="/tmp/layout.json"), \
            patch("epub_layout_gui.simpledialog.askstring", return_value="1,7"):
            app.load_preset()

        self.assertEqual([Path("/tmp/layout.json")], volumes[0].layout_model.applied_presets)
        self.assertEqual([], volumes[1].layout_model.applied_presets)
        self.assertEqual([Path("/tmp/layout.json")], volumes[2].layout_model.applied_presets)
        self.assertEqual(["Edited", "Unreviewed", "Edited"], [volume.status for volume in volumes])
        self.assertTrue(app.list_refreshed)
        self.assertTrue(app.preview_refreshed)
        self.assertTrue(app.series_refreshed)
        self.assertEqual("Loaded preset for 2 volumes: layout.json", app.status.value)

    def test_load_preset_series_mode_cancels_when_scope_is_blank(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakePresetModel([_entry("Page 1")])
        app.series_project = SimpleNamespace(volumes=[])
        app.status = _FakeStatus()

        with patch("epub_layout_gui.filedialog.askopenfilename", return_value="/tmp/layout.json"), \
            patch("epub_layout_gui.simpledialog.askstring", return_value=""):
            app.load_preset()

        self.assertEqual([], app.model.applied_presets)
        self.assertIsNone(app.status.value)

    def test_save_project_writes_series_project_payload(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = _FakeStatus()
        app.model = _FakeDeleteModel([_entry("Page 1")])
        app._store_metadata_fields = lambda: setattr(app, "metadata_stored", True)
        project = SimpleNamespace(to_payload=lambda project_path: {"version": 1, "path": str(project_path)})
        app.series_project = project

        with patch("epub_layout_gui.filedialog.asksaveasfilename", return_value="/tmp/series-project.json"):
            app.save_project()

        self.assertTrue(app.metadata_stored)
        self.assertEqual(
            {"version": 1, "path": "/tmp/series-project.json"},
            json.loads(Path("/tmp/series-project.json").read_text(encoding="utf-8")),
        )
        self.assertEqual("Saved project: series-project.json", app.status.value)
        Path("/tmp/series-project.json").unlink()

    def test_save_project_records_active_volume_number(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = _FakeStatus()
        app.model = None
        active = SimpleNamespace(volume_number=2)
        project = SimpleNamespace(
            active_volume_number=None,
            to_payload=lambda project_path: {"version": 1, "active": project.active_volume_number},
        )
        app.series_project = project
        app.active_series_volume = active

        with patch("epub_layout_gui.filedialog.asksaveasfilename", return_value="/tmp/active-series-project.json"):
            app.save_project()

        self.assertEqual(2, project.active_volume_number)
        Path("/tmp/active-series-project.json").unlink()

    def test_open_project_loads_series_project_and_refreshes_workspace(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.series_list = _FakeListbox(selection=0)
        app.page_list = _FakeListbox(selection=0)
        app.series_pane = _FakeWidget()
        app.spine_pane = _FakeWidget()
        app.status = _FakeStatus()
        app.deleted_entries = ["old"]
        app.ready_status_undo = ["old"]
        app.thumbnail_cache = {"old": object()}
        app._load_metadata_fields = lambda: setattr(app, "metadata_loaded", True)
        app.refresh_list = lambda: setattr(app, "list_refreshed", True)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)
        payload_path = Path("/tmp/open-series-project.json")
        payload_path.write_text(json.dumps({"version": 1}), encoding="utf-8")
        volume = SimpleNamespace(pdf_path=Path("/tmp/vol01.pdf"), volume_number=1, status="Ready")
        loaded_project = SimpleNamespace(volumes=[volume], title="Series", author="", language="zh-Hant")

        with patch("epub_layout_gui.filedialog.askopenfilename", return_value=str(payload_path)), \
            patch("epub_layout_gui.SeriesProject.from_payload", return_value=loaded_project) as from_payload:
            app.open_project()

        from_payload.assert_called_once_with({"version": 1}, payload_path)
        self.assertIs(loaded_project, app.series_project)
        self.assertIsNone(app.model)
        self.assertIsNone(app.pdf_path)
        self.assertIsNone(app.active_series_volume)
        self.assertEqual([], app.deleted_entries)
        self.assertEqual([], app.ready_status_undo)
        self.assertEqual({}, app.thumbnail_cache)
        self.assertTrue(app.metadata_loaded)
        self.assertTrue(app.list_refreshed)
        self.assertTrue(app.preview_refreshed)
        self.assertTrue(app.workspace_refreshed)
        self.assertEqual(["Ready Vol.01 vol01.pdf"], app.series_list.items)
        self.assertEqual("Opened project: open-series-project.json", app.status.value)
        payload_path.unlink()

    def test_open_project_restores_active_series_selection_when_saved_volume_exists(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.series_list = _FakeListbox(selection=0)
        app.page_list = _FakeListbox(selection=0)
        app.series_pane = _FakeWidget()
        app.spine_pane = _FakeWidget()
        app.status = _FakeStatus()
        app.deleted_entries = []
        app.ready_status_undo = []
        app.thumbnail_cache = {}
        app._load_metadata_fields = lambda: None
        app.refresh_preview = lambda: None
        app.refresh_workspace_status = lambda: None
        payload_path = Path("/tmp/open-active-series-project.json")
        payload_path.write_text(json.dumps({"version": 1}), encoding="utf-8")
        volumes = [
            SimpleNamespace(pdf_path=Path("/tmp/vol01.pdf"), volume_number=1, status="Ready"),
            SimpleNamespace(pdf_path=Path("/tmp/vol02.pdf"), volume_number=2, status="Edited"),
        ]
        loaded_project = SimpleNamespace(volumes=volumes, title="Series", author="", language="zh-Hant", active_volume_number=2)

        with patch("epub_layout_gui.filedialog.askopenfilename", return_value=str(payload_path)), \
            patch("epub_layout_gui.SeriesProject.from_payload", return_value=loaded_project):
            app.open_project()

        self.assertIs(volumes[1], app.active_series_volume)
        self.assertEqual(1, app.series_list.selection)
        payload_path.unlink()

    def test_validate_series_updates_warnings_and_status(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = _FakeStatus()
        app.output_dir = Path("/tmp")
        volume = SimpleNamespace(volume_number=1, status="Ready", warnings=["check"], error=None)
        project = SimpleNamespace(
            volumes=[volume],
            validate_all=lambda output_dir: {"ready": 1, "failed": 0, "warnings": 1},
        )
        app.series_project = project
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        with patch("epub_layout_gui.messagebox.showwarning"):
            app.validate_series()

        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)
        self.assertEqual("Series validation: 1 ready, 0 failed, 1 warnings.", app.status.value)

    def test_validate_series_shows_warning_summary_dialog(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = _FakeStatus()
        app.output_dir = Path("/tmp")
        volume = SimpleNamespace(volume_number=1, status="Ready", warnings=["check page count"], error=None)
        app.series_project = SimpleNamespace(
            volumes=[volume],
            validate_all=lambda output_dir: {"ready": 1, "failed": 0, "warnings": 1},
        )
        app.refresh_series_list = lambda: None
        app.refresh_workspace_status = lambda: None

        with patch("epub_layout_gui.messagebox.showwarning") as showwarning:
            app.validate_series()

        showwarning.assert_called_once()
        self.assertIn("Vol.01: check page count", showwarning.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
