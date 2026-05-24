#!/usr/bin/env python3
"""Compatibility wrapper for the EPUB layout GUI."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from manga_pdf_to_epub.gui.layout_app import main


if __name__ == "__main__":
    raise SystemExit(main())
