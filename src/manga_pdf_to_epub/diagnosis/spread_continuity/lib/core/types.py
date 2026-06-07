from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Page:
    name: str
    path: Path
    bgr: np.ndarray
    gray: np.ndarray


@dataclass(frozen=True)
class PairScore:
    right_name: str
    left_name: str
    total: float
    spread: float
    review_score: float
    offset: int
    color: float
    gradient: float
    profile: float
    edge: float
    ink: float
    energy: float
    orientation: float
    line: float
    texture: float
    corr: float
    color_style: float
    panel: float
    page_panel: float
    inner_gutter: float
    composition: float
    seam_activity: float
    seam_contact: float
    patch: float
    barrier: float
    expected: bool
    raw_spread: float = 0.0
    raw_review_score: float = 0.0
    local_margin: float = 0.0
    context_penalty: float = 0.0
    context_boost: float = 0.0
    stability_score: float = 0.0
    relative_score: float = 0.0
    reliability_penalty: float = 0.0
    reliability_boost: float = 0.0
