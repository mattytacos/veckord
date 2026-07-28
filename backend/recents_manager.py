"""
Veckord Recents Manager.

Manages persistence of recently connected voice channels in a local JSON file.
Schema stored:
[
  {
    "guild_id": "string",
    "channel_id": "string",
    "guild_name": "string",
    "channel_name": "string",
    "last_connected": 1722187200
  }
]
"""

import os
import time
from typing import List, Dict, Any, Optional

try:
    from backend.persistence import resolve_persistence_path, load_json_data, atomic_write_json
except ImportError:
    from persistence import resolve_persistence_path, load_json_data, atomic_write_json

MAX_RECENTS = 10


def resolve_recents_path() -> str:
    return resolve_persistence_path("recents.json")


class RecentsManager:
    """
    Manages loading, recording, and updating recently joined voice channels.
    """

    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path or resolve_recents_path()

    def get_recents(self) -> List[Dict[str, Any]]:
        data = load_json_data(self.file_path)
        if not isinstance(data, list):
            return []

        valid_recents: List[Dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            guild_id = item.get("guild_id")
            channel_id = item.get("channel_id")
            guild_name = item.get("guild_name", "Unknown Server")
            channel_name = item.get("channel_name", "Unknown Channel")
            last_connected = item.get("last_connected", 0)

            if guild_id and channel_id:
                valid_recents.append({
                    "guild_id": str(guild_id),
                    "channel_id": str(channel_id),
                    "guild_name": str(guild_name),
                    "channel_name": str(channel_name),
                    "last_connected": int(last_connected) if isinstance(last_connected, (int, float)) else 0,
                })

        # Sort by last_connected descending
        valid_recents.sort(key=lambda r: r.get("last_connected", 0), reverse=True)
        return valid_recents[:MAX_RECENTS]

    def save_recents(self, recents: List[Dict[str, Any]]) -> bool:
        if not isinstance(recents, list):
            return False

        sanitized: List[Dict[str, Any]] = []
        for item in recents:
            if not isinstance(item, dict):
                continue
            guild_id = item.get("guild_id")
            channel_id = item.get("channel_id")
            guild_name = item.get("guild_name", "Unknown Server")
            channel_name = item.get("channel_name", "Unknown Channel")
            last_connected = item.get("last_connected", time.time())

            if guild_id and channel_id:
                sanitized.append({
                    "guild_id": str(guild_id),
                    "channel_id": str(channel_id),
                    "guild_name": str(guild_name),
                    "channel_name": str(channel_name),
                    "last_connected": int(last_connected),
                })

        sanitized.sort(key=lambda r: r.get("last_connected", 0), reverse=True)
        sanitized = sanitized[:MAX_RECENTS]

        return atomic_write_json(self.file_path, sanitized)

    def record_recent(self, guild_id: str, channel_id: str, guild_name: str, channel_name: str) -> bool:
        if not guild_id or not channel_id:
            return False

        recents = self.get_recents()
        # Remove existing entry for same channel if present
        filtered = [r for r in recents if r.get("channel_id") != str(channel_id)]

        # Prepend new entry at top
        new_entry = {
            "guild_id": str(guild_id),
            "channel_id": str(channel_id),
            "guild_name": str(guild_name or "Unknown Server"),
            "channel_name": str(channel_name or "Unknown Channel"),
            "last_connected": int(time.time()),
        }
        filtered.insert(0, new_entry)
        return self.save_recents(filtered)

    def clear_recents(self) -> bool:
        return self.save_recents([])
