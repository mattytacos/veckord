#!/usr/bin/env python3
"""
Veckord Installer v1

Installs, updates, repairs, and checks the Veckord Decky Loader plugin
and its Vesktop/Vencord bridge on Bazzite (Flatpak Vesktop only).

Usage:
    python3 install.py [--tag TAG] {check,install,update,repair}

Requirements:
    - Python 3.8+
    - Bazzite OS (ID=bazzite in /etc/os-release)
    - dev.vencord.Vesktop Flatpak
    - Decky Loader (plugin_loader.service)
    - Run as a normal user (not root)

Release assets expected at:
    https://github.com/mattytacos/veckord/releases/download/{tag}/veckord.zip
    https://github.com/mattytacos/veckord/releases/download/{tag}/vencord-dist.zip
    https://github.com/mattytacos/veckord/releases/download/{tag}/checksums.sha256
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
INSTALLER_VERSION = "1.0.3"

# ---------------------------------------------------------------------------
# Dynamic base paths — NEVER hardcoded
# ---------------------------------------------------------------------------
HOME: Path = Path.home()
UID: int = os.getuid()
RUNTIME_DIR: Path = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{UID}"))

DECKY_PLUGINS_ROOT: Path = HOME / "homebrew" / "plugins"
DECKY_PLUGIN_DIR: Path = DECKY_PLUGINS_ROOT / "Deckord"  # filesystem dir — do NOT rename
VESKTOP_CONFIG: Path = HOME / ".var" / "app" / "dev.vencord.Vesktop" / "config" / "vesktop"
MANAGED_ROOT: Path = HOME / ".local" / "share" / "veckord"
MANAGED_VENCORD_DIR: Path = MANAGED_ROOT / "vencord"

BRIDGE_SOCKET_DECKORD: Path = RUNTIME_DIR / "deckord" / "bridge.sock"
BRIDGE_SOCKET_VECKORD: Path = RUNTIME_DIR / "veckord" / "bridge.sock"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GITHUB_REPO = "mattytacos/veckord"
VESKTOP_FLATPAK_ID = "dev.vencord.Vesktop"
DECKY_SERVICE = "plugin_loader.service"
PLUGIN_DIR_NAME = "Deckord"        # filesystem dir name — immutable
PLUGIN_DISPLAY_NAME = "Veckord"   # display name in plugin.json

# All Vencord plugin setting keys to enable (covers old compiled + new source names)
VENCORD_PLUGIN_KEYS: List[str] = ["VeckordBridge", "DeckordBridge", "deckordBridge"]

# Minimum Flatpak filesystem entries required (MANAGED_VENCORD_DIR:ro added at install time)
FLATPAK_REQUIRED_FILESYSTEMS: List[str] = [
    "xdg-run/deckord:create",
    "xdg-run/veckord:create",
]

DOWNLOAD_TIMEOUT = 60  # seconds
BRIDGE_PING_TIMEOUT = 3.0  # seconds
BRIDGE_WAIT_MAX = 60  # seconds to wait for bridge after install

# Flatpak override file location
FLATPAK_OVERRIDE_FILE: Path = HOME / ".local" / "share" / "flatpak" / "overrides" / VESKTOP_FLATPAK_ID

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class InstallerError(Exception):
    """Raised when the installer encounters an unrecoverable error."""
    pass


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
_COL_W = 72


def _status(label: str, description: str, detail: str = "") -> None:
    colour = {
        "PASS": "\033[32m",
        "WARNING": "\033[33m",
        "FAIL": "\033[31m",
        "ACTION REQUIRED": "\033[36m",
        "INFO": "\033[0m",
    }.get(label, "\033[0m")
    reset = "\033[0m"
    tag = f"[{label}]"
    line = f"  {colour}{tag:17s}{reset} {description}"
    if detail:
        line += f" — {detail}"
    print(line)


def _section(title: str) -> None:
    print(f"\n--- {title} ---")


def _info(msg: str) -> None:
    print(f"  {msg}")


def _ask(prompt: str) -> str:
    try:
        return input(f"\n  {prompt} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "n"


# ---------------------------------------------------------------------------
# Rollback context
# ---------------------------------------------------------------------------

class RollbackContext:
    """Tracks installed items for rollback on failure."""

    def __init__(self) -> None:
        self._actions: List[Callable[[], None]] = []

    def register(self, undo_fn: Callable[[], None]) -> None:
        self._actions.append(undo_fn)

    def rollback(self) -> None:
        print("\n  Rolling back changes...")
        for fn in reversed(self._actions):
            try:
                fn()
            except Exception as e:
                print(f"  Rollback step failed (continuing): {e}")


# ---------------------------------------------------------------------------
# System detection
# ---------------------------------------------------------------------------

def is_bazzite() -> bool:
    """Return True if running on Bazzite."""
    try:
        text = Path("/etc/os-release").read_text()
        for line in text.splitlines():
            if line.startswith("ID=") and line.split("=", 1)[1].strip().strip('"') == "bazzite":
                return True
    except OSError:
        pass
    return False


def is_vesktop_installed() -> bool:
    """Return True if dev.vencord.Vesktop is installed as a Flatpak."""
    try:
        result = subprocess.run(
            ["flatpak", "info", VESKTOP_FLATPAK_ID],
            capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_vesktop_version() -> Optional[str]:
    """Return the installed Vesktop Flatpak version string, or None."""
    try:
        result = subprocess.run(
            ["flatpak", "info", VESKTOP_FLATPAK_ID],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            if "Version:" in line:
                return line.split("Version:", 1)[1].strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def is_vesktop_running() -> bool:
    """Return True if a Vesktop Flatpak process is currently running."""
    try:
        result = subprocess.run(
            ["flatpak", "ps"],
            capture_output=True, text=True, timeout=10,
        )
        return VESKTOP_FLATPAK_ID in result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def is_decky_installed() -> bool:
    """Return True if the Decky Loader binary exists."""
    loader = HOME / "homebrew" / "services" / "PluginLoader"
    return loader.exists()


def get_decky_service_active() -> bool:
    """Return True if plugin_loader.service is currently active."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", DECKY_SERVICE],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() == "active"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_plugin_info() -> Tuple[Optional[str], Optional[str]]:
    """Return (version, display_name) from DECKY_PLUGIN_DIR, or (None, None)."""
    pkg_path = DECKY_PLUGIN_DIR / "package.json"
    plugin_path = DECKY_PLUGIN_DIR / "plugin.json"
    version = None
    display_name = None
    if pkg_path.exists():
        try:
            version = json.loads(pkg_path.read_text()).get("version")
        except (json.JSONDecodeError, OSError):
            pass
    if plugin_path.exists():
        try:
            display_name = json.loads(plugin_path.read_text()).get("name")
        except (json.JSONDecodeError, OSError):
            pass
    return version, display_name


