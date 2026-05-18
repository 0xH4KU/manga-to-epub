# EPUB Layout Lab Improvement TODO

Goal: turn the current manga PDF -> EPUB/CBZ toolkit from a working specialist utility into a safer, repeatable batch workflow for Apple Books manga layout correction.

Execution rule: work in small waves. Each wave must start with focused failing tests where behavior changes, then implementation, then full verification, then a commit. Do not start the next wave until the current wave is committed.

Baseline verification command for every wave:

```bash
./.venv/bin/python -m py_compile epub_layout_gui.py epub_layout_model.py epub_batch_model.py pdf_to_epub_lossless.py pdf_to_cbz_lossless.py
./.venv/bin/python -m unittest
```

Current baseline: 47 tests pass in the project `.venv`.

## Wave 0 - Planning Baseline

Purpose: replace the old feature TODO with this execution checklist so future commits are traceable by wave.

- [x] Rewrite `todo.md` as this detailed wave plan.
- [x] Keep already-completed historical work visible through the current code/tests rather than a stale mixed checklist.
- [x] Verify baseline commands pass.
- [x] Commit with: `docs: expand improvement todo by wave`

## Wave 1 - Inserted Image Cover Support

Purpose: allow an externally inserted JPEG/PNG page to be selected as the EPUB cover, including when the cover is excluded from reading pages.

Why this matters: manga collections often have a separately sourced high-quality cover. The model already supports inserted image pages, but cover identity is still tied to original PDF `source_index`, so inserted images cannot currently be marked as cover.

Files:

- Modify `epub_layout_model.py`
- Modify `epub_layout_gui.py`
- Test `test_epub_layout_model.py`
- Test `test_epub_layout_gui.py`

Detailed tasks:

- [x] Add a model-level cover identifier that can reference both original PDF pages and inserted image entries.
- [x] Keep compatibility with the existing `cover_source_index` behavior so current tests and callers still work.
- [x] Update `LayoutModel.set_cover(...)` or add a spine-entry cover setter so callers can set cover by selected layout entry.
- [x] Update `normalized_cover_item_id()` so inserted image covers map to the normalized EPUB item id.
- [x] Ensure deleting the inserted cover falls back to the first available non-blank image.
- [x] Update GUI `Set Selected As Cover` to accept inserted image pages and still reject blanks.
- [x] Update the spine list marker so inserted image covers show `[cover]`.
- [x] Add model tests:
  - inserted PNG can be set as cover and appears with `properties="cover-image"` in OPF.
  - inserted cover can be excluded from reading spine while image remains in manifest.
  - deleting an inserted cover falls back to first original image.
- [x] Add GUI tests:
  - selecting an inserted image calls the cover setter and marks it as cover.
  - selecting a blank still shows an error and does not change cover.
- [x] Run focused tests, then full verification.
- [x] Commit with: `feat: allow inserted images as epub covers`

## Wave 2 - Preset Format v2

Purpose: make presets capture the real edited layout, metadata, cover rules, and inserted-image references while still loading version 1 presets.

Why this matters: the current preset only stores deleted source pages and blank positions. That is enough for early blank-page correction, but not enough for inserted images, metadata defaults, cover-only exports, or future batch workflows.

Files:

- Modify `epub_layout_model.py`
- Modify `epub_batch_model.py`
- Modify `epub_layout_gui.py` only if GUI messages or commands need small adjustments
- Test `test_epub_layout_model.py`
- Test `test_epub_batch_model.py`

Preset v2 shape:

```json
{
  "version": 2,
  "source_page_count": 4,
  "metadata": {
    "title": "Sample Title",
    "author": "Sample Author",
    "language": "zh-Hant",
    "exclude_cover_from_reading": false
  },
  "cover": {
    "kind": "source",
    "source_index": 1,
    "entry_id": null
  },
  "entries": [
    {"kind": "source", "source_index": 1},
    {"kind": "blank"},
    {"kind": "inserted", "path": "/absolute/path/extra.png"}
  ]
}
```

Detailed tasks:

- [x] Add stable entry identity for inserted images.
- [x] Save new presets as `version: 2` only.
- [x] Preserve loading of old `version: 1` presets.
- [x] Load v2 source entries in saved order, skipping missing source pages with a clear warning path if needed.
- [x] Load v2 blank entries in saved order.
- [x] Load v2 inserted entries by re-reading the saved image path.
- [x] Restore metadata fields from v2 presets.
- [x] Restore cover rule from v2 presets:
  - first image fallback.
  - explicit source page.
  - explicit inserted entry.
