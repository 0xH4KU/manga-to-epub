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


@dataclass(frozen=True)
class SourcePlacement:
    source_index: int
    entry_index: int
    preview_index: int
    preview_pair_index: int


@dataclass(frozen=True)
class SpreadDamage:
    pair_id: str
    start_page: int
    end_page: int
    status: Literal["intact", "damaged", "missing"]
    reason: str
    start_entry_index: int | None
    end_entry_index: int | None


@dataclass(frozen=True)
class InsertReviewPoint:
    kind: Literal["suggested", "protected"]
    gap_id: str
    after_page: int
    before_page: int
    insertion_index: int
    marker_entry_index: int
    score: float
    label: str
    reason: str
    fixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class InsertClassification:
    suggestions: list[InsertReviewPoint]
    protected: list[InsertReviewPoint]
    stale_gap_ids: list[str]


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


class _DiagnosticBlank:
    label = "Diagnostic blank"
    source_index = None
    is_blank = True


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
        after_page = int(row["after_page"])
        before_page = int(row["before_page"])
        reasons = tuple(part.strip() for part in row["reasons"].split(";") if part.strip())
        candidates.append(
            InsertCandidate(
                adjacent_pair_id(after_page, before_page),
                after_page,
                before_page,
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


def source_preview_placements(entries: list, uses_apple_cover_gap: bool) -> dict[int, SourcePlacement]:
    placements: dict[int, SourcePlacement] = {}
    for entry_index, entry in enumerate(entries):
        source_index = getattr(entry, "source_index", None)
        if source_index is None or getattr(entry, "is_blank", False):
            continue
        preview_index = entry_index
        if uses_apple_cover_gap and entry_index >= 1:
            preview_index += 1
        placements[source_index] = SourcePlacement(
            source_index=source_index,
            entry_index=entry_index,
            preview_index=preview_index,
            preview_pair_index=preview_index // 2,
        )
    return placements


def diagnose_spread_damage(
    entries: list,
    confirmed_spreads: list[SpreadCandidate],
    uses_apple_cover_gap: bool,
) -> list[SpreadDamage]:
    placements = source_preview_placements(entries, uses_apple_cover_gap)
    reports: list[SpreadDamage] = []
    for spread in confirmed_spreads:
        start = placements.get(spread.start_page)
        end = placements.get(spread.end_page)
        if start is None or end is None:
            missing = []
            if start is None:
                missing.append(f"Page {spread.start_page}")
            if end is None:
                missing.append(f"Page {spread.end_page}")
            reports.append(
                SpreadDamage(
                    spread.pair_id,
                    spread.start_page,
                    spread.end_page,
                    "missing",
                    f"{' and '.join(missing)} missing from current layout",
                    start.entry_index if start else None,
                    end.entry_index if end else None,
                )
            )
            continue
        if start.preview_index + 1 != end.preview_index:
            reports.append(
                SpreadDamage(
                    spread.pair_id,
                    spread.start_page,
                    spread.end_page,
                    "damaged",
                    "Confirmed pages are in different preview spreads or wrong order",
                    start.entry_index,
                    end.entry_index,
                )
            )
            continue
        if start.preview_pair_index != end.preview_pair_index:
            reports.append(
                SpreadDamage(
                    spread.pair_id,
                    spread.start_page,
                    spread.end_page,
                    "damaged",
                    "Confirmed pages are in different preview spreads",
                    start.entry_index,
                    end.entry_index,
                )
            )
            continue
        reports.append(
            SpreadDamage(
                spread.pair_id,
                spread.start_page,
                spread.end_page,
                "intact",
                "Confirmed spread is paired in the current preview",
                start.entry_index,
                end.entry_index,
            )
        )
    return reports


def classify_insert_points(
    entries: list,
    confirmed_spreads: list[SpreadCandidate],
    insert_candidates: list[InsertCandidate],
    uses_apple_cover_gap: bool,
) -> InsertClassification:
    current_damage = diagnose_spread_damage(entries, confirmed_spreads, uses_apple_cover_gap)
    current_by_id = {item.pair_id: item for item in current_damage}
    intact_before = {item.pair_id for item in current_damage if item.status == "intact"}
    damaged_before = {item.pair_id for item in current_damage if item.status == "damaged"}
    suggestions: list[InsertReviewPoint] = []
    protected: list[InsertReviewPoint] = []
    stale: list[str] = []
    source_to_entry = _source_to_entry_index(entries)

    for candidate in reviewable_insert_candidates(insert_candidates):
        insertion_index = _insertion_index_for_candidate(candidate, source_to_entry)
        if insertion_index is None:
            stale.append(candidate.gap_id)
            continue
        marker_entry_index = max(0, insertion_index - 1)
        inside_pair = _confirmed_pair_for_gap(candidate, confirmed_spreads)
        if inside_pair is not None:
            protected.append(
                InsertReviewPoint(
                    "protected",
                    candidate.gap_id,
                    candidate.after_page,
                    candidate.before_page,
                    insertion_index,
                    marker_entry_index,
                    candidate.safe_insert_score,
                    candidate.label,
                    f"Gap is inside confirmed spread {inside_pair.pair_id}",
                )
            )
            continue

        simulated = list(entries)
        simulated.insert(insertion_index, _DiagnosticBlank())
        after_damage = diagnose_spread_damage(simulated, confirmed_spreads, uses_apple_cover_gap)
        after_by_id = {item.pair_id: item for item in after_damage}
        breaks = sorted(pair_id for pair_id in intact_before if after_by_id[pair_id].status != "intact")
        if breaks:
            protected.append(
                InsertReviewPoint(
                    "protected",
                    candidate.gap_id,
                    candidate.after_page,
                    candidate.before_page,
                    insertion_index,
                    marker_entry_index,
                    candidate.safe_insert_score,
                    candidate.label,
                    f"Insertion would damage confirmed spread {breaks[0]}",
                )
            )
            continue
        fixes = tuple(
            pair_id
            for pair_id in sorted(damaged_before)
            if current_by_id[pair_id].status != "intact" and after_by_id[pair_id].status == "intact"
        )
        if fixes:
            suggestions.append(
                InsertReviewPoint(
                    "suggested",
                    candidate.gap_id,
                    candidate.after_page,
                    candidate.before_page,
                    insertion_index,
                    marker_entry_index,
                    candidate.safe_insert_score,
                    candidate.label,
                    f"Repairs confirmed spread {fixes[0]}",
                    fixes,
                )
            )

    suggestions.sort(key=lambda item: (-item.score, item.insertion_index))
    protected.sort(key=lambda item: (item.insertion_index, -item.score))
    return InsertClassification(suggestions, protected, stale)


def _source_to_entry_index(entries: list) -> dict[int, int]:
    result: dict[int, int] = {}
    for index, entry in enumerate(entries):
        source_index = getattr(entry, "source_index", None)
        if source_index is not None and not getattr(entry, "is_blank", False):
            result[source_index] = index
    return result


def _insertion_index_for_candidate(candidate: InsertCandidate, source_to_entry: dict[int, int]) -> int | None:
    after_index = source_to_entry.get(candidate.after_page)
    before_index = source_to_entry.get(candidate.before_page)
    if after_index is None or before_index is None:
        return None
    if before_index != after_index + 1:
        return None
    return after_index + 1


def _confirmed_pair_for_gap(
    candidate: InsertCandidate, confirmed_spreads: list[SpreadCandidate]
) -> SpreadCandidate | None:
    for spread in confirmed_spreads:
        if spread.start_page == candidate.after_page and spread.end_page == candidate.before_page:
            return spread
    return None


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
