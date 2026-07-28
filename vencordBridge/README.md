# Deckord Vencord Voice Controller Feasibility Probe

This directory contains a standalone Vencord custom plugin experiment for validating Discord voice channel membership, state detection, and control through Vesktop/Vencord Webpack stores.

## Features Verified

- **User Identification**: Read `UserStore.getCurrentUser()`
- **Guild Listing**: Read `GuildStore.getGuilds()`
- **Voice Channels**: Filter voice channels via `ChannelStore`
- **Active Voice State**: Read active channel via `VoiceStateStore.getVoiceChannelId()` and `MediaEngineStore`
- **Voice Actions**:
  - `joinVoiceChannel(channelId)` via `VoiceChannelActions.selectVoiceChannel(channelId)`
  - `leaveVoiceChannel()` via `VoiceChannelActions.selectVoiceChannel(null)`
  - `setMuted(boolean)` via `MediaEngineActions.setSelfMute(boolean)`
  - `setDeafened(boolean)` via `MediaEngineActions.setSelfDeafen(boolean)`

## Prohibited Approach Guarantees

- Zero DOM element queries (`document.querySelector`, `getElementsByClassName`).
- Zero CSS selector dependencies.
- Zero simulated mouse or keyboard clicks.
- Zero raw REST API calls or user token access.
- Zero chat, DM, or messaging code.

## Installation in Vesktop

1. Copy `experiments/vencord-voice-probe/` into your Vencord user plugins directory (`~/.config/vesktop/plugins/` or `src/userplugins/`).
2. Build Vencord or enable user plugins in Vesktop Settings.
3. Enable `DeckordVoiceProbe` in Vencord Plugins settings.
4. Open the plugin settings panel to view live user state, server list, voice channels, and diagnostic action buttons.
