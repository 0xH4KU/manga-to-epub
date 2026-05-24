#!/usr/bin/env python3
"""Package manga source images into fixed-layout EPUB files."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..models.layout import LayoutModel
from ..epub.naming import generated_volume_title, infer_volume_number
from ..pdf.image_extraction import images_in_pdf_page_order
from ..pdf.image_types import ImageStream, PdfImageError
from ..epub.page_factory import page_from_image
from ..epub.validation import validate_epub_structure
from ..epub.writer import EpubPage, media_type_for_ext, write_epub_from_pages


_validate_epub_structure = validate_epub_structure
_media_type_for_ext = media_type_for_ext


def convert_pdf_to_epub(
    pdf_path: Path,
    epub_path: Path,
    overwrite: bool = False,
    title: str | None = None,
    author: str | None = None,
    language: str = "zh-Hant",
    apple_books: bool = False,
    blank_pages_before_cover: int = 0,
    blank_pages_after_cover: int = 0,
    pair_first_two_pages: bool = False,
    cover_item_id: str | None = None,
    exclude_cover_from_reading: bool = False,
) -> dict[str, int]:
    return convert_source_to_epub(
        pdf_path,
        epub_path,
        overwrite=overwrite,
        title=title,
        author=author,
        language=language,
        apple_books=apple_books,
        blank_pages_before_cover=blank_pages_before_cover,
        blank_pages_after_cover=blank_pages_after_cover,
        pair_first_two_pages=pair_first_two_pages,
        cover_item_id=cover_item_id,
        exclude_cover_from_reading=exclude_cover_from_reading,
    )


def convert_source_to_epub(
    source_path: Path,
    epub_path: Path,
    overwrite: bool = False,
    title: str | None = None,
    author: str | None = None,
    language: str = "zh-Hant",
    apple_books: bool = False,
    blank_pages_before_cover: int = 0,
    blank_pages_after_cover: int = 0,
    pair_first_two_pages: bool = False,
    cover_item_id: str | None = None,
    exclude_cover_from_reading: bool = False,
) -> dict[str, int]:
    if epub_path.exists() and not overwrite:
        raise PdfImageError(f"Refusing to overwrite existing file: {epub_path}")

    if source_path.suffix.lower() == ".pdf":
        images = images_in_pdf_page_order(source_path, load_payloads=False)
        if not images:
            raise PdfImageError(f"No image streams found in {source_path}")
        pages, counts = _build_pages(
            images,
            blank_pages_before_cover=blank_pages_before_cover,
            blank_pages_after_cover=blank_pages_after_cover,
        )
    else:
        if blank_pages_before_cover or blank_pages_after_cover:
            model = LayoutModel.from_source(source_path)
            for _ in range(blank_pages_before_cover):
                model.insert_blank(0)
            for _ in range(blank_pages_after_cover):
                model.insert_blank(min(1, len(model.entries)))
            pages = model.normalized_pages()
            counts = model.page_counts()
        else:
            model = LayoutModel.from_source(source_path)
            pages = model.normalized_pages()
            counts = model.page_counts()

    book_title = title or source_path.stem
    return write_epub_from_pages(
        pages,
        epub_path,
        source_path=source_path,
        title=book_title,
        author=author,
        language=language,
        overwrite=True,
        apple_books=apple_books,
        pair_first_two_pages=pair_first_two_pages,
        cover_item_id=cover_item_id,
        exclude_cover_from_reading=exclude_cover_from_reading,
        counts=counts,
    )


def _build_pages(
    images: list[ImageStream],
    blank_pages_before_cover: int = 0,
    blank_pages_after_cover: int = 0,
) -> tuple[list[EpubPage], dict[str, int]]:
    pages: list[EpubPage] = []
    counts = {"jpg": 0, "png": 0}
    padding = max(4, len(str(len(images))))
    for image in images:
        if image.index == 1:
            for blank_index in range(1, blank_pages_before_cover + 1):
                counts["blank"] = counts.get("blank", 0) + 1
                pages.append(_blank_page(image, blank_index, "before"))
        page, ext = page_from_image(image, padding, load_payload=False)
        counts[ext] = counts.get(ext, 0) + 1
        pages.append(page)
        if image.index == 1:
            for blank_index in range(1, blank_pages_after_cover + 1):
                counts["blank"] = counts.get("blank", 0) + 1
                pages.append(_blank_page(image, blank_index, "after"))
    return pages, counts


def _blank_page(reference: ImageStream, blank_index: int, position: str) -> EpubPage:
    if position not in {"before", "after"}:
        raise PdfImageError(f"Unsupported blank page position: {position}")
    item_id = f"blank-{position}-cover-{blank_index:04d}"
    return EpubPage(
        index=blank_index,
        width=reference.width,
        height=reference.height,
        image_href=None,
        image_media_type=None,
        image_data=None,
        xhtml_href=f"xhtml/{item_id}.xhtml",
        item_id=item_id,
        label=f"Blank {position} cover {blank_index}",
        is_blank=True,
    )


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    for source_path in args.sources:
        if source_path.suffix.lower() not in {".pdf", ".cbz", ".zip"}:
            raise PdfImageError(f"Unsupported source file: {source_path}")
        output_dir = args.output_dir or source_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        epub_path = output_dir / source_path.with_suffix(".epub").name
        counts = _convert_from_cli_args(source_path, epub_path, args)
        print(
            f"{source_path.name} -> {epub_path}: "
            f"{counts['total']} pages ({counts.get('jpg', 0)} jpg, {counts.get('png', 0)} png)"
        )
    return 0


def _convert_from_cli_args(source_path: Path, epub_path: Path, args: argparse.Namespace) -> dict[str, int]:
    title = _cli_title(source_path, args)
    if _uses_layout_model(args):
        return _convert_with_layout_model(source_path, epub_path, args, title)
    cover_item_id = f"page-{args.cover_page:04d}" if args.cover_page is not None else None
    try:
        return convert_source_to_epub(
            source_path,
            epub_path,
            overwrite=args.overwrite,
            title=title,
            author=args.author,
            language=args.language,
            apple_books=args.apple_books,
            blank_pages_before_cover=args.blank_pages_before_cover,
            blank_pages_after_cover=args.blank_pages_after_cover,
            pair_first_two_pages=args.pair_first_two_pages,
            cover_item_id=cover_item_id,
            exclude_cover_from_reading=args.cover_only,
        )
    except PdfImageError as exc:
        if args.cover_page is not None and str(exc).startswith("Invalid cover item ID:"):
            raise PdfImageError(f"Invalid cover page: {args.cover_page}") from exc
        raise


def _convert_with_layout_model(
    source_path: Path,
    epub_path: Path,
    args: argparse.Namespace,
    title: str,
) -> dict[str, int]:
    if epub_path.exists() and not args.overwrite:
        raise PdfImageError(f"Refusing to overwrite existing file: {epub_path}")
    model = LayoutModel.from_source(source_path)
    if args.preset is not None:
        model.apply_preset(args.preset)
    _apply_cli_layout_operations(model, args)
    model.title = title
    model.author = args.author or ""
    model.language = args.language
    if args.cover_page is not None:
        try:
            model.set_cover(args.cover_page)
        except ValueError as exc:
            raise PdfImageError(f"Invalid cover page: {args.cover_page}") from exc
    model.exclude_cover_from_reading = args.cover_only
    return model.export_epub(epub_path, overwrite=True)


def _uses_layout_model(args: argparse.Namespace) -> bool:
    return any(
        (
            args.preset is not None,
            bool(args.insert_image_before),
            bool(args.insert_image_after),
            args.delete_first is not None,
            args.delete_last is not None,
            bool(args.delete_range),
        )
    )


def _apply_cli_layout_operations(model: LayoutModel, args: argparse.Namespace) -> None:
    if args.delete_first is not None:
        model.delete_first(args.delete_first)
    if args.delete_last is not None:
        model.delete_last(args.delete_last)
    for start, end in args.delete_range:
        model.delete_range(start - 1, end - 1)
    for position, image_path in args.insert_image_before:
        model.insert_image(position - 1, image_path)
    for position, image_path in args.insert_image_after:
        model.insert_image(position, image_path)


def _cli_title(source_path: Path, args: argparse.Namespace) -> str:
    if args.title:
        return args.title
    if args.series_title:
        volume_number = args.volume_number if args.volume_number is not None else infer_volume_number(source_path)
        return generated_volume_title(args.series_title, volume_number)
    return source_path.stem


def _parse_position_path(value: str) -> tuple[int, Path]:
    position_text, separator, path_text = value.partition("=")
    if not separator or not position_text.isdigit() or int(position_text) < 1 or not path_text:
        raise argparse.ArgumentTypeError("expected POSITION=PATH with a 1-based position")
    return int(position_text), Path(path_text)


def _parse_range(value: str) -> tuple[int, int]:
    start_text, separator, end_text = value.partition("-")
    if not separator or not start_text.isdigit() or not end_text.isdigit():
        raise argparse.ArgumentTypeError("expected START-END with 1-based positions")
    start = int(start_text)
    end = int(end_text)
    if start < 1 or end < start:
        raise argparse.ArgumentTypeError("expected START-END with start >= 1 and end >= start")
    return start, end


class _EpubArgumentParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        parsed = super().parse_args(args, namespace)
        if parsed.apple_books and parsed.pair_first_two_pages:
            self.error("--apple-books cannot be used with --pair-first-two-pages")
        if parsed.title and parsed.series_title:
            self.error("--title cannot be used with --series-title")
        if parsed.volume_number is not None and not parsed.series_title:
            self.error("--volume-number requires --series-title")
        if parsed.cover_page is not None and parsed.cover_page < 1:
            self.error("--cover-page must be 1 or greater")
        for name in ("delete_first", "delete_last"):
            value = getattr(parsed, name)
            if value is not None and value < 1:
                self.error(f"--{name.replace('_', '-')} must be 1 or greater")
        return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = _EpubArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+", type=Path, help="PDF, CBZ, or ZIP files to convert")
    parser.add_argument("--output-dir", type=Path, default=None, help="directory for EPUB output")
    parser.add_argument("--overwrite", action="store_true", help="replace existing EPUB files")
    parser.add_argument("--title", default=None, help="EPUB title")
    parser.add_argument("--author", default=None, help="EPUB creator/author")
    parser.add_argument("--language", default="zh-Hant", help="EPUB language code")
    parser.add_argument("--cover-page", type=int, default=None, help="1-based source page to mark as cover image")
    parser.add_argument("--cover-only", action="store_true", help="use the selected cover only as cover art")
    parser.add_argument("--preset", type=Path, default=None, help="apply a GUI v2 layout preset")
    parser.add_argument(
        "--insert-image-before",
        action="append",
        type=_parse_position_path,
        default=[],
        metavar="POSITION=PATH",
        help="insert a JPEG/PNG before a 1-based spine position",
    )
    parser.add_argument(
        "--insert-image-after",
        action="append",
        type=_parse_position_path,
        default=[],
        metavar="POSITION=PATH",
        help="insert a JPEG/PNG after a 1-based spine position",
    )
    parser.add_argument("--delete-first", type=int, default=None, help="delete the first N spine entries")
    parser.add_argument("--delete-last", type=int, default=None, help="delete the last N spine entries")
    parser.add_argument(
        "--delete-range",
        action="append",
        type=_parse_range,
        default=[],
        metavar="START-END",
        help="delete a 1-based inclusive spine range",
    )
    parser.add_argument("--series-title", default=None, help="generate title as SERIES Vol.NN")
    parser.add_argument("--volume-number", type=int, default=None, help="volume number for --series-title")
    parser.add_argument(
        "--blank-pages-after-cover",
        type=int,
        default=0,
        help="insert this many white XHTML pages immediately after the cover",
    )
    parser.add_argument(
        "--blank-pages-before-cover",
        type=int,
        default=0,
        help="insert this many white XHTML pages immediately before the cover",
    )
    parser.add_argument(
        "--pair-first-two-pages",
        action="store_true",
        help="mark source pages 1 and 2 as an explicit RTL spread pair",
    )
    parser.add_argument(
        "--apple-books",
        action="store_true",
        help="write OPF metadata that forces centered single-page spreads",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
