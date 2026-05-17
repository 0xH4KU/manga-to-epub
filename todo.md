# EPUB Layout Lab Feature TODO

Scope: add safer page operations, image export, metadata/cover editing, and a real multi-PDF batch project workflow for manga volume sets. Do not implement until this TODO is reviewed.

## Assumptions To Review

- "Page 1 / page range" in quick delete means the current left-side Spine order, using 1-based positions after any inserted blanks or deleted pages.
- Source page labels such as `Page 4` should remain visible for traceability, but exported EPUB internal filenames/item ids can be normalized to sequential spine positions.
- "Selected image export" means exporting selected non-blank source images losslessly to a folder. Blank pages are skipped with a warning/status line.
- "Insert image" means adding an external image as a real EPUB page in the editable spine, not modifying the original PDF.
- "Set cover" means choosing which spine entry is marked as the EPUB cover image. By default this is the first non-blank image page.
- Batch Project is the preferred direction over the current preset-file-first workflow.

## Phase 0 - Safety Baseline

- [x] Run the current test suite before changes: `python -m py_compile ...` and `python -m unittest`.
- [x] Add regression tests before implementation for each model-level behavior that changes.
- [ ] Keep existing preset JSON compatibility; old presets with `version: 1` must still load.
- [ ] Keep lossless behavior for original PDF image streams.
- [ ] Avoid destructive UI actions without confirmation when deleting real source pages or overwriting EPUBs.

## Phase 1 - Core Layout Model Cleanup

- [x] Add a layout normalization operation.
  - [x] Rebuild exported image hrefs, XHTML hrefs, item ids, nav labels, and spine itemrefs in current spine order.
  - [x] Keep source page identity separately so the UI can still show "source Page 4" after normalization.
  - [x] Ensure blanks get deterministic sequential ids such as `blank-0002`.
  - [ ] Ensure inserted external image pages get deterministic sequential ids.
  - [ ] Make normalization idempotent: running it twice should not change the result again.
- [x] Decide when normalization runs.
  - [x] Provide a manual "Normalize Export Order" button.
  - [x] Also run normalization automatically before EPUB export.
- [x] Add tests for the case where deleting pages leaves spine position `0001` pointing to source page 4.
- [x] Add tests proving the exported EPUB has sequential manifest/spine/nav ids after delete/insert operations.

## Phase 2 - Quick Delete Tools

- [x] Add model helpers for deleting spine ranges safely.
  - [x] Delete first N spine entries.
  - [x] Delete last N spine entries.
  - [x] Delete inclusive range A-B.
  - [x] Clamp or reject invalid ranges with clear errors.
  - [x] Return deleted entries for undo/recover support.
- [x] Add GUI controls in a new "Quick delete" area.
  - [x] "Delete first [N] pages".
  - [x] "Delete last [N] pages".
  - [x] "Delete range [A] to [B]".
  - [x] Confirmation dialog for ranges containing real source or inserted image pages.
  - [ ] No confirmation needed for blank-only deletion, unless the range is large.
- [x] Preserve current recover behavior.
  - [x] Recover batch-deleted entries as one undo group.
  - [x] Keep `Cmd+Z` / `Ctrl+Z` restoring the whole last operation.
- [ ] Test blank-only, source-page, mixed, empty-model, negative, zero, reversed-range, and over-large range cases.

## Phase 3 - Selected Image Export

- [x] Allow multi-selection in the spine list.
- [x] Add "Export Selected Images..." action.
  - [x] Ask for an output folder.
  - [x] Export only selected non-blank entries with original image bytes where possible.
  - [x] Use collision-safe filenames.
  - [ ] Offer filename mode: spine order (`0001.jpg`) vs source page (`source-0004.jpg`).
- [x] Handle edge cases.
  - [x] Selected blanks only: show a friendly "No exportable images selected" message.
  - [x] Mixed blanks/images: export images and report skipped blanks.
  - [x] Inserted external images: export their stored bytes too.
  - [ ] Existing files: confirm overwrite or auto-suffix.
- [x] Add tests for filename generation and blank skipping.

## Phase 4 - External Image Insertion

- [x] Add model support for external image entries.
  - [x] Accept JPEG and PNG first.
  - [x] Store bytes, dimensions, media type, source path, and a stable entry type.
  - [x] Insert before/after selected spine position.
  - [x] Include inserted images in EPUB export and selected-image export.
- [x] Add GUI actions.
  - [x] "Insert Image Before".
  - [x] "Insert Image After".
  - [x] Preview inserted images in the spread canvas.
- [x] Edge cases.
  - [x] Unsupported file type.
  - [x] Corrupt image.
  - [ ] Very large image.
  - [ ] Inserting into an empty layout should be rejected unless a page size can be inferred.
- [x] Add tests for inserted image export.

## Phase 5 - Metadata And Cover

- [x] Add metadata fields to the model/export path.
  - [x] Title.
  - [x] Author/creator.
  - [x] Language, defaulting to `zh-Hant`.
  - [ ] Optional series/volume fields if useful for batch naming.
- [x] Update EPUB OPF generation.
  - [x] Write `<dc:title>`.
  - [x] Write `<dc:creator>` when author is set.
  - [x] Mark selected cover image with `properties="cover-image"`.
  - [x] Do not mark a blank page as cover.
