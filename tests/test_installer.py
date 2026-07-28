"""
tests/test_installer.py — Unit tests for scripts/install.py

All tests run against temporary directories and mocked subprocess calls.
No live system is modified during any test.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import socket
import stat
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest import mock
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Bootstrap: ensure scripts/ is importable as "install"
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

# We import the module once and then monkey-patch paths per test.
import install as M  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_veckord_zip(dest: Path, extra_files: Optional[Dict[str, bytes]] = None) -> bytes:
    """Build a minimal valid veckord.zip and return its SHA-256 digest."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("dist/index.js", b"// compiled frontend\n")
        zf.writestr("dist/index.js.map", b"{}")
        zf.writestr("main.py", b"class Plugin: pass\n")
        zf.writestr(
            "plugin.json",
            json.dumps({"name": "Veckord", "api_version": 1, "flags": []}).encode(),
        )
        zf.writestr(
            "package.json",
            json.dumps({"name": "veckord", "version": "1.0.3"}).encode(),
        )
        zf.writestr("backend/__init__.py", b"")
        zf.writestr("backend/veckord_backend.py", b"class VeckordBackend: pass\n")
        if extra_files:
            for name, data in extra_files.items():
                zf.writestr(name, data)
    raw = buf.getvalue()
    dest.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _make_vencord_dist_zip(dest: Path) -> bytes:
    """Build a minimal valid vencord-dist.zip and return its SHA-256 digest."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("patcher.js", b"// vencord patcher\n")
        zf.writestr("renderer.js", b"// vencord renderer\n")
        zf.writestr("vencordDesktopMain.js", b"// vencord main\n")
        zf.writestr("package.json", b"{}")
    raw = buf.getvalue()
    dest.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _make_vencord_bridge_zip(dest: Path) -> bytes:
    """Build a minimal valid vencordBridge.zip and return its SHA-256 digest."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("vencordBridge/index.tsx", b"// source index\n")
        zf.writestr("vencordBridge/native.ts", b"// source native\n")
    raw = buf.getvalue()
    dest.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _make_checksums(install_hex: str, veckord_hex: str, bridge_hex: str, vencord_hex: str) -> bytes:
    return (
        f"{install_hex}  install.py\n"
        f"{veckord_hex}  veckord.zip\n"
        f"{bridge_hex}  vencordBridge.zip\n"
        f"{vencord_hex}  vencord-dist.zip\n"
    ).encode()


def _make_zip_with_traversal(dest: Path) -> None:
    """Write a zip containing a path-traversal member."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("../evil.py")
        zf.writestr(info, b"# evil\n")
    dest.write_bytes(buf.getvalue())


def _make_zip_with_symlink(dest: Path) -> None:
    """Write a zip containing a Unix symlink member."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("link")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, b"/etc/passwd")
    dest.write_bytes(buf.getvalue())