- [x] Keep old v1 behavior for blank positions and deleted pages.
- [x] Add tests:
  - v1 fixture still loads.
  - v2 round-trip preserves source, blank, inserted entry order.
  - v2 round-trip preserves title, author, language, and cover-only setting.
  - v2 round-trip restores inserted image cover.
  - missing inserted image path raises a clear `ValueError`.
- [x] Run focused tests, then full verification.
- [x] Commit with: `feat: add v2 layout presets`

## Wave 3 - Batch Project Preset Integration And Safety

Purpose: connect the newer batch project workflow to presets and make batch export safer before overwriting files.

Why this matters: batch processing is the workflow that benefits most from presets, but the GUI still has an older preset-first batch path and the batch project lacks an explicit "export all warnings too" control.

Files:

- Modify `epub_batch_model.py`
- Modify `epub_layout_gui.py`
- Test `test_epub_batch_model.py`
- Test `test_epub_layout_gui.py`

Detailed tasks:

- [x] Teach `LayoutTemplate` to preserve enough v2 preset information for inserted images and cover rules.
- [x] Allow creating a `BatchProject` from a saved preset.
- [x] Allow exporting/saving a preset from the current batch template if needed by the GUI flow.
- [x] Add an `Export All...` GUI action that exports ready and warning items, while still skipping failed items.
- [x] Add a preflight warning for output files that already exist before batch export starts.
- [x] Keep `Export Ready...` conservative: ready items only.
- [x] Keep older `Batch Apply` path available until the new batch-project path covers it fully.
- [x] Add tests:
  - batch project from v2 preset applies source deletion, blanks, metadata, and cover.
  - `export_ready` skips warning items.
  - `export_all` exports warning items and skips failed items.
  - output collision warnings remain visible in queue items.
- [x] Run focused tests, then full verification.
- [x] Commit with: `feat: integrate presets with batch projects`

## Wave 4 - GUI Usability Polish

Purpose: make the Tkinter layout editor less cluttered and clearer during repeated work, without changing the utilitarian style.

Why this matters: the right control column has grown into a long list of buttons. Manga layout correction is repetitive, so better grouping and status messages reduce mistakes.

Files:

- Modify `epub_layout_gui.py`
- Test `test_epub_layout_gui.py`

Detailed tasks:

- [x] Reorganize right-side controls into labeled groups:
  - Insert
  - Delete
  - Metadata
  - Export
  - Batch
- [x] Keep existing button text where tests or muscle memory depend on it.
- [x] Improve status messages:
  - deletion reports count and blank/source mix.
  - selected image export reports exported count and skipped blanks.
  - normalization says how many entries will be normalized during export.
  - batch validation reports ready/warning/failed counts.
- [x] Add safe keyboard shortcuts:
  - Delete selected page.
  - Undo/recover last delete group.
  - Export selected images.
- [x] Avoid adding visual complexity beyond standard Tkinter/ttk widgets.
- [x] Add GUI tests for status-message behavior that can be tested without opening real dialogs.
- [x] Run focused tests, then full verification.
- [x] Commit with: `refactor: clarify layout editor controls`

## Wave 5 - Responsiveness And Long-Task Guardrails

Purpose: reduce UI freezing when loading large PDFs, validating batches, and generating previews.

Why this matters: the current export paths use background threads, but opening PDFs, validating batch queues, and thumbnail rendering can still block the main Tkinter event loop.

Files:

- Modify `epub_layout_gui.py`
- Modify model files only if small helper extraction is needed
- Test `test_epub_layout_gui.py`

Detailed tasks:

- [x] Move PDF open/load work into a background thread.
- [x] Move batch validation into a background thread.
- [x] Prevent duplicate long-running actions while a worker is active.
- [x] Add a simple busy/status state for long tasks.
- [x] Keep all Tkinter UI updates on the main thread via `root.after(...)`.
- [x] Cache thumbnails by stable entry identity rather than object identity when possible.
- [x] Add tests around worker completion callbacks and busy-state transitions.
- [x] Run focused tests, then full verification.
- [x] Commit with: `perf: keep layout editor responsive during long tasks`

## Wave 6 - EPUB Self-Check And Metadata Hygiene

Purpose: add lightweight internal validation of generated EPUBs and clean up metadata behavior.

Why this matters: Apple Books is the primary target, but catching missing manifest items, broken spine refs, or invalid cover references before import saves time.

Files:

- Modify `pdf_to_epub_lossless.py`
- Modify `epub_layout_model.py` if export API needs to expose self-check results
- Test `test_pdf_to_epub_lossless.py`
- Test `test_epub_layout_model.py`

Detailed tasks:

