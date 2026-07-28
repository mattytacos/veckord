# Veckord v1.0.3 Release Notes

## Overview

Veckord v1.0.3 resolves installation permission failures on Bazzite systems where the Decky Loader plugins root directory (`~/homebrew/plugins/Deckord`) is owned by `root:root`.

---

## Key Improvements in v1.0.3

### 1. Targeted Sudo Privilege Handling
- All operations modifying `~/homebrew/plugins/Deckord` now use narrowly-scoped `sudo` subprocess commands (`sudo mv`, `sudo mkdir`, `sudo cp -a`).
- Unprivileged operations (downloading release assets, validating checksums, editing `state.json` and `settings.json`, Flatpak overrides, favorites management) remain 100% user-owned.

### 2. Atomic Same-Filesystem Backups
- Backups during Decky plugin updates are created directly at `~/homebrew/plugins/.veckord-backup-<timestamp>`.
- Enables instant, atomicSame-filesystem renames without `shutil.move` cross-device or permission errors.

### 3. Sudo Preflight Authorization Check
- Installer verifies cached sudo authorization via `check_sudo_preflight()` before making any system modifications.
- Fails closed in non-interactive environments if sudo credentials are unavailable.

### 4. Post-Install Plugin Verification
- Automatically verifies installed plugin manifests (`plugin.json`, `package.json`, `main.py`) after restarting `plugin_loader.service`.
- Immediately triggers clean rollback if verification fails.

---

## Release Assets

| Asset | Description |
|---|---|
| `install.py` | Standalone Python 3 installer script |
| `veckord.zip` | Production Decky Loader plugin package |
| `vencordBridge.zip` | Vencord bridge plugin TypeScript source package |
| `vencord-dist.zip` | Precompiled Vencord distribution with `VeckordBridge` |
| `checksums.sha256` | SHA-256 manifest for all release assets |

---

## Quick Start Command

```bash
wget https://github.com/mattytacos/veckord/releases/download/v1.0.3/install.py
python3 install.py --tag v1.0.3 check
python3 install.py --tag v1.0.3 install
```