def _make_zip_with_absolute_path(dest: Path) -> None:
    """Write a zip containing an absolute-path member."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("/etc/evil.py")
        zf.writestr(info, b"# evil\n")
    dest.write_bytes(buf.getvalue())


class _FakeSocket:
    """A fake Unix socket that returns a canned bridge ping response."""

    def __init__(self, response: Optional[Dict] = None, fail_connect: bool = False):
        self._response = response or {"version": 1, "id": "x", "ok": True, "result": {"pong": True}}
        self._fail_connect = fail_connect
        self._sent = b""

    def settimeout(self, t): pass

    def connect(self, path):
        if self._fail_connect:
            raise ConnectionRefusedError("refused")

    def sendall(self, data):
        self._sent += data

    def recv(self, size):
        payload = json.dumps(self._response).encode() + b"\n"
        result = payload
        self._response = None  # subsequent calls return b""
        return result

    def close(self): pass


# ---------------------------------------------------------------------------
# Base test class that patches global paths
# ---------------------------------------------------------------------------

class InstallerTestBase(unittest.TestCase):
    """Base class that redirects all M.* path constants to a temp directory."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="veckord_test_"))
        self._orig_paths = self._snapshot_paths()
        self._patch_paths()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self._restore_paths()

    # ---- Path helpers -------------------------------------------------------

    def _snapshot_paths(self) -> Dict[str, Any]:
        return {
            "HOME": M.HOME,
            "UID": M.UID,
            "RUNTIME_DIR": M.RUNTIME_DIR,
            "DECKY_PLUGINS_ROOT": M.DECKY_PLUGINS_ROOT,
            "DECKY_PLUGIN_DIR": M.DECKY_PLUGIN_DIR,
            "VESKTOP_CONFIG": M.VESKTOP_CONFIG,
            "MANAGED_ROOT": M.MANAGED_ROOT,
            "MANAGED_VENCORD_DIR": M.MANAGED_VENCORD_DIR,
            "BRIDGE_SOCKET_DECKORD": M.BRIDGE_SOCKET_DECKORD,
            "BRIDGE_SOCKET_VECKORD": M.BRIDGE_SOCKET_VECKORD,
        }

    def _restore_paths(self):
        for k, v in self._orig_paths.items():
            setattr(M, k, v)

    def _patch_paths(self):
        M.HOME = self.tmp
        M.UID = os.getuid()
        M.RUNTIME_DIR = self.tmp / "run"
        M.DECKY_PLUGINS_ROOT = self.tmp / "homebrew" / "plugins"
        M.DECKY_PLUGIN_DIR = M.DECKY_PLUGINS_ROOT / "Deckord"
        M.VESKTOP_CONFIG = self.tmp / "vesktop_config"
        M.MANAGED_ROOT = self.tmp / "managed"
        M.MANAGED_VENCORD_DIR = M.MANAGED_ROOT / "vencord"
        M.BRIDGE_SOCKET_DECKORD = M.RUNTIME_DIR / "deckord" / "bridge.sock"
        M.BRIDGE_SOCKET_VECKORD = M.RUNTIME_DIR / "veckord" / "bridge.sock"

    # ---- Filesystem setup helpers -------------------------------------------

    def _create_vesktop_config(
        self,
        vencord_dir: Optional[str] = None,
        plugin_keys: Optional[List[str]] = None,
    ):
        cfg = M.VESKTOP_CONFIG
        cfg.mkdir(parents=True, exist_ok=True)
        # state.json
        state: Dict[str, Any] = {
            "firstLaunch": False,
            "maximized": True,
        }
        if vencord_dir is not None:
            state["vencordDir"] = vencord_dir
        (cfg / "state.json").write_text(json.dumps(state, indent=4))
        # settings/settings.json
        settings_dir = cfg / "settings"
        settings_dir.mkdir(exist_ok=True)
        plugins_cfg: Dict[str, Any] = {}
        for key in (plugin_keys or []):
            plugins_cfg[key] = {"enabled": True}
        settings = {"plugins": plugins_cfg}
        (settings_dir / "settings.json").write_text(json.dumps(settings, indent=4))

    def _create_decky_plugin(self, version: str = "1.0.1"):
        d = M.DECKY_PLUGIN_DIR
        d.mkdir(parents=True, exist_ok=True)
        (d / "package.json").write_text(json.dumps({"name": "veckord", "version": version}))
        (d / "plugin.json").write_text(json.dumps({"name": "Veckord", "api_version": 1}))
        (d / "main.py").write_text("class Plugin: pass\n")
        dist = d / "dist"
        dist.mkdir(exist_ok=True)
        (dist / "index.js").write_text("// compiled\n")

    def _create_managed_vencord(self):
        M.MANAGED_VENCORD_DIR.mkdir(parents=True, exist_ok=True)
        (M.MANAGED_VENCORD_DIR / "patcher.js").write_text("// patcher\n")
        (M.MANAGED_VENCORD_DIR / "renderer.js").write_text("// renderer\n")

    def _create_flatpak_override(self, filesystems: Optional[List[str]] = None):
        override_dir = self.tmp / "flatpak" / "overrides"
        override_dir.mkdir(parents=True, exist_ok=True)
        override_file = override_dir / M.VESKTOP_FLATPAK_ID
        # Patch M.FLATPAK_OVERRIDE_FILE to use temp path
        M.FLATPAK_OVERRIDE_FILE = override_file
        if filesystems:
            content = "[Context]\nfilesystems=" + ";".join(filesystems) + ";\n"
            override_file.write_text(content)

    def _setup_downloads(self, tag: str = "v1.0.3") -> tuple:
        """Create fake download files, return (install_hex, veckord_hex, bridge_hex, vencord_hex)."""
        dl_dir = M.MANAGED_ROOT / "downloads" / tag
        dl_dir.mkdir(parents=True, exist_ok=True)
        install_py = dl_dir / "install.py"
        install_py.write_bytes(b"# install.py\n")
        install_hex = hashlib.sha256(b"# install.py\n").hexdigest()
        veckord_hex = _make_veckord_zip(dl_dir / "veckord.zip")
        bridge_hex = _make_vencord_bridge_zip(dl_dir / "vencordBridge.zip")
        vencord_hex = _make_vencord_dist_zip(dl_dir / "vencord-dist.zip")
        checksums = _make_checksums(install_hex, veckord_hex, bridge_hex, vencord_hex)
        (dl_dir / "checksums.sha256").write_bytes(checksums)
        return install_hex, veckord_hex, bridge_hex, vencord_hex


# ===========================================================================
# Test: validate_zip
# ===========================================================================

class TestValidateZip(InstallerTestBase):
    """Tests for M.validate_zip security checks."""

    def test_valid_zip_passes(self):
        dest = self.tmp / "extract"
        dest.mkdir()
        z = self.tmp / "good.zip"
        _make_veckord_zip(z)
        with zipfile.ZipFile(z) as zf:
            M.validate_zip(zf, dest)  # should not raise

    def test_path_traversal_rejected(self):
        dest = self.tmp / "extract"
        dest.mkdir()
        z = self.tmp / "bad.zip"
        _make_zip_with_traversal(z)
        with zipfile.ZipFile(z) as zf:
            with self.assertRaises(ValueError, msg="Should reject path traversal"):
                M.validate_zip(zf, dest)

    def test_symlink_rejected(self):
        dest = self.tmp / "extract"
        dest.mkdir()
        z = self.tmp / "sym.zip"
        _make_zip_with_symlink(z)
        with zipfile.ZipFile(z) as zf:
            with self.assertRaises(ValueError, msg="Should reject symlink"):
                M.validate_zip(zf, dest)

    def test_absolute_path_rejected(self):
        dest = self.tmp / "extract"
        dest.mkdir()
        z = self.tmp / "abs.zip"
        _make_zip_with_absolute_path(z)
        with zipfile.ZipFile(z) as zf:
            with self.assertRaises(ValueError, msg="Should reject absolute path"):
                M.validate_zip(zf, dest)


