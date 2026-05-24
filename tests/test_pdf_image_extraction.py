import io
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from manga_pdf_to_epub.pdf.image_extraction import _image_from_xref, images_in_pdf_page_order
from manga_pdf_to_epub.pdf.image_types import PdfImageError
from manga_pdf_to_epub.pdf.png import flate_image_to_png
from tests.helpers import pdf_from_objects, png_predict_none, stream_object, two_page_pdf_with_late_cover


class PdfImageExtractionTests(unittest.TestCase):
    def test_images_follow_pdf_page_tree_order(self):
        cover = b"\xff\xd8COVER\xff\xd9"
        page2 = b"\xff\xd8PAGE2\xff\xd9"
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(two_page_pdf_with_late_cover(cover, page2))

            images = images_in_pdf_page_order(pdf_path)

        self.assertEqual([1, 2], [image.index for image in images])
        self.assertEqual([cover, page2], [image.data for image in images])

    def test_page_order_extraction_requires_pymupdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())

            with patch("manga_pdf_to_epub.pdf.image_extraction._load_fitz", return_value=None):
                with self.assertRaisesRegex(PdfImageError, "PyMuPDF is required"):
                    images_in_pdf_page_order(pdf_path)

    def test_named_jbig2_filter_falls_back_to_decoded_png_image(self):
        class FakeDoc:
            def xref_get_key(self, _xref, key):
                values = {
                    "Subtype": ("name", "/Image"),
                    "Filter": ("name", "/JBIG2Decode"),
                }
                return values.get(key, ("null", "null"))

            def extract_image(self, xref):
                self.extracted_xref = xref
                return {
                    "ext": "png",
                    "width": 2,
                    "height": 3,
                    "image": b"PNG-DATA",
                }

        doc = FakeDoc()

        image = _image_from_xref(doc, xref=351, index=7)

        self.assertEqual(351, doc.extracted_xref)
        self.assertEqual("PNG", image.filter_name)
        self.assertEqual(7, image.index)
        self.assertEqual(2, image.width)
        self.assertEqual(3, image.height)
        self.assertEqual(b"PNG-DATA", image.data)

    def test_flate_indexed_image_accepts_indirect_palette_object(self):
        rows = [bytes([0x12]), bytes([0x34])]
        payload = png_predict_none(rows)
        palette = b"\x00\x00\x00\x55\x55\x55\xaa\xaa\xaa\xff\xff\xff"
        pdf = pdf_from_objects(
            [
                (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
                (2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
                (
                    3,
                    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2 2] "
                    b"/Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>",
                ),
                (4, stream_object(b"<< /Length __LEN__ >>", b"q 2 0 0 2 0 0 cm /Im0 Do Q")),
                (
                    5,
                    stream_object(
                        b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 "
                        b"/BitsPerComponent 4 /ColorSpace [/Indexed /DeviceRGB 3 6 0 R] "
                        b"/DecodeParms << /Predictor 15 /Colors 1 /Columns 2 /BitsPerComponent 4 >> "
                        b"/Filter /FlateDecode /Length __LEN__ >>",
                        payload,
                    ),
                ),
                (6, stream_object(b"<< /Length __LEN__ >>", palette)),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(pdf)

            image = images_in_pdf_page_order(pdf_path)[0]
            png = flate_image_to_png(image)

        self.assertEqual(b"[/Indexed /DeviceRGB 3 <000000555555aaaaaaffffff>]", image.color_space)
        self.assertEqual(palette, _png_chunks(png)[b"PLTE"])


def _png_chunks(data):
    chunks = {}
    stream = io.BytesIO(data[8:])
    while True:
        length_data = stream.read(4)
        if not length_data:
            break
        length = struct.unpack(">I", length_data)[0]
        kind = stream.read(4)
        payload = stream.read(length)
        stream.read(4)
        chunks[kind] = payload
        if kind == b"IEND":
            break
    return chunks


if __name__ == "__main__":
    unittest.main()
