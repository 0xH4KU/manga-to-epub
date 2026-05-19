# Manga PDF to EPUB

Lossless PDF to EPUB/CBZ tools for manga readers who care about page pairing, cover gaps, and Apple Books layout quirks.

This project is not a general-purpose "compress my PDF" converter. It is for fixed-layout manga workflows where the source PDF already contains page images, and the goal is to preserve those images while tuning the reading order for Apple Books.

## Why This Exists

Apple Books can add a virtual blank page beside the cover. For manga, that small invisible choice can shift every following spread and break double-page artwork. Most converters produce technically valid EPUB files but give you no practical way to preview or correct that pairing.

This tool focuses on the boring-but-crucial details:

- Preserve original PDF image streams when possible.
- Export EPUB 3 fixed-layout books for right-to-left manga reading.
- Preview Apple Books' cover-side virtual blank page.
- Insert or remove real blank pages at arbitrary positions.
- Quick-delete the first N, last N, or a spine-position range.
- Normalize exported EPUB internals so spine order, XHTML names, image names, and item IDs stay sequential after edits.
- Set EPUB title, author, language, and cover image from the GUI.
- Insert external JPEG/PNG pages into the EPUB spine, including separately sourced covers.
- Export selected spine images losslessly to a folder.
- Save v2 layout presets with spine order, metadata, cover rule, blanks, deleted pages, and inserted-image references.
- Apply presets to selected series volumes while keeping generated series titles such as `Series Title Vol.01`.
- Import a manga series, review volumes individually, mark reviewed volumes ready, unready selected volumes when needed, and export ready volumes together.
- Validate generated EPUB structure before reporting export success.
- Recover deleted pages during layout editing.

## Features

- PDF to EPUB without image recompression for JPEG image streams.
- PDF Flate image streams are wrapped into PNG containers.
- PDF to CBZ export with page-tree order preservation.
- Tkinter GUI for manual manga layout tuning.
- Preview-only Apple Books cover-gap mode with a virtual blank page on the right of the first spine item.
- Arbitrary blank page insertion before or after selected pages.
- Page deletion with recover support.
- Preset save/load for applying layout corrections to one volume or a scoped set of series volumes.
- Series import with generated `Vol.xx` titles, multi-volume ready marking, selected-volume unready, and ready-only export.

## Install

Use Python 3.11 or newer. Tkinter is included with the standard Python.org macOS installer and most system Python builds.

```bash
cd /Users/HAKU/github/manga-pdf-to-epub
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt
```

## GUI Workflow

Launch the layout editor:

```bash
.venv/bin/python epub_layout_gui.py
```

Typical single-volume Apple Books manga workflow:

1. Open a PDF volume.
2. Keep `Preview Apple Books cover gap` enabled.
3. Inspect spreads in the preview.
4. Insert blank pages where needed to realign double-page artwork.
5. Delete unwanted pages if necessary. Use `Delete Selected Page` for normal edits; open the command palette for `Delete First...`, `Delete Last...`, or `Delete Range...`.
6. Use `Recover Last Deleted` or `Cmd+Z` if a page or range was removed by mistake.
7. Edit title, author, and language, then select any source or inserted image page and use `Set Selected As Cover` when the first image should not be the cover.
8. Enable `Cover only, exclude from pages` when the cover should be used only as EPUB cover art and not appear as a reading page.
9. Insert external JPEG/PNG pages if needed. Inserted pages can be exported as reading pages, selected as cover art, or excluded from reading pages when used as cover-only art.
10. Export EPUB and import it into Apple Books for final checking.

The GUI normalizes EPUB internals during export. For example, if source pages 1-3 are deleted and the visible list starts with source `Page 4`, the exported EPUB still uses sequential names such as `page-0001.xhtml` and `images/page-0001.jpg`. The visible source labels remain unchanged so you can trace edits back to the original PDF.

## Series Project Workflow

For a manga series:

1. Click `Import Series...` and choose the PDFs for the series.
2. Review the `Series volumes` list. Files are naturally sorted, and EPUB titles are generated as `Series Title Vol.xx`.
3. Select a volume to load it into the existing page editor.
4. Fix blank pages, deletions, inserted images, and cover choices per volume.
5. Select one or more volumes and click `Mark Selected Volume Ready` after reviewing them.
6. If a ready volume needs more work, select it and click `Unready Selected`. Only the selected volumes are restored from ready history; the rest of the batch stays ready.
7. Click `Export Ready Series...` to export only volumes marked `Ready`.

