from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


CandidateStatus = Literal["pending", "true", "false"]


def adjacent_pair_id(start_page: int, end_page: int) -> str:
    return f"{start_page:03d}-{end_page:03d}"


@dataclass(frozen=True)
class SpreadCandidate:
    pair_id: str
    start_page: int
    end_page: int
    score: float
    review_score: float
    decision: str
    source: str = "scan"
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class InsertCandidate:
    gap_id: str
    after_page: int
    before_page: int
    safe_insert_score: float
    label: str
    visual_difference: float
    continuity_risk: float
    reasons: tuple[str, ...] = ()


@dataclass
class ReviewedSpreadCandidate:
    candidate: SpreadCandidate
    status: CandidateStatus = "pending"


SPREAD_CLUSTER_REQUIRED_COLUMNS = {
    "start_page",
    "end_page",
    "decision",
    "spread",
    "review_score",
}

INSERT_GAP_REQUIRED_COLUMNS = {
    "gap",
    "after_page",
    "before_page",
    "safe_insert_score",
    "label",
    "visual_difference",
    "continuity_risk",
    "reasons",
}

REVIEWABLE_INSERT_LABEL_PREFIXES = ("A ", "B ", "C ", "D ")


def read_spread_candidates_csv(path: Path) -> list[SpreadCandidate]:
    rows = _read_dict_rows(path, SPREAD_CLUSTER_REQUIRED_COLUMNS)
    candidates: list[SpreadCandidate] = []
    for row in rows:
        start_page = int(row["start_page"])
        end_page = int(row["end_page"])
        candidates.append(
            SpreadCandidate(
                adjacent_pair_id(start_page, end_page),
                start_page,
                end_page,
                float(row["spread"]),
                float(row["review_score"]),
                row["decision"],
                source="spread-continuity",
            )
        )
    return sorted(candidates, key=lambda item: (-item.score, item.start_page, item.end_page))


def read_insert_candidates_csv(path: Path) -> list[InsertCandidate]:
    rows = _read_dict_rows(path, INSERT_GAP_REQUIRED_COLUMNS)
    candidates: list[InsertCandidate] = []
    for row in rows:
        reasons = tuple(part.strip() for part in row["reasons"].split(";") if part.strip())
        candidates.append(
            InsertCandidate(
                row["gap"],
                int(row["after_page"]),
                int(row["before_page"]),
                float(row["safe_insert_score"]),
                row["label"],
                float(row["visual_difference"]),
                float(row["continuity_risk"]),
                reasons,
            )
        )
    return sorted(candidates, key=lambda item: (-item.safe_insert_score, item.after_page, item.before_page))


def reviewable_insert_candidates(candidates: list[InsertCandidate]) -> list[InsertCandidate]:
    return [item for item in candidates if item.label.startswith(REVIEWABLE_INSERT_LABEL_PREFIXES)]


def _read_dict_rows(path: Path, required_columns: set[str]) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(required_columns - fieldnames)
        if missing:
            raise ValueError(f"{path.name} is missing required columns: {', '.join(missing)}")
        return list(reader)


class DiagnosisSession:
    def __init__(self, source_page_count: int):
        self.source_page_count = source_page_count
        self._candidates: dict[str, ReviewedSpreadCandidate] = {}

    def load_spread_candidates(self, candidates: list[SpreadCandidate]) -> None:
        self._candidates = {}
        for candidate in sorted(candidates, key=lambda item: (-item.score, item.start_page, item.end_page)):
            self._validate_pair(candidate.start_page, candidate.end_page)
            self._candidates[candidate.pair_id] = ReviewedSpreadCandidate(candidate)

    def spread_candidates(self) -> list[ReviewedSpreadCandidate]:
        return list(self._candidates.values())

    def mark_candidate(self, pair_id: str, status: CandidateStatus) -> None:
        if status not in {"pending", "true", "false"}:
            raise ValueError("Unsupported spread candidate status")
        if pair_id not in self._candidates:
            raise KeyError(pair_id)
        self._candidates[pair_id].status = status

    def add_manual_spread(self, start_page: int, end_page: int) -> SpreadCandidate:
        self._validate_pair(start_page, end_page)
        pair_id = adjacent_pair_id(start_page, end_page)
        candidate = SpreadCandidate(pair_id, start_page, end_page, 1.0, 1.0, "manual", source="manual")
        self._candidates[pair_id] = ReviewedSpreadCandidate(candidate, "true")
        return candidate

    def pending_count(self) -> int:
        return sum(1 for item in self._candidates.values() if item.status == "pending")

    def confirmed_spreads(self) -> list[SpreadCandidate]:
        confirmed = [item.candidate for item in self._candidates.values() if item.status == "true"]
        return sorted(confirmed, key=lambda item: (item.start_page, item.end_page))

    def _validate_pair(self, start_page: int, end_page: int) -> None:
        if start_page < 1 or end_page > self.source_page_count:
            raise ValueError("Spread pair is outside the source page range")
        if end_page != start_page + 1:
            raise ValueError("Spread pair must use adjacent source pages")
