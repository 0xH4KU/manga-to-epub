# Maintaining This Project

This project should stay small, explicit, and workflow-driven. When adding behavior, prefer the existing model modules over growing the GUI class.

## Boundaries

- Keep runtime code in `src/manga_pdf_to_epub/`; root scripts are compatibility wrappers only.
- Keep PDF image extraction split by responsibility: shared image types in `src/manga_pdf_to_epub/pdf_image_types.py`, byte-level object parsing in `src/manga_pdf_to_epub/pdf_object_parser.py`, PNG wrapping in `src/manga_pdf_to_epub/pdf_png.py`, and PyMuPDF page-order extraction in `src/manga_pdf_to_epub/pdf_image_extraction.py`.
- Keep EPUB archive structure in `src/manga_pdf_to_epub/epub_writer.py` and validation in `src/manga_pdf_to_epub/epub_validation.py`.
- Keep shared naming rules in `src/manga_pdf_to_epub/epub_naming.py`.
- Keep `ImageStream` to `EpubPage` conversion in `src/manga_pdf_to_epub/epub_page_factory.py`.
- Keep layout state, presets, and export glue in `src/manga_pdf_to_epub/epub_layout_model.py`.
- Keep series status, validation, and export policy in `src/manga_pdf_to_epub/epub_series_model.py`.
- Keep GUI preflight/workflow helpers in focused modules such as `src/manga_pdf_to_epub/epub_layout_series_workflow.py`.
- Keep GUI series/project event wiring in `src/manga_pdf_to_epub/epub_layout_series_controller.py`.
- Keep GUI-only event wiring in `src/manga_pdf_to_epub/epub_layout_gui.py`.
- Keep tests in `tests/`; shared test fixtures belong in `tests/helpers.py` or `tests/gui_helpers.py`.
- Avoid adding optional export formats unless they justify their ongoing maintenance cost.

## Legacy Code

`src/manga_pdf_to_epub/epub_batch_model.py` is deprecated. It remains only for old tests and migration reference. Do not add new features to it; add or adapt `SeriesProject` behavior instead.

## Guardrails

- Add a failing test before behavior changes.
- Avoid new parallel state lists in the GUI. Use small helper models like `DeleteHistory`.
- If `EpubLayoutApp` grows, extract a controller/helper before adding more workflow state.
- Do not add hard-coded module lists to CI or Makefile; use package discovery or `compileall`.
- Keep `make test` green before committing.
