# Diagnose Window UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the cramped inspector Diagnose tab with a linked Diagnose window that has its own Spine order view, bidirectional selection sync, large preview, and manual `Add Selected As Spread`.

**Architecture:** Keep `EpubLayoutApp` as the owner of model/state and move Diagnose-specific UI into diagnosis modules. The Diagnose window is a `tk.Toplevel` view over shared app state, while selection sync, stale invalidation, and manual spread addition live in `EpubLayoutDiagnosisMixin`.

**Tech Stack:** Python 3.14, Tkinter/ttk, existing `unittest` suite, existing pure diagnosis model in `epub_layout_diagnosis.py`.

---

## File Structure

- Modify `src/manga_pdf_to_epub/epub_layout_diagnosis_gui.py`
  - Keep summary/list helpers.
  - Change `DiagnosisPanel` into the right-side workflow panel for a window.
  - Add `DiagnosisWindow`, which owns `window`, `spine_list`, `preview`, `photo_refs`, and a `DiagnosisPanel`.
- Modify `src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py`
  - Add Diagnose window lifecycle methods.
  - Add main/diagnose spine selection sync.
  - Add diagnosis-window spine refresh and preview refresh.
  - Add `add_selected_spread_from_diagnosis_spine()`.
  - Keep shared state and stale invalidation here.
- Modify `src/manga_pdf_to_epub/epub_layout_gui.py`
  - Replace the full inspector Diagnose tab with an `Open Diagnose Window` entry point.
  - Route main spine selection through sync controller.
  - Keep class under the current guardrail.
- Modify `src/manga_pdf_to_epub/epub_layout_commands.py`
  - Add an `Open Diagnose Window` command if command palette coverage is already expected by tests.
- Modify `tests/test_epub_layout_gui_diagnosis.py`
  - Add focused lifecycle, sync, and manual-add tests.
- Modify `tests/test_epub_layout_gui.py`
  - Update inspector-tab expectations for the new Diagnose entry point.
- Modify `tests/gui_helpers.py`
  - Extend fakes only when a new test needs event binding, focus, or window destroy behavior.
- Modify docs after implementation:
  - `README.md`
  - `docs/diagnosis-workflow.md`

---

### Task 1: Diagnose Window Lifecycle

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_diagnosis_gui.py`
- Modify: `src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py`
- Test: `tests/test_epub_layout_gui_diagnosis.py`

- [ ] **Step 1: Write the failing lifecycle tests**

Add tests near `DiagnosisGuiIntegrationTests`:

```python
class DiagnosisWindowLifecycleTests(unittest.TestCase):
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
        self.assertEqual([(3, 4)], [(item.start_page, item.end_page) for item in app.diagnosis_session.confirmed_spreads()])
```

- [ ] **Step 2: Run lifecycle tests and verify failure**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis.DiagnosisWindowLifecycleTests -v
```

Expected: failure because `open_diagnose_window`, `_diagnose_window_closed`, and `DiagnosisWindow` do not exist.

- [ ] **Step 3: Add `DiagnosisWindow` shell**

In `epub_layout_diagnosis_gui.py`, add:

```python
class DiagnosisWindow:
    def __init__(self, app, parent, callbacks: DiagnosisPanelCallbacks):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("Diagnose Spreads")
        self.window.geometry("1180x760")
        self.window.minsize(980, 620)
        self.window.protocol("WM_DELETE_WINDOW", app._diagnose_window_closed)
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
        self.spine_list.bind("<<ListboxSelect>>", lambda _event: self.app.sync_selection_from_diagnosis())
        ttk.Label(self.center, text="RTL spread preview").pack(anchor=tk.W)
        self.preview = tk.Canvas(self.center, background="#202020", highlightthickness=0)
        self.preview.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.preview.bind("<Configure>", lambda _event: self.app.refresh_diagnosis_preview())
        self.panel = DiagnosisPanel(self.right, callbacks)

    def focus(self) -> None:
        self.window.lift()
        self.window.focus_force()

    def destroy(self) -> None:
        self.window.destroy()
```