# ===========================================================================
# Test: verify_checksum
# ===========================================================================

class TestVerifyChecksum(InstallerTestBase):

    def test_correct_checksum_passes(self):
        f = self.tmp / "file.zip"
        f.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        M.verify_checksum(f, expected)  # should not raise

    def test_wrong_checksum_raises(self):
        f = self.tmp / "file.zip"
        f.write_bytes(b"hello world")
        with self.assertRaises(M.InstallerError):
            M.verify_checksum(f, "deadbeef" * 8)


# ===========================================================================
# Test: ping_bridge
# ===========================================================================

class TestPingBridge(InstallerTestBase):

    def test_successful_ping(self):
        fake_sock = _FakeSocket(response={"version": 1, "id": "x", "ok": True, "result": {"pong": True}})
        with patch("socket.socket", return_value=fake_sock):
            result = M.ping_bridge(self.tmp / "fake.sock")
        self.assertTrue(result)

    def test_failed_ping_connection_refused(self):
        fake_sock = _FakeSocket(fail_connect=True)
        with patch("socket.socket", return_value=fake_sock):
            result = M.ping_bridge(self.tmp / "fake.sock")
        self.assertFalse(result)

    def test_failed_ping_bad_response(self):
        fake_sock = _FakeSocket(response={"version": 1, "id": "x", "ok": False, "error": {"code": "ERR"}})
        with patch("socket.socket", return_value=fake_sock):
            result = M.ping_bridge(self.tmp / "fake.sock")
        self.assertFalse(result)


# ===========================================================================
# Test: Flatpak override file management
# ===========================================================================

class TestFlatpakOverrides(InstallerTestBase):

    def setUp(self):
        super().setUp()
        self._create_flatpak_override()

    def test_add_new_entry_to_empty_file(self):
        M.ensure_flatpak_filesystem(str(M.MANAGED_VENCORD_DIR) + ":ro")
        content = M.FLATPAK_OVERRIDE_FILE.read_text()
        self.assertIn(str(M.MANAGED_VENCORD_DIR) + ":ro", content)

    def test_add_xdg_run_deckord(self):
        M.ensure_flatpak_filesystem("xdg-run/deckord:create")
        content = M.FLATPAK_OVERRIDE_FILE.read_text()
        self.assertIn("xdg-run/deckord:create", content)

    def test_idempotent_add(self):
        entry = "xdg-run/veckord:create"
        M.ensure_flatpak_filesystem(entry)
        M.ensure_flatpak_filesystem(entry)
        content = M.FLATPAK_OVERRIDE_FILE.read_text()
        self.assertEqual(content.count(entry), 1)

    def test_preserve_existing_bang_host(self):
        """The !host entry must never be removed."""
        M.FLATPAK_OVERRIDE_FILE.write_text(
            "[Context]\nfilesystems=!host;xdg-run/deckord:create;\n"
        )
        M.ensure_flatpak_filesystem("xdg-run/veckord:create")
        content = M.FLATPAK_OVERRIDE_FILE.read_text()
        self.assertIn("!host", content)

    def test_remove_flatpak_filesystem(self):
        M.FLATPAK_OVERRIDE_FILE.write_text(
            "[Context]\nfilesystems=xdg-run/deckord:create;xdg-run/veckord:create;\n"
        )
        M.remove_flatpak_filesystem("xdg-run/veckord:create")
        content = M.FLATPAK_OVERRIDE_FILE.read_text()
        self.assertNotIn("xdg-run/veckord:create", content)
        self.assertIn("xdg-run/deckord:create", content)

    def test_check_flatpak_filesystem_present(self):
        M.FLATPAK_OVERRIDE_FILE.write_text(
            "[Context]\nfilesystems=xdg-run/deckord:create;\n"
        )
        self.assertTrue(M.has_flatpak_filesystem("xdg-run/deckord:create"))
        self.assertFalse(M.has_flatpak_filesystem("xdg-run/veckord:create"))


# ===========================================================================
# Test: state.json handling
# ===========================================================================

class TestStateJson(InstallerTestBase):

    def setUp(self):
        super().setUp()
        self._create_vesktop_config()

    def test_read_vencord_dir_missing(self):
        result = M.read_vencord_dir()
        self.assertIsNone(result)

    def test_write_and_read_vencord_dir(self):
        M.write_vencord_dir(str(M.MANAGED_VENCORD_DIR))
        result = M.read_vencord_dir()
        self.assertEqual(result, str(M.MANAGED_VENCORD_DIR))

    def test_write_is_atomic(self):
        """Writing state.json must not leave partial files."""
        state_path = M.VESKTOP_CONFIG / "state.json"
        M.write_vencord_dir("/some/path")
        self.assertTrue(state_path.exists())
        # No .tmp file should remain
        self.assertFalse((M.VESKTOP_CONFIG / "state.json.tmp").exists())

    def test_repair_invalid_vencord_dir(self):
        """repair_vencord_dir should update state.json when the stored path is wrong."""
        M.write_vencord_dir("/nonexistent/path")
        self._create_managed_vencord()
        M.repair_vencord_dir()
        self.assertEqual(M.read_vencord_dir(), str(M.MANAGED_VENCORD_DIR))


