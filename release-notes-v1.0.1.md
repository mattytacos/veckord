# Veckord v1.0.1 Release Notes 🎮🎧

`v1.0.1` is the first official release under the new project name **Veckord** (formerly Deckord).

> **Note on Versioning**: `v1.0.0` points to the initial pre-rename release. `v1.0.1` incorporates the full project rebrand to Veckord along with seamless upgrade and backward-compatibility fallbacks for existing installations.

---

### 🌟 What's New in v1.0.1

- **Official Project Rebrand**: Renamed to **Veckord** across all UI elements, Decky Loader manifests, logs, and documentation.
- **Automatic Favorites Migration**: Saved favorites in `~/.config/deckord/favorites.json` automatically migrate to `~/.config/veckord/favorites.json` on first launch.
- **Legacy Socket Fallback**: Primary communication occurs over `/run/user/<uid>/veckord/bridge.sock`, with seamless fallback to `/run/user/<uid>/deckord/bridge.sock` if using an existing bridge instance.
- **Legacy Environment Variable Fallback**: Accepts `DECKORD_DISCORD_CLIENT_ID` and `DECKORD_DISCORD_CLIENT_SECRET` as fallbacks for `VECKORD_*` variables.
- **Duplicate Plugin Self-Cleanup**: Automatically cleans legacy `~/homebrew/plugins/Deckord` directory upon launch to prevent duplicate plugin entries in Decky Loader.

---

### 📦 Installation & Upgrade Instructions

#### Decky Loader Plugin
1. Download `veckord.zip` from the release assets below.
2. Extract or install into `~/homebrew/plugins/Veckord`.
3. Restart or reload Decky Loader in Steam Gaming Mode.

#### Vencord / Vesktop Bridge
1. Download `vencordBridge.zip` or use `vencordBridge/` from the repository.
2. Place `vencordBridge` into Vencord userplugins (`Vencord/src/userplugins/veckordBridge`).
3. Enable **VeckordBridge** in Vencord Plugin Settings inside Vesktop.
