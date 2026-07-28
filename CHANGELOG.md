# Changelog

All notable changes to Veckord will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2] - 2026-07-28

### Added
- **Precompiled Vesktop Bridge Release Artifact**: Added `vencord-dist.zip` containing a precompiled Vencord distribution with the `VeckordBridge` user plugin compiled in.
- **Byte-for-Byte Reproducible Builds**: Hardened `scripts/build_release.py` to produce deterministic ZIP archives with normalized timestamps, sorted entries, and normalized file permissions.
- **Official Node.js Checksum Verification**: Automatically fetches and verifies official Node.js `SHASUMS256.txt` manifest before extracting Node build tooling.
- **Strict Vencord Commit & Node/pnpm Version Pinning**: Pinned Vencord commit `83b74e2305cb4718b3d55af5fbd93ade50d2bb50` (v1.15.0), Node.js `v22.14.0`, and pnpm `11.17.0`.
- **Release Build Metadata**: Includes `build-metadata.json` in `vencord-dist.zip` detailing versions, commit SHA, timestamp, plugin identity, socket path, and installer compatibility constraints.
- **Fail-Closed Installer Security**: Updated `scripts/install.py` to download and verify `checksums.sha256` for all release assets (`veckord.zip`, `vencordBridge.zip`, `vencord-dist.zip`) prior to extracting any archive.

## [1.0.1] - 2026-07-28

### Changed
- **Project Rebrand**: Renamed project from Deckord to **Veckord** across all UI strings, plugin manifests, build scripts, and documentation.
- **Settings Auto-Migration**: Automatically migrates existing saved favorite voice channels from `~/.config/deckord/favorites.json` to `~/.config/veckord/favorites.json` upon launch.
- **IPC Socket Fallback**: Connects to primary `/run/user/<uid>/veckord/bridge.sock`, with automatic fallback to legacy `/run/user/<uid>/deckord/bridge.sock` if present.
- **Environment Variable Fallback**: Accepts legacy `DECKORD_DISCORD_CLIENT_ID` and `DECKORD_DISCORD_CLIENT_SECRET` as fallbacks for `VECKORD_*` variables.
- **Duplicate Plugin Self-Cleanup**: Automatically cleans legacy `~/homebrew/plugins/Deckord` directory upon loading to prevent duplicate plugin entries in Decky Loader.

## [1.0.0] - 2026-07-28

### Added
- **Decky Loader Voice Plugin**: Full controller-native Decky Loader plugin UI designed specifically for Steam Gaming Mode.
- **Server & Channel Browser**: Grouped voice channel listing across all joined Discord guilds with smooth controller focus navigation.
- **Favorites Management**: Add, remove, and reorder favorite voice channels with instant fast-join capability from the quick panel.
- **Active Channel Card**: Real-time connected voice channel card with live status indicator, Mute / Unmute, Deafen / Undeafen, and Disconnect actions.
- **Vencord / Vesktop IPC Bridge**: Lightweight, zero-overhead Unix domain socket RPC bridge between Decky Loader backend and Vencord/Vesktop client.
- **Automated Voice State Syncing**: 2-second background polling cycle maintaining sync between Discord stores and Decky UI.
- **Privacy & Security**: Zero secret storage, automatic redaction of sensitive credentials in logs, and portable XDG/Flatpak socket discovery.
