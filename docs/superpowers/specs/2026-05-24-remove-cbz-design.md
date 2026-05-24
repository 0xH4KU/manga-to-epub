# Remove CBZ Export And Split PDF Image Extraction Design

## Goal

Remove the rarely used CBZ export feature completely while preserving EPUB conversion behavior. As part of the removal, replace the oversized CBZ-named module with smaller PDF image extraction modules so future failures are easier to locate.

## Scope

In scope:

- Remove all public CBZ export entry points.
- Remove CBZ documentation, smoke checks, and dedicated CBZ tests.
- Delete the root `pdf_to_cbz_lossless.py` compatibility wrapper.
- Delete `src/manga_pdf_to_epub/pdf_to_cbz_lossless.py` after moving EPUB-required code into focused modules.
- Keep PDF image extraction, JPEG pass-through, Flate-to-PNG conversion, indexed palette handling, and PyMuPDF page-order extraction for EPUB.
- Keep `PdfImageError` as the shared user-facing conversion error type, but move it out of the CBZ module.

Out of scope:

- Changing EPUB archive structure.
- Changing GUI workflows.
- Adding new PDF filters or image formats.
- Reworking the large GUI class in this task. This change should reduce one maintenance hotspot without starting an unrelated GUI refactor.

## Architecture

The current `pdf_to_cbz_lossless.py` mixes four responsibilities: shared error/types, raw PDF object parsing, PDF image decoding, and CBZ archive/CLI behavior. The replacement should split these into smaller modules with one clear reason to change.

Planned module boundaries:

- `src/manga_pdf_to_epub/pdf_image_types.py`
  - Owns `PdfImageError` and `ImageStream`.
  - Has no dependencies on extraction, EPUB, or GUI code.

- `src/manga_pdf_to_epub/pdf_object_parser.py`
  - Owns small helpers for parsing PDF object bytes used by image extraction.
  - Contains dictionary/array/string matching, object extraction, integer extraction, filter-name extraction, and literal string decoding.
  - Does not know about EPUB, PNG, PyMuPDF documents, or CBZ.

- `src/manga_pdf_to_epub/pdf_png.py`
  - Owns conversion from Flate PDF image streams to PNG bytes.
  - Contains predictor undoing, PNG chunk writing, palette extraction, and color-space validation.
  - Depends only on image types and PDF object parsing helpers.

- `src/manga_pdf_to_epub/pdf_image_extraction.py`
  - Owns `images_in_pdf_page_order`.
  - Uses PyMuPDF xref APIs to return `ImageStream` objects in page-tree order.
  - Delegates Flate image payload conversion to `pdf_png.py` through the existing page factory flow.

- `src/manga_pdf_to_epub/epub_page_factory.py`
  - Continues converting `ImageStream` into `EpubPage`.
  - Imports `ImageStream` and image-payload conversion from the new modules instead of from a CBZ module.

No new file should become a dumping ground. If a file starts to combine unrelated concerns during implementation, prefer another small module over preserving the old shape.

## Public Interface Changes

Remove:

- Root command: `python pdf_to_cbz_lossless.py ...`
- Package console script: `pdf-to-cbz-lossless`
- Package module entry: `python -m manga_pdf_to_epub.pdf_to_cbz_lossless`
- Function-level public CBZ API: `convert_pdf_to_cbz`

Keep:

- `pdf-to-epub-lossless`
- `epub-layout-gui`
- Root EPUB and GUI compatibility wrappers.
- EPUB conversion behavior and current EPUB validation behavior.

## Documentation Changes

README should describe the project as PDF-to-EPUB/layout tooling only. Remove references that advertise CBZ export or describe CBZ commands.

`MAINTAINING.md` should be updated so boundaries point to the new image extraction modules instead of the deleted CBZ module. It should explicitly state that optional export formats should not be added unless they justify their maintenance cost.

## Testing Strategy

Use test-first changes:

1. Add or move tests that assert EPUB conversion imports image extraction from the new modules and still preserves JPEG/PNG behavior.
2. Add tests for the new focused modules by moving the useful non-CBZ cases from `tests/test_pdf_to_cbz_lossless.py` into `tests/test_pdf_image_extraction.py` and related module tests.
3. Update guardrail tests so the deleted CBZ module and root wrapper are absent.
4. Remove CBZ CLI/export tests.
5. Run targeted tests after each migration step, then run `make lint` and `make test`.

Expected final state:

- No tracked file named `pdf_to_cbz_lossless.py`.
- No README/Makefile/pyproject public CBZ entry point.
- No imports from `manga_pdf_to_epub.pdf_to_cbz_lossless`.
- EPUB tests continue to pass.

## Risks

- Moving `PdfImageError` can touch many modules. Keep a single canonical location and update imports mechanically.
- PDF image extraction has byte-level edge cases. Preserve tests for literal strings, predictors, indexed palettes, DCT pass-through, Flate PNG wrapping, and page-order extraction.
- A direct rename would be simpler but would keep the old module size problem. The implementation should accept a larger but controlled migration to improve long-term maintainability.

## Success Criteria

- The project has no user-visible CBZ feature.
- EPUB conversion, GUI export, and validation behavior remain unchanged.
- PDF image extraction is split into small files with clear ownership.
- Failures in object parsing, PNG conversion, xref extraction, or EPUB page creation can be localized to a focused module.
- `make lint` passes.
- `make test` passes.
