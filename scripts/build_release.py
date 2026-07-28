#!/usr/bin/env python3
"""
Veckord Reproducible Packaging Script v1.0.2.

Builds production Decky Loader plugin package (veckord.zip),
Vencord bridge source package (vencordBridge.zip),
and precompiled Vencord distribution package (vencord-dist.zip).

Includes build metadata, legal notices, SHA-256 checksums, and byte-for-byte reproducibility.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).parent.parent.resolve()

VECOKD_VERSION = "1.1.0"

# Pinned Vencord release tag / commit
PINNED_VENCORD_TAG = "v1.15.0"
PINNED_VENCORD_COMMIT = "83b74e2305cb4718b3d55af5fbd93ade50d2bb50"
VENCORD_REPO_URL = "https://github.com/Vendicated/Vencord.git"

PINNED_NODE_VERSION = "v22.14.0"
NODE_DIST_URL = f"https://nodejs.org/dist/{PINNED_NODE_VERSION}/node-{PINNED_NODE_VERSION}-linux-x64.tar.xz"
NODE_SHASUMS_URL = f"https://nodejs.org/dist/{PINNED_NODE_VERSION}/SHASUMS256.txt"

PINNED_PNPM_VERSION = "11.17.0"

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


def get_source_date_epoch() -> int:
    """Derive deterministic build epoch from SOURCE_DATE_EPOCH or HEAD git commit timestamp."""
    env_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if env_epoch and env_epoch.isdigit():
        return int(env_epoch)
    try:
        res = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip().isdigit():
            return int(res.stdout.strip())
    except Exception:
        pass
    return 1769558400  # Fallback fixed epoch: 2026-01-28 00:00:00 UTC


def epoch_to_iso(epoch: int) -> str:
    dt = datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def epoch_to_zip_datetime(epoch: int) -> Tuple[int, int, int, int, int, int]:
    dt = datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc)
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def fetch_official_node_shasum(version: str, filename: str) -> str:
    """Fetch official Node.js SHASUMS256.txt and parse expected SHA-256 for filename."""
    req = urllib.request.Request(
        NODE_SHASUMS_URL,
        headers={"User-Agent": f"veckord-build/{VECOKD_VERSION}"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        text = r.read().decode("utf-8")
        for line in text.splitlines():
            line = line.strip()
            if filename in line:
                return line.split()[0]
    raise RuntimeError(f"Could not find SHA-256 for {filename} in official Node.js SHASUMS256.txt")


def verify_file_sha256(file_path: Path, expected_sha: str) -> None:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    actual = h.hexdigest().lower()
    if actual != expected_sha.lower():
        raise RuntimeError(
            f"Node archive SHA-256 mismatch!\nExpected: {expected_sha}\nGot:      {actual}"
        )


def ensure_node_env() -> Tuple[Path, Path]:
    """
    Ensure exact pinned Node.js and pnpm versions are available.
    Downloads official Node.js tarball and verifies SHA-256 against official manifest before extraction.
    """
    cache_dir = ROOT_DIR / ".cache" / "node-env"
    cache_dir.mkdir(parents=True, exist_ok=True)

    node_bin = cache_dir / f"node-{PINNED_NODE_VERSION}-linux-x64" / "bin" / "node"
    npm_bin = cache_dir / f"node-{PINNED_NODE_VERSION}-linux-x64" / "bin" / "npm"
    pnpm_bin = cache_dir / f"node-{PINNED_NODE_VERSION}-linux-x64" / "bin" / "pnpm"

    # Check if system node/pnpm match pinned versions
    sys_node = shutil.which("node")
    sys_pnpm = shutil.which("pnpm")

    if sys_node and sys_pnpm:
        try:
            node_ver = subprocess.run([sys_node, "--version"], capture_output=True, text=True).stdout.strip()
            pnpm_ver = subprocess.run([sys_pnpm, "--version"], capture_output=True, text=True).stdout.strip()
            if node_ver == PINNED_NODE_VERSION and pnpm_ver == PINNED_PNPM_VERSION:
                return Path(sys_node), Path(sys_pnpm)
        except Exception:
            pass

    if not node_bin.exists():
        print(f"Downloading official Node.js {PINNED_NODE_VERSION} archive...")
        tar_name = f"node-{PINNED_NODE_VERSION}-linux-x64.tar.xz"
        tar_path = cache_dir / tar_name
        urllib.request.urlretrieve(NODE_DIST_URL, tar_path)

        print("Verifying official Node.js archive SHA-256 checksum...")
        expected_sha = fetch_official_node_shasum(PINNED_NODE_VERSION, tar_name)
        verify_file_sha256(tar_path, expected_sha)
        print("Node.js archive checksum verified OK.")

        print("Extracting Node.js...")
        subprocess.run(["tar", "-xf", str(tar_path), "-C", str(cache_dir)], check=True)

    if not pnpm_bin.exists() and npm_bin.exists():
        print(f"Installing pinned pnpm@{PINNED_PNPM_VERSION}...")
        subprocess.run([str(node_bin), str(npm_bin), "install", "-g", f"pnpm@{PINNED_PNPM_VERSION}"], check=True)

    bin_dir = node_bin.parent
    os.environ["PATH"] = f"{bin_dir}:{os.environ.get('PATH', '')}"

    return node_bin, pnpm_bin


def build_deterministic_zip(
    target_zip: Path,
    source_dir: Path,
    arc_prefix: str = "",
    epoch: Optional[int] = None,
) -> None:
    """Build a byte-for-byte reproducible zip file with sorted entries and normalized timestamps/permissions."""
    if target_zip.exists():
        target_zip.unlink()

    if epoch is None:
        epoch = get_source_date_epoch()
    dt_tuple = epoch_to_zip_datetime(epoch)

    all_files: List[Tuple[Path, str]] = []
    if source_dir.is_file():
        all_files.append((source_dir, arc_prefix or source_dir.name))
    else:
        for root, dirs, files in os.walk(source_dir):
            dirs.sort()
            files.sort()
            for f in files:
                full = Path(root) / f
                rel = full.relative_to(source_dir).as_posix()
                if should_exclude(rel):
                    continue
                arcname = f"{arc_prefix}/{rel}" if arc_prefix else rel
                all_files.append((full, arcname))

    all_files.sort(key=lambda x: x[1])

    with zipfile.ZipFile(target_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for full_path, arcname in all_files:
            info = zipfile.ZipInfo(filename=arcname, date_time=dt_tuple)
            is_dir = arcname.endswith("/")
            perm = 0o755 if is_dir else 0o644
            info.external_attr = (perm | (0o40000 if is_dir else 0o100000)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(full_path, "rb") as f:
                zf.writestr(info, f.read())


def build_vencord_dist(output_zip: Path, epoch: int) -> Dict[str, Any]:
    """Clone Vencord at pinned commit, inject bridge, compile, and package dist."""
    ensure_node_env()

    build_workspace = ROOT_DIR / ".cache" / "vencord-build"
    vencord_dir = build_workspace / "vencord-src"
    build_workspace.mkdir(parents=True, exist_ok=True)

    if not (vencord_dir / ".git").exists():
        print(f"Cloning Vencord from {VENCORD_REPO_URL}...")
        subprocess.run(["git", "clone", VENCORD_REPO_URL, str(vencord_dir)], check=True)

    print(f"Checking out pinned commit {PINNED_VENCORD_COMMIT} ({PINNED_VENCORD_TAG})...")
    subprocess.run(["git", "-C", str(vencord_dir), "fetch", "--all"], check=True)
    subprocess.run(["git", "-C", str(vencord_dir), "checkout", "-f", PINNED_VENCORD_COMMIT], check=True)
    subprocess.run(["git", "-C", str(vencord_dir), "clean", "-fdx"], check=True)

    # Verify commit hash strictly matches pinned commit
    rev = subprocess.run(
        ["git", "-C", str(vencord_dir), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True
    ).stdout.strip()

    if rev != PINNED_VENCORD_COMMIT:
        raise RuntimeError(f"Vencord checkout commit mismatch: expected {PINNED_VENCORD_COMMIT}, got {rev}")

    # Inject bridge into src/userplugins/deckordBridge/
    bridge_dest = vencord_dir / "src" / "userplugins" / "deckordBridge"
    if bridge_dest.exists():
        shutil.rmtree(bridge_dest)
    shutil.copytree(ROOT_DIR / "vencordBridge", bridge_dest)

    # Build Vencord
    print("Building Vencord with injected VeckordBridge...")
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = str(epoch)
    env["BUILD_TIMESTAMP"] = str(epoch * 1000)
    subprocess.run(["pnpm", "install", "--frozen-lockfile"], cwd=vencord_dir, env=env, check=True)
    subprocess.run(["pnpm", "build"], cwd=vencord_dir, env=env, check=True)

    dist_dir = vencord_dir / "dist"
    if not dist_dir.exists() or not (dist_dir / "patcher.js").exists():
        raise RuntimeError("Vencord build failed: dist/patcher.js not found.")

    # Verify bridge plugin compiled in
    patcher_content = (dist_dir / "patcher.js").read_text(encoding="utf-8", errors="ignore")
    renderer_content = (dist_dir / "renderer.js").read_text(encoding="utf-8", errors="ignore")
    if "deckordBridge" not in patcher_content and "deckordBridge" not in renderer_content and "VeckordBridge" not in renderer_content:
        raise RuntimeError("Compiled Vencord dist does not contain the bridge plugin!")

    # Include Veckord LICENSE in dist
    shutil.copy2(ROOT_DIR / "LICENSE", dist_dir / "VECKORD_LICENSE")

    # Ensure minimal package.json is included in dist
    (dist_dir / "package.json").write_text("{}\n", encoding="utf-8")

    # Generate build metadata
    metadata = {
        "veckord_version": VECOKD_VERSION,
        "vencord_commit": PINNED_VENCORD_COMMIT,
        "vencord_tag": PINNED_VENCORD_TAG,
        "node_version": PINNED_NODE_VERSION,
        "pnpm_version": PINNED_PNPM_VERSION,
        "build_timestamp": epoch_to_iso(epoch),
        "internal_plugin_id": "VeckordBridge",
        "socket_path": "/run/user/{uid}/veckord/bridge.sock",
        "min_installer_version": "1.0.2",
    }

    metadata_file = dist_dir / "build-metadata.json"
    metadata_file.write_text(json.dumps(metadata, indent=2))

    # Package dist/ into vencord-dist.zip
    build_deterministic_zip(output_zip, dist_dir, epoch=epoch)
    print(f"Created vencord-dist.zip: {output_zip} ({output_zip.stat().st_size} bytes)")

    return metadata


def calculate_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_checksums(zip_files: List[Path], output_file: Path) -> Dict[str, str]:
    hashes: Dict[str, str] = {}
    lines: List[str] = []
    for zf in zip_files:
        digest = calculate_sha256(zf)
        hashes[zf.name] = digest
        lines.append(f"{digest}  {zf.name}")

    output_file.write_text("\n".join(lines) + "\n")
    print(f"Generated checksums.sha256: {output_file}")
    return hashes


def main() -> int:
    epoch = get_source_date_epoch()
    print(f"=== Veckord Release Packaging Tool v{VECOKD_VERSION} ===")
    print(f"Root directory: {ROOT_DIR}")
    print(f"Build Epoch: {epoch} ({epoch_to_iso(epoch)})")
    print(f"Pinned Vencord Commit: {PINNED_VENCORD_COMMIT} ({PINNED_VENCORD_TAG})")
    print(f"Pinned Node/pnpm: {PINNED_NODE_VERSION} / pnpm@{PINNED_PNPM_VERSION}")

    # 1. Publish standalone install.py asset
    install_py = ROOT_DIR / "install.py"
    shutil.copy2(ROOT_DIR / "scripts" / "install.py", install_py)
    print(f"Created standalone installer asset: {install_py}")

    # 2. Build Decky Plugin package (veckord.zip)
    decky_zip = ROOT_DIR / "veckord.zip"
    tmp_decky = Path(tempfile.mkdtemp(prefix="veckord_pkg_"))
    try:
        for src, arc in DECKY_PACKAGE_FILES:
            src_p = ROOT_DIR / src
            if not src_p.exists():
                continue
            dst_p = tmp_decky / arc
            if src_p.is_dir():
                shutil.copytree(src_p, dst_p)
            else:
                dst_p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_p, dst_p)
        build_deterministic_zip(decky_zip, tmp_decky, epoch=epoch)
        print(f"Created Decky plugin package: {decky_zip} ({decky_zip.stat().st_size} bytes)")
    finally:
        shutil.rmtree(tmp_decky, ignore_errors=True)

    # 3. Build Vencord Bridge source package (vencordBridge.zip)
    bridge_zip = ROOT_DIR / "vencordBridge.zip"
    build_deterministic_zip(bridge_zip, ROOT_DIR / "vencordBridge", arc_prefix="vencordBridge", epoch=epoch)
    print(f"Created Vencord bridge source package: {bridge_zip} ({bridge_zip.stat().st_size} bytes)")

    # 4. Build compiled Vencord distribution package (vencord-dist.zip)
    vencord_dist_zip = ROOT_DIR / "vencord-dist.zip"
    metadata = build_vencord_dist(vencord_dist_zip, epoch=epoch)

    # 5. Generate checksums.sha256 covering install.py and all 3 zips
    checksums_file = ROOT_DIR / "checksums.sha256"
    hashes = generate_checksums([install_py, decky_zip, bridge_zip, vencord_dist_zip], checksums_file)

    print("\n--- Summary of Generated Release Artifacts ---")
    for name, sha in hashes.items():
        size = (ROOT_DIR / name).stat().st_size
        print(f"  {name:20s}  {size:10d} bytes  SHA-256: {sha}")

    print("\n=== Release packaging completed successfully! ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