- [ ] **Step 4: Add lifecycle controller methods**

In `epub_layout_diagnosis_controller.py`, import `DiagnosisWindow` and add methods to `EpubLayoutDiagnosisMixin`:

```python
def open_diagnose_window(self) -> None:
    if getattr(self, "model", None) is None:
        self.status.set("Open a PDF before opening Diagnose.")
        return
    existing = getattr(self, "diagnosis_window", None)
    if existing is not None:
        existing.focus()
        return
    self.diagnosis_window = DiagnosisWindow(self, self.root, diagnosis_callbacks(self))
    self.refresh_diagnosis_panel()

def _diagnose_window_closed(self) -> None:
    window = getattr(self, "diagnosis_window", None)
    self.diagnosis_window = None
    if window is not None and hasattr(window, "destroy"):
        window.destroy()
```

Update `initialize_diagnosis_state()` to set `app.diagnosis_window = None`.

- [ ] **Step 5: Run lifecycle tests and commit**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis.DiagnosisWindowLifecycleTests -v
PYTHONPATH=src .venv/bin/python -m unittest tests.test_project_guardrails -v
```

Expected: pass.

Commit:

```bash
git add src/manga_pdf_to_epub/epub_layout_diagnosis_gui.py src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py tests/test_epub_layout_gui_diagnosis.py
git commit -m "feat: add diagnose window lifecycle"
```

---

### Task 2: Replace Inspector Panel With Window Entry Point

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_gui.py`
- Modify: `src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py`
- Modify: `src/manga_pdf_to_epub/epub_layout_commands.py`
- Test: `tests/test_epub_layout_gui.py`
- Test: `tests/test_epub_layout_gui_commands.py`
- Test: `tests/test_epub_layout_gui_diagnosis.py`

- [ ] **Step 1: Write failing UI tests**

Update `tests/test_epub_layout_gui.py` to assert the Diagnose inspector tab uses only the window entry:

```python
def test_diagnose_inspector_uses_window_entry_point(self):
    app = EpubLayoutApp.__new__(EpubLayoutApp)
    app.root = FakeRoot()
    app.apple_preview = FakeBool(True)
    app.title_var = SimpleNamespace()
    app.author_var = SimpleNamespace()
    app.language_var = SimpleNamespace()
    app.exclude_cover_var = FakeBool(False)
    app.inspector_tabs = {}
    app.inspector_tab_buttons = {}
    app.status = FakeStatus()
    app.workspace_status = FakeStatus()
    app.refresh_preview = lambda: None
    app.refresh_workspace_status = lambda: None
    app.open_diagnose_window = lambda: setattr(app, "diagnose_opened", True)
    buttons = []

    class FakeFrame(FakeWidget):
        pass

    class FakePanedwindow(FakeWidget):
        pass

    class FakeButton(FakeWidget):
        def __init__(self, *_args, **kwargs):
            super().__init__()
            self.options = kwargs
            buttons.append(self)

    class FakeLabel(FakeButton):
        pass

    class FakeCheckbutton(FakeButton):
        pass

    class FakeListbox(FakeWidget):
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

    with patch("manga_pdf_to_epub.epub_layout_gui.ttk.Frame", FakeFrame), \
        patch("manga_pdf_to_epub.epub_layout_gui.ttk.Panedwindow", FakePanedwindow), \
        patch("manga_pdf_to_epub.epub_layout_gui.ttk.Button", FakeButton), \
        patch("manga_pdf_to_epub.epub_layout_gui.ttk.Label", FakeLabel), \
        patch("manga_pdf_to_epub.epub_layout_gui.ttk.Checkbutton", FakeCheckbutton), \
        patch("manga_pdf_to_epub.epub_layout_gui.ttk.Scrollbar", FakeButton), \
        patch("manga_pdf_to_epub.epub_layout_gui.ttk.Separator", FakeButton), \
        patch("manga_pdf_to_epub.epub_layout_gui.ttk.Entry", FakeButton), \
        patch("manga_pdf_to_epub.epub_layout_gui.tk.Listbox", FakeListbox), \
        patch("manga_pdf_to_epub.epub_layout_gui.tk.Canvas", FakeCanvas):
        app._build_ui()

    labels = [button.options.get("text") for button in buttons]
    self.assertIn("Open Diagnose Window", labels)
    self.assertNotIn("Import Spread Candidates...", labels)
    self.assertNotIn("Run Cross-Page Scan", labels)
```