# ===========================================================================
# Test: settings.json plugin enablement
# ===========================================================================

class TestSettingsJson(InstallerTestBase):

    def setUp(self):
        super().setUp()
        self._create_vesktop_config()

    def test_enable_plugin_keys(self):
        M.enable_vencord_plugins()
        settings = json.loads((M.VESKTOP_CONFIG / "settings" / "settings.json").read_text())
        for key in M.VENCORD_PLUGIN_KEYS:
            self.assertTrue(settings["plugins"].get(key, {}).get("enabled"), f"{key} not enabled")

    def test_enable_is_idempotent(self):
        M.enable_vencord_plugins()
        M.enable_vencord_plugins()
        settings = json.loads((M.VESKTOP_CONFIG / "settings" / "settings.json").read_text())
        for key in M.VENCORD_PLUGIN_KEYS:
            self.assertIn(key, settings["plugins"])

    def test_disable_plugin_keys(self):
        M.enable_vencord_plugins()
        M.disable_vencord_plugins()
        settings = json.loads((M.VESKTOP_CONFIG / "settings" / "settings.json").read_text())
        for key in M.VENCORD_PLUGIN_KEYS:
            self.assertFalse(settings["plugins"].get(key, {}).get("enabled", True))


# ===========================================================================
# Test: install — fresh install
# ===========================================================================

class TestFreshInstall(InstallerTestBase):

    def setUp(self):
        super().setUp()
        M.DECKY_PLUGINS_ROOT.mkdir(parents=True, exist_ok=True)
        self._create_vesktop_config()
        self._create_flatpak_override()
        self._setup_downloads()

    @patch.object(M, "is_bazzite", return_value=True)
    @patch.object(M, "is_vesktop_installed", return_value=True)
    @patch.object(M, "is_decky_installed", return_value=True)
    @patch.object(M, "is_vesktop_running", return_value=False)
    @patch.object(M, "run_sudo", return_value=None)
    def test_fresh_install_succeeds(
        self,
        mock_sudo, mock_running,
        mock_decky, mock_vesktop, mock_bazzite,
    ):
        """A fresh install with no existing plugin should succeed."""
        self.assertFalse(M.DECKY_PLUGIN_DIR.exists())
        dl_dir = M.MANAGED_ROOT / "downloads" / "v1.0.3"
        with patch.object(M, "download_release_assets", return_value=dl_dir):
            result = M.cmd_install(tag="v1.0.3", interactive=False)
        self.assertEqual(result, 0)
        # Plugin dir should now exist with expected files
        self.assertTrue((M.DECKY_PLUGIN_DIR / "main.py").exists())
        self.assertTrue((M.DECKY_PLUGIN_DIR / "dist" / "index.js").exists())
        # Managed vencord should be installed
        self.assertTrue((M.MANAGED_VENCORD_DIR / "patcher.js").exists())
        # state.json should point to managed vencord
        self.assertEqual(M.read_vencord_dir(), str(M.MANAGED_VENCORD_DIR))
        # Plugin should be enabled in settings
        settings = json.loads((M.VESKTOP_CONFIG / "settings" / "settings.json").read_text())
        for key in M.VENCORD_PLUGIN_KEYS:
            self.assertTrue(settings["plugins"].get(key, {}).get("enabled"), f"{key} not enabled")

    @patch.object(M, "is_bazzite", return_value=True)
    @patch.object(M, "is_vesktop_installed", return_value=False)
    def test_install_fails_without_vesktop(self, mock_vesktop, mock_bazzite):
        with self.assertRaises(M.InstallerError):
            M.cmd_install(tag="v1.0.3", interactive=False)

    @patch.object(M, "is_bazzite", return_value=True)
    @patch.object(M, "is_vesktop_installed", return_value=True)
    @patch.object(M, "is_decky_installed", return_value=False)
    def test_install_fails_without_decky(self, mock_decky, mock_vesktop, mock_bazzite):
        with self.assertRaises(M.InstallerError):
            M.cmd_install(tag="v1.0.3", interactive=False)

    @patch.object(M, "is_bazzite", return_value=False)
    def test_install_fails_on_non_bazzite(self, mock_bazzite):
        with self.assertRaises(M.InstallerError):
            M.cmd_install(tag="v1.0.3", interactive=False)


# ===========================================================================
# Test: install — existing Deckord update path
# ===========================================================================

