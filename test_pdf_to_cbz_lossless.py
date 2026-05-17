import io
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

from pdf_to_cbz_lossless import convert_pdf_to_cbz, flate_image_to_png, iter_image_streams


def _png_predict_none(rows):
    return zlib.compress(b"".join(b"\x00" + row for row in rows))


def _minimal_pdf(streams):
    parts = [b"%PDF-1.6\n"]
    offsets = []
    for index, (dictionary, payload) in enumerate(streams, 1):
        offsets.append(sum(map(len, parts)))
        parts.extend(
            [
                f"{index} 0 obj\n".encode(),
                dictionary.replace(b"__LEN__", str(len(payload)).encode()),
                b"\nstream\n",
                payload,
                b"\nendstream\nendobj\n",
            ]
        )
    xref = sum(map(len, parts))
    parts.append(f"xref\n0 {len(streams) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        parts.append(f"{offset:010d} 00000 n \n".encode())
    parts.append(f"trailer << /Size {len(streams) + 1} >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return b"".join(parts)


def _pdf_from_objects(objects):
    parts = [b"%PDF-1.6\n"]
    offsets = {}
    for obj_num, body in objects:
        offsets[obj_num] = sum(map(len, parts))
        parts.extend([f"{obj_num} 0 obj\n".encode(), body, b"\nendobj\n"])
    xref = sum(map(len, parts))
    max_obj = max(offsets)
    parts.append(f"xref\n0 {max_obj + 1}\n0000000000 65535 f \n".encode())
    for obj_num in range(1, max_obj + 1):
        offset = offsets.get(obj_num, 0)
        parts.append((f"{offset:010d} 00000 n \n" if offset else "0000000000 65535 f \n").encode())
    parts.append(f"trailer << /Root 1 0 R /Size {max_obj + 1} >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return b"".join(parts)


def _stream_object(dictionary, payload):
    return b"".join(
        [
            dictionary.replace(b"__LEN__", str(len(payload)).encode()),
            b"\nstream\n",
            payload,
            b"\nendstream",
        ]
    )


def _two_page_pdf_with_late_cover(cover_bytes=b"\xff\xd8COVER\xff\xd9", page2_bytes=b"\xff\xd8PAGE2\xff\xd9"):
    draw = b"q 2 0 0 1 0 0 cm /Im0 Do Q"
    image_template = (
        b"<< /Type /XObject /Subtype /Image /Width 2 /Height 1 "
        b"/BitsPerComponent 8 /ColorSpace /DeviceRGB /Filter /DCTDecode /Length __LEN__ >>"
    )
    return _pdf_from_objects(
        [
            (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
            (2, b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>"),
            (
                3,
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2 1] "
                b"/Resources << /XObject << /Im0 8 0 R >> >> /Contents 6 0 R >>",
            ),
            (
                4,
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2 1] "
                b"/Resources << /XObject << /Im0 5 0 R >> >> /Contents 7 0 R >>",
            ),
            (5, _stream_object(image_template, page2_bytes)),
            (6, _stream_object(b"<< /Length __LEN__ >>", draw)),
            (7, _stream_object(b"<< /Length __LEN__ >>", draw)),
            (8, _stream_object(image_template, cover_bytes)),
        ]
    )


class PdfToCbzLosslessTests(unittest.TestCase):
    def test_dct_image_stream_is_copied_to_cbz_without_reencoding(self):
        jpeg = b"\xff\xd8JPEG-DATA\xff\xd9"
        pdf = _minimal_pdf(
            [
                (
                    b"<< /Type /XObject /Subtype /Image /Width 2 /Height 1 "
                    b"/BitsPerComponent 8 /ColorSpace /DeviceRGB /Filter /DCTDecode /Length __LEN__ >>",
                    jpeg,
                )
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            cbz_path = Path(tmp) / "comic.cbz"
            pdf_path.write_bytes(pdf)

            counts = convert_pdf_to_cbz(pdf_path, cbz_path)

            self.assertEqual({"jpg": 1, "png": 0, "total": 1}, counts)
            with ZipFile(cbz_path) as archive:
                self.assertEqual(["0001.jpg"], archive.namelist())
                self.assertEqual(jpeg, archive.read("0001.jpg"))
                self.assertEqual(ZIP_STORED, archive.getinfo("0001.jpg").compress_type)

    def test_archive_order_follows_pdf_page_tree_not_image_object_order(self):
        cover = b"\xff\xd8COVER\xff\xd9"
        page2 = b"\xff\xd8PAGE2\xff\xd9"
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            cbz_path = Path(tmp) / "comic.cbz"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover(cover, page2))

            convert_pdf_to_cbz(pdf_path, cbz_path)

            with ZipFile(cbz_path) as archive:
                self.assertEqual(["0001.jpg", "0002.jpg"], archive.namelist())
                self.assertEqual(cover, archive.read("0001.jpg"))
                self.assertEqual(page2, archive.read("0002.jpg"))

    def test_flate_indexed_png_predictor_image_is_wrapped_as_png(self):
        rows = [bytes([0x12]), bytes([0x34])]
        payload = _png_predict_none(rows)
        pdf = _minimal_pdf(
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
        payload = _png_predict_none([bytes([0x12]), bytes([0x34])])
        pdf = _minimal_pdf(
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
