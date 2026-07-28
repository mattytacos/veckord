"""
Unit tests for Deckord Decky Plugin Backend, Favorites Persistence, and Error Scenarios.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from favorites_manager import FavoritesManager
from deckord_backend import DeckordBackend


class TestDeckyBackend(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.fav_file = os.path.join(self.tmp_dir.name, "favorites.json")
        self.favorites_mgr = FavoritesManager(file_path=self.fav_file)
        self.backend = DeckordBackend(socket_path="/tmp/nonexistent_deckord_bridge.sock", timeout=1.0)
        self.backend.favorites_mgr = self.favorites_mgr

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_empty_favorites(self):
        favs = self.favorites_mgr.get_favorites()
        self.assertEqual(favs, [])

    def test_favorite_persistence(self):
        sample_favs = [
            {
                "guild_id": "12345",
                "channel_id": "67890",
                "guild_name": "Test Server",
                "channel_name": "General Voice",
            }
        ]
        save_res = self.favorites_mgr.set_favorites(sample_favs)
        self.assertTrue(save_res)

        loaded_favs = self.favorites_mgr.get_favorites()
        self.assertEqual(len(loaded_favs), 1)
        self.assertEqual(loaded_favs[0]["guild_id"], "12345")
        self.assertEqual(loaded_favs[0]["channel_id"], "67890")

    def test_add_remove_move_favorites(self):
        # Add favorite 1
        res1 = self.backend.add_favorite("g1", "c1", "Guild 1", "Channel 1")
        self.assertTrue(res1["ok"])
        # Add favorite 2
        res2 = self.backend.add_favorite("g1", "c2", "Guild 1", "Channel 2")
        self.assertTrue(res2["ok"])

        favs = self.favorites_mgr.get_favorites()
        self.assertEqual(len(favs), 2)
        self.assertEqual(favs[0]["channel_id"], "c1")
        self.assertEqual(favs[1]["channel_id"], "c2")

        # Move c2 up
        move_res = self.backend.move_favorite("c2", "up")
        self.assertTrue(move_res["ok"])
        favs_after_move = self.favorites_mgr.get_favorites()
        self.assertEqual(favs_after_move[0]["channel_id"], "c2")

        # Remove c1
        rem_res = self.backend.remove_favorite("c1")
        self.assertTrue(rem_res["ok"])
        favs_after_rem = self.favorites_mgr.get_favorites()
        self.assertEqual(len(favs_after_rem), 1)
        self.assertEqual(favs_after_rem[0]["channel_id"], "c2")

    def test_bridge_unavailable_error(self):
        res = self.backend.get_bridge_status()
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"]["code"], "BRIDGE_UNAVAILABLE")

    @patch.object(DeckordBackend, "_execute_bridge_call")
    def test_successful_status_read(self, mock_bridge):
        mock_bridge.return_value = {
            "ok": True,
            "data": {
                "client": "Vesktop/Vencord",
                "connected": True,
                "user": {
                    "id": "100",
                    "username": "gamer",
                    "discriminator": "0"
                },
                "voiceSettings": {
                    "isMuted": False,
                    "isDeafened": False,
                    "isSelfMute": False,
                    "isSelfDeaf": False
                },
                "currentVoiceChannel": None
            }
        }
        res = self.backend.get_bridge_status()
        self.assertTrue(res["ok"])
        self.assertEqual(res["data"]["client"], "Vesktop/Vencord")
        self.assertTrue(res["data"]["connected"])

    @patch.object(DeckordBackend, "_execute_bridge_call")
    def test_current_channel_normalization(self, mock_bridge):
        mock_bridge.return_value = {
            "ok": True,
            "data": {
                "channel": {
                    "id": "200",
                    "guildId": "100",
                    "name": "Lounge",
                    "position": 0,
                    "userLimit": 0,
                    "memberCount": 1
                }
            }
        }
        res = self.backend.get_current_voice_channel()
        self.assertTrue(res["ok"])
        self.assertEqual(res["data"]["channel"]["name"], "Lounge")

    @patch.object(DeckordBackend, "_execute_bridge_call")
    def test_join_channel(self, mock_bridge):
        mock_bridge.return_value = {"ok": True, "data": {"success": True}}
        res = self.backend.join_voice_channel("200", "100")
        self.assertTrue(res["ok"])

    def test_invalid_favorite_join_error(self):
        res = self.backend.join_voice_channel("")
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"]["code"], "INVALID_FAVORITE")

    @patch.object(DeckordBackend, "_execute_bridge_call")
    def test_leave_channel(self, mock_bridge):
        mock_bridge.return_value = {"ok": True, "data": {"success": True}}
        res = self.backend.leave_voice_channel()
        self.assertTrue(res["ok"])

    @patch.object(DeckordBackend, "_execute_bridge_call")
    def test_set_muted(self, mock_bridge):
        mock_bridge.return_value = {"ok": True, "data": {"success": True}}
        res = self.backend.set_muted(True)
        self.assertTrue(res["ok"])

    @patch.object(DeckordBackend, "_execute_bridge_call")
    def test_set_deafened(self, mock_bridge):
        mock_bridge.return_value = {"ok": True, "data": {"success": True}}
        res = self.backend.set_deafened(True)
        self.assertTrue(res["ok"])

    @patch.object(DeckordBackend, "_execute_bridge_call")
    def test_get_guilds_and_channels(self, mock_bridge):
        def side_effect(method, params=None):
            if method == "getGuilds":
                return {"ok": True, "data": {"guilds": [{"id": "g1", "name": "Server 1"}]}}
            elif method == "getVoiceChannels":
                return {"ok": True, "data": {"channels": [{"id": "c1", "name": "Voice 1"}]}}
            return {"ok": False}

        mock_bridge.side_effect = side_effect
        res = self.backend.get_guilds_and_channels()
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["data"]["guilds"]), 1)
        self.assertEqual(res["data"]["guilds"][0]["channels"][0]["name"], "Voice 1")


if __name__ == "__main__":
    unittest.main()
