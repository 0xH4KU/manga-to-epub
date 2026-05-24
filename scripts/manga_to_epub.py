#!/usr/bin/env python3
"""Compatibility wrapper for the manga source to EPUB converter CLI."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from manga_pdf_to_epub.cli.pdf_to_epub_lossless import main


if __name__ == "__main__":
    raise SystemExit(main())