def check_duplicate_plugin_dirs() -> bool:
    """Return True if BOTH Deckord/ and Veckord/ exist under DECKY_PLUGINS_ROOT."""
    deckord = DECKY_PLUGINS_ROOT / "Deckord"
    veckord = DECKY_PLUGINS_ROOT / "Veckord"
    return deckord.exists() and veckord.exists()


def is_symlink_target(path: Path) -> bool:
    """Return True if the path is a symlink."""
    return path.is_symlink()


def get_managed_vencord_ok() -> bool:
    """Return True if MANAGED_VENCORD_DIR exists and contains patcher.js."""
    return (MANAGED_VENCORD_DIR / "patcher.js").exists()


# ---------------------------------------------------------------------------
# state.json — vencordDir
# ---------------------------------------------------------------------------

def _state_path() -> Path:
    return VESKTOP_CONFIG / "state.json"


def _read_state() -> Dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_state(state: Dict[str, Any]) -> None:
    """Atomically write state.json."""
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=4))
    tmp.replace(path)


def read_vencord_dir() -> Optional[str]:
    """Return the vencordDir value from state.json, or None."""
    return _read_state().get("vencordDir")


def write_vencord_dir(new_path: str) -> None:
    """Set vencordDir in state.json atomically."""
    state = _read_state()
    state["vencordDir"] = new_path
    _write_state(state)


def repair_vencord_dir() -> None:
    """Update vencordDir to point to MANAGED_VENCORD_DIR if it is wrong or missing."""
    write_vencord_dir(str(MANAGED_VENCORD_DIR))


# ---------------------------------------------------------------------------
# settings/settings.json — plugin enablement
# ---------------------------------------------------------------------------

def _settings_path() -> Path:
    return VESKTOP_CONFIG / "settings" / "settings.json"


def _read_settings() -> Dict[str, Any]:
    path = _settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_settings(settings: Dict[str, Any]) -> None:
    """Atomically write settings.json."""
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, indent=4))
    tmp.replace(path)


def enable_vencord_plugins() -> None:
    """Enable all VENCORD_PLUGIN_KEYS in Vencord settings.json."""
    settings = _read_settings()
    plugins = settings.setdefault("plugins", {})
    for key in VENCORD_PLUGIN_KEYS:
        plugins.setdefault(key, {})["enabled"] = True
    _write_settings(settings)


def disable_vencord_plugins() -> None:
    """Disable all VENCORD_PLUGIN_KEYS in Vencord settings.json."""
    settings = _read_settings()
    plugins = settings.get("plugins", {})
    for key in VENCORD_PLUGIN_KEYS:
        if key in plugins:
            plugins[key]["enabled"] = False
    _write_settings(settings)


def get_vencord_plugin_states() -> Dict[str, Optional[bool]]:
    """Return {key: enabled|None} for each key in VENCORD_PLUGIN_KEYS."""
    plugins = _read_settings().get("plugins", {})
    return {
        key: plugins[key].get("enabled") if key in plugins else None
        for key in VENCORD_PLUGIN_KEYS
    }


# ---------------------------------------------------------------------------
# Flatpak override file management
# ---------------------------------------------------------------------------

def _read_flatpak_overrides() -> Dict[str, List[str]]:
    """Parse the Flatpak override file. Returns {section: [raw_entries]}."""
    sections: Dict[str, List[str]] = {}
    if not FLATPAK_OVERRIDE_FILE.exists():
        return sections
    current_section: Optional[str] = None
    for raw_line in FLATPAK_OVERRIDE_FILE.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1]
            sections.setdefault(current_section, [])
        elif "=" in line and current_section is not None:
            sections.setdefault(current_section, []).append(line)
    return sections


def _write_flatpak_overrides(sections: Dict[str, List[str]]) -> None:
    """Atomically write the Flatpak override file from sections dict."""
    FLATPAK_OVERRIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for section, entries in sections.items():
        lines.append(f"[{section}]")
        for entry in entries:
            lines.append(entry)
    text = "\n".join(lines) + "\n"
    tmp = FLATPAK_OVERRIDE_FILE.with_suffix(".tmp")
    tmp.write_text(text)
    tmp.replace(FLATPAK_OVERRIDE_FILE)


def _get_context_filesystems() -> List[str]:
    """Return the list of filesystem entries in [Context] filesystems=."""
    sections = _read_flatpak_overrides()
    for entry in sections.get("Context", []):
        if entry.startswith("filesystems="):
            raw = entry[len("filesystems="):]
            # Split by semicolon, filter empty strings
            return [f for f in raw.split(";") if f]
    return []


def _set_context_filesystems(entries: List[str]) -> None:
    """Write filesystem entries back to the Flatpak override file."""
    sections = _read_flatpak_overrides()
    sections.setdefault("Context", [])
    # Remove existing filesystems= line
    sections["Context"] = [e for e in sections["Context"] if not e.startswith("filesystems=")]
    if entries:
        sections["Context"].append("filesystems=" + ";".join(entries) + ";")
    _write_flatpak_overrides(sections)


def has_flatpak_filesystem(entry: str) -> bool:
    """Return True if the exact filesystem entry is present."""
    return entry in _get_context_filesystems()


def ensure_flatpak_filesystem(entry: str) -> None:
    """Add a filesystem entry to the Flatpak override if not already present."""
    entries = _get_context_filesystems()
    if entry not in entries:
        entries.append(entry)
        _set_context_filesystems(entries)


def remove_flatpak_filesystem(entry: str) -> None:
    """Remove a specific filesystem entry from the Flatpak override."""
    entries = _get_context_filesystems()
    new_entries = [e for e in entries if e != entry]
    if new_entries != entries:
        _set_context_filesystems(new_entries)


def ensure_all_flatpak_filesystems() -> None:
    """Ensure all required filesystem overrides are present."""
    for fs in FLATPAK_REQUIRED_FILESYSTEMS:
        ensure_flatpak_filesystem(fs)
    vencord_entry = str(MANAGED_VENCORD_DIR) + ":ro"
    ensure_flatpak_filesystem(vencord_entry)


