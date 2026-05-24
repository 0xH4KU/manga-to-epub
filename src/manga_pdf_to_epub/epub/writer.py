from __future__ import annotations

import html
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from .validation import validate_epub_structure
from ..pdf.image_types import PdfImageError


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
    image_data_loader: Callable[[], bytes] | None = None
    is_blank: bool = False

    def load_image_data(self) -> bytes:
        if self.image_data is not None:
            return self.image_data
        if self.image_data_loader is not None:
            return self.image_data_loader()
        raise PdfImageError(f"Page {self.label} has no image payload")


def media_type_for_ext(ext: str) -> str:
    ext = ext.lower()
    if ext in {"jpg", "jpeg"}:
        return "image/jpeg"
    if ext == "png":
        return "image/png"
    raise PdfImageError(f"Unsupported image extension for EPUB: {ext}")


def write_epub_from_pages(
    pages: list[EpubPage],
    epub_path: Path,
    source_path: Path,
    title: str,
    author: str | None = None,
    language: str = "zh-Hant",
    overwrite: bool = False,
    apple_books: bool = False,
    pair_first_two_pages: bool = False,
    cover_item_id: str | None = None,
    exclude_cover_from_reading: bool = False,
    counts: dict[str, int] | None = None,
) -> dict[str, int]:
    if epub_path.exists() and not overwrite:
        raise PdfImageError(f"Refusing to overwrite existing file: {epub_path}")
    identifier = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, source_path.resolve().as_uri())}"

    cover_id = cover_item_id or _first_image_item_id(pages)
    _validate_cover_item_id(pages, cover_id)
    reading_pages = _reading_pages(pages, cover_id, exclude_cover_from_reading)
    if not reading_pages:
        raise PdfImageError("Cover-only export would leave no reading pages")

    with ZipFile(epub_path, "w") as archive:
        _write_stored(archive, "mimetype", b"application/epub+zip")
        _write_deflated(archive, "META-INF/container.xml", _container_xml())
        _write_deflated(
            archive,
            "EPUB/content.opf",
            _content_opf(
                title,
                identifier,
                pages,
                reading_pages,
                apple_books,
                pair_first_two_pages,
                author,
                language,
                cover_id,
            ),
        )
        _write_deflated(archive, "EPUB/nav.xhtml", _nav_xhtml(title, reading_pages, language))
        _write_deflated(archive, "EPUB/styles/page.css", _page_css())
        for page in reading_pages:
            if page.is_blank:
                _write_deflated(archive, f"EPUB/{page.xhtml_href}", _blank_page_xhtml(title, page, language))
            else:
                _write_deflated(archive, f"EPUB/{page.xhtml_href}", _page_xhtml(title, page, language))
        for page in pages:
            if not page.is_blank:
                _write_stored(archive, f"EPUB/{page.image_href}", page.load_image_data())

    validate_epub_structure(epub_path)
    result = dict(counts or {})
    result["total"] = len(reading_pages)
    return result


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
    reading_pages: list[EpubPage],
    apple_books: bool = False,
    pair_first_two_pages: bool = False,
    author: str | None = None,
    language: str = "zh-Hant",
    cover_item_id: str | None = None,
) -> str:
    title_xml = html.escape(title, quote=True)
    language_xml = html.escape(language or "zh-Hant", quote=True)
    creator_xml = html.escape(author, quote=True) if author else None
    cover_id = cover_item_id or _first_image_item_id(pages)
    image_items = "\n".join(
        _image_manifest_item(page, cover_id)
        for page in pages
        if not page.is_blank
    )
    xhtml_items = "\n".join(
        _xhtml_manifest_item(page)
        for page in reading_pages
    )
    spread = "none" if apple_books else "auto"
    if apple_books:
        spine_items = "\n".join(
            f'    <itemref idref="{page.item_id}" properties="rendition:page-spread-center"/>'
            for page in reading_pages
        )
    else:
        spine_items = "\n".join(_spine_itemref(page, pair_first_two_pages) for page in reading_pages)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package version="3.0" unique-identifier="bookid" prefix="rendition: http://www.idpf.org/vocab/rendition/#" xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{html.escape(identifier, quote=True)}</dc:identifier>
    <dc:title>{title_xml}</dc:title>
{f"    <dc:creator>{creator_xml}</dc:creator>" if creator_xml else ""}
    <dc:language>{language_xml}</dc:language>
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


def _image_manifest_item(page: EpubPage, cover_id: str | None) -> str:
    properties = ' properties="cover-image"' if page.item_id == cover_id else ""
    return f'    <item id="img-{page.index:04d}" href="{page.image_href}" media-type="{page.image_media_type}"{properties}/>'


def _xhtml_manifest_item(page: EpubPage) -> str:
    properties = ' properties="svg"' if not page.is_blank else ""
    return f'    <item id="{page.item_id}" href="{page.xhtml_href}" media-type="application/xhtml+xml"{properties}/>'


def _first_image_item_id(pages: list[EpubPage]) -> str | None:
    for page in pages:
        if not page.is_blank:
            return page.item_id
    return None


def _validate_cover_item_id(pages: list[EpubPage], cover_item_id: str | None) -> None:
    if cover_item_id is None:
        return
    if any(not page.is_blank and page.item_id == cover_item_id for page in pages):
        return
    raise PdfImageError(f"Invalid cover item ID: {cover_item_id}")


def _reading_pages(pages: list[EpubPage], cover_item_id: str | None, exclude_cover_from_reading: bool) -> list[EpubPage]:
    if not exclude_cover_from_reading or cover_item_id is None:
        return pages
    return [page for page in pages if page.item_id != cover_item_id]


def _spine_itemref(page: EpubPage, pair_first_two_pages: bool) -> str:
    if pair_first_two_pages and not page.is_blank and page.index in {1, 2}:
        side = "right" if page.index == 1 else "left"
        return f'    <itemref idref="{page.item_id}" properties="rendition:page-spread-{side}"/>'
    return f'    <itemref idref="{page.item_id}"/>'


def _nav_xhtml(title: str, pages: list[EpubPage], language: str = "zh-Hant") -> str:
    title_xml = html.escape(title, quote=True)
    language_xml = html.escape(language or "zh-Hant", quote=True)
    links = "\n".join(
        f'        <li><a href="{page.xhtml_href}">{html.escape(page.label, quote=True)}</a></li>'
        for page in pages
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{language_xml}" xml:lang="{language_xml}">
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


def _page_xhtml(title: str, page: EpubPage, language: str = "zh-Hant") -> str:
    page_title = html.escape(f"{title} - Page {page.index}", quote=True)
    language_xml = html.escape(language or "zh-Hant", quote=True)
    href = html.escape(f"../{page.image_href}", quote=True)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{language_xml}" xml:lang="{language_xml}">
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


def _blank_page_xhtml(title: str, page: EpubPage, language: str = "zh-Hant") -> str:
    page_title = html.escape(f"{title} - {page.label}", quote=True)
    language_xml = html.escape(language or "zh-Hant", quote=True)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{language_xml}" xml:lang="{language_xml}">
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