Add a command-palette test in `tests/test_epub_layout_gui_commands.py`:

```python
def test_command_palette_includes_open_diagnose_window(self):
    commands = [command.label for command in EpubLayoutApp._commands()]

    self.assertIn("Open Diagnose Window", commands)
```

- [ ] **Step 2: Run UI tests and verify failure**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui.EpubLayoutGuiUiTests.test_diagnose_inspector_uses_window_entry_point tests.test_epub_layout_gui_commands.EpubLayoutGuiCommandTests.test_command_palette_includes_open_diagnose_window -v
```

Expected: fail because the full Diagnose panel is still built in the inspector and the command palette lacks the new command.

- [ ] **Step 3: Replace inspector tab build**

In `epub_layout_diagnosis_controller.py`, add:

```python
def build_diagnosis_entry_tab(app, parent) -> None:
    ttk.Button(parent, text="Open Diagnose Window", command=app.open_diagnose_window).pack(fill=tk.X, pady=(6, 0))
```

Import `ttk` if this function lives in the controller module.

In `epub_layout_gui.py`, replace:

```python
build_diagnosis_tab(self, diagnose_tab)
```

with:

```python
build_diagnosis_entry_tab(self, diagnose_tab)
```

Update imports accordingly.

- [ ] **Step 4: Add command palette entry**

In `epub_layout_commands.py`, add:

```python
AppCommand("Open Diagnose Window", "open_diagnose_window"),
```

Place it near other window/workflow commands, before export commands if the command list is grouped by workflow.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui tests.test_epub_layout_gui_commands tests.test_project_guardrails -v
```

Expected: pass.

Commit:

```bash
git add src/manga_pdf_to_epub/epub_layout_gui.py src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py src/manga_pdf_to_epub/epub_layout_commands.py tests/test_epub_layout_gui.py tests/test_epub_layout_gui_commands.py
git commit -m "feat: open diagnose from a separate window"
```

---

### Task 3: Diagnose Spine List Rendering And Markers

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py`
- Test: `tests/test_epub_layout_gui_diagnosis.py`
- Test helper: `tests/gui_helpers.py`

- [ ] **Step 1: Write failing spine-render tests**

Add tests:

```python
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

    def test_refresh_diagnosis_spine_noops_when_window_closed(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1)])
        app.diagnosis_window = None

        app.refresh_diagnosis_spine()

        self.assertIsNone(app.diagnosis_window)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis.DiagnosisSpineViewTests -v
```

Expected: fail because `refresh_diagnosis_spine()` does not exist.

- [ ] **Step 3: Implement diagnose spine refresh**

In `EpubLayoutDiagnosisMixin`, add:

```python
def refresh_diagnosis_spine(self, preserve_yview: bool = False) -> None:
    window = getattr(self, "diagnosis_window", None)
    if window is None or getattr(window, "spine_list", None) is None:
        return
    if getattr(self, "model", None) is None:
        return
    listbox = window.spine_list
    selected = _first_selection(listbox)
    yview_start = listbox.yview()[0] if preserve_yview else None
    listbox.delete(0, tk.END)
    for index, entry in enumerate(self.model.entries, start=1):
        row_index = index - 1
        marker = "[blank]" if entry.is_blank else "[page]"
        cover = " [cover]" if self._is_cover_entry(entry) else ""
        spine_marker = self._marker_text_for_entry(row_index)
        listbox.insert(tk.END, f"{index:04d} {marker}{cover}{spine_marker} {entry.label}")
        self._apply_spine_marker_color_to_listbox(listbox, row_index)
    if yview_start is not None:
        listbox.yview_moveto(yview_start)
    if selected is not None and self.model.entries:
        listbox.selection_set(min(selected, len(self.model.entries) - 1))