# ---------------------------------------------------------------------------
# ZIP security
# ---------------------------------------------------------------------------

def validate_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    """
    Raise ValueError if the archive contains any unsafe members:
    - Path traversal (member resolves outside dest)
    - Absolute paths
    - Unix symlinks
    """
    dest_resolved = dest.resolve()
    for info in zf.infolist():
        # Symlink detection: Unix mode stored in high 16 bits of external_attr
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(unix_mode):
            raise ValueError(f"Symlink in archive rejected: {info.filename!r}")
        member_path = Path(info.filename)
        if member_path.is_absolute():
            raise ValueError(f"Absolute path in archive rejected: {info.filename!r}")
        # Resolve to check traversal (handles ..)
        target = (dest / info.filename).resolve()
        if not str(target).startswith(str(dest_resolved)):
            raise ValueError(f"Path traversal in archive rejected: {info.filename!r}")


# ---------------------------------------------------------------------------
# Checksum verification
# ---------------------------------------------------------------------------

def verify_checksum(file_path: Path, expected_hex: str) -> None:
    """Raise InstallerError if the SHA-256 of file_path does not match expected_hex."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual.lower() != expected_hex.lower():
        raise InstallerError(
            f"Checksum mismatch for {file_path.name}:\n"
            f"  Expected: {expected_hex}\n"
            f"  Got:      {actual}"
        )


def parse_checksums(checksums_text: str) -> Dict[str, str]:
    """Parse a sha256sum-format file into {filename: hex_digest}."""
    result: Dict[str, str] = {}
    for line in checksums_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            hex_digest, filename = parts
            result[filename.lstrip("*").strip()] = hex_digest.strip()
    return result


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _github_url(tag: str, asset: str) -> str:
    return f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/{asset}"


def _download_file(url: str, dest: Path) -> None:
    """Download url to dest with progress dots. No curl|bash."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"veckord-installer/{INSTALLER_VERSION}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
            if resp.status == 404:
                raise InstallerError(
                    f"Asset not found (HTTP 404): {url}\n"
                    f"  The release asset may not have been published yet.\n"
                    f"  Run 'scripts/build_release.py' and publish a new release."
                )
            if resp.status != 200:
                raise InstallerError(f"HTTP {resp.status} downloading {url}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            downloaded = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(102400)  # 100 KB
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if downloaded % (100 * 1024) < len(chunk):
                        print(".", end="", flush=True)
            print()  # newline after dots
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise InstallerError(
                f"Asset not found (HTTP 404): {url}\n"
                f"  This release asset has not been published yet.\n"
                f"  The vencord-dist.zip must be built and added to the GitHub release.\n"
                f"  See INSTALL.md for instructions."
            )
        raise InstallerError(f"HTTP error {e.code} downloading {url}: {e}")
    except urllib.error.URLError as e:
        raise InstallerError(f"Network error downloading {url}: {e}")


def download_release_assets(tag: str) -> Path:
    """
    Download checksums.sha256, veckord.zip, vencordBridge.zip, and vencord-dist.zip for the
    given tag into MANAGED_ROOT/downloads/{tag}/.
    Returns the download directory path.
    """
    dl_dir = MANAGED_ROOT / "downloads" / tag
    dl_dir.mkdir(parents=True, exist_ok=True)

    assets = ["checksums.sha256", "install.py", "veckord.zip", "vencordBridge.zip", "vencord-dist.zip"]
    for asset in assets:
        dest = dl_dir / asset
        if dest.exists():
            _info(f"  Using cached {asset}")
        else:
            print(f"  Downloading {asset} ", end="", flush=True)
            _download_file(_github_url(tag, asset), dest)
    return dl_dir


def verify_release_checksums(dl_dir: Path) -> Dict[str, str]:
    """
    Verify checksums.sha256 file and all required assets before extraction.
    Fails closed immediately if checksum file or any asset is missing or corrupted.
    """
    cs_file = dl_dir / "checksums.sha256"
    if not cs_file.exists():
        raise InstallerError("Missing checksums.sha256 file in release downloads.")

    checksums = parse_checksums(cs_file.read_text())
    required_assets = ["veckord.zip", "vencordBridge.zip", "vencord-dist.zip"]
    if "install.py" in checksums:
        required_assets.insert(0, "install.py")

    for asset in required_assets:
        if asset not in checksums:
            raise InstallerError(f"Required release asset {asset} missing from checksums.sha256 manifest.")
        asset_file = dl_dir / asset
        if not asset_file.exists():
            raise InstallerError(f"Required release asset file missing: {asset}")
        verify_checksum(asset_file, checksums[asset])
        _status("PASS", f"Checksum OK: {asset}")

    return checksums


# ---------------------------------------------------------------------------
# Atomic directory replacement
# ---------------------------------------------------------------------------

def atomic_replace_dir(
    src: Path,
    dest: Path,
    backup: Optional[Path] = None,
) -> Optional[Path]:
    """
    Replace dest with src atomically.
    If backup is given and dest exists, move dest to backup first.
    Returns the actual backup path used, or None.
    """
    actual_backup: Optional[Path] = None
    if dest.exists() and backup is not None:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest), str(backup))
        actual_backup = backup
    elif dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(src), str(dest))
    return actual_backup


# ---------------------------------------------------------------------------
# sudo helper & preflight
# ---------------------------------------------------------------------------

