# Veckord Installation Guide v1.0.2

**Veckord** is a controller-native Decky Loader plugin that controls Discord voice channels from the Steam Gaming Mode quick-access panel. It works exclusively with **Vesktop** (Flatpak `dev.vencord.Vesktop`) and **Decky Loader** on **Bazzite**.

---

## Requirements

| Requirement | Notes |
|---|---|
| **Bazzite** | Only Bazzite is supported (`ID=bazzite` in `/etc/os-release`) |
| **Vesktop Flatpak** | `flatpak install flathub dev.vencord.Vesktop` |
| **Decky Loader** | Installed from https://decky.xyz |
| **Normal user account** | Do NOT run as root |
| **Python 3.8+** | Pre-installed on Bazzite |
| **Internet access** | For downloading release assets |

---

## Release Assets (v1.0.2)

Each GitHub release at `https://github.com/mattytacos/veckord/releases` contains:

| Asset | Contents |
|---|---|
| `veckord.zip` | Compiled Decky plugin (`dist/`, `backend/`, `main.py`, manifests) |
| `vencordBridge.zip` | Vencord bridge plugin source files (`index.tsx`, `native.ts`, etc.) |
| `vencord-dist.zip` | Precompiled Vencord distribution with `VeckordBridge` compiled in (`patcher.js`, `renderer.js`, `build-metadata.json`, etc.) |
| `checksums.sha256` | SHA-256 digests of all release zip files |

---

## Quick Start

### 1. Check current state

```bash
python3 ~/Documents/deckord/scripts/install.py check
```

### 2. Fresh install

```bash
# Close Vesktop first, then:
python3 ~/Documents/deckord/scripts/install.py --tag v1.0.2 install
```

### 3. Update to a new release

```bash
python3 ~/Documents/deckord/scripts/install.py --tag v1.0.2 update
```

### 4. Repair broken configuration

```bash
python3 ~/Documents/deckord/scripts/install.py repair
```

---

## Reproducible Build System

Veckord v1.0.2 features a byte-for-byte reproducible release build script (`scripts/build_release.py`):

- **Pinned Vencord commit**: `83b74e2305cb4718b3d55af5fbd93ade50d2bb50` (Vencord `v1.15.0`)
- **Pinned build toolchain**: Node.js `v22.14.0` (SHA-256 verified against official Node manifest) and `pnpm@11.17.0`
- **Deterministic archives**: Entry paths sorted alphabetically, permissions normalized to `0o644`/`0o755`, zip timestamps derived from commit epoch/`SOURCE_DATE_EPOCH`

To build release assets locally:

```bash
python3 scripts/build_release.py
```

Outputs:
- `veckord.zip`
- `vencordBridge.zip`
- `vencord-dist.zip`
- `checksums.sha256`

---

## Verification & Safety Controls

The installer enforcing fail-closed security:
1. Downloads `checksums.sha256`, `veckord.zip`, `vencordBridge.zip`, and `vencord-dist.zip`.
2. Verifies SHA-256 hashes of **all** assets against `checksums.sha256` before opening or extracting any archive.
3. Parses `build-metadata.json` from `vencord-dist.zip` and verifies installer compatibility constraints (`min_installer_version <= 1.0.2`).
4. Rejects zip files containing symlinks, absolute paths, or directory traversal (`../`).
5. Performs timestamped backup of replaced plugin/vencord directories prior to writing.
6. Automatically rolls back all filesystem and config modifications if any step fails.

---

## Running Tests

```bash
cd ~/Documents/deckord
python3 -m unittest discover tests
```

Tests run in isolated temporary directories using mocked subprocess/download calls. The live system is never touched.
