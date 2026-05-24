from __future__ import annotations

from collections import Counter
import mimetypes
import posixpath
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile
from xml.etree import ElementTree

from ..pdf.image_types import PdfImageError


def validate_epub_structure(epub_path: Path) -> None:
    with ZipFile(epub_path) as archive:
        names = archive.namelist()
        duplicate_names = [name for name, count in Counter(names).items() if count > 1]
        if duplicate_names:
            raise PdfImageError(f"Duplicate EPUB zip entry: {duplicate_names[0]}")
        name_set = set(names)
        if not names or names[0] != "mimetype":
            raise PdfImageError("EPUB mimetype must be the first zip entry")
        if archive.getinfo("mimetype").compress_type != ZIP_STORED:
            raise PdfImageError("EPUB mimetype must be stored without compression")
        if archive.read("mimetype") != b"application/epub+zip":
            raise PdfImageError("EPUB mimetype has invalid content")
        for required in ("META-INF/container.xml", "EPUB/content.opf"):
            if required not in name_set:
                raise PdfImageError(f"Required EPUB file missing: {required}")

        opf = ElementTree.fromstring(archive.read("EPUB/content.opf"))
        ns = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
        manifest: dict[str, tuple[str, str, str]] = {}
        manifest_paths: set[str] = set()
        xhtml_paths: dict[str, str] = {}
        xhtml_images: dict[str, set[str]] = {}
        image_paths: set[str] = set()
        nav_items = 0
        language = _opf_language(opf, ns)
        for item in opf.findall(".//opf:manifest/opf:item", ns):
            item_id = item.attrib.get("id")
            href = item.attrib.get("href")
            media_type = item.attrib.get("media-type", "")
            properties = item.attrib.get("properties", "")
            if not item_id or not href:
                continue
            manifest[item_id] = (href, media_type, properties)
            archive_path = posixpath.normpath(posixpath.join("EPUB", href))
            manifest_paths.add(archive_path)
            if archive_path not in name_set:
                raise PdfImageError(f"Manifest href missing from EPUB: {archive_path}")
            if "nav" in properties.split():
                if archive_path != "EPUB/nav.xhtml" or media_type != "application/xhtml+xml":
                    raise PdfImageError("EPUB nav item must reference EPUB/nav.xhtml")
                nav_items += 1
            if media_type == "application/xhtml+xml":
                xhtml_paths[item_id] = archive_path
                xhtml_images[item_id] = _validate_xhtml(archive, archive_path, language)
            if media_type.startswith("image/"):
                _validate_image_media_type(archive_path, media_type)
                image_paths.add(archive_path)

        if nav_items != 1:
            raise PdfImageError("EPUB nav item missing")

        for itemref in opf.findall(".//opf:spine/opf:itemref", ns):
            idref = itemref.attrib.get("idref")
            if idref and idref not in manifest:
                raise PdfImageError(f"Spine itemref {idref} has no manifest item")
            if idref and idref in xhtml_paths:
                referenced_images = xhtml_images[idref]
                for image_path in referenced_images:
                    if image_path not in manifest_paths:
                        raise PdfImageError(f"Reading page image missing from manifest: {image_path}")
                    if image_path not in image_paths:
                        raise PdfImageError(f"Reading page image is not an image manifest item: {image_path}")

        cover_items = [
            (item_id, media_type)
            for item_id, (_href, media_type, properties) in manifest.items()
            if "cover-image" in properties.split()
        ]
        if len(cover_items) != 1:
            raise PdfImageError("EPUB must have exactly one cover image")
        for item_id, media_type in cover_items:
            if not media_type.startswith("image/"):
                raise PdfImageError(f"Cover item {item_id} is not an image")


def _validate_xhtml(archive: ZipFile, archive_path: str, expected_language: str | None = None) -> set[str]:
    try:
        root = ElementTree.fromstring(archive.read(archive_path))
    except ElementTree.ParseError as exc:
        raise PdfImageError(f"Malformed XHTML file: {archive_path}") from exc
    if expected_language:
        lang = root.attrib.get("lang")
        xml_lang = root.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")
        if lang != expected_language or xml_lang != expected_language:
            raise PdfImageError(f"XHTML language mismatch for {archive_path}")
    return _xhtml_image_paths(root, archive_path)


def _opf_language(opf: ElementTree.Element, ns: dict[str, str]) -> str | None:
    language = opf.find(".//dc:language", ns)
    if language is None or language.text is None:
        return None
    value = language.text.strip()
    return value or None


def _xhtml_image_paths(root: ElementTree.Element, archive_path: str) -> set[str]:
    paths: set[str] = set()
    for image in root.findall(".//{http://www.w3.org/2000/svg}image"):
        href = image.attrib.get("href") or image.attrib.get("{http://www.w3.org/1999/xlink}href")
        if not href:
            continue
        if ":" in href.partition("/")[0]:
            continue
        paths.add(posixpath.normpath(posixpath.join(posixpath.dirname(archive_path), href)))
    return paths


def _validate_image_media_type(archive_path: str, media_type: str) -> None:
    ext = Path(archive_path).suffix.lower()
    expected = "image/jpeg" if ext in {".jpg", ".jpeg"} else mimetypes.types_map.get(ext)
    if expected and expected != media_type:
        raise PdfImageError(f"Image media type mismatch for {archive_path}: {media_type} != {expected}")
