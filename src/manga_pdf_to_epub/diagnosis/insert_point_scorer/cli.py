from __future__ import annotations

import argparse
from pathlib import Path

from .features import extract_page_features
from .pdf_render import load_thumbnail, render_pdf_thumbnails
from .report import write_features_csv, write_gaps_csv, write_html_report
from .scoring import score_gaps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score safe blank-page insertion points in a manga PDF.")
    parser.add_argument("pdf", type=Path, help="Input manga PDF")
    parser.add_argument("--output", "-o", type=Path, default=Path("out/report"), help="Output directory")
    parser.add_argument("--thumb-height", type=int, default=900, help="Rendered thumbnail height in pixels")
    args = parser.parse_args(argv)

    analyze_pdf(args.pdf, args.output, thumb_height=args.thumb_height)
    return 0


def analyze_pdf(pdf_path: Path, output_dir: Path, *, thumb_height: int = 900) -> tuple[int, int]:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir = output_dir / "thumbs"
    thumb_paths = render_pdf_thumbnails(pdf_path, thumbs_dir, height=thumb_height)
    features = [extract_page_features(index, load_thumbnail(path)) for index, path in enumerate(thumb_paths, start=1)]
    gaps = score_gaps(features)

    write_features_csv(features, output_dir / "features.csv")
    write_gaps_csv(gaps, output_dir / "gaps.csv")
    write_html_report(
        gaps,
        output_dir / "report.html",
        title=pdf_path.name,
        thumbs_dir_name="thumbs",
        page_count=len(features),
    )
    return len(features), len(gaps)


if __name__ == "__main__":
    raise SystemExit(main())
