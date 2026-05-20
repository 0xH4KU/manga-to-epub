PYTHON ?= .venv/bin/python

.PHONY: setup test lint smoke

setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install -U pip
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m py_compile epub_layout_gui.py epub_layout_gui_support.py epub_layout_preview.py epub_layout_model.py epub_batch_model.py epub_series_model.py epub_writer.py epub_validation.py pdf_to_epub_lossless.py pdf_to_cbz_lossless.py fitz_compat.py
	$(PYTHON) -m unittest

lint:
	$(PYTHON) -m py_compile epub_layout_gui.py epub_layout_gui_support.py epub_layout_preview.py epub_layout_model.py epub_batch_model.py epub_series_model.py epub_writer.py epub_validation.py pdf_to_epub_lossless.py pdf_to_cbz_lossless.py fitz_compat.py

smoke:
	$(PYTHON) pdf_to_epub_lossless.py --help >/dev/null
	$(PYTHON) pdf_to_cbz_lossless.py --help >/dev/null
