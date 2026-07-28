"""
Veckord Decky Plugin Backend Wrapper.

Wraps VeckordBridgeClient and FavoritesManager to expose normalized API methods to Decky ServerAPI.
"""

import os
import sys
from typing import Dict, Any, Optional, List

try:
    from backend.bridge_client import VeckordBridgeClient, resolve_socket_path
except ImportError:
    from bridge_client import VeckordBridgeClient, resolve_socket_path

try:
    from backend.favorites_manager import FavoritesManager
except ImportError:
    from favorites_manager import FavoritesManager

try:
    from backend.recents_manager import RecentsManager
except ImportError:
    from recents_manager import RecentsManager


class VeckordBackend:
    """
    Veckord Decky backend service.
    """

    def __init__(self, socket_path: Optional[str] = None, timeout: float = 15.0):
        self.socket_path = socket_path or resolve_socket_path()
        self.timeout = timeout
        self.favorites_mgr = FavoritesManager()
        self.recents_mgr = RecentsManager()

    def _execute_bridge_call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            client = VeckordBridgeClient(socket_path=self.socket_path, timeout=self.timeout)
            res = client.send_request(method, params or {})
            return {
                "ok": True,
                "data": res,
            }
        except FileNotFoundError as e:
            return {
                "ok": False,
                "error": {
                    "code": "BRIDGE_UNAVAILABLE",
                    "message": "Discord not running or bridge socket missing.",
                },
            }
        except ConnectionError as e:
            return {
                "ok": False,
                "error": {
                    "code": "BRIDGE_UNAVAILABLE",
                    "message": f"Bridge connection refused: {e}",
                },
            }
        except RuntimeError as e:
            err_str = str(e)
            code = "ADAPTER_ERROR"
            msg = err_str

            if "Bridge Error [" in err_str:
                parts = err_str.split("Bridge Error [", 1)[1].split("]: ", 1)
                if len(parts) == 2:
                    code = parts[0]
                    msg = parts[1]
                elif len(parts) == 1:
                    code = parts[0].rstrip("]")

            return {
                "ok": False,
                "error": {
                    "code": code,
                    "message": msg,
                },
            }
        except Exception as e:
            return {
                "ok": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": f"Unexpected backend error: {e}",
                },
            }

    def get_bridge_status(self) -> Dict[str, Any]:
        return self._execute_bridge_call("getStatus")

    def get_current_voice_channel(self) -> Dict[str, Any]:
        return self._execute_bridge_call("getCurrentVoiceChannel")

    def get_voice_settings(self) -> Dict[str, Any]:
        return self._execute_bridge_call("getVoiceSettings")

    def get_favorite_channels(self) -> Dict[str, Any]:
        favs = self.favorites_mgr.get_favorites()
        return {
            "ok": True,
            "data": {
                "favorites": favs,
            },
        }

    def set_favorite_channels(self, favorites: List[Dict[str, Any]]) -> Dict[str, Any]:
        success = self.favorites_mgr.set_favorites(favorites)
        if success:
            return {
                "ok": True,
                "data": {
                    "favorites": self.favorites_mgr.get_favorites(),
                },
            }
        return {
            "ok": False,
            "error": {
                "code": "PERSISTENCE_ERROR",
                "message": "Failed to save favorites settings",
            },
        }

    def add_favorite(self, guild_id: str, channel_id: str, guild_name: str, channel_name: str) -> Dict[str, Any]:
        success = self.favorites_mgr.add_favorite(guild_id, channel_id, guild_name, channel_name)
        if success:
            return {
                "ok": True,
                "data": {
                    "favorites": self.favorites_mgr.get_favorites(),
                },
            }
        return {
            "ok": False,
            "error": {
                "code": "PERSISTENCE_ERROR",
                "message": "Failed to add favorite channel",
            },
        }

    def remove_favorite(self, channel_id: str) -> Dict[str, Any]:
        success = self.favorites_mgr.remove_favorite(channel_id)
        if success:
            return {
                "ok": True,
                "data": {
                    "favorites": self.favorites_mgr.get_favorites(),
                },
            }
        return {
            "ok": False,
            "error": {
                "code": "PERSISTENCE_ERROR",
                "message": "Failed to remove favorite channel",
            },
        }

    def move_favorite(self, channel_id: str, direction: str) -> Dict[str, Any]:
        success = self.favorites_mgr.move_favorite(channel_id, direction)
        if success:
            return {
                "ok": True,
                "data": {
                    "favorites": self.favorites_mgr.get_favorites(),
                },
            }
        return {
            "ok": False,
            "error": {
                "code": "PERSISTENCE_ERROR",
                "message": "Failed to move favorite channel",
            },
        }

    # Channels returned by Discord with this name are inaccessible sentinel
    # placeholders for hidden category slots. Filter them from the browser.
    _HIDDEN_CHANNEL_SENTINEL = "___hidden___"

    def get_guilds_and_channels(self) -> Dict[str, Any]:
        guilds_res = self._execute_bridge_call("getGuilds")
        if not guilds_res.get("ok") or not guilds_res.get("data"):
            return guilds_res

        guilds = guilds_res["data"].get("guilds", [])
        result_guilds: List[Dict[str, Any]] = []

        for g in guilds:
            g_id = g.get("id")
            g_name = g.get("name", "Unnamed Server")
            if not g_id:
                continue

            channels_res = self._execute_bridge_call("getVoiceChannels", {"guildId": str(g_id)})
            v_channels = []
            if channels_res.get("ok") and channels_res.get("data"):
                v_channels = channels_res["data"].get("channels", [])

            # Filter hidden sentinel channels and sort by position for stable display
            joinable = [
                c for c in v_channels
                if c.get("id")
                and c.get("name", "") != self._HIDDEN_CHANNEL_SENTINEL
            ]
            joinable.sort(key=lambda c: c.get("position", 0))

            if joinable:
                result_guilds.append({
                    "id": str(g_id),
                    "name": str(g_name),
                    "channels": [
                        {
                            "id": str(c.get("id")),
                            "guildId": str(g_id),
                            "name": str(c.get("name", "Voice Channel")),
                            "position": c.get("position", 0),
                            "userLimit": c.get("userLimit", 0),
                            "memberCount": c.get("memberCount", 0),
                        }
                        for c in joinable
                    ],
                })

        return {
            "ok": True,
            "data": {
                "guilds": result_guilds,
            },
        }

    def get_recent_channels(self) -> Dict[str, Any]:
        recents = self.recents_mgr.get_recents()
        return {
            "ok": True,
            "data": {
                "recents": recents,
            },
        }

    def record_recent_channel(self, guild_id: str, channel_id: str, guild_name: str, channel_name: str) -> Dict[str, Any]:
        success = self.recents_mgr.record_recent(guild_id, channel_id, guild_name, channel_name)
        if success:
            return {
                "ok": True,
                "data": {
                    "recents": self.recents_mgr.get_recents(),
                },
            }
        return {
            "ok": False,
            "error": {
                "code": "PERSISTENCE_ERROR",
                "message": "Failed to record recent channel",
            },
        }

    def clear_recents(self) -> Dict[str, Any]:
        success = self.recents_mgr.clear_recents()
        return {
            "ok": success,
            "data": {
                "recents": [],
            },
        }

    def join_voice_channel(self, channel_id: str, guild_id: Optional[str] = None, guild_name: Optional[str] = None, channel_name: Optional[str] = None) -> Dict[str, Any]:
        if not channel_id or not str(channel_id).strip():
            return {
                "ok": False,
                "error": {
                    "code": "INVALID_FAVORITE",
                    "message": "Invalid channel ID provided for join",
                },
            }

        params = {"channelId": str(channel_id)}
        if guild_id:
            params["guildId"] = str(guild_id)

        res = self._execute_bridge_call("joinVoiceChannel", params)
        if res.get("ok") and guild_id and channel_id:
            # If names are not provided directly, check favorites for matching names
            g_name = guild_name or "Voice Server"
            c_name = channel_name or "Voice Channel"
            for f in self.favorites_mgr.get_favorites():
                if f.get("channel_id") == str(channel_id):
                    g_name = f.get("guild_name", g_name)
                    c_name = f.get("channel_name", c_name)
                    break
            self.recents_mgr.record_recent(str(guild_id), str(channel_id), str(g_name), str(c_name))

        return res

    def leave_voice_channel(self) -> Dict[str, Any]:
        return self._execute_bridge_call("leaveVoiceChannel")

    def set_muted(self, muted: bool) -> Dict[str, Any]:
        return self._execute_bridge_call("setMuted", {"muted": bool(muted)})

    def set_deafened(self, deafened: bool) -> Dict[str, Any]:
        return self._execute_bridge_call("setDeafened", {"deafened": bool(deafened)})

    def get_audio_devices(self) -> Dict[str, Any]:
        return self._execute_bridge_call("getAudioDevices")

    def set_audio_device(self, device_type: str, device_id: str) -> Dict[str, Any]:
        return self._execute_bridge_call("setAudioDevice", {"type": str(device_type), "deviceId": str(device_id)})

    def get_audio_volumes(self) -> Dict[str, Any]:
        return self._execute_bridge_call("getAudioVolumes")

    def set_audio_volume(self, device_type: str, volume: float) -> Dict[str, Any]:
        return self._execute_bridge_call("setAudioVolume", {"type": str(device_type), "volume": float(volume)})

    def get_audio_levels(self) -> Dict[str, Any]:
        return self._execute_bridge_call("getAudioLevels")
