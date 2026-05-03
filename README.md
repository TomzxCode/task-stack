# Task Stack

A persistent task-stack tray app. The top of the stack is your current task;
everything below it is queued. A configurable global hotkey opens a compact
window where you can add, reorder, promote, and remove tasks.

## Features

- System tray icon with current task as tooltip and quick "Mark Done (pop)"
- Compact stack window with keyboard- and mouse-driven editing
- Description panel for adding notes to any task
- Configurable global hotkey (default: **Ctrl+Shift+T**)
- Dark and light theme, following your OS preference
- Configurable font family and size
- Configurable icon color thresholds
- Persists window size and position across launches
- Soft-deletes: removed tasks are kept with a `deleted_at` timestamp
- Records `created_at`, `started_at`, `last_current`, and cumulative `duration`

## Quick Start

```bash
cd python
uv sync
uv run task-stack
```

The app starts in the menu bar / system tray. Press **Ctrl+Shift+T** to open
the stack window.

## Documentation

Full documentation is available in the [`docs/`](docs/) directory and can be
built with MkDocs:

```bash
uv run mkdocs serve
```

## Project Structure

```
python/src/task_stack/
├── __main__.py          # Entry point
├── app.py               # Tray icon, hotkey listener, app coordinator
├── window.py            # Stack window UI, theming, description panel
├── stack.py             # YAML-backed task store with soft deletes
├── settings.py          # Window geometry, hotkey, font, icon config
├── hotkey.py            # Hotkey spec parser and key event matcher
├── icon.py              # Dynamic tray icon generation
├── macos_permissions.py # macOS Accessibility / Input Monitoring
└── tcl_tk_env.py        # Tcl/Tk discovery for macOS Python builds
```

## Development

```bash
cd python
uv sync
uv run ruff check .
uv run task-stack
```

## License

See [LICENSE](LICENSE).
