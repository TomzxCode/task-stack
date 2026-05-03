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

```
uv sync
uv run task-stack
```

See [Getting Started](user-guide/getting-started.md) for platform-specific setup and
[Configuration](user-guide/configuration.md) to customize the hotkey, font, and icon.
