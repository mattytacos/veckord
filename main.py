"""
Deckord Decky Loader Plugin Main Backend Entrypoint.
"""

import os
import sys
import traceback

# Ensure backend directory is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from deckord_backend import DeckordBackend

backend = DeckordBackend()


class Plugin:
    """
    Decky Loader Plugin entrypoint.
    """

    async def _main(self):
        print("[DeckordPlugin] Deckord Decky backend loaded.", flush=True)

    async def _unload(self):
        print("[DeckordPlugin] Deckord Decky backend unloaded.", flush=True)

    async def get_bridge_status(self):
        try:
            return backend.get_bridge_status()
        except Exception as e:
            err_msg = f"Exception in get_bridge_status: {type(e).__name__}: {e}\n{traceback.format_exc()}"
            print(f"[DeckordPlugin] {err_msg}", flush=True)
            return {"ok": False, "error": {"code": "PYTHON_EXCEPTION", "message": err_msg}}

    async def get_current_voice_channel(self):
        return backend.get_current_voice_channel()

    async def get_voice_settings(self):
        return backend.get_voice_settings()

    async def get_favorite_channels(self):
        return backend.get_favorite_channels()

    async def set_favorite_channels(self, favorites):
        print(f"[DeckordPlugin] set_favorite_channels invoked with: {favorites}", flush=True)
        return backend.set_favorite_channels(favorites)

    async def add_favorite(self, guild_id, channel_id, guild_name, channel_name):
        print(f"[DeckordPlugin] add_favorite invoked: {guild_name}/{channel_name}", flush=True)
        return backend.add_favorite(guild_id, channel_id, guild_name, channel_name)

    async def remove_favorite(self, channel_id):
        print(f"[DeckordPlugin] remove_favorite invoked: {channel_id}", flush=True)
        return backend.remove_favorite(channel_id)

    async def move_favorite(self, channel_id, direction):
        print(f"[DeckordPlugin] move_favorite invoked: {channel_id} {direction}", flush=True)
        return backend.move_favorite(channel_id, direction)

    async def get_guilds_and_channels(self):
        print("[DeckordPlugin] get_guilds_and_channels invoked", flush=True)
        return backend.get_guilds_and_channels()

    async def join_voice_channel(self, channel_id, guild_id=None):
        print(f"[DeckordPlugin] join_voice_channel invoked with channel_id={channel_id}, guild_id={guild_id}", flush=True)
        return backend.join_voice_channel(channel_id, guild_id)

    async def leave_voice_channel(self):
        print("[DeckordPlugin] leave_voice_channel invoked", flush=True)
        return backend.leave_voice_channel()

    async def set_muted(self, muted):
        print(f"[DeckordPlugin] set_muted invoked with muted={muted}", flush=True)
        return backend.set_muted(muted)

    async def set_deafened(self, deafened):
        print(f"[DeckordPlugin] set_deafened invoked with deafened={deafened}", flush=True)
        return backend.set_deafened(deafened)
