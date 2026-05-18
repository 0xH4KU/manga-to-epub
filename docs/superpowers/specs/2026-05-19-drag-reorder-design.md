# Single-Page Drag Reorder Design

## Context

The EPUB Layout Lab already treats the visible `LayoutModel.entries` list as the editable EPUB spine. Existing blank insertion, page deletion, image insertion, v2 presets, batch templates, preview rendering, and EPUB export all derive from that entry order.

Some manga PDFs contain image pages in the wrong order. Users need a direct way to fix that order before export without changing the underlying PDF extraction logic.

## Goal

Add first-version drag reorder support to the Tkinter spine list:

- Drag one visible spine entry to a new position.
- Support source pages, inserted image pages, and blank pages.
- Update the model order, spine list, preview, status, presets, and batch templates through the existing `LayoutModel.entries` flow.
- Leave multi-select or automatic sorting for future work.

## Non-Goals

- Multi-entry drag reorder.
- Automatic page-order detection.
- Filename/page-number sorting rules.
- Reordering the source PDF or changing low-level PDF image extraction order.
- A separate sorting dialog or sorting mode.

## UX

The user drags a single row in the left `Spine order` list and releases it over the target row. The dragged entry is moved to the drop position. The GUI then:

- Keeps the moved entry selected at its new position.
- Preserves the list scroll position when practical.
- Refreshes the RTL spread preview.
- Shows a status message such as `Moved Page 4 to position 2.`

If the mouse is released without moving to a different row, no model change is made.

The first version will not try to preserve multi-row selections during a drag. If several rows are selected, the row where the drag begins is the only moved entry. Multi-page drag remains a future enhancement.

## Model Design

Add a small model operation:

```python
LayoutModel.move_entry(from_index: int, to_index: int) -> int
```

Behavior:

- Validate `from_index` and `to_index` against current `entries`.
- Treat `to_index` as the desired final visible row after the move.
- Remove the entry at `from_index`.
- Insert it so the moved entry lands at that final row, adjusting for the removal when moving downward.
- Return the final inserted index.
- Call `_ensure_valid_cover()` after the move.

Moving a cover entry keeps cover identity intact because cover tracking is based on source index or inserted entry id, not list position.

## GUI Design

Bind mouse events on `self.page_list`:

- `<ButtonPress-1>` stores the row nearest the press as the drag source.
- `<B1-Motion>` optionally updates a lightweight drag indicator through selection/highlight behavior.
- `<ButtonRelease-1>` finds the release row and calls the model move operation when the source and target differ.

The drop target is clamped to the valid list range. Dragging below the last visible row should move the entry to the end.

After a successful move:

- `refresh_list(preserve_yview=True)`
- Clear selection and select the moved row.
- `refresh_preview()`
- Update status.

The command palette does not need a new command for drag reorder.

## Data Flow

`Listbox drag event -> EpubLayoutApp.move_selected_entry/drop handler -> LayoutModel.move_entry -> refresh_list -> refresh_preview`

EPUB export, selected image export naming, preset save, and batch template creation need no special reorder-specific persistence because they already consume the current `entries` order.

## Error Handling

Invalid drag sources or targets are ignored without showing a dialog. Model-level index errors should be caught by the GUI and shown with `messagebox.showerror("Move page failed", str(exc))`, though normal GUI clamping should prevent them.

## Testing

Model tests:

- Moving a middle source page to the front changes `entries` order.
- Moving an entry down accounts for the removed source index correctly.
- Moving a blank page is allowed.
- Moving the cover entry keeps `normalized_cover_item_id()` valid.
- Invalid indexes raise `IndexError`.

GUI tests:

- Simulated drag release calls `move_entry`, refreshes list and preview, selects the final row, and sets a status message.
- Releasing on the original row does nothing.
- Dragging a row while multiple rows are selected only moves the pressed row.

Full verification remains:

```bash
./.venv/bin/python -m py_compile epub_layout_gui.py epub_layout_model.py epub_batch_model.py pdf_to_epub_lossless.py pdf_to_cbz_lossless.py
./.venv/bin/python -m unittest
```

## Future Work

- Multi-entry drag reorder for moving selected page ranges as a group.
- Keyboard move commands, such as move up/down, as accessibility and precision helpers.
- Automatic or rule-based sorting for imported image folders or unusual PDFs.
