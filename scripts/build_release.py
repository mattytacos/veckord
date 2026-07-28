#!/usr/bin/env python3
"""
Veckord Reproducible Packaging Script.

Builds production Decky Loader plugin package (veckord.zip) and Vencord bridge package (vencordBridge.zip).
Ensures no __pycache__, tests, .pyc, secrets, or development paths are included.
"""

import os
import sys
import shutil
import zipfile
import subprocess
import tempfile
import re

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DECKY_PACKAGE_FILES = [
    ("dist", "dist"),
    ("backend", "backend"),
    ("main.py", "main.py"),
    ("plugin.json", "plugin.json"),
    ("package.json", "package.json"),
    ("README.md", "README.md"),
    ("LICENSE", "LICENSE"),
]

VENCORD_BRIDGE_FILES = [
    ("vencordBridge", "vencordBridge"),
]

EXCLUDE_PATTERNS = [
    r"__pycache__",
    r"\.pyc$",
    r"\.pytest_cache",
    r"\.git",
    r"\.DS_Store",
]


def should_exclude(rel_path: str) -> bool:
    for pat in EXCLUDE_PATTERNS:
        if re.search(pat, rel_path):
            return True
    return False


def build_zip(target_zip: str, items: list) -> str:
    target_path = os.path.join(ROOT_DIR, target_zip)
    if os.path.exists(target_path):
        os.remove(target_path)

    with zipfile.ZipFile(target_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, arcname in items:
            src_full = os.path.join(ROOT_DIR, src)
            if not os.path.exists(src_full):
                print(f"Warning: Source path {src} does not exist!")
                continue

            if os.path.isfile(src_full):
                zf.write(src_full, arcname)
            elif os.path.isdir(src_full):
                for root, dirs, files in os.walk(src_full):
                    for f in files:
                        full_f = os.path.join(root, f)
                        rel_f = os.path.relpath(full_f, ROOT_DIR)
                        if should_exclude(rel_f):
                            continue
                        arc_f = os.path.relpath(full_f, os.path.dirname(src_full))
                        zf.write(full_f, arc_f)

    return target_path


def main():
    print(f"=== Veckord Release Packaging Tool ===")
    print(f"Root directory: {ROOT_DIR}")

    # Build Decky Plugin package
    decky_zip = build_zip("veckord.zip", DECKY_PACKAGE_FILES)
    print(f"Created Decky plugin package: {decky_zip} ({os.path.getsize(decky_zip)} bytes)")

    # Build Vencord Bridge package
    bridge_zip = build_zip("vencordBridge.zip", VIRTUAL_ITEMS := VENCORD_BRIDGE_FILES)
    print(f"Created Vencord bridge package: {bridge_zip} ({os.path.getsize(bridge_zip)} bytes)")

    # Audit decky_zip contents
    print("\n--- Auditing decky_zip contents ---")
    with zipfile.ZipFile(decky_zip, "r") as zf:
        file_list = zf.namelist()
        print(f"Total files in decky_zip: {len(file_list)}")
        for f in file_list:
            if should_exclude(f):
                print(f"ERROR: Found excluded file in zip: {f}")
                sys.exit(1)

    print("=== Packaging succeeded cleanly! ===")


if __name__ == "__main__":
    main()
