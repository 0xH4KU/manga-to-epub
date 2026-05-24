import tempfile
import unittest
from pathlib import Path

from manga_pdf_to_epub.pdf_object_parser import iter_image_streams
from tests.helpers import minimal_pdf, png_predict_none


class PdfObjectParserTests(unittest.TestCase):
    def test_iter_image_streams_extracts_basic_image_dictionary(self):
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

        self.assertEqual(1, image.index)
        self.assertEqual(2, image.width)
        self.assertEqual(2, image.height)
        self.assertEqual(4, image.bits_per_component)
        self.assertEqual("FlateDecode", image.filter_name)
        self.assertEqual(payload, image.data)


if __name__ == "__main__":
    unittest.main()