- [x] Add GUI controls.
  - [x] Editable title field, default from PDF stem.
  - [x] Editable author field.
  - [x] "Set Selected As Cover".
  - [x] Visual marker in spine list for the cover entry.
- [x] Edge cases.
  - [x] If selected cover is deleted, fall back to first non-blank image.
  - [x] If no image pages remain, block EPUB export.
  - [ ] If cover is an inserted image, include it correctly in the manifest.
- [x] Add tests for OPF metadata escaping, cover selection, and cover deletion fallback.

## Phase 6 - Preset Format Upgrade

- [ ] Introduce preset `version: 2`.
  - [ ] Store operations or normalized entry descriptors instead of only blank positions and deleted pages.
  - [ ] Store metadata template options separately from per-book metadata.
  - [ ] Store cover rule: first image, explicit source page, explicit spine position, or per-book override.
  - [ ] Store quick-delete operations in a way that can be applied to different page counts safely.
- [ ] Keep loading version 1 presets.
  - [ ] Convert v1 blank positions and deleted source pages into the new in-memory plan.
  - [ ] Save new presets as v2 only.
- [ ] Validate preset application.
  - [ ] Same source page count: apply directly.
  - [ ] Different page count: warn and show what operations still apply.
  - [ ] Missing source pages after delete rules: skip with warning, not crash.
- [ ] Add tests for v1 compatibility and v2 round-trip.

## Phase 7 - Batch Project Workflow

- [x] Add a batch project data model.
  - [x] Queue item: PDF path, page count, title, author, output path, status, warnings, error text.
  - [x] Shared layout plan derived from the currently edited sample PDF.
  - [x] Per-PDF title/author fields in the data model.
- [x] Add GUI structure for the batch workspace.
  - [x] Left queue of PDFs with status: Pending, Ready, Warning, Exported, Failed.
  - [x] "Use Current Layout As Batch Template".
  - [x] "Add PDFs...".
  - [x] "Validate Batch...".
  - [x] "Export Ready...".
  - [ ] "Export All".
- [x] Batch validation.
  - [x] Detect page count mismatch.
  - [x] Detect output filename collisions.
  - [x] Detect unsupported/corrupt PDFs before export.
  - [x] Report warnings per queue item without stopping the whole batch.
- [x] Batch export behavior.
  - [x] Continue exporting other files if one fails.
  - [x] Show a final summary with exported/failed/skipped counts.
  - [x] Write EPUBs to a chosen output directory.
  - [x] Run normalization before each export.
- [ ] Preset integration.
  - [ ] Still support saving/loading presets.
  - [ ] Allow creating a batch project from a saved preset.
  - [ ] Allow exporting a preset from the current batch template.
- [x] Add tests for queue validation and partial failure handling.

## Phase 8 - GUI Polish And Usability

- [ ] Reorganize right-side controls into clear groups.
  - [ ] Insert.
  - [ ] Delete.
  - [ ] Export.
  - [ ] Metadata.
  - [ ] Batch.
- [ ] Keep the utilitarian Tkinter style, but reduce button clutter.
- [ ] Add status messages that say exactly what changed: deleted count, skipped blanks, normalized entries, exported count.
- [ ] Add keyboard shortcuts only where safe.
  - [ ] Delete selected page/range.
  - [ ] Undo/recover last delete group.
  - [ ] Export selected images.
- [ ] Avoid UI freezes during PDF loading, validation, thumbnail generation, and batch export.

## Phase 9 - Documentation

- [ ] Update README GUI workflow.
- [ ] Document quick delete semantics.
- [ ] Document normalization and why source labels can differ from exported filenames.
- [ ] Document selected image export.
- [ ] Document metadata and cover controls.
- [ ] Document batch project workflow with a recommended volume-set flow.
- [ ] Add a migration note for old presets.

## Open Questions For Review

- [ ] Should quick delete page numbers refer to current spine positions or original PDF source page numbers?
- [ ] Should "Normalize Export Order" rename only exported EPUB internals, or also change visible list labels from `Page 4` to `Page 1`?
- [ ] For selected image export, do you prefer filenames by current spine order or original source page number as the default?
- [ ] Should inserted external images be included in presets, or should presets store only their positions and require re-linking image files?
- [ ] In batch projects, should one sample layout be mandatory, or should the queue support per-PDF independent edits from day one?
- [ ] Should batch export auto-fill titles from PDF filenames only, or support a series template such as `Book Name Vol. {n}`?

## Suggested Implementation Order

- [ ] First: model normalization plus quick delete, because they fix page-order correctness and deletion speed.
- [x] Second: metadata and cover, because they touch EPUB OPF and should be stable before batch export.
- [x] Third: selected image export and external image insertion.
- [ ] Fourth: preset v2 compatibility.
- [x] Fifth: batch project queue and validation.
- [ ] Sixth: README and GUI polish.

## Verification Checklist Before Marking Complete

- [ ] `python -m py_compile epub_layout_gui.py epub_layout_model.py pdf_to_epub_lossless.py pdf_to_cbz_lossless.py`
- [ ] `python -m unittest`
- [ ] Manual GUI smoke test: open PDF, quick delete, normalize, undo, export EPUB.
- [ ] Manual GUI smoke test: set title/author/cover and inspect OPF inside EPUB.
- [ ] Manual GUI smoke test: export selected images.
- [ ] Manual GUI smoke test: batch project with at least two PDFs, one matching and one mismatched.
