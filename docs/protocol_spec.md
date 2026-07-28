# Discord RPC Binary Protocol Specification

## Overview

Discord RPC over Unix domain sockets uses a binary packet format consisting of an 8-byte little-endian header followed by a UTF-8 encoded JSON payload.

---

## Important Distinction: Handshake vs. Authentication

- **Handshake (`READY` Event)**:
  - Sent immediately after opening the Unix socket using opcode `0` (`HANDSHAKE`).
  - Proves that the socket connection to the local Discord client and binary protocol framing succeeded.
  - **Does NOT mean the user is authenticated.** No OAuth tokens or user permissions are granted by `READY` alone.

- **User Authorization & Authentication (`AUTHORIZE` / `AUTHENTICATE`)**:
  - Requires sending opcode `1` (`FRAME`) with `cmd="AUTHORIZE"` and scopes `["rpc", "identify"]`.
  - Triggers an in-app authorization dialog in the Discord GUI for the user to approve.
  - Returns an authorization code, which must be exchanged for an OAuth access token over HTTP.
  - Full authentication is established only when `cmd="AUTHENTICATE"` is sent with a valid `access_token` and returns granted scopes including `rpc` and `identify`.

---

## Binary Frame Structure

```text
+-----------------------+-----------------------+-----------------------------------+
| Opcode (uint32 LE)    | Payload Length        | Payload (UTF-8 JSON)              |
| 4 Bytes               | 4 Bytes (uint32 LE)   | N Bytes                           |
+-----------------------+-----------------------+-----------------------------------+
```

### Struct Layout
- **Header Layout**: `<II` (two 32-bit unsigned little-endian integers).
- **Header Size**: 8 bytes.

---

## Opcodes

| Opcode Name | Value | Purpose |
| :--- | :--- | :--- |
| `HANDSHAKE` | `0` | Sent by client to establish connection with `client_id` and protocol version `v`. |
| `FRAME` | `1` | Used for RPC commands, events, dispatch payloads, and responses. |
| `CLOSE` | `2` | Sent when connection is being terminated. |
| `PING` | `3` | Heartbeat / ping check. |
| `PONG` | `4` | Response to `PING`. |

---

## Payload Size Limits & Defensive Rules

- **`MAX_PAYLOAD_SIZE`**: `16 * 1024 * 1024` bytes (16 MB / 16,777,216 bytes).
- **Rationale**: Discord RPC payloads (guild lists, voice state updates) are typically small (a few KB), but large guild structures or channel trees may reach hundreds of KB. A 16 MB ceiling prevents memory exhaustion attacks from untrusted socket buffers while accommodating any legitimate Discord RPC frame.
- **Unchecked Allocation Defense**: The parser verifies `length <= MAX_PAYLOAD_SIZE` before reserving memory or reading payload bytes.

---

## Exception Hierarchy

All protocol errors derive from `ProtocolError`:

- `ProtocolError`
  - `MalformedHeaderError`: Raised when header cannot be unpacked.
  - `UnsupportedOpcodeError`: Raised when an unknown opcode integer is encountered.
  - `OversizedPayloadError`: Raised when declared payload length exceeds `MAX_PAYLOAD_SIZE`.
  - `InvalidUTF8Error`: Raised when payload bytes cannot be decoded as strict UTF-8.
  - `InvalidJSONError`: Raised when payload text is not valid JSON.

---

## Stream Parser Behavior (`FrameParser`)

1. **Buffer Accumulation**: Incoming bytes are appended to an internal `bytearray` buffer (`feed()`).
2. **Partial Read Support**: If the buffer contains `< 8` bytes, parsing pauses until more header bytes arrive.
3. **Partial Payload Support**: If header declares `N` bytes payload, but `< N` bytes exist in buffer after header, parsing pauses until remaining payload bytes arrive.
4. **Multi-Frame Processing**: If multiple complete frames arrive in a single buffer chunk, `pop_all_frames()` returns all completed `ParsedFrame` objects sequentially.
5. **Buffer State Integrity**: Incomplete trailing bytes remain safely stored in the parser buffer across invocations.
