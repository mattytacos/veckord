# Display Streaming Feasibility & Architecture Findings Report

## Executive Summary

This report documents the feasibility audit for introducing controller-native display streaming to Veckord on Bazzite (Linux / Steam Gaming Mode).

## 1. Wayland, PipeWire, and xdg-desktop-portal Analysis

- **Vesktop Flatpak Sandbox**: Vesktop runs inside a Flatpak container under Wayland/Gamescope. Screen capture relies on standard Chromium/Electron PipeWire portals (`org.freedesktop.portal.ScreenCast` & `org.freedesktop.portal.Desktop`).
- **Gamescope Modal Focus Issue**: In Steam Gaming Mode, native desktop portal pickers pop up outside Gamescope's window hierarchy. This causes modal dialogs to be hidden or unresponsive to controller input.
- **Resolution Path**: To avoid desktop portal dialog traps, source selection must be driven programmatically via Discord's internal Webpack source discovery (`getScreenShareSources`) rather than triggering an unmanaged portal dialog.

## 2. Runtime Module Discovery Matrix

Rather than assuming hardcoded store names, runtime discovery checks for:
- `ApplicationStreamingActions` / `StreamActions`: `createStream` / `startStream` / `stopStream`
- `MediaEngineStore`: `getScreenShareSources`
- `ApplicationStreamingStore`: active stream state tracking

## 3. Security & Non-Automation Policies

- Zero simulated mouse or keyboard clicks.
- Zero DOM scraping or selector queries.
- **Zero Auto-Streaming**: Streaming strictly requires explicit button press in the controller interface.

## 4. Current POC Status

- Feasibility audit completed and isolated in `experiments/display-streaming-probe/`.
- Production bridge commands and UI controls remain omitted until hardware test verification is conducted on Bazzite test setup.
