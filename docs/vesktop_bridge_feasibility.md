# Vesktop Vencord Bridge Feasibility Report

## Executive Summary

Following the architecture pivot away from legacy Discord RPC authentication, a custom Vencord plugin probe was constructed in `experiments/vencord-voice-probe/` to evaluate voice-channel control feasibility inside Vesktop.

**Go/No-Go Recommendation**: **GO**.
The Vencord Webpack store and action interface provides complete, clean, non-DOM access to all required MVP capabilities without scraping HTML, simulating mouse inputs, or storing Discord user tokens.

---

## Discord Internal Modules & Maintenance Assessment

| Discord Module / Store | Lookup Strategy | Required Methods / Properties | Stability Rating | Fallback / Failure Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **`UserStore`** | `getByStoreName("UserStore")` or `findByProps("getCurrentUser")` | `getCurrentUser()` | **High** | Returns `null`, logs error in diagnostic panel. |
| **`GuildStore`** | `getByStoreName("GuildStore")` or `findByProps("getGuilds")` | `getGuilds()` | **High** | Returns empty array `[]`. |
| **`ChannelStore`** | `getByStoreName("ChannelStore")` or `findByProps("getChannel", "getChannels")` | `getChannels(guildId)`, `getChannel(id)` | **High** | Returns empty channel list `[]`. |
| **`VoiceStateStore`** | `getByStoreName("VoiceStateStore")` or `findByProps("getVoiceChannelId")` | `getVoiceChannelId()` | **Medium-High** | Returns `null` (disconnected). |
| **`MediaEngineStore`** | `getByStoreName("MediaEngineStore")` or `findByProps("isSelfMute", "isSelfDeaf")` | `isSelfMute()`, `isSelfDeaf()` | **Medium-High** | Returns default `{ isMuted: false, isDeafened: false }`. |
| **`VoiceChannelActions`** | `findByProps("selectVoiceChannel")` | `selectVoiceChannel(channelId)` | **Medium** | Throws typed error `VoiceChannelActions unavailable`. |
| **`MediaEngineActions`** | `findByProps("toggleSelfMute", "toggleSelfDeaf")` | `setSelfMute(bool)`, `setSelfDeafen(bool)` | **Medium** | Throws typed error `MediaEngineActions unavailable`. |

---

## Live Operations Demonstrated

Inside Vesktop with Vencord active:

1. **Plugin Initialization**: Plugin loads cleanly via Vencord `definePlugin`.
2. **Current User Detection**: `getCurrentUser()` identifies logged-in Discord tag and ID.
3. **Guild Listing**: `getGuilds()` enumerates all joined servers.
4. **Voice Channel Listing**: `getVoiceChannels(guildId)` filters channels by voice type.
5. **Join Voice Channel**: `joinVoiceChannel(channelId)` dispatches `selectVoiceChannel(id)`. Account connects to channel in Vesktop.
6. **Leave Voice Channel**: `leaveVoiceChannel()` dispatches `selectVoiceChannel(null)` to disconnect.
7. **Mute Toggle**: `setMuted(boolean)` toggles microphone mute state cleanly.
8. **Deafen Toggle**: `setDeafened(boolean)` toggles deafen state cleanly.
9. **Bi-directional State Sync**: External mute/deafen actions performed in Vesktop UI are immediately detected in `getVoiceSettings()`.

---

## Compliance & Prohibited Approach Verification

- **Zero DOM Scraping**: 0 calls to `document.querySelector` or CSS class name lookups.
- **Zero UI Automation**: 0 mouse or keyboard click simulations.
- **Zero Token Handling**: Discord user tokens are never read, stored, or transmitted.
- **Zero Direct REST Calls**: Voice state and actions are routed through Discord's internal action dispatchers.
