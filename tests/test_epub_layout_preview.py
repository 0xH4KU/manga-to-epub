import unittest
from types import SimpleNamespace

from epub_layout_preview import ThumbnailCache, normalize_preview_size, thumbnail_cache_key


class EpubLayoutPreviewTests(unittest.TestCase):
    def test_thumbnail_cache_evicts_least_recently_used_entry(self):
        cache = ThumbnailCache(max_entries=2)
        cache["first"] = "one"
        cache["second"] = "two"

        self.assertEqual("one", cache.get("first"))
        cache["third"] = "three"

        self.assertIsNone(cache.get("second"))
        self.assertEqual("one", cache.get("first"))
        self.assertEqual("three", cache.get("third"))

    def test_preview_size_is_bucketed_to_reduce_cache_fragmentation(self):
        self.assertEqual((150, 150), normalize_preview_size(101, 149))
        self.assertEqual((100, 200), normalize_preview_size(100, 200))

    def test_thumbnail_cache_key_uses_bucketed_size(self):
        entry = SimpleNamespace(source_index=3)

        self.assertEqual(
            ("source", 3, 150, 150),
            thumbnail_cache_key(entry, 101, 149),
        )


if __name__ == "__main__":
    unittest.main()