class TestExistingInstallUpdate(InstallerTestBase):

    def setUp(self):
        super().setUp()
        M.DECKY_PLUGINS_ROOT.mkdir(parents=True, exist_ok=True)
        self._create_decky_plugin(version="1.0.0")
        self._create_managed_vencord()
        self._create_vesktop_config(vencord_dir=str(M.MANAGED_VENCORD_DIR))
        self._create_flatpak_override()
        self._setup_downloads()

    @patch.object(M, "is_bazzite", return_value=True)
    @patch.object(M, "is_vesktop_installed", return_value=True)
    @patch.object(M, "is_decky_installed", return_value=True)
    @patch.object(M, "is_vesktop_running", return_value=False)
    @patch.object(M, "run_sudo", return_value=None)
    def test_update_replaces_plugin(
        self, mock_sudo, mock_running,
        mock_decky, mock_vesktop, mock_bazzite,
    ):
        dl_dir = M.MANAGED_ROOT / "downloads" / "v1.0.3"
        with patch.object(M, "download_release_assets", return_value=dl_dir):
            result = M.cmd_update(tag="v1.0.3", interactive=False)
        self.assertEqual(result, 0)
        # New version should be installed
        pkg = json.loads((M.DECKY_PLUGIN_DIR / "package.json").read_text())
        self.assertEqual(pkg["version"], "1.0.3")
        # Backup should exist
        backups = list((M.MANAGED_ROOT / "backups").iterdir())
        self.assertTrue(len(backups) >= 1, "Backup should have been created")

    @patch.object(M, "is_bazzite", return_value=True)
    @patch.object(M, "is_vesktop_installed", return_value=True)
    @patch.object(M, "is_decky_installed", return_value=True)
    def test_update_fails_when_not_installed(self, mock_decky, mock_vesktop, mock_bazzite):
        """update should error when DECKY_PLUGIN_DIR does not exist."""
        import shutil
        shutil.rmtree(M.DECKY_PLUGIN_DIR)
        with self.assertRaises(M.InstallerError):
            M.cmd_update(tag="v1.0.3", interactive=False)


# ===========================================================================
# Test: duplicate directory detection
# ===========================================================================

class TestDuplicateDirectoryDetection(InstallerTestBase):

    def setUp(self):
        super().setUp()
        M.DECKY_PLUGINS_ROOT.mkdir(parents=True, exist_ok=True)

    def test_no_duplicate_if_only_deckord(self):
        (M.DECKY_PLUGINS_ROOT / "Deckord").mkdir()
        result = M.check_duplicate_plugin_dirs()
        self.assertFalse(result, "Should return False (no duplicate) with only Deckord/")

    def test_duplicate_detected(self):
        (M.DECKY_PLUGINS_ROOT / "Deckord").mkdir()
        (M.DECKY_PLUGINS_ROOT / "Veckord").mkdir()
        result = M.check_duplicate_plugin_dirs()
        self.assertTrue(result, "Should return True (duplicate detected)")

    def test_only_veckord_dir_is_unusual(self):
        """Veckord/ without Deckord/ is suspicious — check_duplicate returns False but install will warn."""
        (M.DECKY_PLUGINS_ROOT / "Veckord").mkdir()
        result = M.check_duplicate_plugin_dirs()
        # Only Veckord/ (no Deckord/) is not a duplicate condition per spec
        self.assertFalse(result)


# ===========================================================================
# Test: checksum verification
# ===========================================================================

class TestChecksumVerification(InstallerTestBase):

    def setUp(self):
        super().setUp()
        M.MANAGED_ROOT.mkdir(parents=True, exist_ok=True)

    def test_invalid_checksum_raises(self):
        f = M.MANAGED_ROOT / "veckord.zip"
        f.write_bytes(b"corrupted data")
        with self.assertRaises(M.InstallerError):
            M.verify_checksum(f, "deadbeef" * 8)

    def test_valid_checksum_passes(self):
        f = M.MANAGED_ROOT / "veckord.zip"
        data = b"legitimate data"
        f.write_bytes(data)
        good_hex = hashlib.sha256(data).hexdigest()
        M.verify_checksum(f, good_hex)  # must not raise


# ===========================================================================
# Test: malicious ZIP paths
# ===========================================================================

class TestMaliciousZip(InstallerTestBase):

    def test_path_traversal_rejected(self):
        dest = self.tmp / "extract"
        dest.mkdir()
        z = self.tmp / "traverse.zip"
        _make_zip_with_traversal(z)
        with zipfile.ZipFile(z) as zf:
            with self.assertRaises(ValueError):
                M.validate_zip(zf, dest)

    def test_symlink_rejected(self):
        dest = self.tmp / "extract"
        dest.mkdir()
        z = self.tmp / "sym.zip"
        _make_zip_with_symlink(z)
        with zipfile.ZipFile(z) as zf:
            with self.assertRaises(ValueError):
                M.validate_zip(zf, dest)


# ===========================================================================
# Test: atomic replacement
# ===========================================================================

class TestAtomicReplace(InstallerTestBase):

    def test_atomic_replace_succeeds(self):
        src = self.tmp / "src"
        src.mkdir()
        (src / "new_file.txt").write_text("new")
        dest = self.tmp / "dest"
        dest.mkdir()
        (dest / "old_file.txt").write_text("old")
        backup = self.tmp / "backup"
        M.atomic_replace_dir(src, dest, backup=backup)
        self.assertTrue((dest / "new_file.txt").exists())
        self.assertFalse((dest / "old_file.txt").exists())
        self.assertTrue((backup / "old_file.txt").exists())

    def test_atomic_replace_no_dest(self):
        src = self.tmp / "src"
        src.mkdir()
        (src / "file.txt").write_text("data")
        dest = self.tmp / "dest"  # does not exist
        M.atomic_replace_dir(src, dest)
        self.assertTrue((dest / "file.txt").exists())


