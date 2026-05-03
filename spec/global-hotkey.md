# Global Hotkey

Registers a system-wide keyboard shortcut that brings the stack window forward from any application.

## Requirements

- The application MUST register a global hotkey listener on startup.
- The default hotkey MUST be `ctrl+shift+t`.
- The hotkey MUST be configurable via the settings.
- The hotkey listener MUST match key events by character code, by Apple virtual key code (for macOS Ctrl-masking), and by Windows virtual key code resolution (for Windows modifier masking).
- The listener MUST track held modifier keys (ctrl, shift, alt, cmd) and fire the callback only when the exact modifier combination and non-modifier key are pressed together.
- The hotkey MUST toggle the window visibility: show if hidden, hide if visible.

### Hotkey spec format

- The hotkey spec MUST be a `+`-separated string (e.g. `ctrl+shift+t`, `alt+space`).
- The spec MUST include at least one modifier and exactly one non-modifier key.
- Modifier tokens are case-insensitive and MUST support aliases: `ctrl`/`control`, `shift`, `alt`/`option`/`opt`, `cmd`/`command`/`super`/`win`/`meta`.
- Non-modifier key tokens MUST support: single printable characters (a-z, 0-9, punctuation), function keys (f1-f24), and named keys (`space`, `tab`, `enter`/`return`, `esc`/`escape`, `up`, `down`, `left`, `right`, `home`, `end`, `page_up`, `page_down`, `insert`, `delete`, `backspace`).
- Parsing an invalid hotkey spec MUST produce an error.
- The application MUST fall back to the default hotkey if the configured spec is invalid.

### macOS permissions

- On macOS, the application MUST check for Accessibility and Input Monitoring permissions on startup.
- If Accessibility access is not granted, the application MUST open the System Settings privacy pane.
- On non-macOS platforms, permission checks MUST be skipped.
