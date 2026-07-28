# Veckord v1.1.0 Release Notes

## Overview

Veckord v1.1.0 introduces **Recent Voice Channels** tracking, **Audio Device & Volume Controls**, **Live Audio Level Metering**, a modular UI component architecture, and a **Display Streaming Feasibility Audit**.

---

## Key Features & Improvements in v1.1.0

### 1. Recent Voice Channels
- Automatically tracks joined voice channels with Most-Recently-Used (MRU) ordering.
- Displays recent channels directly underneath the active voice card for 1-click reconnect.
- Persisted across restarts in `~/.config/veckord/recents.json`.

### 2. Audio Device Selection & Volume Sliders
- Controller-native device selection (`Dropdown`) for input/output audio devices while connected.
- Dual input and output volume sliders (`SliderField`) with smooth controller navigation and debounced IPC updates.

### 3. Live Audio Level Metering
- Real-time input (microphone) and output level meters (`AudioLevelMeters.tsx`) with speaking indicators.

### 4. Modular Component Architecture
- Refactored frontend into focused sub-components (`VoiceCard.tsx`, `RecentChannels.tsx`, `AudioControls.tsx`, `AudioLevelMeters.tsx`, `ConnectionStatus.tsx`).

### 5. Display Streaming Feasibility Audit
- Conducted technical evaluation (`docs/display_streaming_findings.md`) assessing Wayland / PipeWire / `xdg-desktop-portal` behavior in Steam Gaming Mode.

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
wget https://github.com/mattytacos/veckord/releases/download/v1.1.0/install.py
python3 install.py --tag v1.1.0 check
python3 install.py --tag v1.1.0 install
```
