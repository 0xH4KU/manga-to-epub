from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.types import Page, PairScore


def write_debug(score: PairScore, pages: dict[str, Page], output: Path) -> None:
    right = pages[score.right_name].gray
    left = pages[score.left_name].gray
    preview_h = min(720, left.shape[0], right.shape[0])
    left_w = round(left.shape[1] * preview_h / left.shape[0])
    right_w = round(right.shape[1] * preview_h / right.shape[0])
    left_img = cv2.resize(left, (left_w, preview_h), interpolation=cv2.INTER_AREA)
    right_img = cv2.resize(right, (right_w, preview_h), interpolation=cv2.INTER_AREA)
    seam = np.zeros((preview_h, 7), dtype=np.uint8)
    canvas = np.concatenate([left_img, seam, right_img], axis=1)
    rgb = cv2.cvtColor(canvas, cv2.COLOR_GRAY2RGB)
    rgb[:, left_w : left_w + 7] = (255, 0, 0)

    label_h = 112
    pil = Image.fromarray(rgb)
    out = Image.new("RGB", (pil.width, pil.height + label_h), "white")
    out.paste(pil, (0, label_h))
    draw = ImageDraw.Draw(out)
    font = ImageFont.load_default()
    text = (
        f"{score.left_name} | {score.right_name}\n"
        f"total={score.total:.3f} spread={score.spread:.3f} review={score.review_score:.3f} "
        f"raw={score.raw_spread:.3f}/{score.raw_review_score:.3f} expected={'yes' if score.expected else 'no'} dy={score.offset}\n"
        f"color={score.color:.3f} grad={score.gradient:.3f} profile={score.profile:.3f} "
        f"edge={score.edge:.3f} ink={score.ink:.3f} energy={score.energy:.3f}\n"
        f"orient={score.orientation:.3f} line={score.line:.3f} texture={score.texture:.3f} "
        f"corr={score.corr:.3f} color={score.color_style:.3f}\n"
        f"panel={score.panel:.3f} page_panel={score.page_panel:.3f} gutter={score.inner_gutter:.3f} "
        f"comp={score.composition:.3f}\n"
        f"activity={score.seam_activity:.3f} contact={score.seam_contact:.3f} "
        f"patch={score.patch:.3f} barrier={score.barrier:.3f} "
        f"local_margin={score.local_margin:.3f} ctx_penalty={score.context_penalty:.3f}\n"
        f"stability={score.stability_score:.3f} relative={score.relative_score:.3f} "
        f"rel_penalty={score.reliability_penalty:.3f} rel_boost={score.reliability_boost:.3f}"
    )
    draw.multiline_text((10, 8), text, fill=(0, 0, 0), font=font, spacing=4)
    out.save(output)
