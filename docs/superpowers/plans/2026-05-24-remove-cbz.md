# Remove CBZ Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove CBZ export and split PDF image extraction into small, focused modules while preserving EPUB behavior.

**Architecture:** Move shared image types into `pdf_image_types.py`, byte-level PDF parsing into `pdf_object_parser.py`, Flate/PNG conversion into `pdf_png.py`, and PyMuPDF page-order extraction into `pdf_image_extraction.py`. Delete public CBZ wrappers and update all EPUB imports to the new module names.

**Tech Stack:** Python 3.11+, unittest, PyMuPDF, Makefile targets.

---

### Task 1: Create Red Tests For The New Boundary

**Files:**
- Create: `tests/test_pdf_object_parser.py`
- Create: `tests/test_pdf_png.py`
- Create: `tests/test_pdf_image_extraction.py`
- Modify: `tests/test_project_guardrails.py`
- Modify: `tests/test_pdf_to_epub_lossless.py`
- Modify: `tests/test_epub_layout_model.py`
- Modify: `tests/test_epub_page_factory.py`
- Modify: `tests/test_fitz_compat.py`

- [ ] **Step 1: Add tests importing the new modules**

Move useful non-CBZ image extraction checks out of `tests/test_pdf_to_cbz_lossless.py` and update imports to:

```python
from manga_pdf_to_epub.pdf_image_types import ImageStream, PdfImageError
from manga_pdf_to_epub.pdf_image_extraction import images_in_pdf_page_order, _image_from_xref
from manga_pdf_to_epub.pdf_object_parser import iter_image_streams
from manga_pdf_to_epub.pdf_png import flate_image_to_png, image_to_epub_member
```

- [ ] **Step 2: Add guardrail tests for removed CBZ files**

Add assertions that `pdf_to_cbz_lossless.py`, `src/manga_pdf_to_epub/pdf_to_cbz_lossless.py`, and `tests/test_pdf_to_cbz_lossless.py` do not exist, and that tracked source/test/docs files contain no `pdf_to_cbz_lossless` import references.

- [ ] **Step 3: Run targeted tests to verify red**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_pdf_object_parser tests.test_pdf_png tests.test_pdf_image_extraction tests.test_project_guardrails -v
```

Expected: FAIL because the new modules do not exist and old CBZ files still exist.

### Task 2: Split The PDF Image Extraction Code

**Files:**
- Create: `src/manga_pdf_to_epub/pdf_image_types.py`
- Create: `src/manga_pdf_to_epub/pdf_object_parser.py`
- Create: `src/manga_pdf_to_epub/pdf_png.py`
- Create: `src/manga_pdf_to_epub/pdf_image_extraction.py`
- Modify: `src/manga_pdf_to_epub/epub_page_factory.py`
- Modify: `src/manga_pdf_to_epub/pdf_to_epub_lossless.py`
- Modify: `src/manga_pdf_to_epub/epub_layout_model.py`
- Modify: `src/manga_pdf_to_epub/epub_writer.py`
- Modify: `src/manga_pdf_to_epub/epub_validation.py`
- Modify: `src/manga_pdf_to_epub/fitz_compat.py`

- [ ] **Step 1: Create minimal new modules by moving existing code**

Move `PdfImageError` and `ImageStream` into `pdf_image_types.py`; PDF object byte parsing into `pdf_object_parser.py`; Flate/PNG conversion into `pdf_png.py`; PyMuPDF page-order extraction into `pdf_image_extraction.py`.

- [ ] **Step 2: Update production imports**

Replace imports from `.pdf_to_cbz_lossless` with imports from the new focused modules.

- [ ] **Step 3: Run targeted tests to verify green**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_pdf_object_parser tests.test_pdf_png tests.test_pdf_image_extraction tests.test_epub_page_factory tests.test_fitz_compat -v
```

Expected: PASS after imports and modules are correct.

### Task 3: Remove Public CBZ Feature

**Files:**
- Delete: `pdf_to_cbz_lossless.py`
- Delete: `src/manga_pdf_to_epub/pdf_to_cbz_lossless.py`
- Delete: `tests/test_pdf_to_cbz_lossless.py`
- Modify: `pyproject.toml`
- Modify: `Makefile`
- Modify: `README.md`
- Modify: `MAINTAINING.md`
- Modify: `src/manga_pdf_to_epub/__init__.py`

- [ ] **Step 1: Delete CBZ files and entry points**

Remove the root wrapper, package module, CBZ tests, package console script, and smoke checks.

- [ ] **Step 2: Update docs**

Remove CBZ feature text from README and update maintainer boundaries to point at the new image extraction modules.

- [ ] **Step 3: Search for stale references**

Run:

```bash
rg -n "pdf_to_cbz_lossless|pdf-to-cbz|convert_pdf_to_cbz|CBZ|cbz" .
```

Expected: only historical plan/spec references may remain; runtime code, README, Makefile, pyproject, and tests should not advertise CBZ.

### Task 4: Final Verification

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run lint**

Run:

```bash
make lint
```

Expected: PASS.

- [ ] **Step 2: Run full tests**

Run:

```bash
make test
```

Expected: PASS.

- [ ] **Step 3: Inspect git diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: only planned CBZ removal, image extraction split, docs, tests, and plan changes.