def _apply_spine_marker_color_to_listbox(self, listbox, row_index: int) -> None:
    marker = getattr(self, "spine_markers", {}).get(row_index)
    if marker is None:
        return
    color = "#0b6b2b" if marker.kind == "suggested" else "#9f1d20"
    try:
        listbox.itemconfig(row_index, foreground=color)
    except tk.TclError:
        pass
```

Add module helper:

```python
def _first_selection(listbox) -> int | None:
    selection = listbox.curselection()
    return selection[0] if selection else None
```

Update `_apply_spine_marker_color()` to delegate:

```python
def _apply_spine_marker_color(self, row_index: int) -> None:
    self._apply_spine_marker_color_to_listbox(self.page_list, row_index)
```

- [ ] **Step 4: Run tests and commit**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis.DiagnosisSpineViewTests tests.test_epub_layout_gui_diagnosis.DiagnosisInsertWorkflowTests tests.test_project_guardrails -v
```

Expected: pass.

Commit:

```bash
git add src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py tests/test_epub_layout_gui_diagnosis.py
git commit -m "feat: render diagnose spine view"
```

---

### Task 4: Bidirectional Selection Sync

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_gui.py`
- Modify: `src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py`
- Test: `tests/test_epub_layout_gui_diagnosis.py`

- [ ] **Step 1: Write failing sync tests**

Add tests:

```python
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

        app.sync_selection_from_main()

        self.assertEqual(None, app.diagnosis_window.spine_list.selection)
        self.assertFalse(hasattr(app, "main_preview_refreshed"))
```

- [ ] **Step 2: Run sync tests and verify failure**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis.DiagnosisSelectionSyncTests -v
```

Expected: fail because sync methods do not exist and the main list bind still calls `refresh_preview` directly.

- [ ] **Step 3: Implement sync methods**

In `initialize_diagnosis_state()`, set:

```python
app._syncing_spine_selection = False
```

In `EpubLayoutDiagnosisMixin`, add:

```python
def sync_selection_from_main(self) -> None:
    if getattr(self, "_syncing_spine_selection", False):
        return
    self._syncing_spine_selection = True
    try:
        selected = self.selected_index()
        self._set_diagnosis_selection(selected)
    finally:
        self._syncing_spine_selection = False
    self.refresh_preview()
    self.refresh_diagnosis_preview()

def sync_selection_from_diagnosis(self) -> None:
    if getattr(self, "_syncing_spine_selection", False):
        return
    window = getattr(self, "diagnosis_window", None)
    if window is None:
        return
    selected = _first_selection(window.spine_list)
    self._syncing_spine_selection = True
    try:
        self._set_main_selection(selected)
    finally:
        self._syncing_spine_selection = False
    self.refresh_preview()
    self.refresh_diagnosis_preview()

def _set_main_selection(self, selected: int | None) -> None:
    self.page_list.selection_clear(0, tk.END)
    if selected is not None:
        self.page_list.selection_set(selected)

def _set_diagnosis_selection(self, selected: int | None) -> None:
    window = getattr(self, "diagnosis_window", None)
    if window is None:
        return
    window.spine_list.selection_clear(0, tk.END)
    if selected is not None:
        window.spine_list.selection_set(selected)
```

In `epub_layout_gui.py`, replace main spine binding:

```python
self.page_list.bind("<<ListboxSelect>>", lambda _event: self.sync_selection_from_main())
```

- [ ] **Step 4: Run sync tests and commit**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis.DiagnosisSelectionSyncTests tests.test_epub_layout_gui_preview tests.test_project_guardrails -v
```

Expected: pass.

Commit:

```bash
git add src/manga_pdf_to_epub/epub_layout_gui.py src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py tests/test_epub_layout_gui_diagnosis.py
git commit -m "feat: sync main and diagnose spine selection"
```

---

### Task 5: Diagnose Preview Rendering

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_gui.py`
- Modify: `src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py`
- Test: `tests/test_epub_layout_gui_diagnosis.py`
- Test: `tests/test_epub_layout_gui_preview.py`

