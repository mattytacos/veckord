"""
Veckord Favorites Manager.

Manages persistence of favorite voice channels in a local JSON settings file.
Schema stored:
[
  {
    "guild_id": "string",
    "channel_id": "string",
    "guild_name": "string",
    "channel_name": "string"
  }
]
"""

import os
from typing import List, Dict, Any, Optional

try:
    from backend.persistence import resolve_persistence_path, load_json_data, atomic_write_json
except ImportError:
    from persistence import resolve_persistence_path, load_json_data, atomic_write_json


def resolve_settings_path() -> str:
    return resolve_persistence_path("favorites.json")


class FavoritesManager:
    """
    Manages loading, saving, adding, removing, and reordering favorite voice channels.
    """

    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path or resolve_settings_path()

    def get_favorites(self) -> List[Dict[str, str]]:
        data = load_json_data(self.file_path)
        if not isinstance(data, list):
            return []

        valid_favorites: List[Dict[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            guild_id = item.get("guild_id")
            channel_id = item.get("channel_id")
            guild_name = item.get("guild_name", "Unknown Server")
            channel_name = item.get("channel_name", "Unknown Channel")

            if guild_id and channel_id:
                valid_favorites.append({
                    "guild_id": str(guild_id),
                    "channel_id": str(channel_id),
                    "guild_name": str(guild_name),
                    "channel_name": str(channel_name),
                })

        return valid_favorites

    def set_favorites(self, favorites: List[Dict[str, Any]]) -> bool:
        if not isinstance(favorites, list):
            return False

        sanitized: List[Dict[str, str]] = []
        for item in favorites:
            if not isinstance(item, dict):
                continue
            guild_id = item.get("guild_id")
            channel_id = item.get("channel_id")
            guild_name = item.get("guild_name", "Unknown Server")
            channel_name = item.get("channel_name", "Unknown Channel")

            if guild_id and channel_id:
                sanitized.append({
                    "guild_id": str(guild_id),
                    "channel_id": str(channel_id),
                    "guild_name": str(guild_name),
                    "channel_name": str(channel_name),
                })

        return atomic_write_json(self.file_path, sanitized)

    def add_favorite(self, guild_id: str, channel_id: str, guild_name: str, channel_name: str) -> bool:
        favs = self.get_favorites()
        # Avoid duplicate
        for f in favs:
            if f.get("channel_id") == str(channel_id):
                return True

        favs.append({
            "guild_id": str(guild_id),
            "channel_id": str(channel_id),
            "guild_name": str(guild_name),
            "channel_name": str(channel_name),
        })
        return self.set_favorites(favs)

    def remove_favorite(self, channel_id: str) -> bool:
        favs = self.get_favorites()
        filtered = [f for f in favs if f.get("channel_id") != str(channel_id)]
        return self.set_favorites(filtered)

    def move_favorite(self, channel_id: str, direction: str) -> bool:
        favs = self.get_favorites()
        idx = -1
        for i, f in enumerate(favs):
            if f.get("channel_id") == str(channel_id):
                idx = i
                break

        if idx == -1:
            return False

        if direction == "up" and idx > 0:
            favs[idx], favs[idx - 1] = favs[idx - 1], favs[idx]
        elif direction == "down" and idx < len(favs) - 1:
            favs[idx], favs[idx + 1] = favs[idx + 1], favs[idx]
        else:
            return False

        return self.set_favorites(favs)
