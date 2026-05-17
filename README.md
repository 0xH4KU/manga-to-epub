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
- Save a layout preset and batch-apply it to a volume set.
- Recover deleted pages during layout editing.

## Features

- PDF to EPUB without image recompression for JPEG image streams.
- PDF Flate image streams are wrapped into PNG containers.
- PDF to CBZ export with page-tree order preservation.
- Tkinter GUI for manual manga layout tuning.
- Apple Books-like preview mode with a virtual blank page on the right of the first spine item.
- Arbitrary blank page insertion before or after selected pages.
- Page deletion with recover support.
- Preset save/load for applying the same layout correction to multiple volumes.
- Batch export from a saved preset.

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

Typical Apple Books manga workflow:

1. Open a PDF volume.
2. Keep `Apple Books-like cover-right gap` enabled.
3. Inspect spreads in the preview.
4. Insert blank pages where needed to realign double-page artwork.
5. Delete unwanted pages if necessary.
6. Use `Recover Last Deleted` or `Cmd+Z` if a page was removed by mistake.
7. Save a preset after one volume is correct.
8. Batch-apply the preset to the rest of the set when the books share the same page structure.
9. Export EPUB and import it into Apple Books for final checking.

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

Export CBZ:

```bash
.venv/bin/python pdf_to_cbz_lossless.py "Volume 01.pdf" --overwrite
```

## Apple Books Notes

The GUI preview deliberately models Apple Books' cover behavior by adding a virtual blank page on the right of the first spine item. This virtual page is not exported into the EPUB. It is only a preview aid so you can decide whether to insert a real blank page into the EPUB spine.

If Apple Books shifts spreads after import, try inserting a real blank page before the cover, then preview again with Apple Books-like mode enabled.

## Lossless Scope

The converter avoids recompressing source artwork where the PDF stores JPEG image streams. Those JPEG bytes are copied directly into the EPUB/CBZ.

For Flate-compressed PDF image streams, the tool wraps the image data into PNG. If the PDF uses PNG-style predictors, the compressed rows can be reused inside the PNG container. Unsupported PDF color spaces or filter chains raise an error instead of silently degrading output.

## Project Files

- `pdf_to_epub_lossless.py` - fixed-layout EPUB exporter.
- `pdf_to_cbz_lossless.py` - CBZ exporter and low-level PDF image extraction.
- `epub_layout_model.py` - editable spine model, blank pages, presets, export glue.
- `epub_layout_gui.py` - Apple Books-oriented layout GUI.
- `test_*.py` - unit tests for conversion, layout, and preview behavior.

## Test

```bash
.venv/bin/python -m py_compile epub_layout_gui.py epub_layout_model.py pdf_to_epub_lossless.py pdf_to_cbz_lossless.py
.venv/bin/python -m unittest
```

## Limitations

- Designed for image-based comic PDFs, not text-first PDFs.
- Multi-image PDF pages may need more validation.
- Apple Books behavior is modeled from observed behavior and should still be checked with real imports.
- The GUI is intentionally utilitarian; it prioritizes reliable layout correction over visual polish.

## Positioning

This is a specialist tool for manga collectors and readers who want Apple Books to preserve intentional spreads. If Calibre/KCC-style conversion is enough for a book, use that. This project earns its keep when a volume needs page-level correction, Apple Books preview assumptions, and lossless source-image handling.
