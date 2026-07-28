"""
Unit tests for Veckord migration, settings auto-migration, socket fallbacks, and env var fallbacks.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from favorites_manager import resolve_settings_path, FavoritesManager
from veckord_backend import resolve_socket_path
from discord_rpc.auth import AuthManager
from discord_rpc.client import DiscordRPCClient


class TestMigrationAndFallbacks(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def test_primary_settings_path_resolution(self):
        with patch.dict(os.environ, {"HOME": self.tmp_dir.name, "DECKY_PLUGIN_SETTINGS_DIR": ""}):
            path = resolve_settings_path()
            expected = os.path.join(self.tmp_dir.name, ".config", "veckord", "favorites.json")
            self.assertEqual(path, expected)

    def test_legacy_settings_migration(self):
        home = self.tmp_dir.name
        legacy_dir = os.path.join(home, ".config", "deckord")
        os.makedirs(legacy_dir, exist_ok=True)
        legacy_file = os.path.join(legacy_dir, "favorites.json")

        sample_data = '[{"guild_id": "111", "channel_id": "222", "guild_name": "G", "channel_name": "C"}]'
        with open(legacy_file, "w", encoding="utf-8") as f:
            f.write(sample_data)

        with patch.dict(os.environ, {"HOME": home, "DECKY_PLUGIN_SETTINGS_DIR": ""}):
            resolved_path = resolve_settings_path()
            primary_file = os.path.join(home, ".config", "veckord", "favorites.json")
            self.assertEqual(resolved_path, primary_file)
            self.assertTrue(os.path.exists(primary_file))

            with open(primary_file, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content, sample_data)

    def test_primary_settings_preferred_over_legacy(self):
        home = self.tmp_dir.name
        primary_dir = os.path.join(home, ".config", "veckord")
        legacy_dir = os.path.join(home, ".config", "deckord")
        os.makedirs(primary_dir, exist_ok=True)
        os.makedirs(legacy_dir, exist_ok=True)

        primary_file = os.path.join(primary_dir, "favorites.json")
        legacy_file = os.path.join(legacy_dir, "favorites.json")

        with open(primary_file, "w", encoding="utf-8") as f:
            f.write('[{"channel_id": "primary"}]')
        with open(legacy_file, "w", encoding="utf-8") as f:
            f.write('[{"channel_id": "legacy"}]')

        with patch.dict(os.environ, {"HOME": home, "DECKY_PLUGIN_SETTINGS_DIR": ""}):
            resolved_path = resolve_settings_path()
            self.assertEqual(resolved_path, primary_file)

    def test_socket_path_fallback(self):
        runtime_dir = self.tmp_dir.name
        legacy_sock_dir = os.path.join(runtime_dir, "deckord")
        os.makedirs(legacy_sock_dir, exist_ok=True)
        legacy_sock = os.path.join(legacy_sock_dir, "bridge.sock")
        open(legacy_sock, "a").close()

        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime_dir}):
            resolved = resolve_socket_path()
            self.assertEqual(resolved, legacy_sock)

    def test_primary_socket_preferred_over_legacy(self):
        runtime_dir = self.tmp_dir.name
        primary_sock_dir = os.path.join(runtime_dir, "veckord")
        legacy_sock_dir = os.path.join(runtime_dir, "deckord")
        os.makedirs(primary_sock_dir, exist_ok=True)
        os.makedirs(legacy_sock_dir, exist_ok=True)

        primary_sock = os.path.join(primary_sock_dir, "bridge.sock")
        legacy_sock = os.path.join(legacy_sock_dir, "bridge.sock")
        open(primary_sock, "a").close()
        open(legacy_sock, "a").close()

        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime_dir}):
            resolved = resolve_socket_path()
            self.assertEqual(resolved, primary_sock)

    def test_legacy_env_var_fallback(self):
        client = DiscordRPCClient()
        auth_mgr = AuthManager(client)

        with patch.dict(os.environ, {
            "DECKORD_DISCORD_CLIENT_ID": "legacy_cid_123",
            "DECKORD_DISCORD_CLIENT_SECRET": "legacy_sec_456"
        }, clear=True):
            mock_resp = unittest.mock.MagicMock()
            mock_resp.read.return_value = b'{"rpc_token": "mock_rpc_token_123"}'
            mock_resp.__enter__.return_value = mock_resp

            with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
                token = auth_mgr.request_rpc_token()
                self.assertEqual(token, "mock_rpc_token_123")
                call_args = mock_urlopen.call_args
                req = call_args[0][0]
                body = req.data.decode("utf-8")
                self.assertIn("client_id=legacy_cid_123", body)
                self.assertIn("client_secret=legacy_sec_456", body)


if __name__ == "__main__":
    unittest.main()
