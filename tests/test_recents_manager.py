import os
import json
import tempfile
import unittest

from backend.recents_manager import RecentsManager, MAX_RECENTS


class TestRecentsManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.file_path = os.path.join(self.temp_dir.name, "recents.json")
        self.manager = RecentsManager(file_path=self.file_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_recents_empty(self):
        recents = self.manager.get_recents()
        self.assertEqual(recents, [])

    def test_record_recent_and_ordering(self):
        self.assertTrue(self.manager.record_recent("g1", "c1", "Guild 1", "Channel 1"))
        self.assertTrue(self.manager.record_recent("g1", "c2", "Guild 1", "Channel 2"))

        recents = self.manager.get_recents()
        self.assertEqual(len(recents), 2)
        # Channel 2 was recorded last, so it must be first
        self.assertEqual(recents[0]["channel_id"], "c2")
        self.assertEqual(recents[1]["channel_id"], "c1")

    def test_rejoining_older_channel_moves_to_top(self):
        self.manager.record_recent("g1", "c1", "Guild 1", "Channel 1")
        self.manager.record_recent("g1", "c2", "Guild 1", "Channel 2")
        # Rejoin Channel 1
        self.manager.record_recent("g1", "c1", "Guild 1", "Channel 1")

        recents = self.manager.get_recents()
        self.assertEqual(len(recents), 2)
        self.assertEqual(recents[0]["channel_id"], "c1")
        self.assertEqual(recents[1]["channel_id"], "c2")

    def test_max_recents_cap(self):
        for i in range(MAX_RECENTS + 5):
            self.manager.record_recent("g1", f"c{i}", "Guild 1", f"Channel {i}")

        recents = self.manager.get_recents()
        self.assertEqual(len(recents), MAX_RECENTS)
        # Most recent recorded was c{MAX_RECENTS + 4}
        self.assertEqual(recents[0]["channel_id"], f"c{MAX_RECENTS + 4}")

    def test_clear_recents(self):
        self.manager.record_recent("g1", "c1", "Guild 1", "Channel 1")
        self.assertTrue(self.manager.clear_recents())
        self.assertEqual(self.manager.get_recents(), [])


if __name__ == "__main__":
    unittest.main()
