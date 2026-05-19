# TODO: Series Project Workflow Refactor

This backlog replaces the old "open one PDF, save a template, add the rest" workflow with a series-first workflow for manga volumes.

The core product model is now:

1. Import a whole series of PDFs.
2. Store shared series metadata once.
3. Keep a sorted volume list.
4. Let every volume keep its own layout edits.
5. Use correction presets only as optional accelerators, never as blind truth.
6. Export only reviewed/ready volumes by default.

## Product Decisions

- Treat a manga series as the main workspace.
- Keep single-volume editing, but make it a detail view inside a series.
- Generate EPUB titles from series metadata and volume order, not from a fixed preset title.
- Store author/language at the series level and apply them to all volumes unless a future per-volume override is explicitly added.
- Keep layout corrections per volume.
- Mark imported volumes as `Unreviewed`.
- Mark a volume `Edited` when its layout changes.
- Let the user mark reviewed volumes as `Ready`.
- `Export Ready` exports only `Ready` volumes.
- `Export All` must make unreviewed/edited volume risk visible before export.
- Old batch-template workflows should be removed once the series workflow covers their use cases.

## Target User Flow

1. Click `Import Series...`.
2. Select a folder or multiple PDFs.
3. The app creates a series workspace:
   - Series title, for example `晚安,布布`
   - Author, for example `淺野一二O`
   - Language
   - Sorted volume list
4. The user can reorder volumes by drag/drop in the series list.
5. Clicking a volume opens the existing page preview/editor for that volume.
6. The user fixes blank pages/deletions/cover per volume.
7. The user marks reviewed volumes as `Ready`.
8. `Export Ready` writes EPUB files with titles like:
   - `晚安,布布 Vol.01`
   - `晚安,布布 Vol.02`
   - `晚安,布布 Vol.03`

## P0 - Establish Series Data Model

### 1. Add `SeriesProject` and `SeriesVolume`

**Problem:** Current `BatchProject` stores a layout template and queue items. That structure assumes the same correction is valid for all volumes.

**New model:**

- `SeriesProject`
  - `title`
  - `author`
  - `language`
  - `volumes`
- `SeriesVolume`
  - `pdf_path`
  - `volume_number`
  - `status`
  - `layout_model`
  - `output_path`
  - `error`
  - `warnings`

**Files:**

- `epub_series_model.py`
- `test_epub_series_model.py`
- `pyproject.toml`

**Acceptance:**

- Importing PDFs creates one volume per PDF.
- Volumes are naturally sorted by filename.
- Generated titles use series metadata plus sorted volume number.
- Author and language come from the series, not from a copied template title.
- Initial volume status is `Unreviewed`.

### 2. Infer series metadata from filenames conservatively

**Problem:** A filename like `晚安,布布 淺野一二O Vol.01.pdf` contains title, author, and volume number. The old batch item title keeps the whole filename or copies the first volume title.

**Decision:**

- Start with a conservative parser:
  - Detect `Vol.01`, `Vol 01`, `Volume 01`, or trailing number groups.
  - Strip the volume token from the display stem.
  - If user-provided series title/author exist, trust them.
  - Do not guess author aggressively if ambiguous.

**Acceptance:**

- `晚安,布布 淺野一二O Vol.01.pdf` can become `晚安,布布 Vol.01` when series title is `晚安,布布`.
- Subsequent sorted volumes export as matching `Vol.xx` titles.
- Bad guesses are editable at the series level.

## P1 - Make Series Workspace the GUI Primary Flow

### 3. Add series import/list UI

**Problem:** The GUI starts from a single PDF and exposes batch as a secondary tool. Series work should start from the series list.

**Files:**

- `epub_layout_gui.py`
- `test_epub_layout_gui.py`

**Tasks:**

- Add toolbar action `Import Series...`.
- Add a left-column series/volume list above or instead of old single spine-only navigation.
- Selecting a volume loads that volume's `LayoutModel` into the existing editor.
- Keep `Open PDF` as a single-volume fallback during migration.

**Acceptance:**

- Imported volumes appear in a series list.
- Selecting a volume updates the page list and preview.
- The left column no longer treats batch queue as the series concept.

### 4. Add series metadata controls

**Problem:** Title and author currently belong to one layout model, but they should belong to the series.

**Files:**

- `epub_layout_gui.py`
- `test_epub_layout_gui.py`

**Tasks:**

- Add Book/Series metadata fields:
  - Series title
  - Author
  - Language
  - Volume title preview
