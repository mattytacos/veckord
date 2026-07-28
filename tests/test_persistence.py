"""
Unit tests for Veckord persistence helper functions.
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from persistence import (
    resolve_persistence_path,
    load_json_data,
    atomic_write_json,
    atomic_write_content,
)


class TestPersistenceHelpers(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def test_atomic_write_content(self):
        target_path = os.path.join(self.tmp_dir.name, "sub", "test.txt")
        self.assertTrue(atomic_write_content(target_path, "hello world"))
        self.assertTrue(os.path.exists(target_path))
        with open(target_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "hello world")

    def test_atomic_write_json(self):
        target_path = os.path.join(self.tmp_dir.name, "sub", "data.json")
        sample_data = {"key": "value", "number": 42}
        self.assertTrue(atomic_write_json(target_path, sample_data))
        self.assertTrue(os.path.exists(target_path))
        
        loaded = load_json_data(target_path)
        self.assertEqual(loaded, sample_data)

    def test_load_json_data_nonexistent(self):
        nonexistent = os.path.join(self.tmp_dir.name, "does_not_exist.json")
        self.assertIsNone(load_json_data(nonexistent))

    def test_load_json_data_invalid(self):
        invalid_file = os.path.join(self.tmp_dir.name, "invalid.json")
        with open(invalid_file, "w", encoding="utf-8") as f:
            f.write("not valid json {")
        self.assertIsNone(load_json_data(invalid_file))

    def test_atomic_write_cleanup_on_error(self):
        target_path = os.path.join(self.tmp_dir.name, "error.json")
        # Mock os.replace to raise an Exception
        with patch("os.replace", side_effect=OSError("Disk write error")):
            result = atomic_write_json(target_path, {"test": True})
            self.assertFalse(result)
            # Ensure target path wasn't written
            self.assertFalse(os.path.exists(target_path))

    def test_resolve_persistence_path_primary(self):
        home = self.tmp_dir.name
        with patch.dict(os.environ, {"HOME": home, "DECKY_PLUGIN_SETTINGS_DIR": ""}):
            path = resolve_persistence_path("custom.json")
            expected = os.path.join(home, ".config", "veckord", "custom.json")
            self.assertEqual(path, expected)

    def test_resolve_persistence_path_decky_env(self):
        decky_dir = os.path.join(self.tmp_dir.name, "decky_settings")
        os.makedirs(decky_dir, exist_ok=True)
        with patch.dict(os.environ, {"DECKY_PLUGIN_SETTINGS_DIR": decky_dir}):
            path = resolve_persistence_path("custom.json")
            expected = os.path.join(decky_dir, "custom.json")
            self.assertEqual(path, expected)

    def test_resolve_persistence_path_legacy_migration(self):
        home = self.tmp_dir.name
        legacy_dir = os.path.join(home, ".config", "deckord")
        os.makedirs(legacy_dir, exist_ok=True)
        legacy_file = os.path.join(legacy_dir, "custom.json")
        sample_data = '{"migrated": true}'
        with open(legacy_file, "w", encoding="utf-8") as f:
            f.write(sample_data)

        with patch.dict(os.environ, {"HOME": home, "DECKY_PLUGIN_SETTINGS_DIR": ""}):
            resolved = resolve_persistence_path("custom.json")
            primary_file = os.path.join(home, ".config", "veckord", "custom.json")
            self.assertEqual(resolved, primary_file)
            self.assertTrue(os.path.exists(primary_file))
            with open(primary_file, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), sample_data)


if __name__ == "__main__":
    unittest.main()
