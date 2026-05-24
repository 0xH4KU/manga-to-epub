# Repo Structure Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize the repository layout by keeping the root clean, moving command wrappers into `scripts/`, and grouping source modules into focused packages.

**Architecture:** Keep public console entry points working through `pyproject.toml`. Move implementation modules into `pdf/`, `epub/`, `gui/`, and `models/` packages, then update relative imports and tests. Keep compatibility aliases only where external imports are likely.

**Tech Stack:** Python 3.14, setuptools `src` layout, unittest, Makefile.

---

### Task 1: Add Structure Guardrails

**Files:**
- Modify: `tests/test_project_guardrails.py`

- [ ] **Step 1: Write failing tests**

Add tests that assert root wrappers are gone, `scripts/` wrappers exist, and package subdirectories exist:

```python
def test_root_only_keeps_project_level_files(self):
    self.assertFalse(Path("epub_layout_gui.py").exists())
    self.assertFalse(Path("pdf_to_epub_lossless.py").exists())
    self.assertTrue(Path("scripts/epub_layout_gui.py").exists())
    self.assertTrue(Path("scripts/pdf_to_epub_lossless.py").exists())

def test_source_modules_are_grouped_by_responsibility(self):
    expected_packages = [
        Path("src/manga_pdf_to_epub/pdf"),
        Path("src/manga_pdf_to_epub/epub"),
        Path("src/manga_pdf_to_epub/gui"),
        Path("src/manga_pdf_to_epub/models"),
    ]
    self.assertEqual([], [str(path) for path in expected_packages if not path.is_dir()])
```

- [ ] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_project_guardrails.ProjectGuardrailTests.test_root_only_keeps_project_level_files tests.test_project_guardrails.ProjectGuardrailTests.test_source_modules_are_grouped_by_responsibility
```

Expected: FAIL because wrappers and package directories have not moved yet.

### Task 2: Move Files And Update Imports

**Files:**
- Move: root wrappers into `scripts/`
- Move: PDF modules into `src/manga_pdf_to_epub/pdf/`
- Move: EPUB modules into `src/manga_pdf_to_epub/epub/`
- Move: GUI modules into `src/manga_pdf_to_epub/gui/`
- Move: model modules into `src/manga_pdf_to_epub/models/`
- Modify: package imports, `pyproject.toml`, `Makefile`, README

- [ ] **Step 1: Create package directories**

Create `__init__.py` files in `pdf/`, `epub/`, `gui/`, and `models/`.

- [ ] **Step 2: Move implementation modules**

Move files by responsibility and update imports with `rg` plus targeted edits.

- [ ] **Step 3: Keep console scripts valid**

Update `pyproject.toml` scripts:

```toml
pdf-to-epub-lossless = "manga_pdf_to_epub.cli.pdf_to_epub_lossless:main"
epub-layout-gui = "manga_pdf_to_epub.gui.epub_layout_gui:main"
```

- [ ] **Step 4: Verify focused tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_project_guardrails
```

Expected: PASS.

### Task 3: Documentation And Full Verification

**Files:**
- Modify: `README.md`
- Modify: `Makefile`
- Optional create: `docs/project-structure.md`

- [ ] **Step 1: Update usage docs**

Prefer console scripts and `python -m` examples over root script examples.

- [ ] **Step 2: Run final checks**

Run:

```bash
make test
make lint
make smoke
git diff --check
```

Expected: all commands exit 0.