- [ ] **Step 1: Write failing diagnose-preview tests**

Add tests:

```python
class DiagnosisPreviewTests(unittest.TestCase):
    def test_refresh_diagnosis_preview_draws_selected_spread(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2), page(3)])
        app.apple_preview = SimpleNamespace(get=lambda: False)
        app.diagnosis_window = SimpleNamespace(
            spine_list=FakeListbox(selection=1),
            preview=FakeCanvas(),
            photo_refs=[],
        )
        app.draws = []
        app._draw_entry_on_canvas = lambda canvas, photo_refs, entry, x, y, width, height: app.draws.append(entry.label)

        app.refresh_diagnosis_preview()

        self.assertEqual(["Page 1", "Page 2"], app.draws)

    def test_refresh_diagnosis_preview_noops_when_window_closed(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.diagnosis_window = None

        app.refresh_diagnosis_preview()

        self.assertIsNone(app.diagnosis_window)
```

- [ ] **Step 2: Run preview tests and verify failure**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis.DiagnosisPreviewTests -v
```

Expected: fail because `refresh_diagnosis_preview()` and reusable canvas drawing helper do not exist.

- [ ] **Step 3: Extract reusable preview rendering**

In `epub_layout_gui.py`, change `refresh_preview()` to delegate:

```python
def refresh_preview(self) -> None:
    self._refresh_preview_canvas(self.preview, self.photo_refs, self.selected_index())

def _refresh_preview_canvas(self, canvas, photo_refs: list, selected: int | None) -> None:
    canvas.delete("all")
    photo_refs.clear()
    if self.model is None or not self.model.entries:
        return
    if selected is None:
        selected = 0
    preview_entries = self._preview_entries()
    preview_selected = self._preview_index_for_selection(selected)
    pair_start = preview_selected if preview_selected % 2 == 0 else preview_selected - 1
    entries = preview_entries[pair_start : pair_start + 2]
    width = max(400, canvas.winfo_width())
    height = max(300, canvas.winfo_height())
    gap = 12
    page_w = (width - gap * 3) // 2
    page_h = height - gap * 2
    slots = self._spread_slots(pair_start, gap, page_w)
    for entry, (x, y) in zip(entries, slots):
        self._draw_entry_on_canvas(canvas, photo_refs, entry, x, y, page_w, page_h)
```

Rename the existing `_draw_entry()` body to accept `canvas` and `photo_refs`:

```python
def _draw_entry_on_canvas(self, canvas, photo_refs: list, entry, x: int, y: int, max_w: int, max_h: int) -> None:
    canvas.create_rectangle(x, y, x + max_w, y + max_h, fill="#ffffff", outline="#707070")
    if entry.is_blank:
        fill = "#a0a0a0" if isinstance(entry, VirtualBlank) else "#606060"
        canvas.create_text(x + max_w // 2, y + max_h // 2, text=entry.label, fill=fill)
        return
    if getattr(entry, "source_index", None) is None:
        photo = self._thumbnail_for_entry(entry, max_w, max_h)
    else:
        photo = self._thumbnail_for_page(entry.page.index, max_w, max_h)
    if photo is None:
        canvas.create_text(x + max_w // 2, y + max_h // 2, text=entry.label, fill="#202020")
        return
    photo_refs.append(photo)
    image_x = x + (max_w - photo.width()) // 2
    image_y = y + (max_h - photo.height()) // 2
    canvas.create_image(image_x, image_y, anchor=tk.NW, image=photo)
    canvas.create_text(x + 8, y + 16, text=entry.label, anchor=tk.W, fill="#ffffff")

def _draw_entry(self, entry, x: int, y: int, max_w: int, max_h: int) -> None:
    self._draw_entry_on_canvas(self.preview, self.photo_refs, entry, x, y, max_w, max_h)
```

- [ ] **Step 4: Implement diagnose preview**

In `EpubLayoutDiagnosisMixin`, add:

```python
def refresh_diagnosis_preview(self) -> None:
    window = getattr(self, "diagnosis_window", None)
    if window is None or getattr(window, "preview", None) is None:
        return
    selected = _first_selection(window.spine_list)
    self._refresh_preview_canvas(window.preview, window.photo_refs, selected)
```

- [ ] **Step 5: Run preview tests and commit**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis.DiagnosisPreviewTests tests.test_epub_layout_gui_preview tests.test_project_guardrails -v
```

Expected: pass.

Commit:

```bash
git add src/manga_pdf_to_epub/epub_layout_gui.py src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py tests/test_epub_layout_gui_diagnosis.py tests/test_epub_layout_gui_preview.py
git commit -m "feat: render diagnose preview"
```

---

### Task 6: Manual Add Selected As Spread

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_diagnosis_gui.py`
- Modify: `src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py`
- Test: `tests/test_epub_layout_gui_diagnosis.py`

- [ ] **Step 1: Write failing manual-add tests**

Add tests:

```python
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
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), blank])
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
```

- [ ] **Step 2: Run manual-add tests and verify failure**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis.DiagnosisManualSpreadSelectionTests -v
```