- Store series metadata on `SeriesProject`.
- Keep per-volume title generated from series title + volume number.

**Acceptance:**

- Editing series title changes generated volume title previews.
- Author applies to all exported volumes.
- Loading a volume does not overwrite series metadata with that PDF filename.

## P1 - Per-Volume Review and Export Safety

### 5. Add volume status transitions

**Problem:** Template batch export encourages exporting volumes that were never inspected.

**Statuses:**

- `Unreviewed`
- `Edited`
- `Ready`
- `Warning`
- `Exported`
- `Failed`

**Acceptance:**

- Imported volumes start `Unreviewed`.
- Layout edits mark the active volume `Edited`.
- User can mark selected volume(s) `Ready`.
- Export failures mark individual volumes `Failed`.

### 6. Export ready series volumes

**Problem:** Old `BatchProject.export_ready()` is based on template validation, not per-volume review.

**Files:**

- `epub_series_model.py`
- `test_epub_series_model.py`
- `epub_layout_gui.py`
- `test_epub_layout_gui.py`

**Tasks:**

- Implement `SeriesProject.export_ready(output_dir)`.
- Use each volume's own `LayoutModel`.
- Generate output filenames from generated titles.
- Skip `Unreviewed` and `Edited` by default.

**Acceptance:**

- `Export Ready` only exports `Ready` volumes.
- Exported EPUB metadata uses generated title, series author, and series language.
- Layout edits remain per-volume.

## P2 - Correction Presets as Accelerators

### 7. Add apply-correction-to-selected-volumes

**Problem:** Users still need a fast way to apply the same blank-page fix to several volumes.

**Decision:**

- Keep correction presets, but do not mark target volumes `Ready`.
- Applying a correction marks targets `Edited`.
- Users must review or explicitly mark ready afterward.

**Acceptance:**

- A correction can be applied to selected volumes.
- Applying a correction never silently exports unreviewed volumes.
- The UI wording avoids saying "template export".

### 8. Remove old batch-template UI when series export is in place

**Problem:** Old batch flow duplicates and conflicts with series flow.

**Files:**

- `epub_batch_model.py`
- `test_epub_batch_model.py`
- `epub_layout_gui.py`
- `test_epub_layout_gui.py`
- `README.md`
- `pyproject.toml`

**Tasks:**

- Remove `BatchProject` from GUI.
- Delete batch-template controls:
  - `Use Current Layout As Template`
  - `Load Template Preset...`
  - `Add PDFs...`
  - `Validate Batch...`
  - `Export Ready...` batch implementation
  - `Export All...` batch implementation
- Keep or delete `epub_batch_model.py` depending on whether any tests still justify it.

**Acceptance:**

- GUI has one series export path.
- No visible old batch-template workflow remains.
- README describes series workflow first.

## P2 - Persistence

### 9. Save/load series project files

**Problem:** A series may require many per-volume edits; users need to resume work.

**Files:**

- `epub_series_model.py`
- `test_epub_series_model.py`
- `epub_layout_gui.py`
- `test_epub_layout_gui.py`

**Decision:**

- Use a JSON project file, for example `.manga-series.json`.
- Store:
  - series metadata
  - volume order
  - volume status
  - per-volume layout preset payload

**Acceptance:**

- A saved series can be reopened.
- Per-volume blank pages, deletions, inserted images, cover choice, and status survive reload.

## P3 - Polish

### 10. Add "Open next unreviewed"

**Why:** Speeds up review flow.

**Acceptance:**

- Command jumps to the next `Unreviewed` or `Edited` volume.

### 11. Add manual QA checklist

**Files:**

- `docs/manual-qa.md` or `README.md`

**Checklist must include:**

- Import a series folder.
- Edit series title/author.
- Reorder volumes.
- Open a volume, add blank page, mark ready.
- Confirm Delete/Backspace in text fields does not delete pages.
- Export ready volumes.
- Confirm Vol.01/Vol.02 titles.
- Confirm an unreviewed volume is skipped by `Export Ready`.

## Suggested Commit Waves

1. Roadmap only: replace this TODO with the series-first plan.
2. Add `epub_series_model.py` and tests.
3. Add GUI import/list skeleton.
4. Add series metadata and generated titles.
5. Add per-volume status and ready export.
6. Update README around series workflow.
7. Remove old batch-template controls and dead batch code.
8. Add series project save/load.

## Current Safety Rule

`.gitignore` is user-owned in this workspace. Do not modify, stage, or revert it unless explicitly requested.
