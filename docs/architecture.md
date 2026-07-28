# Deckord Architecture Specification

## Overview & Architecture Pivot

Deckord is a controller-native Decky plugin for Steam Gaming Mode (target: Bazzite) that controls voice-channel membership, mute/deafen, and voice state in an already-running Vesktop client.

### Architecture Audit & Decision Record
- **IPC Sockets & Framing**: Discord Unix IPC socket discovery (`/run/user/$UID/discord-ipc-0`), binary framing (8-byte LE header), and connection handshakes were successfully completed in Phases 1–3.
- **Legacy RPC Authentication Status**: **BLOCKED**. Discord's local RPC `AUTHORIZE` command returns contradictory errors (`Missing "redirect_uri"` vs `Redirect URI cannot be used`) and the legacy `/oauth2/token/rpc` endpoint returns HTTP 404. Legacy RPC work is preserved in `backend/discord_rpc/` as an experimental artifact.
- **Primary Architecture Pivot**: **Vesktop / Vencord Local Bridge**. Deckord uses Vesktop as the primary Discord client. A custom Vencord plugin running inside Vesktop exposes a narrow, authenticated local Unix domain socket bridge (`$XDG_RUNTIME_DIR/deckord/bridge.sock`) to Deckord's backend.

---

## Component Layout

```text
+-------------------------------------------------------------+
|                     Steam Gaming Mode                       |
|  +-------------------------------------------------------+  |
|  | Decky Frontend (React, TypeScript, @decky/ui)        |  |
|  +---------------------------+---------------------------+  |
+------------------------------|------------------------------+
                               | IPC (Decky plugin API)
+------------------------------v------------------------------+
| Decky Backend (Python)                                      |
|  - Communicates with Vencord Bridge over local Unix socket  |
|  - Redacts credentials, manages state & structured errors  |
+------------------------------+------------------------------+
                               | Authenticated Local Unix Domain Socket ($XDG_RUNTIME_DIR/deckord/bridge.sock)
+------------------------------v------------------------------+
| Vesktop Application (Flatpak / Native Host)                |
|  +-------------------------------------------------------+  |
|  | Deckord Vencord Native Server (`native.ts`)             |  |
|  |  - Listens on local Unix socket (Mode 0600)           |  |
|  |  - Enforces allowlist, line-framing & 64KB limits     |  |
|  +---------------------------+---------------------------+  |
|                              | IPC Bridge                   |
|  +---------------------------v---------------------------+  |
|  | Deckord Vencord Renderer (`index.tsx`, `adapter.ts`)   |  |
|  |  - Interfaces with Discord Webpack Stores & Actions   |  |
|  +-------------------------------------------------------+  |
|  | Discord Client Engine                                 |  |
|  |  - Handles Discord login, servers, channels, voice    |  |
|  |    transport, microphone, audio output, permissions   |  |
|  +-------------------------------------------------------+  |
+-------------------------------------------------------------+
```

---

## Bridge Socket & Protocol Specification

- **Socket Path**: `$XDG_RUNTIME_DIR/deckord/bridge.sock` (Fallback: `/run/user/$UID/deckord/bridge.sock`).
- **Parent Directory**: Mode `0700` (`rwx------`).
- **Socket Permissions**: Mode `0600` (`rw-------`).
- **Protocol**: Newline-delimited JSON (`\n`). Max request size: `64 KB`. Version: `1`.
- **Supported Methods**: `ping`, `getStatus`, `getGuilds`, `getVoiceChannels`, `getCurrentVoiceChannel`, `getVoiceSettings`, `joinVoiceChannel`, `leaveVoiceChannel`, `setMuted`, `setDeafened`.
