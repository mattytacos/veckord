# Veckord v1.0.2 Release Notes

## Overview

Veckord v1.0.2 introduces a **precompiled Vesktop bridge distribution (`vencord-dist.zip`)**, **byte-for-byte reproducible release builds**, **official Node.js manifest checksum verification**, and **fail-closed installer security**.

---

## What's New in v1.0.2

### 1. Precompiled Vesktop Bridge Artifact (`vencord-dist.zip`)
- Eliminates the need for end users to install Node.js, `pnpm`, or build Vencord from source.
- Contains a full, precompiled Vencord distribution (v1.15.0) with the `VeckordBridge` user plugin compiled directly into `patcher.js` and `renderer.js`.
- Includes `build-metadata.json` containing build timestamps, commit SHAs, plugin IDs, and minimum installer version bounds.

### 2. Byte-for-Byte Reproducible Builds
- `scripts/build_release.py` produces byte-for-byte identical ZIP archives across separate build runs.
- Normalizes entry ordering, file modes (`0o644`/`0o755`), and derives zip timestamps from git commit epoch or `SOURCE_DATE_EPOCH`.

### 3. Supply-Chain & Build Hardening
- Automatically downloads official Node.js `SHASUMS256.txt` manifest and verifies `node-v22.14.0-linux-x64.tar.xz` hash before extraction.
- Strictly pins toolchain versions:
  - **Vencord commit**: `83b74e2305cb4718b3d55af5fbd93ade50d2bb50` (`v1.15.0`)
  - **Node.js**: `v22.14.0`
  - **pnpm**: `11.17.0`

### 4. Fail-Closed Installer Verification
- `scripts/install.py` downloads `checksums.sha256`, `veckord.zip`, `vencordBridge.zip`, and `vencord-dist.zip`.
- Verifies all SHA-256 hashes against `checksums.sha256` before opening or extracting any archive.
- Immediately aborts and cleans up if any checksum, file, or metadata check fails.

---

## Release Assets

| Asset | Description |
|---|---|
| `veckord.zip` | Production Decky Loader plugin package |
| `vencordBridge.zip` | Vencord bridge plugin TypeScript source package |
| `vencord-dist.zip` | Precompiled Vencord distribution with `VeckordBridge` |
| `checksums.sha256` | SHA-256 manifest for all release zip files |

---

## Quick Install Command

```bash
python3 scripts/install.py --tag v1.0.2 install
```
