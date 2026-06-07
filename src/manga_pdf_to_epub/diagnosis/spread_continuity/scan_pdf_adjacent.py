#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Callable

import cv2
import fitz
import numpy as np

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.context import apply_contextual_adjustment, attach_raw_scores
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.reliability import apply_reliability_adjustment
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.types import Page
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.outputs import (
    write_adjacent_clusters,
    write_debug,
    write_review,
    write_scores,
    write_selected,
)
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.scoring import (
    reliability_signals_for_candidates,
    score_candidate_pairs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reading", choices=["rtl", "ltr"], default="rtl")
    parser.add_argument("--band-ratio", type=float, default=0.08)
    parser.add_argument("--wide-ratio", type=float, default=0.20)
    parser.add_argument("--max-offset", type=int, default=18)
    parser.add_argument("--max-height", type=int, default=1000)
    parser.add_argument("--spread-threshold", type=float, default=0.53)
    parser.add_argument("--debug-limit", type=int, default=40)
    parser.add_argument("--workers", type=int, default=1, help="Parallel scoring workers; 1 disables multiprocessing.")
    parser.add_argument(
        "--stability-threshold",
        type=float,
        default=0.47,
        help="Only adjacent candidates at or above this score get multi-scale stability probes.",
    )
    parser.add_argument(
        "--no-context-adjustment",
        action="store_true",
        help="Disable adjacent-page contextual score adjustment and write raw scores only.",
    )
    parser.add_argument(
        "--no-reliability-adjustment",
        action="store_true",
        help="Disable multi-scale stability and per-volume reliability adjustment.",
    )
    parser.add_argument("--page-from", type=int, default=1)
    parser.add_argument("--page-to", type=int, default=0, help="Inclusive page number; 0 means end of PDF.")
    parser.add_argument("--progress", action="store_true", help="Emit machine-readable progress events on stderr.")
    return parser.parse_args()


def render_page(doc: fitz.Document, page_no: int, max_height: int) -> Page:
    page = doc.load_page(page_no - 1)
    scale = max_height / float(page.rect.height)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 1:
        bgr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    else:
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return Page(f"page-{page_no:03d}", Path(f"page-{page_no:03d}.png"), bgr, gray)


def progress_reporter(enabled: bool) -> Callable[[int, int, str], None]:
    def report(completed: int, total: int, message: str) -> None:
        if not enabled:
            return
        payload = {"completed": completed, "total": max(1, total), "message": message}
        print(f"MTE_PROGRESS {json.dumps(payload, separators=(',', ':'))}", file=sys.stderr, flush=True)

    return report


def main() -> int:
    args = parse_args()
    if not args.pdf.exists():
        print(f"missing PDF: {args.pdf}", file=sys.stderr)
        return 1

    started = time.perf_counter()
    args.output.mkdir(parents=True, exist_ok=True)
    debug_dir = args.output / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    progress = progress_reporter(args.progress)

    doc = fitz.open(args.pdf)
    page_to = args.page_to if args.page_to > 0 else doc.page_count
    if args.page_from < 1 or page_to > doc.page_count or args.page_from >= page_to:
        print(f"invalid page range {args.page_from}-{page_to}; PDF has {doc.page_count} pages", file=sys.stderr)
        return 1

    render_started = time.perf_counter()
    page_numbers = list(range(args.page_from, page_to + 1))
    total_pages = len(page_numbers)
    total_pairs = max(0, total_pages - 1)
    reliability_budget = 0 if args.no_reliability_adjustment else total_pairs
    score_base = total_pages
    total_units = total_pages + total_pairs + reliability_budget + 1
    completed_units = 0
    progress(completed_units, total_units, "Preparing cross-page scan.")
    pages = []
    for page_no in page_numbers:
        pages.append(render_page(doc, page_no, args.max_height))
        completed_units += 1
        progress(completed_units, total_units, f"Rendering page {len(pages)}/{total_pages}.")
    render_elapsed = time.perf_counter() - render_started
    pages_by_name = {page.name: page for page in pages}

    score_started = time.perf_counter()
    candidate_pairs = []
    for first, second in zip(pages, pages[1:]):
        if args.reading == "rtl":
            right, left = first, second
        else:
            right, left = second, first
        candidate_pairs.append((right, left))
    scored_pairs = 0

    def score_progress(_score) -> None:
        nonlocal scored_pairs
        scored_pairs += 1
        progress(score_base + scored_pairs, total_units, f"Scoring adjacent pair {scored_pairs}/{total_pairs}.")

    scores = score_candidate_pairs(
        candidate_pairs,
        args.band_ratio,
        args.wide_ratio,
        args.max_offset,
        None,
        args.workers,
        score_progress,
    )
    completed_units = score_base + total_pairs
    score_elapsed = time.perf_counter() - score_started

    scores = attach_raw_scores(scores) if args.no_context_adjustment else apply_contextual_adjustment(scores)
    if not args.no_reliability_adjustment:
        reliability_started = time.perf_counter()
        reliability_candidates = [
            score for score in scores if max(score.spread, score.review_score) >= args.stability_threshold
        ]
        reliability_total = len(reliability_candidates)
        reliability_done = 0

        def reliability_progress(_signals) -> None:
            nonlocal reliability_done
            reliability_done += 1
            progress(
                completed_units + reliability_done,
                total_units,
                f"Checking stability {reliability_done}/{reliability_total}.",
            )

        signals = reliability_signals_for_candidates(
            candidate_pairs,
            scores,
            args.band_ratio,
            args.wide_ratio,
            args.max_offset,
            None,
            args.workers,
            args.stability_threshold,
            reliability_progress,
        )
        completed_units += reliability_budget
        scores = apply_reliability_adjustment(scores, signals)
        score_elapsed += time.perf_counter() - reliability_started
    progress(total_units - 1, total_units, "Writing scan results.")
    scores.sort(key=lambda s: (-s.spread, -s.review_score, s.right_name, s.left_name))
    write_scores(scores, args.output / "scores.csv")
    write_review(scores, args.output / "review.csv", args.spread_threshold)
    write_adjacent_clusters(scores, args.output / "adjacent_clusters.csv", args.spread_threshold, doc.page_count)
    selected = write_selected(scores, args.output / "selected_adjacent.csv", args.spread_threshold)

    for idx, score in enumerate(scores[: args.debug_limit], 1):
        filename = (
            f"{idx:03d}_{score.right_name}_{score.left_name}_"
            f"spread-{score.spread:.3f}_review-{score.review_score:.3f}.png"
        )
        write_debug(score, pages_by_name, debug_dir / filename)

    elapsed = time.perf_counter() - started
    progress(total_units, total_units, "Cross-page scan complete.")
    print(
        f"Rendered {len(pages)} pages in {render_elapsed:.2f}s; "
        f"scored {len(scores)} adjacent pairs in {score_elapsed:.2f}s; total {elapsed:.2f}s"
    )
    print("Top candidates:")
    for idx, score in enumerate(scores[:15], 1):
        print(
            f"{idx:2d} {score.right_name}+{score.left_name} "
            f"spread={score.spread:.3f} review={score.review_score:.3f} "
            f"comp={score.composition:.3f} patch={score.patch:.3f}"
        )
    if selected:
        print("Selected clear-margin adjacent candidates:")
        for score in selected[:20]:
            print(f"  {score.right_name}+{score.left_name} spread={score.spread:.3f} review={score.review_score:.3f}")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