Expected: fail because `add_selected_spread_from_diagnosis_spine()` does not exist.

- [ ] **Step 3: Update callbacks and button label**

In `DiagnosisPanelCallbacks`, replace `add_missing_spread` with:

```python
add_selected_spread: Callable[[], None]
```

In `DiagnosisPanel._build()`, replace the old button:

```python
ttk.Button(parent, text="Add Selected As Spread", command=self.callbacks.add_selected_spread).pack(
    fill=tk.X,
    pady=(6, 0),
)
```

Update tests that assert callback field names and button labels.

- [ ] **Step 4: Implement manual add from diagnose spine**

In `EpubLayoutDiagnosisMixin`, add:

```python
def add_selected_spread_from_diagnosis_spine(self) -> None:
    window = getattr(self, "diagnosis_window", None)
    if window is None or getattr(self, "model", None) is None:
        return
    selection = list(window.spine_list.curselection())
    if len(selection) != 2:
        self.status.set("Select exactly two adjacent real pages.")
        return
    first_index, second_index = sorted(selection)
    entries = self.model.entries
    if second_index >= len(entries):
        self.status.set("Select exactly two adjacent real pages.")
        return
    first = entries[first_index]
    second = entries[second_index]
    first_source = getattr(first, "source_index", None)
    second_source = getattr(second, "source_index", None)
    if getattr(first, "is_blank", False) or getattr(second, "is_blank", False):
        self.status.set("Select exactly two adjacent real pages.")
        return
    if first_source is None or second_source is None or second_source != first_source + 1:
        self.status.set("Select exactly two adjacent real pages.")
        return
    self._add_missing_spread_pair(first_source, second_source)
```

Update `diagnosis_callbacks()`:

```python
add_selected_spread=app.add_selected_spread_from_diagnosis_spine,
```

Keep `add_missing_spread()` and `import_spread_candidates()` as non-primary controller methods for advanced/test use.

- [ ] **Step 5: Run manual-add tests and commit**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis.DiagnosisManualSpreadSelectionTests tests.test_epub_layout_gui_diagnosis.DiagnosisPanelTests tests.test_project_guardrails -v
```

Expected: pass.

Commit:

```bash
git add src/manga_pdf_to_epub/epub_layout_diagnosis_gui.py src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py tests/test_epub_layout_gui_diagnosis.py
git commit -m "feat: add selected spine pages as spread"
```

---

### Task 7: Refresh Both Main And Diagnose Views On State Changes

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py`
- Modify: `src/manga_pdf_to_epub/epub_layout_gui.py`
- Test: `tests/test_epub_layout_gui_diagnosis.py`
- Test: `tests/test_epub_layout_gui_editing.py`
- Test: `tests/test_epub_layout_gui_project.py`
- Test: `tests/test_epub_layout_gui_series.py`

- [ ] **Step 1: Write failing refresh tests**

Add tests:

