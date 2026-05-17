#!/usr/bin/env python3
"""Package PDF page images into fixed-layout EPUB files without re-encoding."""

from __future__ import annotations

import argparse
import html
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from pdf_to_cbz_lossless import ImageStream, PdfImageError, image_to_archive_member, images_in_pdf_page_order


@dataclass(frozen=True)
class EpubPage:
    index: int
    width: int
    height: int
    image_href: str | None
    image_media_type: str | None
    image_data: bytes | None
    xhtml_href: str
    item_id: str
    label: str
    is_blank: bool = False


def convert_pdf_to_epub(
    pdf_path: Path,
    epub_path: Path,
    overwrite: bool = False,
    title: str | None = None,
    apple_books: bool = False,
    blank_pages_before_cover: int = 0,
    blank_pages_after_cover: int = 0,
    pair_first_two_pages: bool = False,
) -> dict[str, int]:
    if epub_path.exists() and not overwrite:
        raise PdfImageError(f"Refusing to overwrite existing file: {epub_path}")

    images = images_in_pdf_page_order(pdf_path)
    if not images:
        raise PdfImageError(f"No image streams found in {pdf_path}")

    book_title = title or pdf_path.stem
    pages, counts = _build_pages(
        images,
        blank_pages_before_cover=blank_pages_before_cover,
        blank_pages_after_cover=blank_pages_after_cover,
    )
    return write_epub_from_pages(
        pages,
        epub_path,
        source_path=pdf_path,
        title=book_title,
        overwrite=True,
        apple_books=apple_books,
        pair_first_two_pages=pair_first_two_pages,
        counts=counts,
    )


def write_epub_from_pages(
    pages: list[EpubPage],
    epub_path: Path,
    source_path: Path,
    title: str,
    overwrite: bool = False,
    apple_books: bool = False,
    pair_first_two_pages: bool = False,
    counts: dict[str, int] | None = None,
) -> dict[str, int]:
    if epub_path.exists() and not overwrite:
        raise PdfImageError(f"Refusing to overwrite existing file: {epub_path}")
    identifier = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, source_path.resolve().as_uri())}"

    with ZipFile(epub_path, "w") as archive:
        _write_stored(archive, "mimetype", b"application/epub+zip")
        _write_deflated(archive, "META-INF/container.xml", _container_xml())
        _write_deflated(
            archive,
            "EPUB/content.opf",
            _content_opf(title, identifier, pages, apple_books, pair_first_two_pages),
        )
        _write_deflated(archive, "EPUB/nav.xhtml", _nav_xhtml(title, pages))
        _write_deflated(archive, "EPUB/styles/page.css", _page_css())
        for page in pages:
            if page.is_blank:
                _write_deflated(archive, f"EPUB/{page.xhtml_href}", _blank_page_xhtml(title, page))
            else:
                _write_deflated(archive, f"EPUB/{page.xhtml_href}", _page_xhtml(title, page))
                _write_stored(archive, f"EPUB/{page.image_href}", page.image_data)

    result = dict(counts or {})
    result["total"] = len(pages)
    return result


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
        ext, payload = _image_payload(image)
        counts[ext] = counts.get(ext, 0) + 1
        page_number = f"{image.index:0{padding}d}"
        image_href = f"images/page-{page_number}.{ext}"
        pages.append(
            EpubPage(
                index=image.index,
                width=image.width,
                height=image.height,
                image_href=image_href,
                image_media_type=_media_type_for_ext(ext),
                image_data=payload,
                xhtml_href=f"xhtml/page-{page_number}.xhtml",
                item_id=f"page-{image.index:04d}",
                label=f"Page {image.index}",
            )
        )
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


def _image_payload(image: ImageStream) -> tuple[str, bytes]:
    if image.filter_name == "PNG":
        return "png", image.data
    return image_to_archive_member(image)


def _media_type_for_ext(ext: str) -> str:
    if ext == "jpg":
        return "image/jpeg"
    guessed = mimetypes.types_map.get(f".{ext}")
    if guessed:
        return guessed
    raise PdfImageError(f"Unsupported image extension for EPUB: {ext}")


def _write_stored(archive: ZipFile, filename: str, payload: bytes) -> None:
    info = ZipInfo(filename)
    info.compress_type = ZIP_STORED
    archive.writestr(info, payload)


def _write_deflated(archive: ZipFile, filename: str, payload: str | bytes) -> None:
    info = ZipInfo(filename)
    info.compress_type = ZIP_DEFLATED
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    archive.writestr(info, payload)