The series workflow avoids blindly applying a single correction template to every volume. If Vol.05 needs no blank page while Vol.06 needs two blanks, each volume can keep its own layout before it is marked ready.

When no deleted page is waiting to be recovered, `Cmd+Z` uses the same selected-first unready behavior as `Unready Selected`.

## Presets

Newly saved presets use `version: 2`. They preserve the edited spine order, blank pages, deleted source pages, metadata defaults, cover-only mode, selected cover rule, and paths to inserted JPEG/PNG pages.

In series mode, `Load Preset` asks which volumes should receive the preset. Scope input supports comma-separated volumes such as `1,2,7`, ranges such as `1-7`, or `all`. After applying a preset, each target volume still uses the series title, author, language, and generated `Vol.xx` title instead of copying one volume's full metadata onto every book.

Version 1 presets from earlier builds still load. When a v2 preset references an inserted image, that image file must still exist at the saved path so it can be reinserted into the target layout.

## Command Line

Convert PDF files to fixed-layout EPUB:

```bash
.venv/bin/python pdf_to_epub_lossless.py "Volume 01.pdf" --overwrite
```

Insert one real blank page before the cover:

```bash
.venv/bin/python pdf_to_epub_lossless.py "Volume 01.pdf" \
  --blank-pages-before-cover 1 \
  --overwrite
```

Export multiple PDFs into a directory:

```bash
.venv/bin/python pdf_to_epub_lossless.py *.pdf \
  --output-dir ./epub-output \
  --overwrite
```

For OPF spread metadata, `--pair-first-two-pages` explicitly marks the first two source pages as a right-to-left spread pair. `--apple-books` instead writes centered single-page spread metadata for every reading page; these modes are mutually exclusive.

Export CBZ:

```bash
.venv/bin/python pdf_to_cbz_lossless.py "Volume 01.pdf" --overwrite
```

## Apple Books Notes

The GUI preview deliberately models Apple Books' cover behavior by adding a virtual blank page on the right of the first spine item. This virtual page is not exported into the EPUB. It is only a preview aid so you can decide whether to insert a real blank page into the EPUB spine.

If Apple Books shifts spreads after import, try inserting a real blank page before the cover, then preview again with `Preview Apple Books cover gap` enabled.

## EPUB Validation

Every EPUB export now runs a lightweight structure check before success is reported. The check verifies the `mimetype` entry, core container/OPF files, manifest hrefs, spine idrefs, and cover-image references.

The OPF modified timestamp is intentionally deterministic so repeated exports are easier to compare.

## Lossless Scope

The converter avoids recompressing source artwork where the PDF stores JPEG image streams. Those JPEG bytes are copied directly into the EPUB/CBZ.

For Flate-compressed PDF image streams, the tool wraps the image data into PNG. If the PDF uses PNG-style predictors, the compressed rows can be reused inside the PNG container. Unsupported PDF color spaces or filter chains raise an error instead of silently degrading output.

## Project Files

- `pdf_to_epub_lossless.py` - fixed-layout EPUB exporter.
- `pdf_to_cbz_lossless.py` - CBZ exporter and low-level PDF image extraction.
- `epub_layout_model.py` - editable spine model, blank pages, image insertion, metadata, presets, export glue.
- `epub_series_model.py` - series workspace, volume status, generated titles, and ready-volume export.
- `epub_batch_model.py` - legacy batch project queue retained for tests and migration while series workflow replaces it.
- `epub_layout_gui.py` - Apple Books-oriented layout GUI.
- `test_*.py` - unit tests for conversion, layout, and preview behavior.

## Test

```bash
.venv/bin/python -m py_compile epub_layout_gui.py epub_layout_model.py epub_batch_model.py epub_series_model.py pdf_to_epub_lossless.py pdf_to_cbz_lossless.py
.venv/bin/python -m unittest
```

## Limitations

- Designed for image-based comic PDFs, not text-first PDFs.
- Multi-image PDF pages may need more validation.
- Apple Books behavior is modeled from observed behavior and should still be checked with real imports.
- The GUI is intentionally utilitarian; it prioritizes reliable layout correction over visual polish.

## Positioning

This is a specialist tool for manga collectors and readers who want Apple Books to preserve intentional spreads. If Calibre/KCC-style conversion is enough for a book, use that. This project earns its keep when a volume needs page-level correction, Apple Books preview assumptions, and lossless source-image handling.
