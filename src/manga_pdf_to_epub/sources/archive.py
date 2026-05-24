from __future__ import annotations

import re
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable
from zipfile import BadZipFile, ZipFile, ZipInfo

from ..pdf.image_types import PdfImageError


_JPEG_IMAGE_EXTS = {"jpg", "jpeg", "jpe", "jfif"}
_PNG_IMAGE_EXTS = {"png", "apng"}
_DIRECT_IMAGE_EXTS = _JPEG_IMAGE_EXTS | _PNG_IMAGE_EXTS
_CONVERTED_IMAGE_EXTS = {
    "webp",
    "bmp",
    "tif",
    "tiff",
    "gif",
    "avif",
    "avifs",
    "jp2",
    "j2k",
    "j2c",
    "jpc",
    "jpf",
    "jpx",
    "heic",
    "heif",
    "hif",
}
_SUPPORTED_IMAGE_EXTS = _DIRECT_IMAGE_EXTS | _CONVERTED_IMAGE_EXTS


@dataclass(frozen=True)
class ArchiveImage:
    index: int
    source_index: int
    label: str
    width: int
    height: int
    epub_ext: str
    data: bytes | None
    data_loader: Callable[[], bytes] | None = None

    def load_data(self) -> bytes:
        if self.data is not None:
            return self.data
        if self.data_loader is not None:
            return self.data_loader()
        raise PdfImageError(f"Archive image {self.label} has no payload data")


@dataclass(frozen=True)
class _ArchiveMember:
    info: ZipInfo
    path: PurePosixPath


def archive_images_in_page_order(archive_path: Path, load_payloads: bool = True) -> list[ArchiveImage]:
    archive_path = Path(archive_path)
    if archive_path.suffix.lower() not in {".cbz", ".zip"}:
        raise PdfImageError(f"Unsupported archive source: {archive_path}")

    try:
        with ZipFile(archive_path) as archive:
            members = sorted(_image_members(archive), key=lambda member: _natural_archive_key(member.path.as_posix()))
    except BadZipFile as exc:
        raise PdfImageError(f"Cannot read archive source: {archive_path}") from exc

    if not members:
        raise PdfImageError(f"No supported image files found in {archive_path}")

    images: list[ArchiveImage] = []
    for index, member_name in enumerate(members, start=1):
        images.append(_archive_image(archive_path, member_name, index, load_payloads=load_payloads))
    return images


def _image_members(archive: ZipFile) -> list[_ArchiveMember]:
    members: list[_ArchiveMember] = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        path = _archive_member_path(info.filename)
        if _is_junk_path(path):
            continue
        if _source_ext(path.name) in _SUPPORTED_IMAGE_EXTS:
            members.append(_ArchiveMember(info=info, path=path))
    return members


def _archive_member_path(member_name: str) -> PurePosixPath:
    return PurePosixPath(member_name.replace("\\", "/"))


def _is_junk_path(path: PurePosixPath) -> bool:
    parts = path.parts
    if any(part == "__MACOSX" for part in parts):
        return True
    return path.name.startswith(".") or path.name.startswith("._")


def _archive_image(archive_path: Path, member: _ArchiveMember, index: int, load_payloads: bool) -> ArchiveImage:
    ext = _source_ext(member.path.name)
    label = member.path.stem
    raw = _read_member(archive_path, member.info)
    if ext in _DIRECT_IMAGE_EXTS:
        payload = _payload_or_loader(load_payloads, lambda: _read_member(archive_path, member.info))
        width, height = _image_dimensions(raw)
        epub_ext = "jpg" if ext in _JPEG_IMAGE_EXTS else "png"
    else:
        width, height = _image_dimensions(raw)
        payload = _payload_or_loader(
            load_payloads,
            lambda: _image_bytes_to_png(_read_member(archive_path, member.info), member.path.as_posix()),
        )
        epub_ext = "png"
    return ArchiveImage(
        index=index,
        source_index=index,
        label=label,
        width=width,
        height=height,
        epub_ext=epub_ext,
        data=payload[0],
        data_loader=payload[1],
    )


def _payload_or_loader(
    load_payloads: bool,
    load_data: Callable[[], bytes],
) -> tuple[bytes | None, Callable[[], bytes] | None]:
    if load_payloads:
        return load_data(), None
    return None, load_data


def _read_member(archive_path: Path, member_info: ZipInfo) -> bytes:
    try:
        with ZipFile(archive_path) as archive:
            return archive.read(member_info)
    except BadZipFile as exc:
        raise PdfImageError(f"Cannot read archive source: {archive_path}") from exc
    except KeyError as exc:
        raise PdfImageError(f"Archive member missing: {member_info.filename}") from exc


def _image_dimensions(payload: bytes) -> tuple[int, int]:
    try:
        Image = _pillow_image_module()

        with Image.open(BytesIO(payload)) as image:
            return int(image.width), int(image.height)
    except PdfImageError:
        raise
    except Exception as exc:
        raise PdfImageError("Cannot read archive image dimensions") from exc


def _image_bytes_to_png(payload: bytes, member_name: str) -> bytes:
    try:
        Image = _pillow_image_module()

        with Image.open(BytesIO(payload)) as image:
            frame = image.copy()
            if frame.mode not in {"RGB", "RGBA", "L", "LA", "P"}:
                frame = frame.convert("RGBA" if "A" in frame.getbands() else "RGB")
            output = BytesIO()
            frame.save(output, format="PNG")
            return output.getvalue()
    except PdfImageError:
        raise
    except Exception as exc:
        raise PdfImageError(f"Cannot convert archive image to PNG: {member_name}") from exc


def _pillow_image_module():
    from PIL import Image

    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    return Image


def _natural_archive_key(member_name: str) -> list[int | str]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", member_name)]


def _source_ext(name: str) -> str:
    return PurePosixPath(name).suffix.lower().lstrip(".")
