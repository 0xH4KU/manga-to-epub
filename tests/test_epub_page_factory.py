import unittest

from manga_pdf_to_epub.epub_page_factory import page_from_image
from manga_pdf_to_epub.pdf_image_types import ImageStream


class EpubPageFactoryTests(unittest.TestCase):
    def test_page_from_image_preserves_lossless_payload_and_builds_epub_paths(self):
        image = ImageStream(
            index=12,
            width=100,
            height=200,
            bits_per_component=8,
            color_space=b"/DeviceRGB",
            filter_name="DCTDecode",
            decode_parms=None,
            data=b"\xff\xd8JPEG\xff\xd9",
        )

        page, ext = page_from_image(image, padding=4)

        self.assertEqual("jpg", ext)
        self.assertEqual(12, page.index)
        self.assertEqual(100, page.width)
        self.assertEqual(200, page.height)
        self.assertEqual("images/page-0012.jpg", page.image_href)
        self.assertEqual("image/jpeg", page.image_media_type)
        self.assertEqual(b"\xff\xd8JPEG\xff\xd9", page.image_data)
        self.assertEqual("xhtml/page-0012.xhtml", page.xhtml_href)
        self.assertEqual("page-0012", page.item_id)
        self.assertEqual("Page 12", page.label)


if __name__ == "__main__":
    unittest.main()
