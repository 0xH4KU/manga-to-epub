import tempfile
import unittest
import warnings
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo

from PIL import Image

from manga_pdf_to_epub.pdf.image_types import PdfImageError
from manga_pdf_to_epub.sources.archive import archive_images_in_page_order
from tests.helpers import tiny_png


class ArchiveSourceTests(unittest.TestCase):
    def test_archive_images_are_naturally_sorted_and_skip_junk_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "comic.cbz"
            png_bytes = tiny_png()
            jpeg_bytes = _render_sample_image("jpeg")
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("__MACOSX/._page-1.jpg", b"junk")
                archive.writestr(".DS_Store", b"junk")
                archive.writestr("notes.txt", b"not an image")
                archive.writestr("chapter/page-10.png", png_bytes)
                archive.writestr("chapter/page-2.jpg", jpeg_bytes)
                archive.writestr("chapter/page-1.png", png_bytes)

            images = archive_images_in_page_order(archive_path, load_payloads=False)

            self.assertEqual(["page-1", "page-2", "page-10"], [image.label for image in images])
            self.assertEqual([1, 2, 3], [image.source_index for image in images])
            self.assertEqual(["png", "jpg", "png"], [image.epub_ext for image in images])
            self.assertIsNone(images[0].data)
            self.assertIsNotNone(images[0].data_loader)
            self.assertEqual(png_bytes, images[0].load_data())
            self.assertEqual(jpeg_bytes, images[1].load_data())

    def test_archive_converts_wide_image_formats_to_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            archive_path = tmp_path / "comic.zip"
            payloads = {
                "page-1.webp": _render_sample_image("webp"),
                "page-2.bmp": _render_sample_image("bmp"),
                "page-3.tiff": _render_sample_image("tiff"),
                "page-4.gif": _render_sample_image("gif"),
            }
            with ZipFile(archive_path, "w") as archive:
                for name, payload in payloads.items():
                    archive.writestr(name, payload)

            images = archive_images_in_page_order(archive_path)

            self.assertEqual(["png", "png", "png", "png"], [image.epub_ext for image in images])
            self.assertEqual([2, 3, 4, 5], [image.width for image in images])
            self.assertEqual([3, 4, 5, 6], [image.height for image in images])
            for image in images:
                self.assertTrue(image.load_data().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_archive_imports_common_camera_and_modern_image_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "photos.zip"
            payloads = {
                "page-1.jfif": _render_sample_image("jpeg"),
                "page-2.jpe": _render_sample_image("jpeg"),
                "page-3.avif": _render_sample_image("avif"),
                "page-4.jp2": _render_sample_image("jpeg2000"),
                "page-5.heic": _render_sample_image("heif"),
                "page-6.heif": _render_sample_image("heif"),
            }
            with ZipFile(archive_path, "w") as archive:
                for name, payload in payloads.items():
                    archive.writestr(name, payload)

            images = archive_images_in_page_order(archive_path)

            self.assertEqual(["page-1", "page-2", "page-3", "page-4", "page-5", "page-6"], [image.label for image in images])
            self.assertEqual(["jpg", "jpg", "png", "png", "png", "png"], [image.epub_ext for image in images])
            self.assertEqual([2, 2, 6, 7, 8, 8], [image.width for image in images])
            self.assertEqual([3, 3, 7, 8, 9, 9], [image.height for image in images])
            self.assertEqual(payloads["page-1.jfif"], images[0].load_data())
            self.assertEqual(payloads["page-2.jpe"], images[1].load_data())
            for image in images[2:]:
                self.assertTrue(image.load_data().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_archive_reads_duplicate_member_names_by_entry_not_filename_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "duplicates.zip"
            first_payload = _render_sample_image("jpeg", color=(255, 0, 0))
            second_payload = _render_sample_image("jpeg", color=(0, 255, 0))
            with ZipFile(archive_path, "w") as archive:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    archive.writestr(ZipInfo("page.jpg"), first_payload)
                    archive.writestr(ZipInfo("page.jpg"), second_payload)

            images = archive_images_in_page_order(archive_path, load_payloads=False)

            self.assertEqual(2, len(images))
            self.assertEqual(first_payload, images[0].load_data())
            self.assertEqual(second_payload, images[1].load_data())

    def test_empty_archive_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "empty.cbz"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("readme.txt", "hello")

            with self.assertRaisesRegex(PdfImageError, "No supported image files found"):
                archive_images_in_page_order(archive_path)


def _render_sample_image(fmt: str, color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    width = {"jpeg": 2, "webp": 2, "bmp": 3, "tiff": 4, "gif": 5, "avif": 6, "jpeg2000": 7, "heif": 8}[fmt]
    height = width + 1
    image = Image.new("RGB", (width, height), color)
    stream = BytesIO()
    if fmt == "heif":
        import pillow_heif

        pillow_heif.register_heif_opener()
    image.save(
        stream,
        format={
            "jpeg": "JPEG",
            "webp": "WEBP",
            "bmp": "BMP",
            "tiff": "TIFF",
            "gif": "GIF",
            "avif": "AVIF",
            "jpeg2000": "JPEG2000",
            "heif": "HEIF",
        }[fmt],
    )
    return stream.getvalue()


if __name__ == "__main__":
    unittest.main()