```python
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
        self.assertTrue(app.diagnose_refreshed)
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
        self.assertTrue(app.diagnose_refreshed)
        self.assertTrue(app.preview_refreshed)
        self.assertTrue(app.diagnosis_preview_refreshed)
```

- [ ] **Step 2: Run refresh tests and verify failure**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis.DiagnosisViewRefreshTests -v
```

Expected: fail because state changes only refresh the main list or only refresh panel.

- [ ] **Step 3: Add shared refresh helpers**

In `EpubLayoutDiagnosisMixin`, add:

```python
def refresh_spine_views(self, preserve_yview: bool = False) -> None:
    self.refresh_list(preserve_yview=preserve_yview)
    self.refresh_diagnosis_spine(preserve_yview=preserve_yview)

def refresh_preview_views(self) -> None:
    self.refresh_preview()
    self.refresh_diagnosis_preview()
```

Update diagnosis controller methods:

```python
self.refresh_spine_views(preserve_yview=True)
```

for `_load_spread_candidates()`, `_load_insert_candidates()`, `check_confirmed_spread_damage()`, and `_mark_diagnosis_stale(refresh_spine=True)`.

Update `refresh_preview_after_diagnosis_layout_option_change()`:

```python
self._mark_diagnosis_stale(refresh_spine=True)
self.refresh_preview_views()
```

In `_refresh_after_layout_edit()`, replace separate preview refresh:

```python
self.refresh_preview_views()
```

- [ ] **Step 4: Run related tests and commit**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis tests.test_epub_layout_gui_editing tests.test_epub_layout_gui_project tests.test_epub_layout_gui_series tests.test_project_guardrails -v
```

Expected: pass.

Commit:

```bash
git add src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py src/manga_pdf_to_epub/epub_layout_gui.py tests/test_epub_layout_gui_diagnosis.py tests/test_epub_layout_gui_editing.py tests/test_epub_layout_gui_project.py tests/test_epub_layout_gui_series.py
git commit -m "feat: refresh diagnose views with shared state"
```

---