- [x] Add an internal EPUB self-check helper that validates:
  - `mimetype` is first and stored.
  - `META-INF/container.xml` exists.
  - `EPUB/content.opf` exists.
  - every spine `idref` has a manifest XHTML item.
  - every XHTML/image href referenced by OPF exists in the zip.
  - cover image property points to an image item that exists.
- [x] Run self-check automatically after EPUB export.
- [x] Keep self-check errors as `PdfImageError` with specific messages.
- [x] Decide and document timestamp behavior:
  - keep deterministic default if reproducibility is preferred.
  - or write current UTC modified time if real metadata freshness is preferred.
- [x] Add tests for a valid generated EPUB passing self-check.
- [x] Add unit tests for broken OPF references failing self-check.
- [x] Run focused tests, then full verification.
- [x] Commit with: `feat: validate generated epub structure`

## Wave 7 - Documentation Refresh

Purpose: update user-facing docs to match the improved workflow.

Files:

- Modify `README.md`
- Modify `todo.md`

Detailed tasks:

- [x] Document inserted image covers.
- [x] Document preset v1 compatibility and v2 behavior.
- [x] Document batch project from preset.
- [x] Document `Export Ready...` vs `Export All...`.
- [x] Document EPUB self-check behavior.
- [x] Mark completed waves in this file.
- [x] Run full verification.
- [x] Commit with: `docs: document improved layout workflow`

## Completion Checklist

- [x] All waves above are either complete and committed or intentionally deferred.
- [x] `git log --oneline` shows one commit per completed wave.
- [x] Full verification command passes.
- [x] `git status --short` is clean except for intentionally untracked local books/output files ignored by `.gitignore`.

## UI Refresh Continuation - Professional Workbench

Goal: turn the current crowded Tkinter editor into a professional, non-clipping desktop workbench while keeping the tool practical for manga EPUB layout correction.

Design direction: combine the approved A/C mockup direction. Keep the A-style inspector workbench as the main structure: left navigation, center RTL preview, right inspector. Add a lighter C-style efficiency layer: command entry, keyboard access, validation/status feedback, and stronger batch visibility. Do this in small waves so each step is easy to review and revert.

Primary UI problems to fix:

- The current right control column stacks every action vertically, so bottom controls are clipped on shorter screens.
- The toolbar mixes workflow actions and status text, making the top of the app feel ordinary and crowded.
- Batch state is visually buried even though batch workflows are now a core feature.
- There is no professional "command surface" for frequent actions.
- Status messages are useful but not separated from persistent workspace health.

Execution rule: continue committing by wave. For every behavior change, write a focused failing test first, run it to verify the red state, implement the minimum code, run focused tests, then run full verification before committing.

Baseline verification command for every UI refresh wave:

```bash
./.venv/bin/python -m py_compile epub_layout_gui.py epub_layout_model.py epub_batch_model.py pdf_to_epub_lossless.py pdf_to_cbz_lossless.py
./.venv/bin/python -m unittest
```

## Wave 8 - UI Refresh Planning Baseline

Purpose: capture the approved A/C hybrid direction in `todo.md` before touching the GUI code.

Files:

- Modify `todo.md`

Detailed tasks:

- [x] Append this UI refresh continuation section.
- [x] Document the non-clipping inspector goal.
- [x] Document the professional workbench direction.
- [x] Split implementation into small waves with expected tests and commit messages.
- [x] Run full verification to prove the planning-only change did not disturb the codebase.
- [x] Commit with: `docs: plan professional ui refresh`

## Wave 9 - Workbench Shell And Non-Clipping Inspector

Purpose: reshape the main window into the approved professional workbench layout and remove the clipped right-side control stack.

Why this matters: the current GUI can hide bottom controls even when the window is maximized. A tabbed, scrollable inspector keeps every control reachable and makes the app feel like an editing tool instead of a long form.

Files:

- Modify `epub_layout_gui.py`
- Test `test_epub_layout_gui.py`

Detailed tasks:

- [x] Add tests for window sizing configuration so the app opens with a more appropriate workbench geometry and minimum size.
- [x] Add tests for the inspector tab specification so future edits keep `Edit`, `Book`, and `Batch` grouped intentionally.
- [x] Move title, geometry, and minimum-size setup into a small window configuration helper.
- [x] Increase initial geometry from `1120x720` to a roomier workbench size while still allowing smaller supported windows.
- [x] Replace the single long right-side frame with a `ttk.Notebook`.
- [x] Put insert/delete/normalize controls in the `Edit` tab.
- [x] Put metadata, cover, and selected-image export controls in the `Book` tab.
- [x] Put batch template, add PDFs, validate, export ready, and export all controls in the `Batch` tab.
- [x] Make each inspector tab scrollable so every control remains reachable on shorter screens.
- [x] Move transient status text out of the toolbar into a bottom status bar.
- [x] Keep existing button labels for muscle memory and tests.
- [x] Run focused GUI tests, then full verification.
- [x] Commit with: `refactor: reshape layout editor workbench`