def check_sudo_preflight(interactive: bool) -> None:
    """Verify that sudo authentication is available before starting any modifications."""
    if not _decky_plugin_dir_needs_sudo():
        return

    _info("Checking sudo authorization for Decky Loader plugin directory operations...")
    cmd = ["sudo", "-n", "v"] if not interactive else ["sudo", "-v"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            if not interactive:
                raise InstallerError(
                    "Sudo authorization is required to modify the Decky Loader plugins directory,\n"
                    "but cached sudo credentials are not available in non-interactive mode.\n"
                    "Please run interactively or refresh sudo timestamp first with 'sudo -v'."
                )
            else:
                raise InstallerError("Sudo authentication failed or was cancelled.")
    except FileNotFoundError:
        raise InstallerError("sudo command is not available on this system.")


def run_sudo(*args: str) -> None:
    """Run a targeted command with sudo (never shell=True). Raises InstallerError on failure."""
    cmd = ["sudo"] + list(args)
    _info(f"Executing privileged action: {' '.join(cmd)}")
    result = subprocess.run(cmd, timeout=60, capture_output=True, text=True)
    if result.returncode != 0:
        err = result.stderr.strip() if result.stderr else f"exit code {result.returncode}"
        raise InstallerError(f"Privileged action failed ({' '.join(cmd)}): {err}")


# ---------------------------------------------------------------------------
# Bridge ping
# ---------------------------------------------------------------------------

def ping_bridge(socket_path: Path, timeout: float = BRIDGE_PING_TIMEOUT) -> bool:
    """
    Return True if the bridge at socket_path responds to a JSON ping.
    Returns False on any error (connection refused, timeout, bad response).
    """
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(str(socket_path))
        req_id = str(uuid.uuid4())
        payload = json.dumps({
            "version": 1,
            "id": req_id,
            "method": "ping",
            "params": {},
        }) + "\n"
        sock.sendall(payload.encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                return False
            buf += chunk
        line = buf.split(b"\n")[0]
        resp = json.loads(line.decode("utf-8"))
        sock.close()
        return resp.get("ok") is True
    except Exception:
        return False


def find_active_bridge_socket() -> Optional[Path]:
    """Return the first bridge socket that exists (prefer veckord, fall back to deckord)."""
    for path in [BRIDGE_SOCKET_VECKORD, BRIDGE_SOCKET_DECKORD]:
        if path.exists():
            return path
    return None


# ---------------------------------------------------------------------------
# Vencord-dist ZIP extraction
# ---------------------------------------------------------------------------

def _extract_vencord_dist(zip_path: Path, dest: Path) -> None:
    """
    Extract vencord-dist.zip to dest.
    Handles both layouts:
      - Files at zip root: patcher.js, renderer.js, ...
      - Files under a dist/ prefix: dist/patcher.js, ...
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        validate_zip(zf, dest)
        # Detect if files are under a single prefix directory
        names = zf.namelist()
        # Find common prefix (if all files share one)
        prefixes = set()
        for name in names:
            parts = name.split("/")
            if len(parts) > 1:
                prefixes.add(parts[0])
            else:
                prefixes.add("")  # file at root

        use_prefix: Optional[str] = None
        if prefixes == {"dist"}:
            use_prefix = "dist/"

        dest.mkdir(parents=True, exist_ok=True)
        for info in zf.infolist():
            name = info.filename
            if use_prefix and name.startswith(use_prefix):
                relative = name[len(use_prefix):]
            else:
                relative = name
            if not relative or relative.endswith("/"):
                continue
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


def _extract_veckord_plugin(zip_path: Path, dest: Path) -> None:
    """Extract veckord.zip to dest (files directly from zip root)."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        validate_zip(zf, dest)
        dest.mkdir(parents=True, exist_ok=True)
        for info in zf.infolist():
            if info.filename.endswith("/"):
                (dest / info.filename).mkdir(parents=True, exist_ok=True)
                continue
            target = dest / info.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


# ---------------------------------------------------------------------------
# Decky plugin installation
# ---------------------------------------------------------------------------

def _decky_plugin_dir_needs_sudo() -> bool:
    """Return True if we need sudo to create or modify the Decky plugin dir."""
    return not os.access(DECKY_PLUGINS_ROOT, os.W_OK)


def validate_staged_plugin(staging_dir: Path) -> None:
    """Validate extracted plugin contents prior to installation."""
    pkg_json = staging_dir / "package.json"
    plugin_json = staging_dir / "plugin.json"
    main_py = staging_dir / "main.py"

    if not plugin_json.exists():
        raise InstallerError("Invalid Decky plugin archive: missing plugin.json")
    if not main_py.exists():
        raise InstallerError("Invalid Decky plugin archive: missing main.py")

    try:
        meta = json.loads(plugin_json.read_text(encoding="utf-8"))
        if meta.get("name") != PLUGIN_DISPLAY_NAME:
            raise InstallerError(f"Invalid plugin.json: expected name '{PLUGIN_DISPLAY_NAME}', got '{meta.get('name')}'")
    except (json.JSONDecodeError, OSError) as e:
        raise InstallerError(f"Failed to parse plugin.json in staged package: {e}")


def _rollback_decky_plugin(backup_path: Optional[Path], needs_sudo: bool) -> None:
    """Roll back Decky plugin directory state upon failure."""
    print("  Rolling back Decky plugin installation...")
    try:
        if DECKY_PLUGIN_DIR.exists():
            if needs_sudo:
                run_sudo("rm", "-rf", str(DECKY_PLUGIN_DIR))
            else:
                shutil.rmtree(DECKY_PLUGIN_DIR, ignore_errors=True)

        if backup_path and backup_path.exists():
            if needs_sudo:
                run_sudo("mv", str(backup_path), str(DECKY_PLUGIN_DIR))
            else:
                backup_path.rename(DECKY_PLUGIN_DIR)
            print(f"  Restored plugin from backup: {backup_path}")
    except Exception as e:
        print(f"  CRITICAL ROLLBACK FAILURE: {e}")
        if backup_path:
            print("  MANUAL RECOVERY INSTRUCTIONS:")
            print(f"    sudo rm -rf {DECKY_PLUGIN_DIR}")
            print(f"    sudo mv {backup_path} {DECKY_PLUGIN_DIR}")
            print(f"    sudo systemctl restart {DECKY_SERVICE}")


def install_decky_plugin(veckord_zip: Path, rollback: RollbackContext) -> Optional[Path]:
    """
    Install/update the Decky plugin from veckord_zip into DECKY_PLUGIN_DIR.
    Uses targeted sudo commands for root-owned directory operations.
    Returns backup_path if a backup was created.
    """
    if is_symlink_target(DECKY_PLUGIN_DIR):
        raise InstallerError(
            f"{DECKY_PLUGIN_DIR} is a symlink. Remove it manually before installing."
        )

    # 1. Extract and validate in user-owned temporary staging dir
    staging_dir = Path(tempfile.mkdtemp(prefix="veckord_staging_"))
    try:
        _extract_veckord_plugin(veckord_zip, staging_dir)
        validate_staged_plugin(staging_dir)

        backup_path: Optional[Path] = None
        needs_sudo = _decky_plugin_dir_needs_sudo()

        # 2. Atomic backup on the SAME filesystem inside DECKY_PLUGINS_ROOT
        if DECKY_PLUGIN_DIR.exists():
            backup_name = f".veckord-backup-{time.strftime('%Y%m%d_%H%M%S')}"
            backup_path = DECKY_PLUGINS_ROOT / backup_name

            if needs_sudo:
                run_sudo("mv", str(DECKY_PLUGIN_DIR), str(backup_path))
            else:
                DECKY_PLUGIN_DIR.rename(backup_path)

            _info(f"Created atomic backup at {backup_path}")

        # 3. Create fresh plugin directory & copy staged files
        try:
            if needs_sudo:
                run_sudo("mkdir", "-p", str(DECKY_PLUGIN_DIR))
                run_sudo("cp", "-a", f"{str(staging_dir)}/.", str(DECKY_PLUGIN_DIR))
            else:
                DECKY_PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
                for item in staging_dir.iterdir():
                    dst = DECKY_PLUGIN_DIR / item.name
                    if item.is_dir():
                        shutil.copytree(str(item), str(dst))
                    else:
                        shutil.copy2(str(item), str(dst))
        except Exception as e:
            # Failed during creation/copy -> restore backup immediately
            _rollback_decky_plugin(backup_path, needs_sudo)
            raise InstallerError(f"Failed to write plugin files into {DECKY_PLUGIN_DIR}: {e}")

        # 4. Register rollback function in case subsequent install steps fail
        rollback.register(lambda bp=backup_path, ns=needs_sudo: _rollback_decky_plugin(bp, ns))
        _status("PASS", "Decky plugin installed", str(DECKY_PLUGIN_DIR))
        return backup_path
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def update_decky_plugin(veckord_zip: Path, rollback: RollbackContext) -> Optional[Path]:
    """Update the Decky plugin files (preserving favorites which live outside the plugin dir)."""
    return install_decky_plugin(veckord_zip, rollback)


def verify_vencord_dist_metadata(dist_dir: Path) -> Optional[Dict[str, Any]]:
    """Read and verify build-metadata.json in dist_dir if present."""
    meta_path = dist_dir / "build-metadata.json"
    if not meta_path.exists():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        min_ver = data.get("min_installer_version")
        if min_ver:
            def parse_v(v: str) -> Tuple[int, ...]:
                return tuple(int(x) for x in re.findall(r"\d+", v))
            if parse_v(INSTALLER_VERSION) < parse_v(min_ver):
                raise InstallerError(
                    f"Installer version v{INSTALLER_VERSION} is outdated.\n"
                    f"This release requires installer version >= v{min_ver}."
                )
        return data
    except (json.JSONDecodeError, OSError) as e:
        raise InstallerError(f"Failed to parse build-metadata.json: {e}")


def install_managed_vencord(vencord_dist_zip: Path, rollback: RollbackContext) -> None:
    """Install the pre-built Vencord distribution to MANAGED_VENCORD_DIR."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="veckord_vencord_"))
    try:
        _extract_vencord_dist(vencord_dist_zip, tmp_dir)
        verify_vencord_dist_metadata(tmp_dir)

        # Backup existing if present
        backup_path = None
        if MANAGED_VENCORD_DIR.exists():
            backup_path = MANAGED_ROOT / "backups" / f"vencord_{time.strftime('%Y%m%d_%H%M%S')}"
            shutil.move(str(MANAGED_VENCORD_DIR), str(backup_path))
            rollback.register(lambda bp=backup_path: _restore_managed_vencord(bp))

        MANAGED_VENCORD_DIR.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_dir), str(MANAGED_VENCORD_DIR))
        rollback.register(lambda: _remove_managed_vencord(backup_path))
        _status("PASS", "Managed Vencord distribution installed", str(MANAGED_VENCORD_DIR))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _restore_managed_vencord(backup_path: Path) -> None:
    if MANAGED_VENCORD_DIR.exists():
        shutil.rmtree(MANAGED_VENCORD_DIR)
    if backup_path.exists():
        shutil.move(str(backup_path), str(MANAGED_VENCORD_DIR))


def _remove_managed_vencord(backup_path: Optional[Path]) -> None:
    if MANAGED_VENCORD_DIR.exists():
        shutil.rmtree(MANAGED_VENCORD_DIR, ignore_errors=True)
    if backup_path and backup_path.exists():
        shutil.move(str(backup_path), str(MANAGED_VENCORD_DIR))


# ---------------------------------------------------------------------------
# pre-flight guards
# ---------------------------------------------------------------------------

def _assert_not_root() -> None:
    if os.getuid() == 0:
        raise InstallerError(
            "Do not run the installer as root. Run as your normal user account.\n"
            "The installer uses targeted sudo only for the operations that require it."
        )


def _assert_bazzite() -> None:
    if not is_bazzite():
        raise InstallerError(
            "This installer only supports Bazzite. "
            "Detected OS is not Bazzite (ID != 'bazzite' in /etc/os-release)."
        )


def _assert_vesktop() -> None:
    if not is_vesktop_installed():
        raise InstallerError(
            f"Vesktop Flatpak ({VESKTOP_FLATPAK_ID}) is not installed.\n"
            f"Install it with: flatpak install flathub {VESKTOP_FLATPAK_ID}"
        )


def _assert_decky() -> None:
    if not is_decky_installed():
        raise InstallerError(
            "Decky Loader is not installed. "
            "Install it from https://decky.xyz before running this installer."
        )


def _maybe_ask_stop_vesktop(interactive: bool) -> None:
    """Warn if Vesktop is running; ask user to stop it (never kill without asking)."""
    if not is_vesktop_running():
        return
    _status("WARNING", "Vesktop is currently running")
    _info("The installer must write to Vesktop config files while Vesktop is stopped.")
    if interactive:
        answer = _ask("Close Vesktop now and continue?")
        if answer != "y":
            raise InstallerError(
                "Installation cancelled. Please close Vesktop and run the installer again."
            )
        # Wait for Vesktop to close
        for _ in range(30):
            time.sleep(1)
            if not is_vesktop_running():
                _info("Vesktop has closed. Continuing...")
                return
        raise InstallerError(
            "Vesktop is still running after 30 seconds. Please close it manually."
        )
    else:
        # Non-interactive mode: fail with guidance
        raise InstallerError(
            "Vesktop is running. Stop it with:\n"
            "  flatpak kill dev.vencord.Vesktop\n"
            "Then re-run the installer."
        )


def _determine_tag(tag_arg: Optional[str]) -> str:
    """Resolve the release tag. If not given, derive from installed package.json."""
    if tag_arg:
        return tag_arg
    pkg = DECKY_PLUGIN_DIR / "package.json"
    if pkg.exists():
        try:
            version = json.loads(pkg.read_text()).get("version", "")
            if version:
                return f"v{version}"
        except (json.JSONDecodeError, OSError):
            pass
    # Fallback to the installer's own version
    return f"v{INSTALLER_VERSION}"


def _wait_for_bridge(timeout: int = BRIDGE_WAIT_MAX) -> bool:
    """Wait for the bridge socket to appear and respond. Returns True if ping succeeds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        sock = find_active_bridge_socket()
        if sock and ping_bridge(sock):
            return True
        time.sleep(2)
    return False


# ---------------------------------------------------------------------------
# cmd_check
# ---------------------------------------------------------------------------

def cmd_check() -> int:
    """Report the full system status. Returns 0 if all PASS, 1 otherwise."""
    has_fail = False

    print(f"\nVeckord Installer {INSTALLER_VERSION} — System Check")
    print("=" * _COL_W)

    # --- Environment ---
    _section("Environment")
    uid = os.getuid()
    username = os.environ.get("USER", str(uid))

    if uid == 0:
        _status("FAIL", f"Running as root (uid=0) — must run as a normal user")
        has_fail = True
    else:
        _status("PASS", f"Running as user '{username}' (uid={uid})")

    if is_bazzite():
        _status("PASS", "Bazzite OS detected")
    else:
        _status("FAIL", "Not running on Bazzite (ID != 'bazzite')")
        has_fail = True

    # --- Vesktop ---
    _section("Vesktop")
    if is_vesktop_installed():
        ver = get_vesktop_version() or "unknown"
        _status("PASS", f"Flatpak {VESKTOP_FLATPAK_ID} installed", f"v{ver}")
    else:
        _status("FAIL", f"Flatpak {VESKTOP_FLATPAK_ID} NOT installed")
        has_fail = True

    if is_vesktop_running():
        _status("WARNING", "Vesktop is currently running (must be closed for config changes)")
    else:
        _status("PASS", "Vesktop is not running")

    # --- Decky ---
    _section("Decky Loader")
    if is_decky_installed():
        _status("PASS", "Decky Loader binary present")
    else:
        _status("FAIL", "Decky Loader NOT installed")
        has_fail = True

    if get_decky_service_active():
        _status("PASS", f"{DECKY_SERVICE} is active (running)")
    else:
        _status("FAIL", f"{DECKY_SERVICE} is NOT active")
        has_fail = True

    # --- Plugin ---
    _section("Veckord Decky Plugin")
    if DECKY_PLUGIN_DIR.exists():
        version, display_name = get_plugin_info()
        _status(
            "PASS",
            f"Plugin directory exists: {DECKY_PLUGIN_DIR}",
            f"v{version or 'unknown'}, name={display_name or 'unknown'}",
        )
        if display_name and display_name != PLUGIN_DISPLAY_NAME:
            _status("WARNING", f"Display name is '{display_name}', expected '{PLUGIN_DISPLAY_NAME}'")
        if is_symlink_target(DECKY_PLUGIN_DIR):
            _status("WARNING", "Plugin directory is a symlink — unexpected")
    else:
        _status("FAIL", f"Plugin directory NOT found: {DECKY_PLUGIN_DIR}")
        has_fail = True

    if check_duplicate_plugin_dirs():
        veckord_path = DECKY_PLUGINS_ROOT / "Veckord"
        _status(
            "FAIL",
            f"Duplicate plugin directories detected!",
            f"Both Deckord/ and Veckord/ exist — Decky will load both",
        )
        _info(f"  Remove one: rm -rf {veckord_path}")
        has_fail = True
    else:
        _status("PASS", "No duplicate plugin directories")

    # --- Managed Vencord ---
    _section("Managed Vencord Distribution")
    if get_managed_vencord_ok():
        _status("PASS", "Managed Vencord dir present and has patcher.js", str(MANAGED_VENCORD_DIR))
    else:
        _status("FAIL", "Managed Vencord dir missing or incomplete", str(MANAGED_VENCORD_DIR))
        has_fail = True

    # state.json vencordDir
    current_vencord_dir = read_vencord_dir()
    if current_vencord_dir is None:
        _status("FAIL", "state.json: vencordDir not set — Vesktop uses auto-updated bundled Vencord")
        has_fail = True
    elif not Path(current_vencord_dir).exists():
        _status(
            "FAIL",
            "state.json: vencordDir points to a non-existent path",
            current_vencord_dir,
        )
        has_fail = True
    elif current_vencord_dir == str(MANAGED_VENCORD_DIR):
        _status("PASS", "state.json: vencordDir → managed Vencord dir")
    else:
        _status(
            "WARNING",
            "state.json: vencordDir is set but not the installer-managed path",
            current_vencord_dir,
        )

    # --- Vencord plugin settings ---
    _section("Vencord Bridge Plugin Settings")
    plugin_states = get_vencord_plugin_states()
    for key, enabled in plugin_states.items():
        if enabled is True:
            _status("PASS", f"Vencord plugin '{key}' is enabled")
        elif enabled is False:
            _status("FAIL", f"Vencord plugin '{key}' is DISABLED")
            has_fail = True
        else:
            _status("WARNING", f"Vencord plugin '{key}' has no settings entry")

    # --- Flatpak overrides ---
    _section("Flatpak Filesystem Overrides")
    for fs in FLATPAK_REQUIRED_FILESYSTEMS:
        if has_flatpak_filesystem(fs):
            _status("PASS", f"Flatpak filesystem: {fs}")
        else:
            _status("FAIL", f"Flatpak filesystem NOT set: {fs}")
            has_fail = True
    vencord_fs = str(MANAGED_VENCORD_DIR) + ":ro"
    if has_flatpak_filesystem(vencord_fs):
        _status("PASS", f"Flatpak filesystem: {vencord_fs}")
    else:
        _status("FAIL", f"Flatpak filesystem NOT set: {vencord_fs}")
        has_fail = True

    # --- Bridge socket ---
    _section("Bridge Socket")
    if BRIDGE_SOCKET_VECKORD.exists():
        _status("PASS", f"veckord socket exists", str(BRIDGE_SOCKET_VECKORD))
    else:
        _status("WARNING", f"veckord socket not found", str(BRIDGE_SOCKET_VECKORD))

    if BRIDGE_SOCKET_DECKORD.exists():
        _status("PASS", f"deckord socket exists (legacy)", str(BRIDGE_SOCKET_DECKORD))
    else:
        _status("INFO", f"deckord socket not found", str(BRIDGE_SOCKET_DECKORD))

    active_sock = find_active_bridge_socket()
    if active_sock:
        if ping_bridge(active_sock):
            _status("PASS", f"Bridge ping OK", str(active_sock))
        else:
            _status("FAIL", "Bridge socket exists but ping FAILED — is Vesktop running with bridge enabled?")
            has_fail = True
    else:
        _status("FAIL", "No bridge socket found — launch Vesktop with VeckordBridge enabled")
        has_fail = True

    print()
    if has_fail:
        _info("Some checks FAILED. Run 'install.py install' (first time) or 'install.py repair' (fix).")
        return 1
    else:
        _info("All checks passed.")
        return 0


def verify_installed_decky_plugin(expected_version: Optional[str] = None) -> None:
    """Verify that installed Decky plugin files and manifests exist and parse cleanly."""
    plugin_json = DECKY_PLUGIN_DIR / "plugin.json"
    pkg_json = DECKY_PLUGIN_DIR / "package.json"
    main_py = DECKY_PLUGIN_DIR / "main.py"

    if not plugin_json.exists() or not main_py.exists():
        raise InstallerError("Post-installation verification failed: plugin.json or main.py missing in installed directory.")

    try:
        meta = json.loads(plugin_json.read_text(encoding="utf-8"))
        if meta.get("name") != PLUGIN_DISPLAY_NAME:
            raise InstallerError(f"Post-installation verification failed: name mismatch ({meta.get('name')})")
    except Exception as e:
        raise InstallerError(f"Post-installation verification failed parsing plugin.json: {e}")

    if expected_version and pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            installed_v = pkg.get("version", "")
            target_v = expected_version.lstrip("v")
            if installed_v and target_v and installed_v != target_v:
                raise InstallerError(f"Post-installation verification failed: version mismatch (expected {target_v}, got {installed_v})")
        except (json.JSONDecodeError, OSError):
            pass


# ---------------------------------------------------------------------------
# cmd_install
# ---------------------------------------------------------------------------

def cmd_install(tag: Optional[str] = None, interactive: bool = True) -> int:
    """Fresh install of the Veckord Decky plugin and managed Vencord distribution."""
    print(f"\nVeckord Installer {INSTALLER_VERSION} — Install")
    print("=" * _COL_W)

    # Pre-flight
    _assert_not_root()
    _assert_bazzite()
    _assert_vesktop()
    _assert_decky()
    check_sudo_preflight(interactive)

    if DECKY_PLUGIN_DIR.exists():
        _status("WARNING", f"Plugin directory already exists: {DECKY_PLUGIN_DIR}")
        if interactive:
            answer = _ask("Continue? (This will update the existing installation.)")
            if answer != "y":
                raise InstallerError("Installation cancelled by user.")
        # Treat as update from here
        return cmd_update(tag=tag, interactive=interactive)

    resolved_tag = _determine_tag(tag)
    _info(f"Target release: {resolved_tag}")

    _maybe_ask_stop_vesktop(interactive)

    rollback = RollbackContext()

    # Download
    _section("Downloading release assets")
    dl_dir = download_release_assets(resolved_tag)

    # Verify checksums (fail closed)
    _section("Verifying checksums")
    verify_release_checksums(dl_dir)

    try:
        # Install Decky plugin
        _section("Installing Decky plugin")
        install_decky_plugin(dl_dir / "veckord.zip", rollback)

        # Install managed Vencord
        _section("Installing managed Vencord distribution")
        install_managed_vencord(dl_dir / "vencord-dist.zip", rollback)

        # Configure Vesktop state.json
        _section("Configuring Vesktop")
        old_vencord_dir = read_vencord_dir()
        write_vencord_dir(str(MANAGED_VENCORD_DIR))
        if old_vencord_dir:
            rollback.register(lambda old=old_vencord_dir: write_vencord_dir(old))
        else:
            rollback.register(lambda: _remove_vencord_dir_from_state())
        _status("PASS", "state.json vencordDir → managed Vencord dir")

        # Add Flatpak overrides
        old_filesystems = _get_context_filesystems()
        ensure_all_flatpak_filesystems()
        rollback.register(lambda old=old_filesystems: _set_context_filesystems(old))
        _status("PASS", "Flatpak filesystem overrides set")

        # Enable Vencord bridge plugin
        _maybe_ask_stop_vesktop(interactive)  # re-check; might have been started
        enable_vencord_plugins()
        rollback.register(disable_vencord_plugins)
        _status("PASS", "Vencord bridge plugin keys enabled in settings.json")

        # Restart Decky service
        _section("Restarting Decky Loader")
        run_sudo("systemctl", "restart", DECKY_SERVICE)
        _status("PASS", "Decky Loader service restarted")

        # Verify installed plugin
        verify_installed_decky_plugin(resolved_tag)

    except Exception:
        rollback.rollback()
        raise

    # Final guidance
    print()
    _status("ACTION REQUIRED", "Launch Vesktop to activate the bridge")
    _info("After Vesktop loads, run:")
    _info(f"  python3 {Path(__file__).name} check")
    print()
    _info("Installation complete.")
    return 0


def _remove_vencord_dir_from_state() -> None:
    state = _read_state()
    state.pop("vencordDir", None)
    _write_state(state)


# ---------------------------------------------------------------------------
# cmd_update
# ---------------------------------------------------------------------------

def cmd_update(tag: Optional[str] = None, interactive: bool = True) -> int:
    """Update the Veckord Decky plugin and (if available) the managed Vencord distribution."""
    print(f"\nVeckord Installer {INSTALLER_VERSION} — Update")
    print("=" * _COL_W)

    _assert_not_root()
    _assert_bazzite()
    _assert_vesktop()
    _assert_decky()
    check_sudo_preflight(interactive)

    if not DECKY_PLUGIN_DIR.exists():
        raise InstallerError(
            f"Plugin directory not found: {DECKY_PLUGIN_DIR}\n"
            f"Run 'install.py install' for a fresh installation."
        )

    resolved_tag = _determine_tag(tag)
    _info(f"Target release: {resolved_tag}")

    _maybe_ask_stop_vesktop(interactive)

    rollback = RollbackContext()

    # Download
    _section("Downloading release assets")
    dl_dir = download_release_assets(resolved_tag)

    # Verify checksums (fail closed)
    _section("Verifying checksums")
    verify_release_checksums(dl_dir)

    try:
        # Update Decky plugin (favorites live in ~/.config/veckord, not in plugin dir)
        _section("Updating Decky plugin")
        update_decky_plugin(dl_dir / "veckord.zip", rollback)

        # Update managed Vencord
        _section("Updating managed Vencord distribution")
        install_managed_vencord(dl_dir / "vencord-dist.zip", rollback)

        # Ensure state.json still points to managed dir
        current = read_vencord_dir()
        if current != str(MANAGED_VENCORD_DIR):
            old = current
            write_vencord_dir(str(MANAGED_VENCORD_DIR))
            if old:
                rollback.register(lambda o=old: write_vencord_dir(o))
            _status("PASS", "state.json vencordDir updated → managed Vencord dir")
        else:
            _status("PASS", "state.json vencordDir already correct")

        # Ensure Flatpak overrides
        old_filesystems = _get_context_filesystems()
        ensure_all_flatpak_filesystems()
        rollback.register(lambda old=old_filesystems: _set_context_filesystems(old))
        _status("PASS", "Flatpak filesystem overrides verified")

        # Ensure plugin keys enabled
        _maybe_ask_stop_vesktop(interactive)
        enable_vencord_plugins()
        _status("PASS", "Vencord bridge plugin keys verified in settings.json")

        # Restart Decky
        _section("Restarting Decky Loader")
        run_sudo("systemctl", "restart", DECKY_SERVICE)
        _status("PASS", "Decky Loader service restarted")

        # Verify installed plugin
        verify_installed_decky_plugin(resolved_tag)

    except Exception:
        rollback.rollback()
        raise

    print()
    _status("ACTION REQUIRED", "Relaunch Vesktop to activate the updated bridge")
    _info("After Vesktop loads, run:")
    _info(f"  python3 {Path(__file__).name} check")
    print()
    _info("Update complete.")
    return 0


# ---------------------------------------------------------------------------
# cmd_repair
# ---------------------------------------------------------------------------

def cmd_repair(interactive: bool = True) -> int:
    """
    Repair a broken Veckord installation without downloading if not necessary.
    Fixes: wrong/missing vencordDir, disabled plugin keys, missing Flatpak overrides.
    """
    print(f"\nVeckord Installer {INSTALLER_VERSION} — Repair")
    print("=" * _COL_W)

    _assert_not_root()
    _assert_bazzite()
    _assert_vesktop()
    _assert_decky()

    fixed_anything = False

    _section("Checking installation state")

    if not DECKY_PLUGIN_DIR.exists():
        raise InstallerError(
            f"Plugin directory not found: {DECKY_PLUGIN_DIR}\n"
            f"Run 'install.py install' for a fresh installation."
        )

    # Fix vencordDir
    current_dir = read_vencord_dir()
    if current_dir != str(MANAGED_VENCORD_DIR):
        if not get_managed_vencord_ok():
            _status(
                "FAIL",
                "Managed Vencord dir is missing — cannot set vencordDir",
                str(MANAGED_VENCORD_DIR),
            )
            _info("Run 'install.py update' to re-download and reinstall the managed Vencord.")
            return 1
        repair_vencord_dir()
        _status("PASS", "Fixed: state.json vencordDir → managed Vencord dir")
        fixed_anything = True
    else:
        _status("PASS", "state.json vencordDir is correct")

    # Fix Flatpak overrides
    missing_fs = []
    for fs in FLATPAK_REQUIRED_FILESYSTEMS:
        if not has_flatpak_filesystem(fs):
            missing_fs.append(fs)
    vencord_fs = str(MANAGED_VENCORD_DIR) + ":ro"
    if not has_flatpak_filesystem(vencord_fs):
        missing_fs.append(vencord_fs)

    if missing_fs:
        ensure_all_flatpak_filesystems()
        for fs in missing_fs:
            _status("PASS", f"Fixed: added Flatpak filesystem override: {fs}")
        fixed_anything = True
    else:
        _status("PASS", "All Flatpak filesystem overrides are present")

    # Fix plugin keys in settings.json
    if is_vesktop_running():
        _status(
            "WARNING",
            "Vesktop is running — skipping settings.json repair to avoid data loss",
        )
        _info("Close Vesktop and re-run 'install.py repair' to enable bridge plugins.")
    else:
        states = get_vencord_plugin_states()
        needs_enable = [k for k, v in states.items() if v is not True]
        if needs_enable:
            enable_vencord_plugins()
            for key in needs_enable:
                _status("PASS", f"Fixed: enabled Vencord plugin '{key}'")
            fixed_anything = True
        else:
            _status("PASS", "All Vencord bridge plugin keys are enabled")

    # Restart Decky if we changed anything that affects it
    if fixed_anything and not is_vesktop_running():
        _section("Restarting Decky Loader")
        run_sudo("systemctl", "restart", DECKY_SERVICE)
        _status("PASS", "Decky Loader service restarted")

    print()
    if fixed_anything:
        _status("ACTION REQUIRED", "Relaunch Vesktop to activate the repaired configuration")
        _info("After Vesktop loads, run:")
        _info(f"  python3 {Path(__file__).name} check")
    else:
        _info("Nothing to repair — installation appears healthy.")
        _info("If the bridge is still not working, run:")
        _info(f"  python3 {Path(__file__).name} check")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="install.py",
        description=f"Veckord Installer v{INSTALLER_VERSION} — Bazzite/Vesktop/Decky only",
    )
    parser.add_argument(
        "--tag",
        default=None,
        metavar="TAG",
        help="GitHub release tag to install (default: derived from installed version)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Disable all user prompts (suitable for scripting; fails on blocked conditions)",
    )
    parser.add_argument(
        "command",
        choices=["check", "install", "update", "repair"],
        help="Operation to perform",
    )
    args = parser.parse_args()
    interactive = not args.non_interactive

    try:
        if args.command == "check":
            return cmd_check()
        elif args.command == "install":
            return cmd_install(tag=args.tag, interactive=interactive)
        elif args.command == "update":
            return cmd_update(tag=args.tag, interactive=interactive)
        elif args.command == "repair":
            return cmd_repair(interactive=interactive)
    except InstallerError as e:
        print(f"\n  [FAIL] {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n  Interrupted by user.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
