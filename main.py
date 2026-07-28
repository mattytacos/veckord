"""
Veckord Decky Loader Plugin Main Backend Entrypoint.
"""

import os
import sys
import traceback

# Ensure backend directory is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from veckord_backend import VeckordBackend

backend = VeckordBackend()


class Plugin:
    """
    Decky Loader Plugin entrypoint.
    """

    async def _main(self):
        print("[VeckordPlugin] Veckord Decky backend loaded.", flush=True)

    async def _unload(self):
        print("[VeckordPlugin] Veckord Decky backend unloaded.", flush=True)

    async def get_bridge_status(self):
        try:
            return backend.get_bridge_status()
        except Exception as e:
            err_msg = f"Exception in get_bridge_status: {type(e).__name__}: {e}\n{traceback.format_exc()}"
            print(f"[VeckordPlugin] {err_msg}", flush=True)
            return {"ok": False, "error": {"code": "PYTHON_EXCEPTION", "message": err_msg}}

    async def get_current_voice_channel(self):
        return backend.get_current_voice_channel()

    async def get_voice_settings(self):
        return backend.get_voice_settings()

    async def get_favorite_channels(self):
        return backend.get_favorite_channels()

    async def set_favorite_channels(self, favorites):
        print(f"[VeckordPlugin] set_favorite_channels invoked with: {favorites}", flush=True)
        return backend.set_favorite_channels(favorites)

    async def add_favorite(self, guild_id, channel_id, guild_name, channel_name):
        print(f"[VeckordPlugin] add_favorite invoked: {guild_name}/{channel_name}", flush=True)
        return backend.add_favorite(guild_id, channel_id, guild_name, channel_name)

    async def remove_favorite(self, channel_id):
        print(f"[VeckordPlugin] remove_favorite invoked: {channel_id}", flush=True)
        return backend.remove_favorite(channel_id)

    async def move_favorite(self, channel_id, direction):
        print(f"[VeckordPlugin] move_favorite invoked: {channel_id} {direction}", flush=True)
        return backend.move_favorite(channel_id, direction)

    async def get_recent_channels(self):
        return backend.get_recent_channels()

    async def record_recent_channel(self, guild_id, channel_id, guild_name, channel_name):
        return backend.record_recent_channel(guild_id, channel_id, guild_name, channel_name)

    async def clear_recents(self):
        return backend.clear_recents()

    async def get_guilds_and_channels(self):
        print("[VeckordPlugin] get_guilds_and_channels invoked", flush=True)
        return backend.get_guilds_and_channels()

    async def join_voice_channel(self, channel_id, guild_id=None, guild_name=None, channel_name=None):
        print(f"[VeckordPlugin] join_voice_channel invoked with channel_id={channel_id}, guild_id={guild_id}", flush=True)
        return backend.join_voice_channel(channel_id, guild_id, guild_name, channel_name)

    async def leave_voice_channel(self):
        print("[VeckordPlugin] leave_voice_channel invoked", flush=True)
        return backend.leave_voice_channel()

    async def set_muted(self, muted):
        print(f"[VeckordPlugin] set_muted invoked with muted={muted}", flush=True)
        return backend.set_muted(muted)

    async def set_deafened(self, deafened):
        print(f"[VeckordPlugin] set_deafened invoked with deafened={deafened}", flush=True)
        return backend.set_deafened(deafened)

    async def get_audio_devices(self):
        return backend.get_audio_devices()

    async def set_audio_device(self, device_type, device_id):
        print(f"[VeckordPlugin] set_audio_device invoked: {device_type} -> {device_id}", flush=True)
        return backend.set_audio_device(device_type, device_id)

    async def get_audio_volumes(self):
        return backend.get_audio_volumes()

    async def set_audio_volume(self, device_type, volume):
        print(f"[VeckordPlugin] set_audio_volume invoked: {device_type} -> {volume}", flush=True)
        return backend.set_audio_volume(device_type, volume)

    async def get_audio_levels(self):
        return backend.get_audio_levels()