# ===========================================================================
# Test: rollback
# ===========================================================================

class TestRollback(InstallerTestBase):

    def test_rollback_context_calls_undo_in_reverse(self):
        order = []
        ctx = M.RollbackContext()
        ctx.register(lambda: order.append(1))
        ctx.register(lambda: order.append(2))
        ctx.register(lambda: order.append(3))
        ctx.rollback()
        self.assertEqual(order, [3, 2, 1])

    def test_rollback_continues_on_error(self):
        order = []
        ctx = M.RollbackContext()
        ctx.register(lambda: order.append(1))
        ctx.register(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        ctx.register(lambda: order.append(3))
        ctx.rollback()  # must not raise
        self.assertIn(1, order)
        self.assertIn(3, order)

    def test_install_rollback_on_checksum_failure(self):
        """If checksum fails, no files should be written to DECKY_PLUGIN_DIR."""
        M.DECKY_PLUGINS_ROOT.mkdir(parents=True, exist_ok=True)
        self._create_vesktop_config()
        self._create_flatpak_override()
        # Create downloads with wrong checksum
        dl_dir = M.MANAGED_ROOT / "downloads" / "v1.0.3"
        dl_dir.mkdir(parents=True, exist_ok=True)
        _make_veckord_zip(dl_dir / "veckord.zip")
        _make_vencord_bridge_zip(dl_dir / "vencordBridge.zip")
        _make_vencord_dist_zip(dl_dir / "vencord-dist.zip")
        # Write checksums file with wrong hex
        (dl_dir / "checksums.sha256").write_bytes(
            b"deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef  veckord.zip\n"
            b"deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef  vencordBridge.zip\n"
            b"deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef  vencord-dist.zip\n"
        )
        dl_dir = M.MANAGED_ROOT / "downloads" / "v1.0.3"
        with patch.object(M, "is_bazzite", return_value=True), \
             patch.object(M, "is_vesktop_installed", return_value=True), \
             patch.object(M, "is_decky_installed", return_value=True), \
             patch.object(M, "is_vesktop_running", return_value=False), \
             patch.object(M, "run_sudo", return_value=None), \
             patch.object(M, "download_release_assets", return_value=dl_dir):
            with self.assertRaises(M.InstallerError):
                M.cmd_install(tag="v1.0.3", interactive=False)
        # Plugin dir must NOT exist
        self.assertFalse(M.DECKY_PLUGIN_DIR.exists())


# ===========================================================================
# Test: repeated installation
# ===========================================================================

class TestRepeatedInstallation(InstallerTestBase):

    def setUp(self):
        super().setUp()
        M.DECKY_PLUGINS_ROOT.mkdir(parents=True, exist_ok=True)
        self._create_vesktop_config()
        self._create_flatpak_override()
        self._setup_downloads()

    @patch.object(M, "is_bazzite", return_value=True)
    @patch.object(M, "is_vesktop_installed", return_value=True)
    @patch.object(M, "is_decky_installed", return_value=True)
    @patch.object(M, "is_vesktop_running", return_value=False)
    @patch.object(M, "run_sudo", return_value=None)
    def test_install_twice_does_not_create_veckord_dir(
        self, mock_sudo, mock_running, mock_decky, mock_vesktop, mock_bazzite
    ):
        """Running install twice should never create a Veckord/ directory."""
        dl_dir = M.MANAGED_ROOT / "downloads" / "v1.0.3"
        with patch.object(M, "download_release_assets", return_value=dl_dir):
            # First install
            M.cmd_install(tag="v1.0.3", interactive=False)
            # Second install (will route to update since plugin_dir exists)
            M.cmd_install(tag="v1.0.3", interactive=False)
        self.assertTrue(M.DECKY_PLUGIN_DIR.exists())  # Deckord/ exists
        self.assertFalse((M.DECKY_PLUGINS_ROOT / "Veckord").exists())  # Veckord/ never created


# ===========================================================================
# Test: repair — invalid vencordDir
# ===========================================================================

class TestRepair(InstallerTestBase):

    def setUp(self):
        super().setUp()
        M.DECKY_PLUGINS_ROOT.mkdir(parents=True, exist_ok=True)
        self._create_decky_plugin()
        self._create_managed_vencord()
        self._create_vesktop_config(vencord_dir="/nonexistent/path")
        self._create_flatpak_override()

    @patch.object(M, "is_bazzite", return_value=True)
    @patch.object(M, "is_vesktop_installed", return_value=True)
    @patch.object(M, "is_decky_installed", return_value=True)
    @patch.object(M, "is_vesktop_running", return_value=False)
    @patch.object(M, "run_sudo", return_value=None)
    def test_repair_fixes_vencord_dir(self, mock_sudo, mock_running, mock_decky, mock_vesktop, mock_bazzite):
        result = M.cmd_repair(interactive=False)
        self.assertEqual(result, 0)
        self.assertEqual(M.read_vencord_dir(), str(M.MANAGED_VENCORD_DIR))

    @patch.object(M, "is_bazzite", return_value=True)
    @patch.object(M, "is_vesktop_installed", return_value=True)
    @patch.object(M, "is_decky_installed", return_value=True)
    @patch.object(M, "is_vesktop_running", return_value=False)
    @patch.object(M, "run_sudo", return_value=None)
    def test_repair_enables_plugins(self, mock_sudo, mock_running, mock_decky, mock_vesktop, mock_bazzite):
        M.cmd_repair(interactive=False)
        settings = json.loads((M.VESKTOP_CONFIG / "settings" / "settings.json").read_text())
        for key in M.VENCORD_PLUGIN_KEYS:
            self.assertTrue(
                settings["plugins"].get(key, {}).get("enabled"),
                f"Expected {key} to be enabled after repair"
            )


# ===========================================================================
# Test: bridge ping — success and failure
# ===========================================================================

class TestBridgePingVariants(InstallerTestBase):

    def test_ping_success(self):
        fake_sock = _FakeSocket()
        with patch("socket.socket", return_value=fake_sock):
            self.assertTrue(M.ping_bridge(self.tmp / "fake.sock"))

    def test_ping_connection_refused(self):
        fake_sock = _FakeSocket(fail_connect=True)
        with patch("socket.socket", return_value=fake_sock):
            self.assertFalse(M.ping_bridge(self.tmp / "fake.sock"))

    def test_ping_non_existent_socket_returns_false(self):
        result = M.ping_bridge(self.tmp / "does_not_exist.sock")
        self.assertFalse(result)

    def test_ping_garbage_response_returns_false(self):
        class GarbageSock:
            def settimeout(self, t): pass
            def connect(self, p): pass
            def sendall(self, d): pass
            def recv(self, n): return b"not json\n"
            def close(self): pass

        with patch("socket.socket", return_value=GarbageSock()):
            self.assertFalse(M.ping_bridge(self.tmp / "fake.sock"))


# ===========================================================================
# Test: symlinked target detection
# ===========================================================================

class TestSymlinkedTarget(InstallerTestBase):

    def test_symlinked_plugin_dir_detected(self):
        """If DECKY_PLUGIN_DIR is a symlink, installer should refuse to overwrite."""
        M.DECKY_PLUGINS_ROOT.mkdir(parents=True, exist_ok=True)
        link_target = self.tmp / "real_dir"
        link_target.mkdir()
        M.DECKY_PLUGIN_DIR.symlink_to(link_target)
        self.assertTrue(M.is_symlink_target(M.DECKY_PLUGIN_DIR))

    def test_real_dir_not_flagged_as_symlink(self):
        M.DECKY_PLUGINS_ROOT.mkdir(parents=True, exist_ok=True)
        M.DECKY_PLUGIN_DIR.mkdir()
        self.assertFalse(M.is_symlink_target(M.DECKY_PLUGIN_DIR))


# ===========================================================================
# Test: cmd_check output coverage
# ===========================================================================

class TestCmdCheck(InstallerTestBase):

    def setUp(self):
        super().setUp()
        M.DECKY_PLUGINS_ROOT.mkdir(parents=True, exist_ok=True)
        self._create_decky_plugin()
        self._create_managed_vencord()
        self._create_vesktop_config(
            vencord_dir=str(M.MANAGED_VENCORD_DIR),
            plugin_keys=["VeckordBridge", "DeckordBridge", "deckordBridge"],
        )
        self._create_flatpak_override(filesystems=[
            "xdg-run/deckord:create",
            "xdg-run/veckord:create",
            str(M.MANAGED_VENCORD_DIR) + ":ro",
        ])

    @patch.object(M, "is_bazzite", return_value=True)
    @patch.object(M, "is_vesktop_installed", return_value=True)
    @patch.object(M, "get_vesktop_version", return_value="1.6.5")
    @patch.object(M, "get_decky_service_active", return_value=True)
    def test_check_runs_without_exception(self, mock_svc, mock_ver, mock_vc, mock_baz):
        """check should run to completion without exceptions."""
        try:
            M.cmd_check()
        except SystemExit:
            pass  # check may call sys.exit(0) or sys.exit(1)


# ===========================================================================
# Test: missing Vesktop/Decky detection in check
# ===========================================================================

class TestCheckMissingComponents(InstallerTestBase):

    def setUp(self):
        super().setUp()
        self._create_vesktop_config()
        self._create_flatpak_override()

    @patch.object(M, "is_bazzite", return_value=True)
    @patch.object(M, "is_vesktop_installed", return_value=False)
    @patch.object(M, "get_decky_service_active", return_value=False)
    def test_check_reports_missing_vesktop(self, mock_decky, mock_vesktop, mock_bazzite):
        """check should not crash when Vesktop is missing."""
        try:
            M.cmd_check()
        except SystemExit:
            pass

    @patch.object(M, "is_bazzite", return_value=True)
    @patch.object(M, "is_vesktop_installed", return_value=True)
    @patch.object(M, "get_vesktop_version", return_value="1.6.5")
    @patch.object(M, "get_decky_service_active", return_value=False)
    def test_check_reports_decky_service_inactive(self, mock_svc, mock_ver, mock_vc, mock_baz):
        """check should not crash when Decky service is inactive."""
        try:
            M.cmd_check()
        except SystemExit:
            pass


# ===========================================================================
# Test: privilege handling & rollback
# ===========================================================================

class TestPrivilegeHandlingAndRollback(InstallerTestBase):

    def setUp(self):
        super().setUp()
        M.DECKY_PLUGINS_ROOT.mkdir(parents=True, exist_ok=True)
        self._create_vesktop_config()
        self._create_flatpak_override()
        self._setup_downloads("v1.0.3")

    @patch.object(M, "_decky_plugin_dir_needs_sudo", return_value=True)
    @patch("subprocess.run")
    def test_sudo_preflight_fails_noninteractive_when_sudo_unavailable(self, mock_run, mock_needs):
        """In non-interactive mode, check_sudo_preflight fails immediately if sudo -n v fails."""
        mock_run.return_value = MagicMock(returncode=1, stderr="sudo: a password is required")
        with self.assertRaises(M.InstallerError) as ctx:
            M.check_sudo_preflight(interactive=False)
        self.assertIn("Sudo authorization is required", str(ctx.exception))

    @patch.object(M, "_decky_plugin_dir_needs_sudo", return_value=True)
    @patch.object(M, "run_sudo")
    @patch.object(M, "is_bazzite", return_value=True)
    @patch.object(M, "is_vesktop_installed", return_value=True)
    @patch.object(M, "is_decky_installed", return_value=True)
    @patch.object(M, "is_vesktop_running", return_value=False)
    @patch.object(M, "check_sudo_preflight", return_value=None)
    def test_root_owned_plugins_dir_uses_targeted_sudo(
        self, mock_preflight, mock_running, mock_decky, mock_vesktop, mock_bazzite, mock_sudo, mock_needs
    ):
        """Root-owned Decky plugin updates must use targeted sudo mv, mkdir, cp commands."""
        M.DECKY_PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        (M.DECKY_PLUGIN_DIR / "plugin.json").write_text('{"name": "Veckord"}')
        dl_dir = M.MANAGED_ROOT / "downloads" / "v1.0.3"

        with patch.object(M, "download_release_assets", return_value=dl_dir), \
             patch.object(M, "verify_installed_decky_plugin", return_value=None):
            M.cmd_update(tag="v1.0.3", interactive=False)

        sudo_cmds = [call.args for call in mock_sudo.call_args_list]
        cmd_names = [cmd[0] for cmd in sudo_cmds]
        self.assertIn("mv", cmd_names)
        self.assertIn("mkdir", cmd_names)
        self.assertIn("cp", cmd_names)
        self.assertIn("systemctl", cmd_names)

    @patch.object(M, "is_bazzite", return_value=True)
    @patch.object(M, "is_vesktop_installed", return_value=True)
    @patch.object(M, "is_decky_installed", return_value=True)
    @patch.object(M, "is_vesktop_running", return_value=False)
    @patch.object(M, "check_sudo_preflight", return_value=None)
    def test_favorites_untouched_on_update(
        self, mock_preflight, mock_running, mock_decky, mock_vesktop, mock_bazzite
    ):
        """Favorites stored in ~/.config/veckord/ must not be modified or deleted during update."""
        fav_dir = M.HOME / ".config" / "veckord"
        fav_dir.mkdir(parents=True, exist_ok=True)
        fav_file = fav_dir / "favorites.json"
        fav_file.write_text('{"channels": ["123456789"]}')

        dl_dir = M.MANAGED_ROOT / "downloads" / "v1.0.3"
        with patch.object(M, "download_release_assets", return_value=dl_dir), \
             patch.object(M, "run_sudo", return_value=None):
            M.cmd_install(tag="v1.0.3", interactive=False)

        self.assertTrue(fav_file.exists())
        self.assertEqual(fav_file.read_text(), '{"channels": ["123456789"]}')

    @patch.object(M, "is_bazzite", return_value=True)
    @patch.object(M, "is_vesktop_installed", return_value=True)
    @patch.object(M, "is_decky_installed", return_value=True)
    @patch.object(M, "is_vesktop_running", return_value=False)
    @patch.object(M, "check_sudo_preflight", return_value=None)
    def test_no_sudo_used_for_vesktop_config(
        self, mock_preflight, mock_running, mock_decky, mock_vesktop, mock_bazzite
    ):
        """Vesktop state.json, settings.json, and Flatpak override edits must remain unprivileged."""
        sudo_calls = []

        def spy_sudo(*args):
            sudo_calls.append(args)

        dl_dir = M.MANAGED_ROOT / "downloads" / "v1.0.3"
        with patch.object(M, "download_release_assets", return_value=dl_dir), \
             patch.object(M, "run_sudo", side_effect=spy_sudo):
            M.cmd_install(tag="v1.0.3", interactive=False)

        for call_args in sudo_calls:
            cmd_str = " ".join(call_args)
            self.assertNotIn("state.json", cmd_str)
            self.assertNotIn("settings.json", cmd_str)
            self.assertNotIn("flatpak", cmd_str)


# ===========================================================================
# Main
# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
