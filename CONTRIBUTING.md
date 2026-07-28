# Contributing to Veckord 🤝

Thank you for your interest in contributing to Veckord! We welcome bug reports, documentation improvements, feature suggestions, and pull requests.

---

## 🛠️ Development Workflow

### Prerequisites
- Linux development environment (SteamOS, Bazzite, Fedora, Ubuntu)
- Node.js 22+ & `pnpm`
- Python 3.10+ & `pytest` / `unittest`

### Setup Workspace
```bash
# Clone repository
git clone https://github.com/mattytacos/veckord.git
cd veckord

# Install frontend dependencies
pnpm install

# Build frontend
pnpm build
```

---

## 🧪 Testing Guidelines

Before submitting a pull request, ensure all verification steps pass:

1. **Python Unit Tests**:
   ```bash
   python3 -m unittest discover tests
   ```
2. **Frontend Build**:
   ```bash
   pnpm build
   ```
3. **Vencord Bridge Build**:
   ```bash
   cd vencord-src && pnpm build
   ```

---

## 📜 Pull Request Rules

- **Strict Architecture Boundaries**: Do not scrape Discord DOM elements, do not automate mouse clicks, and do not expose Discord tokens to JavaScript.
- **Redact Credentials**: Never include personal tokens, machine paths, or user credentials in code or logs.
- **Typed Interfaces**: Ensure all TypeScript/Python boundaries use explicit type definitions.
- **Code Style**: Maintain clean GitHub-flavored markdown and existing formatting style.

Thank you for helping make gaming on Steam Deck better! 🎮
