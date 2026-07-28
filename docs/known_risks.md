# Veckord Known Risks & Mitigation Matrix

## 1. Architecture & Maintenance Risks

| Risk Area | Risk Description | Impact | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **Discord Internal Webpack Changes** | Discord updates may rename internal Webpack store properties or action method signatures. | Medium | Isolate all Webpack module lookups inside a single adapter file (`discordAdapter.ts`). Provide defensive fallback lookups and structured error reporting when a store method is unresolved. |
| **Vencord Plugin Updates** | Changes to Vencord's plugin API (`definePlugin`) or build environment. | Low | Rely only on standard Vencord `definePlugin` and `Webpack` finder methods (`getByProps`, `getByStoreName`, `common`). |
| **Local Bridge Socket Security** | Untrusted local processes could attempt to connect to the Vencord bridge socket. | Medium | Restrict parent directory permissions to `0700` (`rwx------`) and socket file to `0600` (`rw-------`) under `$XDG_RUNTIME_DIR/veckord/`. Perform strict input validation, method allowlist, and 64 KB request size ceiling. |
| **Vesktop Process Lifecycle** | Vesktop client closed or restarted while Decky plugin is active. | Low | Decky Python backend auto-reconnects with backoff when local Unix socket connection drops. Stale socket cleanup on server startup/shutdown prevents orphan sockets. |

---

## 2. Prohibited Approaches Checklist

- [x] **No DOM Scraping**: Never query HTML elements, CSS selectors, or class names.
- [x] **No UI Automation**: Never simulate mouse clicks or synthetic keyboard events.
- [x] **No Direct Token Access**: Never extract or transmit Discord user tokens.
- [x] **No Direct REST API Calls**: Never invoke Discord HTTP REST endpoints directly.
- [x] **No Selfbots**: Never perform user automated actions (messages, DMs, reactions).
- [x] **No Scope Expansion**: Exclude chat, DMs, video, streaming, or notifications.
