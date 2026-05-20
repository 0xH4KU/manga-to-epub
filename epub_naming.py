from __future__ import annotations

import re
from pathlib import Path


def infer_volume_number(path: Path, fallback: int = 1) -> int:
    match = re.search(r"\b(?:vol(?:ume)?\.?\s*)(\d+)\b", path.stem, re.IGNORECASE)
    if match:
        return int(match.group(1))
    trailing = re.search(r"(\d+)\s*$", path.stem)
    if trailing:
        return int(trailing.group(1))
    return fallback


def generated_volume_title(series_title: str, volume_number: int) -> str:
    return f"{series_title} Vol.{volume_number:02d}"


def safe_filename(title: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "Untitled"
