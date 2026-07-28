"""
Veckord Persistence Helpers.

Stateless functions for resolving settings file paths, performing atomic JSON writes,
and safely loading JSON data.
"""

import os
import json
import tempfile
from typing import Any, Optional


def atomic_write_content(file_path: str, content: str) -> bool:
    """
    Atomically write string content to file_path using a temporary file and os.replace.
    Returns True on success, False on failure.
    """
    try:
        parent_dir = os.path.dirname(file_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, mode=0o700, exist_ok=True)

        temp_fd, temp_path = tempfile.mkstemp(dir=parent_dir or ".", prefix=".tmp_veckord_")
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(temp_path, file_path)
            return True
        except Exception as write_err:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise write_err
    except Exception as e:
        print(f"[VeckordPersistence] Write error ({file_path}): {e}")
        return False


def atomic_write_json(file_path: str, data: Any, indent: int = 2) -> bool:
    """
    Atomically serialize and write data to file_path as JSON.
    Returns True on success, False on failure.
    """
    try:
        serialized = json.dumps(data, indent=indent)
        return atomic_write_content(file_path, serialized)
    except Exception as e:
        print(f"[VeckordPersistence] JSON serialization error ({file_path}): {e}")
        return False


def resolve_persistence_path(filename: str) -> str:
    """
    Resolve settings file path with Decky environment support, legacy migration,
    and fallback handling.
    """
    decky_settings = os.environ.get("DECKY_PLUGIN_SETTINGS_DIR")
    if decky_settings and os.path.exists(decky_settings):
        return os.path.join(decky_settings, filename)

    home = os.environ.get("HOME") or os.path.expanduser("~")
    primary_dir = os.path.join(home, ".config", "veckord")
    legacy_dir = os.path.join(home, ".config", "deckord")
    primary_file = os.path.join(primary_dir, filename)
    legacy_file = os.path.join(legacy_dir, filename)

    if os.path.exists(primary_file):
        return primary_file
    elif os.path.exists(legacy_file):
        # Auto-migrate legacy file to primary directory
        try:
            os.makedirs(primary_dir, mode=0o700, exist_ok=True)
            with open(legacy_file, "r", encoding="utf-8") as f_old:
                data = f_old.read()
            if atomic_write_content(primary_file, data):
                return primary_file
            return legacy_file
        except Exception:
            return legacy_file

    if not os.path.exists(primary_dir):
        try:
            os.makedirs(primary_dir, mode=0o700, exist_ok=True)
        except Exception:
            pass

    return primary_file


def load_json_data(file_path: str) -> Optional[Any]:
    """
    Safely load JSON data from file_path.
    Returns None if file does not exist or read/parse fails.
    """
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[VeckordPersistence] Read error ({file_path}): {e}")
        return None
