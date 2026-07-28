# Security Policy 🔒

## Supported Versions

Only the latest release of Deckord receives security updates.

| Version | Supported |
| :--- | :--- |
| 0.1.x | ✅ Supported |
| < 0.1.0 | ❌ Unsupported |

## Reporting a Vulnerability

If you discover a security vulnerability in Deckord, please follow responsible disclosure guidelines:

1. **Do NOT open a public issue.**
2. Send a private report detailing the issue and steps to reproduce via GitHub Private Vulnerability Reporting or directly to the repository maintainer.
3. We will acknowledge receipt of your report within 48 hours and provide a timeline for a fix.

## Security Guarantees

- **No Remote Tokens**: Deckord never sends your Discord token to third-party servers.
- **Local IPC Scope**: All IPC occurs over local Unix domain stream sockets (`AF_UNIX`) bound to the current user's runtime directory (`/run/user/<uid>`).
- **Log Sanitization**: Logs automatically redact passwords, tokens, and authorization parameters.
