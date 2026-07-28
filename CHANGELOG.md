# Changelog

All notable changes to Veckord will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-28

### Added
- **Decky Loader Voice Plugin**: Full controller-native Decky Loader plugin UI designed specifically for Steam Gaming Mode.
- **Server & Channel Browser**: Grouped voice channel listing across all joined Discord guilds with smooth controller focus navigation.
- **Favorites Management**: Add, remove, and reorder favorite voice channels with instant fast-join capability from the quick panel.
- **Active Channel Card**: Real-time connected voice channel card with live status indicator, Mute / Unmute, Deafen / Undeafen, and Disconnect actions.
- **Vencord / Vesktop IPC Bridge**: Lightweight, zero-overhead Unix domain socket RPC bridge between Decky Loader backend and Vencord/Vesktop client.
- **Automated Voice State Syncing**: 2-second background polling cycle maintaining sync between Discord stores and Decky UI.
- **Privacy & Security**: Zero secret storage, automatic redaction of sensitive credentials in logs, and portable XDG/Flatpak socket discovery.
