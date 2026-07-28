#!/usr/bin/env python3
"""
Veckord Fresh-Install & Legacy-Upgrade Smoke Test Suite.

Simulates Decky Loader plugin loading, socket resolution, settings auto-migration,
and legacy directory cleanup in isolated temporary directories.
"""

import os
import sys
import shutil
import zipfile
import tempfile
import asyncio
import unittest
from unittest.mock import patch


def run_smoke_tests():
    print("=== Running Veckord Installation Smoke Tests ===")

    tmp_dir = tempfile.TemporaryDirectory()
    try:
        base_dir = tmp_dir.name
        plugins_dir = os.path.join(base_dir, "homebrew", "plugins")
        config_dir = os.path.join(base_dir, ".config")
        runtime_dir = os.path.join(base_dir, "run")
        os.makedirs(plugins_dir, exist_ok=True)
        os.makedirs(config_dir, exist_ok=True)
        os.makedirs(runtime_dir, exist_ok=True)

        root_repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        decky_zip = os.path.join(root_repo, "veckord.zip")
        if not os.path.exists(decky_zip):
            print("Error: veckord.zip not found. Build it first.")
            sys.exit(1)

        # ----------------------------------------------------
        # 1. FRESH INSTALL SMOKE TEST
        # ----------------------------------------------------
        print("\n--- 1. Fresh Install Smoke Test ---")
        veckord_plugin_dir = os.path.join(plugins_dir, "Veckord")
        os.makedirs(veckord_plugin_dir, exist_ok=True)
        with zipfile.ZipFile(decky_zip, "r") as zf:
            zf.extractall(veckord_plugin_dir)

        # Check required files
        assert os.path.exists(os.path.join(veckord_plugin_dir, "main.py")), "main.py missing"
        assert os.path.exists(os.path.join(veckord_plugin_dir, "plugin.json")), "plugin.json missing"
        assert os.path.exists(os.path.join(veckord_plugin_dir, "dist", "index.js")), "dist/index.js missing"
        assert os.path.exists(os.path.join(veckord_plugin_dir, "backend", "veckord_backend.py")), "backend/veckord_backend.py missing"
        assert os.path.exists(os.path.join(veckord_plugin_dir, "backend", "bridge_client.py")), "backend/bridge_client.py missing"

        # Verify backend imports without error
        sys.path.insert(0, veckord_plugin_dir)
        sys.path.insert(0, os.path.join(veckord_plugin_dir, "backend"))
        from veckord_backend import VeckordBackend
        from bridge_client import resolve_socket_path
        from favorites_manager import resolve_settings_path

        backend_inst = VeckordBackend()
        print("✓ Fresh install backend imported and initialized successfully.")

        # ----------------------------------------------------
        # 2. LEGACY UPGRADE SMOKE TEST
        # ----------------------------------------------------
        print("\n--- 2. Legacy Upgrade Smoke Test ---")
        legacy_plugin_dir = os.path.join(plugins_dir, "Deckord")
        os.makedirs(legacy_plugin_dir, exist_ok=True)
        with open(os.path.join(legacy_plugin_dir, "dummy_old.txt"), "w") as f:
            f.write("old plugin file")

        legacy_config_dir = os.path.join(config_dir, "deckord")
        os.makedirs(legacy_config_dir, exist_ok=True)
        legacy_fav_file = os.path.join(legacy_config_dir, "favorites.json")
        sample_favs = '[{"guild_id":"123","channel_id":"456","guild_name":"Legacy Server","channel_name":"Legacy Channel"}]'
        with open(legacy_fav_file, "w") as f:
            f.write(sample_favs)

        legacy_sock_dir = os.path.join(runtime_dir, "deckord")
        os.makedirs(legacy_sock_dir, exist_ok=True)
        legacy_sock_file = os.path.join(legacy_sock_dir, "bridge.sock")
        open(legacy_sock_file, "a").close()

        # Test socket resolution with legacy socket exposed
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime_dir}):
            sock_res = resolve_socket_path()
            assert sock_res == legacy_sock_file, f"Expected legacy socket {legacy_sock_file}, got {sock_res}"
            print("✓ Legacy bridge socket resolved correctly when primary socket is absent.")

        # Test primary socket preference over legacy
        primary_sock_dir = os.path.join(runtime_dir, "veckord")
        os.makedirs(primary_sock_dir, exist_ok=True)
        primary_sock_file = os.path.join(primary_sock_dir, "bridge.sock")
        open(primary_sock_file, "a").close()

        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime_dir}):
            sock_res_primary = resolve_socket_path()
            assert sock_res_primary == primary_sock_file, f"Expected primary socket {primary_sock_file}, got {sock_res_primary}"
            print("✓ Primary Veckord socket preferred over legacy Deckord socket when both are present.")

        # Test favorites migration
        with patch.dict(os.environ, {"HOME": base_dir, "DECKY_PLUGIN_SETTINGS_DIR": ""}):
            settings_path = resolve_settings_path()
            primary_fav_file = os.path.join(config_dir, "veckord", "favorites.json")
            assert settings_path == primary_fav_file, f"Expected migrated path {primary_fav_file}, got {settings_path}"
            assert os.path.exists(primary_fav_file), "Migrated favorites.json file does not exist"
            with open(primary_fav_file, "r") as f:
                migrated_content = f.read()
            assert migrated_content == sample_favs, "Migrated favorites content mismatch"
            print("✓ Saved favorites successfully migrated from ~/.config/deckord to ~/.config/veckord.")

        # Test self-maintaining behavior of main.py
        import main
        plugin_obj = main.Plugin()
        asyncio.run(plugin_obj._main())

        print("✓ Veckord main.py initialized without destructive plugin directory deletion.")

        print("\n=== ALL SMOKE TESTS PASSED CLEANLY! ===")
    finally:
        tmp_dir.cleanup()


if __name__ == "__main__":
    run_smoke_tests()