### Task 8: Update Runner-Unavailable And Import UX

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py`
- Modify: `src/manga_pdf_to_epub/epub_layout_diagnosis_gui.py`
- Test: `tests/test_epub_layout_gui_diagnosis.py`

- [ ] **Step 1: Write failing message tests**

Add tests:

```python
class DiagnosisImportUxTests(unittest.TestCase):
    def test_spread_scan_unavailable_points_to_manual_spine_review(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2)])
        app.pdf_path = Path("/tmp/book.pdf")
        app.diagnosis_session = DiagnosisSession(source_page_count=2)

        with patch("manga_pdf_to_epub.epub_layout_diagnosis_controller.resolve_spread_scan_command", return_value=None), \
            patch("manga_pdf_to_epub.epub_layout_diagnosis_controller.messagebox.showerror") as showerror:
            app.run_spread_diagnosis()

        title, message = showerror.call_args.args
        self.assertEqual("Spread scan unavailable", title)
        self.assertIn("Use Add Selected As Spread", message)
        self.assertNotIn("Use Import Spread Candidates", message)

    def test_primary_panel_has_no_import_spread_candidates_button(self):
        labels = []
        parent = object()

        class FakeStringVar:
            def __init__(self, *_args, **kwargs):
                self.value = kwargs.get("value", "")

            def set(self, value):
                self.value = value

        class FakeWidget:
            def __init__(self, *args, **kwargs):
                self.options = kwargs

            def pack(self, *_args, **_kwargs):
                pass

        class FakeButton(FakeWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                labels.append(kwargs.get("text"))

        callbacks = DiagnosisPanelCallbacks(
            run_spread_diagnosis=lambda: None,
            mark_selected_spread_true=lambda: None,
            mark_selected_spread_false=lambda: None,
            add_selected_spread=lambda: None,
            check_confirmed_spread_damage=lambda: None,
            run_insert_point_scoring=lambda: None,
            import_insert_scores=lambda: None,
            insert_selected_diagnosis_blank=lambda: None,
            recheck_diagnosis_layout=lambda: None,
        )
        with patch("manga_pdf_to_epub.epub_layout_diagnosis_gui.tk.StringVar", FakeStringVar), \
            patch("manga_pdf_to_epub.epub_layout_diagnosis_gui.tk.Listbox", FakeWidget), \
            patch("manga_pdf_to_epub.epub_layout_diagnosis_gui.ttk.Label", FakeWidget), \
            patch("manga_pdf_to_epub.epub_layout_diagnosis_gui.ttk.Button", FakeButton), \
            patch("manga_pdf_to_epub.epub_layout_diagnosis_gui.ttk.Separator", FakeWidget):
            DiagnosisPanel(parent, callbacks)

        self.assertNotIn("Import Spread Candidates...", labels)
        self.assertIn("Add Selected As Spread", labels)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis.DiagnosisImportUxTests -v
```

Expected: fail because the old button and message still exist.

- [ ] **Step 3: Update message and primary panel**

In `run_spread_diagnosis()` message:

```python
"Could not find sibling manga-spread-continuity environment. Use Add Selected As Spread in the Diagnose window for manual review."
```

Keep `import_spread_candidates()` method for advanced/test use, but remove it from `DiagnosisPanelCallbacks` and `DiagnosisPanel._build()` primary UI.

- [ ] **Step 4: Run tests and commit**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis tests.test_epub_layout_gui -v
```

Expected: pass.

Commit:

```bash
git add src/manga_pdf_to_epub/epub_layout_diagnosis_controller.py src/manga_pdf_to_epub/epub_layout_diagnosis_gui.py tests/test_epub_layout_gui_diagnosis.py
git commit -m "fix: make manual spread selection primary"
```

---

### Task 9: Documentation And Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/diagnosis-workflow.md`
- Modify: `docs/superpowers/specs/2026-05-23-diagnose-window-ux-design.md` only if implementation differs from the approved spec.

- [ ] **Step 1: Update docs**

Update diagnosis workflow docs so they describe:

- Open `Diagnose Window`.
- Use `Run Cross-Page Scan` for candidates.
- Select two adjacent real pages in the Diagnose Spine order and click `Add Selected As Spread` for missed spreads.
- Use `Check Damage Against Current Layout`.
- Use `Run Insert-Point Scoring`.
- Insert exactly one selected blank and recheck.

- [ ] **Step 2: Run full verification**

Run:

```bash
make test
make lint
make smoke
PYTHONPATH=src .venv/bin/python - <<'PY'
from pathlib import Path
text = Path('src/manga_pdf_to_epub/epub_layout_gui.py').read_text()
start = text.index('class EpubLayoutApp')
end = text.index('\ndef main', start)
print(text[start:end].count('\n'))
PY
git status --short --branch
```

Expected:

- `make test`: all tests pass.
- `make lint`: exit 0.
- `make smoke`: exit 0.
- `EpubLayoutApp` class line count stays at or below the guardrail in `tests/test_project_guardrails.py`.
- `git status` shows only intended doc/code/test changes before commit.

- [ ] **Step 3: Commit docs**

```bash
git add README.md docs/diagnosis-workflow.md docs/superpowers/specs/2026-05-23-diagnose-window-ux-design.md
git commit -m "docs: update diagnose window workflow"
```

- [ ] **Step 4: Request final code review**

Use the requesting-code-review workflow with:

- Base SHA: the commit before Task 1.
- Head SHA: current HEAD after docs.
- Requirements: `docs/superpowers/specs/2026-05-23-diagnose-window-ux-design.md`.

Reviewer must check:

- Diagnose window is a linked view, not a split state.
- Selection sync is bidirectional and guarded.
- Manual add uses selected real adjacent pages.
- Primary UI does not present CSV spread import as normal workflow.
- HITL staging remains manual.
- Stale insert suggestions are still invalidated.

- [ ] **Step 5: Address review findings or finish branch**

If review returns findings, use superpowers:receiving-code-review before changing code.

If approved, use superpowers:finishing-a-development-branch and present integration options.
