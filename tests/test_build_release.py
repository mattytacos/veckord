"""
tests/test_build_release.py — Tests for build_release.py and release artifact validation.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import build_release as B
import install as I


class TestBuildRelease(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="veckord_test_build_"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_metadata_creation_and_parsing(self):
        """Test build metadata structure and installer parsing."""
        meta_dir = self.tmp / "dist"
        meta_dir.mkdir()
        metadata = {
            "veckord_version": "1.0.2",
            "vencord_commit": "83b74e2305cb4718b3d55af5fbd93ade50d2bb50",
            "vencord_tag": "v1.15.0",
            "node_version": "v22.14.0",
            "pnpm_version": "11.17.0",
            "build_timestamp": "2026-07-28T12:00:00Z",
            "internal_plugin_id": "VeckordBridge",
            "socket_path": "/run/user/{uid}/veckord/bridge.sock",
            "min_installer_version": "1.0.0",
        }
        (meta_dir / "build-metadata.json").write_text(json.dumps(metadata))

        parsed = I.verify_vencord_dist_metadata(meta_dir)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["vencord_commit"], "83b74e2305cb4718b3d55af5fbd93ade50d2bb50")
        self.assertEqual(parsed["internal_plugin_id"], "VeckordBridge")

    def test_installer_version_compatibility_pass(self):
        """Installer version >= min_installer_version passes."""
        meta_dir = self.tmp / "dist"
        meta_dir.mkdir()
        metadata = {
            "min_installer_version": "1.0.0",
        }
        (meta_dir / "build-metadata.json").write_text(json.dumps(metadata))
        with patch.object(I, "INSTALLER_VERSION", "1.0.2"):
            parsed = I.verify_vencord_dist_metadata(meta_dir)
            self.assertIsNotNone(parsed)

    def test_installer_version_compatibility_fail(self):
        """Installer version < min_installer_version raises InstallerError."""
        meta_dir = self.tmp / "dist"
        meta_dir.mkdir()
        metadata = {
            "min_installer_version": "2.0.0",
        }
        (meta_dir / "build-metadata.json").write_text(json.dumps(metadata))
        with patch.object(I, "INSTALLER_VERSION", "1.0.2"):
            with self.assertRaises(I.InstallerError):
                I.verify_vencord_dist_metadata(meta_dir)

    def test_missing_vencord_build_output_raises(self):
        """If Vencord build produces no dist/patcher.js, build_vencord_dist raises error."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="83b74e2305cb4718b3d55af5fbd93ade50d2bb50\n")
            with patch.object(B, "ensure_node_env", return_value=(Path("/bin/node"), Path("/bin/pnpm"))):
                with patch.object(B, "ROOT_DIR", self.tmp):
                    vencord_src = self.tmp / ".cache" / "vencord-build" / "vencord-src"
                    (vencord_src / ".git").mkdir(parents=True)
                    (self.tmp / "vencordBridge").mkdir(parents=True)
                    with self.assertRaises(RuntimeError) as ctx:
                        B.build_vencord_dist(self.tmp / "vencord-dist.zip", epoch=1769558400)
                    self.assertIn("dist/patcher.js not found", str(ctx.exception))

    def test_incorrect_vencord_commit_raises(self):
        """If checked-out Vencord commit != pinned commit, build raises error."""
        with patch("subprocess.run") as mock_run:
            # Return different commit SHA
            mock_run.return_value = MagicMock(returncode=0, stdout="badcommit123456\n")
            with patch.object(B, "ensure_node_env", return_value=(Path("/bin/node"), Path("/bin/pnpm"))):
                with patch.object(B, "ROOT_DIR", self.tmp):
                    vencord_src = self.tmp / ".cache" / "vencord-build" / "vencord-src"
                    (vencord_src / ".git").mkdir(parents=True)
                    with self.assertRaises(RuntimeError) as ctx:
                        B.build_vencord_dist(self.tmp / "vencord-dist.zip", epoch=1769558400)
                    self.assertIn("commit mismatch", str(ctx.exception))

    def test_missing_compiled_bridge_raises(self):
        """If compiled dist files do not contain bridge references, build raises error."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="83b74e2305cb4718b3d55af5fbd93ade50d2bb50\n")
            with patch.object(B, "ensure_node_env", return_value=(Path("/bin/node"), Path("/bin/pnpm"))):
                with patch.object(B, "ROOT_DIR", self.tmp):
                    vencord_src = self.tmp / ".cache" / "vencord-build" / "vencord-src"
                    (vencord_src / ".git").mkdir(parents=True)
                    (self.tmp / "vencordBridge").mkdir(parents=True)
                    (self.tmp / "LICENSE").write_text("MIT")
                    dist_dir = vencord_src / "dist"
                    dist_dir.mkdir(parents=True)
                    (dist_dir / "patcher.js").write_text("// clean patcher without bridge")
                    (dist_dir / "renderer.js").write_text("// clean renderer without bridge")

                    with self.assertRaises(RuntimeError) as ctx:
                        B.build_vencord_dist(self.tmp / "vencord-dist.zip", epoch=1769558400)
                    self.assertIn("does not contain the bridge plugin", str(ctx.exception))

    def test_archive_path_traversal_detection(self):
        """Validate that path traversal in zip archives is detected and rejected."""
        dest = self.tmp / "extracted"
        dest.mkdir()
        bad_zip = self.tmp / "bad.zip"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../traversal.txt", b"evil")
        bad_zip.write_bytes(buf.getvalue())

        with zipfile.ZipFile(bad_zip) as zf:
            with self.assertRaises(ValueError):
                I.validate_zip(zf, dest)

    def test_invalid_artifact_checksum(self):
        """Verify checksum mismatch detection."""
        f = self.tmp / "file.zip"
        f.write_bytes(b"content")
        with self.assertRaises(I.InstallerError):
            I.verify_checksum(f, "badhash" * 8)

    def test_missing_checksum_file_fails_closed(self):
        """If checksums.sha256 is missing, verify_release_checksums fails closed immediately."""
        dl_dir = self.tmp / "downloads"
        dl_dir.mkdir()
        with self.assertRaises(I.InstallerError) as ctx:
            I.verify_release_checksums(dl_dir)
        self.assertIn("Missing checksums.sha256", str(ctx.exception))

    def test_missing_asset_fails_closed(self):
        """If a required zip asset is missing from download dir or manifest, verification fails closed."""
        dl_dir = self.tmp / "downloads"
        dl_dir.mkdir()
        v_data = b"data"
        v_hash = hashlib.sha256(v_data).hexdigest()
        (dl_dir / "checksums.sha256").write_text(f"{v_hash}  veckord.zip\n")
        (dl_dir / "veckord.zip").write_bytes(v_data)

        with self.assertRaises(I.InstallerError) as ctx:
            I.verify_release_checksums(dl_dir)
        self.assertIn("missing", str(ctx.exception).lower())

    def test_incorrect_checksum_fails_closed(self):
        """If an asset hash does not match checksums.sha256, verification fails closed."""
        dl_dir = self.tmp / "downloads"
        dl_dir.mkdir()
        (dl_dir / "checksums.sha256").write_text(
            "badhash  veckord.zip\nbadhash  vencordBridge.zip\nbadhash  vencord-dist.zip\n"
        )
        (dl_dir / "veckord.zip").write_bytes(b"data1")
        (dl_dir / "vencordBridge.zip").write_bytes(b"data2")
        (dl_dir / "vencord-dist.zip").write_bytes(b"data3")

        with self.assertRaises(I.InstallerError):
            I.verify_release_checksums(dl_dir)

    def test_no_archive_extracted_before_checksum_pass(self):
        """Confirm that cmd_install fails before creating any plugin dir if checksum verification fails."""
        dl_dir = self.tmp / "downloads"
        dl_dir.mkdir()
        (dl_dir / "checksums.sha256").write_text("invalid checksums")
        target_plugin_dir = self.tmp / "homebrew" / "plugins" / "Deckord"

        with patch.object(I, "is_bazzite", return_value=True), \
             patch.object(I, "is_vesktop_installed", return_value=True), \
             patch.object(I, "is_decky_installed", return_value=True), \
             patch.object(I, "is_vesktop_running", return_value=False), \
             patch.object(I, "DECKY_PLUGIN_DIR", target_plugin_dir), \
             patch.object(I, "download_release_assets", return_value=dl_dir):
            with self.assertRaises(I.InstallerError):
                I.cmd_install(tag="v1.0.2", interactive=False)
            # Ensure plugin directory was never created
            self.assertFalse(target_plugin_dir.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
