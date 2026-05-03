# Architecture

## Module Overview

| Module | Responsibility |
|---|---|
| `__main__.py` | Entry point; wires together all components |
| `app.py` | Tray icon, global hotkey listener, and app coordinator |
| `window.py` | Stack window UI with keyboard/mouse interaction, theming, description panel |
| `stack.py` | YAML-backed task store with soft deletes and duration tracking |
| `settings.py` | Persisted settings (window geometry, hotkey, font, icon thresholds) |
| `hotkey.py` | Hotkey spec parser and key event matcher |
| `icon.py` | Dynamic tray icon generation |
| `macos_permissions.py` | macOS Accessibility / Input Monitoring prompts |
| `tcl_tk_env.py` | Tcl/Tk discovery for macOS Python builds |

## Threading Model

- The **main thread** runs the UI event loop.
- The **tray icon** runs on the main thread on macOS (required by Cocoa) or in
  a daemon thread on other platforms.
- The **hotkey listener** runs in a daemon background thread.
- An **app coordinator** bridges background threads to the UI via a
  thread-safe queue, draining requests on the main event loop.
- On Windows, a **theme watcher** thread monitors registry changes for live
  dark/light theme switching.

## Data Flow

```
User action (keyboard/mouse/tray)
  -> Window / TrayApp
    -> stack.py (read/write ~/.task-stack.yaml)
    -> AppCoordinator.notify_stack_changed()
      -> TrayApp.update() (refresh icon + menu)
```

All writes to `~/.task-stack.yaml` are atomic (temp file + rename).

## Theme Detection

- **Windows**: Live registry change notifications via `RegNotifyChangeKeyValue`.
- **macOS / Linux**: Periodic polling of the OS theme preference.
- The window applies the detected theme to all UI elements including the
  description panel and entry fields.
