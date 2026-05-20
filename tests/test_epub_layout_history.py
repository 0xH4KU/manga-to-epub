import unittest

from epub_layout_history import CoverState, DeleteHistory


class EpubLayoutHistoryTests(unittest.TestCase):
    def test_delete_history_pushes_and_pops_entries_with_cover_state(self):
        history = DeleteHistory()
        cover = CoverState(source_index=2, entry_id=None)

        history.push([(1, "Page 2")], cover)

        self.assertTrue(history)
        deleted, restored_cover = history.pop()
        self.assertEqual([(1, "Page 2")], deleted)
        self.assertEqual(cover, restored_cover)
        self.assertFalse(history)

    def test_delete_history_clear_removes_entries_and_cover_states(self):
        history = DeleteHistory()
        history.push([(0, "Page 1")], CoverState(source_index=1, entry_id=None))

        history.clear()

        self.assertFalse(history)
        self.assertEqual(([], None), history.pop())


if __name__ == "__main__":
    unittest.main()
