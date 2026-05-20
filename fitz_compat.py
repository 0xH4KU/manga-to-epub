from __future__ import annotations

import importlib

from pdf_to_cbz_lossless import PdfImageError


def load_fitz():
    try:
        return importlib.import_module("fitz")
    except ModuleNotFoundError as exc:
        raise PdfImageError(
            "PyMuPDF is required for GUI previews and layout editing. "
            "Install project dependencies with `.venv/bin/python -m pip install -r requirements.txt`."
        ) from exc
