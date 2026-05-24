import io
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from manga_pdf_to_epub.pdf.image_types import ImageStream
from manga_pdf_to_epub.pdf.object_parser import iter_image_streams
from manga_pdf_to_epub.pdf.png import flate_image_to_png, image_to_epub_member
from tests.helpers import minimal_pdf, png_predict_none


class PdfPngTests(unittest.TestCase):
    def test_already_extracted_png_stream_is_epub_ready_without_rewrapping(self):
        image = ImageStream(
            index=1,
            width=2,
            height=3,
            bits_per_component=8,
            color_space=b"/DeviceRGB",
            filter_name="PNG",
            decode_parms=None,
            data=b"PNG-DATA",
        )

        self.assertEqual(("png", b"PNG-DATA"), image_to_epub_member(image))

    def test_flate_indexed_png_predictor_image_is_wrapped_as_png(self):
        rows = [bytes([0x12]), bytes([0x34])]
        payload = png_predict_none(rows)
        pdf = minimal_pdf(
            [
                (
                    b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 "
                    b"/BitsPerComponent 4 /ColorSpace [/Indexed /DeviceRGB 3 ("
                    b"\x00\x00\x00\x55\x55\x55\xaa\xaa\xaa\xff\xff\xff"
                    b")] /DecodeParms << /Predictor 15 /Colors 1 /Columns 2 /BitsPerComponent 4 >> "
                    b"/Filter /FlateDecode /Length __LEN__ >>",
                    payload,
                )
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(pdf)
            image = iter_image_streams(pdf_path)[0]

        png = flate_image_to_png(image)

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        chunks = _png_chunks(png)
        self.assertEqual((2, 2, 4, 3), struct.unpack(">IIBB", chunks[b"IHDR"][:10]))
        self.assertEqual(b"\x00\x00\x00\x55\x55\x55\xaa\xaa\xaa\xff\xff\xff", chunks[b"PLTE"])
        self.assertEqual(b"\x00\x12\x00\x34", zlib.decompress(chunks[b"IDAT"]))

    def test_flate_png_predictor_reuses_original_zlib_stream_as_png_idat(self):
        payload = png_predict_none([bytes([0x12]), bytes([0x34])])
        pdf = minimal_pdf(
            [
                (
                    b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 "
                    b"/BitsPerComponent 4 /ColorSpace [/Indexed /DeviceRGB 3 ("
                    b"\x00\x00\x00\x55\x55\x55\xaa\xaa\xaa\xff\xff\xff"
                    b")] /DecodeParms << /Predictor 15 /Colors 1 /Columns 2 /BitsPerComponent 4 >> "
                    b"/Filter /FlateDecode /Length __LEN__ >>",
                    payload,
                )
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(pdf)
            image = iter_image_streams(pdf_path)[0]

        chunks = _png_chunks(flate_image_to_png(image))

        self.assertEqual(payload, chunks[b"IDAT"])


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
