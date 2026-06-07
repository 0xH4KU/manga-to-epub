from __future__ import annotations

import csv
import html
from pathlib import Path

from .features import PageFeatures
from .scoring import GapScore


FEATURE_FIELDS = [
    "page",
    "width",
    "height",
    "ink_ratio",
    "edge_density",
    "blank_ratio",
    "dark_ratio",
    "title_likeness",
    "content_density",
    "center_ink_ratio",
    "border_ink_ratio",
    "bottom_activity",
]

GAP_FIELDS = [
    "gap",
    "after_page",
    "before_page",
    "safe_insert_score",
    "label",
    "visual_difference",
    "continuity_risk",
    "reasons",
]


def write_features_csv(features: list[PageFeatures], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FEATURE_FIELDS)
        writer.writeheader()
        for item in features:
            writer.writerow(
                {
                    "page": item.page,
                    "width": item.width,
                    "height": item.height,
                    "ink_ratio": _fmt(item.ink_ratio),
                    "edge_density": _fmt(item.edge_density),
                    "blank_ratio": _fmt(item.blank_ratio),
                    "dark_ratio": _fmt(item.dark_ratio),
                    "title_likeness": _fmt(item.title_likeness),
                    "content_density": _fmt(item.content_density),
                    "center_ink_ratio": _fmt(item.center_ink_ratio),
                    "border_ink_ratio": _fmt(item.border_ink_ratio),
                    "bottom_activity": _fmt(item.bottom_activity),
                }
            )


def write_gaps_csv(gaps: list[GapScore], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=GAP_FIELDS)
        writer.writeheader()
        for gap in gaps:
            writer.writerow(_gap_row(gap))


def write_html_report(
    gaps: list[GapScore],
    path: Path,
    *,
    title: str,
    thumbs_dir_name: str,
    page_count: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    escaped_title = html.escape(title, quote=True)
    sorted_gaps = sorted(gaps, key=lambda item: item.safe_insert_score, reverse=True)
    rows = "\n".join(_gap_card(gap, thumbs_dir_name, page_count) for gap in sorted_gaps)
    path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escaped_title}</title>
  <style>
    body {{
      margin: 0;
      background: #f4f1ea;
      color: #171717;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 2;
      background: #fffdf7;
      border-bottom: 1px solid #d8d0c1;
      padding: 14px 18px;
    }}
    h1 {{
      margin: 0;
      font-size: 20px;
      font-weight: 700;
    }}
    .meta {{
      margin-top: 4px;
      color: #5b554d;
      font-size: 13px;
    }}
    main {{
      padding: 18px;
    }}
    .gap {{
      display: grid;
      grid-template-columns: 150px 1fr;
      gap: 14px;
      margin-bottom: 14px;
      padding: 12px;
      background: #fffdf9;
      border: 1px solid #d8d0c1;
      border-radius: 8px;
    }}
    .score {{
      font-size: 28px;
      font-weight: 750;
    }}
    .label {{
      margin-top: 4px;
      font-size: 14px;
      color: #3c3630;
    }}
    .thumbs {{
      display: grid;
      grid-template-columns: repeat(4, minmax(90px, 1fr));
      gap: 10px;
      align-items: end;
    }}
    figure {{
      margin: 0;
    }}
    img {{
      width: 100%;
      max-height: 220px;
      object-fit: contain;
      background: #222;
      border: 1px solid #c8c0b2;
    }}
    figcaption {{
      margin-top: 4px;
      font-size: 12px;
      color: #5b554d;
      text-align: center;
    }}
    .details {{
      margin-top: 10px;
      font-size: 13px;
      color: #3c3630;
    }}
  </style>
</head>
<body>
  <header>
    <h1>{escaped_title}</h1>
    <div class="meta">{len(gaps)} gaps scored across {page_count} pages. Sorted by safest insertion score.</div>
  </header>
  <main>
    {rows}
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )


def _gap_card(gap: GapScore, thumbs_dir_name: str, page_count: int) -> str:
    left_outer = gap.gap_after_page - 1
    right_outer = gap.gap_before_page + 1
    pages = [left_outer, gap.gap_after_page, gap.gap_before_page, right_outer]
    figures = "\n".join(_figure(page, thumbs_dir_name, page_count) for page in pages)
    return f"""<section class="gap">
  <div>
    <div class="score">{gap.safe_insert_score:.3f}</div>
    <div class="label">{html.escape(gap.label)}</div>
    <div class="details">Gap {gap.gap_after_page:03d}-{gap.gap_before_page:03d}</div>
    <div class="details">diff {gap.visual_difference:.3f} / risk {gap.continuity_risk:.3f}</div>
    <div class="details">{html.escape('; '.join(gap.reasons))}</div>
  </div>
  <div class="thumbs">{figures}</div>
</section>"""


def _figure(page: int, thumbs_dir_name: str, page_count: int) -> str:
    if page < 1 or page > page_count:
        return "<figure><div></div><figcaption>missing</figcaption></figure>"
    filename = f"{thumbs_dir_name}/page-{page:04d}.jpg"
    return (
        f'<figure><img src="{html.escape(filename)}" alt="Page {page}">'
        f"<figcaption>Page {page}</figcaption></figure>"
    )


def _gap_row(gap: GapScore) -> dict[str, str | int]:
    return {
        "gap": f"{gap.gap_after_page:03d}-{gap.gap_before_page:03d}",
        "after_page": gap.gap_after_page,
        "before_page": gap.gap_before_page,
        "safe_insert_score": _fmt(gap.safe_insert_score),
        "label": gap.label,
        "visual_difference": _fmt(gap.visual_difference),
        "continuity_risk": _fmt(gap.continuity_risk),
        "reasons": "; ".join(gap.reasons),
    }


def _fmt(value: float) -> str:
    return f"{value:.6f}"
