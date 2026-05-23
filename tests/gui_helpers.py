from pathlib import Path
from types import SimpleNamespace

from manga_pdf_to_epub.epub_layout_gui import EpubLayoutApp


class FakeBool:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeCanvas:
    def delete(self, *_args):
        pass

    def winfo_width(self):
        return 400

    def winfo_height(self):
        return 300


class FakeListbox:
    def __init__(self, selection=0, yview=(0.4, 0.7)):
        self.items = []
        self.selection = selection
        self.current_yview = yview
        self.moved_to = None
        self.item_options = {}

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

    def itemconfig(self, index, **kwargs):
        self.item_options[index] = kwargs


class FakeStatus:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class FakeRoot:
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


class FakeWidget:
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


class FakeDeleteModel:
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
        self.entries.insert(index, entry(f"Image {index + 1}"))

    def insert_blank(self, index):
        self.entries.insert(index, entry(f"Blank {index + 1}", is_blank=True))

    def export_selected_images(self, indexes, output_dir):
        return [output_dir / f"{index + 1:04d}.jpg" for index in indexes], 0

    def move_entry(self, from_index, to_index):
        entry_to_move = self.entries.pop(from_index)
        self.entries.insert(to_index, entry_to_move)
        return to_index


class FakePresetModel(FakeDeleteModel):
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


def entry(label, is_blank=False):
    source_index = None if is_blank else int(label.split()[-1])
    return SimpleNamespace(label=label, is_blank=is_blank, source_index=source_index)


def inserted_entry(label):
    return SimpleNamespace(label=label, is_blank=False, source_index=None)


def app_for_preview(entries, selected):
    app = EpubLayoutApp.__new__(EpubLayoutApp)
    app.preview = FakeCanvas()
    app.photo_refs = []
    app.model = SimpleNamespace(entries=entries)
    app.apple_preview = FakeBool(True)
    app.selected_index = lambda: selected
    app.draws = []
    app._draw_entry = lambda entry, x, y, width, height: app.draws.append((entry.label, x))
    return app