def _container_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def _content_opf(
    title: str,
    identifier: str,
    pages: list[EpubPage],
    apple_books: bool = False,
    pair_first_two_pages: bool = False,
) -> str:
    title_xml = html.escape(title, quote=True)
    image_items = "\n".join(
        f'    <item id="img-{page.index:04d}" href="{page.image_href}" media-type="{page.image_media_type}"'
        f'{" properties=\"cover-image\"" if page.index == 1 else ""}/>'
        for page in pages
        if not page.is_blank
    )
    xhtml_items = "\n".join(
        f'    <item id="{page.item_id}" href="{page.xhtml_href}" media-type="application/xhtml+xml"'
        f'{" properties=\"svg\"" if not page.is_blank else ""}/>'
        for page in pages
    )
    spread = "none" if apple_books else "auto"
    if apple_books:
        spine_items = "\n".join(
            f'    <itemref idref="{page.item_id}" properties="rendition:page-spread-center"/>'
            for page in pages
        )
    else:
        spine_items = "\n".join(_spine_itemref(page, pair_first_two_pages) for page in pages)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package version="3.0" unique-identifier="bookid" prefix="rendition: http://www.idpf.org/vocab/rendition/#" xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{html.escape(identifier, quote=True)}</dc:identifier>
    <dc:title>{title_xml}</dc:title>
    <dc:language>zh-Hant</dc:language>
    <meta property="dcterms:modified">2026-05-17T00:00:00Z</meta>
    <meta property="rendition:layout">pre-paginated</meta>
    <meta property="rendition:orientation">auto</meta>
    <meta property="rendition:spread">{spread}</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="css-page" href="styles/page.css" media-type="text/css"/>
{image_items}
{xhtml_items}
  </manifest>
  <spine page-progression-direction="rtl">
{spine_items}
  </spine>
</package>
"""


def _spine_itemref(page: EpubPage, pair_first_two_pages: bool) -> str:
    if pair_first_two_pages and not page.is_blank and page.index in {1, 2}:
        side = "right" if page.index == 1 else "left"
        return f'    <itemref idref="{page.item_id}" properties="rendition:page-spread-{side}"/>'
    return f'    <itemref idref="{page.item_id}"/>'


def _nav_xhtml(title: str, pages: list[EpubPage]) -> str:
    title_xml = html.escape(title, quote=True)
    links = "\n".join(
        f'        <li><a href="{page.xhtml_href}">{html.escape(page.label, quote=True)}</a></li>'
        for page in pages
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-Hant" xml:lang="zh-Hant">
  <head>
    <title>{title_xml}</title>
  </head>
  <body>
    <nav epub:type="toc" id="toc">
      <h1>{title_xml}</h1>
      <ol>
{links}
      </ol>
    </nav>
  </body>
</html>
"""


def _page_css() -> str:
    return """html, body {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  background: #000;
}

svg {
  display: block;
  width: 100vw;
  height: 100vh;
}
"""


def _page_xhtml(title: str, page: EpubPage) -> str:
    page_title = html.escape(f"{title} - Page {page.index}", quote=True)
    href = html.escape(f"../{page.image_href}", quote=True)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-Hant" xml:lang="zh-Hant">
  <head>
    <title>{page_title}</title>
    <meta name="viewport" content="width={page.width}, height={page.height}"/>
    <link rel="stylesheet" type="text/css" href="../styles/page.css"/>
  </head>
  <body>
    <svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{page.width}" height="{page.height}" viewBox="0 0 {page.width} {page.height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Page {page.index}">
      <image width="{page.width}" height="{page.height}" href="{href}"/>
    </svg>
  </body>
</html>
"""


def _blank_page_xhtml(title: str, page: EpubPage) -> str:
    page_title = html.escape(f"{title} - {page.label}", quote=True)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-Hant" xml:lang="zh-Hant">
  <head>
    <title>{page_title}</title>
    <meta name="viewport" content="width={page.width}, height={page.height}"/>
    <link rel="stylesheet" type="text/css" href="../styles/page.css"/>
  </head>
  <body>
    <svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{page.width}" height="{page.height}" viewBox="0 0 {page.width} {page.height}" preserveAspectRatio="xMidYMid meet" role="presentation" aria-label="{html.escape(page.label, quote=True)}">
      <rect width="{page.width}" height="{page.height}" fill="#ffffff"/>
    </svg>
  </body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdfs", nargs="+", type=Path, help="PDF files to convert")
    parser.add_argument("--output-dir", type=Path, default=None, help="directory for EPUB output")
    parser.add_argument("--overwrite", action="store_true", help="replace existing EPUB files")
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
        help="force centered single-page spreads for Apple Books",
    )
    args = parser.parse_args()

    for pdf_path in args.pdfs:
        if pdf_path.suffix.lower() != ".pdf":
            raise PdfImageError(f"Not a PDF file: {pdf_path}")
        output_dir = args.output_dir or pdf_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        epub_path = output_dir / pdf_path.with_suffix(".epub").name
        counts = convert_pdf_to_epub(
            pdf_path,
            epub_path,
            overwrite=args.overwrite,
            apple_books=args.apple_books,
            blank_pages_before_cover=args.blank_pages_before_cover,
            blank_pages_after_cover=args.blank_pages_after_cover,
            pair_first_two_pages=args.pair_first_two_pages,
        )
        print(
            f"{pdf_path.name} -> {epub_path}: "
            f"{counts['total']} pages ({counts.get('jpg', 0)} jpg, {counts.get('png', 0)} png)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