## Wave 10 - Command Palette Efficiency Layer

Purpose: add the first C-style power feature without overwhelming the A-style workbench.

Why this matters: professional tools usually expose a fast action surface. A command palette makes repeated layout operations easier while keeping the visible interface calmer.

Files:

- Modify `epub_layout_gui.py`
- Test `test_epub_layout_gui.py`

Detailed tasks:

- [x] Add tests for command matching so typed queries find expected actions.
- [x] Add tests for command execution dispatch so palette commands call the intended app methods.
- [x] Add tests that `Command-K` and `Control-K` are bound to the command palette.
- [x] Add a compact `Command Palette...` entry point in the toolbar.
- [x] Implement a lightweight Tkinter palette with an entry, filtered listbox, Enter execution, double-click execution, and Escape close.
- [x] Include core commands:
  - Open PDF
  - Export EPUB
  - Save Preset
  - Load Preset
  - Batch Apply
  - Insert Blank Before
  - Insert Blank After
  - Insert Image Before
  - Insert Image After
  - Delete Selected Page
  - Recover Last Deleted
  - Set Selected As Cover
  - Export Selected Images
  - Validate Batch
  - Export Ready Batch
  - Export All Batch
- [x] Keep commands safe by reusing existing methods and their current guards.
- [x] Run focused GUI tests, then full verification.
- [x] Commit with: `feat: add command palette for layout actions`

## Wave 11 - Workspace Status And Batch Feedback

Purpose: add persistent professional status feedback without turning the UI into a dashboard.

Why this matters: transient messages say what just happened, but users also need stable context: page count, queue count, and batch readiness. A bottom status bar gives that context without crowding the editing surface.

Files:

- Modify `epub_layout_gui.py`
- Test `test_epub_layout_gui.py`

Detailed tasks:

- [x] Add tests for a workspace summary string with no PDF loaded.
- [x] Add tests for a workspace summary string with page count and batch counts.
- [x] Add a second status variable for persistent workspace summary.
- [x] Show transient status on the left side of the bottom bar.
- [x] Show persistent workspace summary on the right side of the bottom bar.
- [x] Update the summary after opening PDFs, refreshing the spine list, adding PDFs, validating batches, and exporting batches.
- [x] Include ready/warning/failed batch counts when a batch project exists.
- [x] Keep wording compact enough for small windows.
- [x] Run focused GUI tests, then full verification.
- [x] Commit with: `feat: add workspace status summary`

## UI Refresh Completion Checklist

- [x] Right-side controls no longer clip on the provided screenshot-sized window.
- [x] The main app reads as a professional editing workbench: navigation, preview, inspector, command access, and status bar.
- [x] All existing layout, preset, batch, export, and validation behavior remains intact.
- [x] Full verification command passes after every wave.
- [x] `git log --oneline` shows one commit per UI refresh wave.

## Wave 12 - Inspector Ordering Polish

Purpose: make the inspector controls follow user intent rather than the order they happened to be implemented.

Why this matters: the right panel is now reachable, but some groups still feel awkward. Cover blank shortcuts are insert actions, not delete actions. Batch operations should read as a workflow: create/load template, add files, validate/preflight, then export. The tab strip also needs a bit more space so `Edit`, `Book`, and `Batch` do not visually collide.

Files:

- Modify `epub_layout_gui.py`
- Test `test_epub_layout_gui.py`

Detailed tasks:

- [x] Add tests for `Edit` inspector section order:
  - Insert
  - Delete
  - Repair
- [x] Add tests for `Batch` inspector section order:
  - Template
  - Queue
  - Preflight
  - Export
- [x] Move `Quick: Blank Before Cover` and `Quick: Blank After Cover` into the `Insert` group, directly after the blank before/after controls.
- [x] Keep delete-only actions in `Delete`.
- [x] Move `Recover Last Deleted` and `Normalize Export Order` into `Repair`.
- [x] Split batch controls into workflow groups:
  - `Template`: Use Current Layout As Template, Load Template Preset...
  - `Queue`: Add PDFs...
  - `Preflight`: Validate Batch...
  - `Export`: Export Ready..., Export All...
- [x] Add helper methods for section labels/buttons so spacing is consistent and future ordering is harder to accidentally break.
- [x] Add a little notebook/tab padding or inspector width room so tab labels do not visually overlap.
- [x] Run focused GUI tests, then full verification.
- [x] Commit with: `refactor: polish inspector control ordering`
