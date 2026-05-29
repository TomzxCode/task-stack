# task-stack (Go)

A small persistent task-stack tray app — a Go port of the Python `task-stack`.
The top of the stack is your current task; everything below it is queued. A
global hotkey opens a compact window where you can add, reorder, promote, edit,
annotate, filter, and remove tasks.

State and deletions are kept in the same YAML files in your home directory as
the Python version, so the two implementations are interchangeable on disk.

## Features

- Tray icon whose badge color and number reflect how many tasks are queued, with
  the current task as the tooltip and a quick **Mark Done (pop)** menu item.
- Compact stack window with keyboard- and mouse-driven editing, multi-select,
  drag-to-reorder, per-task descriptions, and fuzzy filtering.
- Configurable global hotkey (default: **Ctrl+Shift+T**) to bring the window
  forward from anywhere.
- Persists window size across launches.
- Soft-deletes: removed/popped tasks are kept in a history YAML file with a
  `deleted_at` timestamp.
- Records `created_at`, `started_at`, `last_current`, accumulated active
  `duration`, and `execution_count` for each task.
- Light/dark palette chosen from the desktop theme at launch.

## Requirements

- Go **1.24+**
- macOS, Linux, or Windows
- A desktop environment (the UI uses [Fyne](https://fyne.io); on Linux you need
  the usual X11/OpenGL development libraries to build: `libgl1-mesa-dev`,
  `xorg-dev`).

## Build & run

```bash
cd go
go build -o task-stack .
./task-stack
```

or simply:

```bash
go run .
```

The app starts in the system tray and the stack window stays hidden until you
press the hotkey or pick **Open Stack** from the tray menu.

## Keyboard shortcuts

In the stack window:

| Action | Shortcut |
| --- | --- |
| Open the window from anywhere | **Ctrl+Shift+T** (configurable) |
| Add task to top (becomes current) | **Enter** in the input field |
| Add task as next (after current) | **Shift+Enter** in the input |
| Add task to bottom | **End** in the input field |
| Edit selected task text | **Enter** with a row selected (Enter to save, Esc to cancel) |
| Select a row by index | **0**–**9** |
| Extend selection (range) | **Shift+0–9**, **Shift+↑/↓**, or **Shift+click** |
| Move selection up / down | **Up** / **Down** |
| Reorder selected row | **Left** / **Right** |
| Promote selected row to top | **Home** |
| Send selected row to bottom | **End** |
| Delete selected row(s) | **Backspace** / **Delete** |
| Filter | start typing with nothing selected |
| Show this help | **?** |
| Clear selection/filter, then hide | **Esc** |

Select a single row to reveal the description panel at the bottom of the window.

## Tray menu

- **\<current task\>** — non-clickable label showing the active task.
- **Open Stack (\<hotkey\>)** — show the stack window.
- **Mark Done (pop)** — pop the current task off the top.
- **Keyboard Shortcuts** — open the help window.
- **Quit** — exit.

## Files

| File | Purpose |
| --- | --- |
| `~/.task-stack.yaml` | Active stack (YAML list of tasks). |
| `~/.task-stack.history.yaml` | Soft-deleted task history. |
| `~/.task-stack.settings.yaml` | Window size, hotkey, font, and icon thresholds. |

### Customize the hotkey

Edit `~/.task-stack.settings.yaml`, set the `hotkey` field, and restart the app:

```yaml
hotkey: ctrl+shift+t
# hotkey: alt+space
# hotkey: cmd+shift+space
# hotkey: ctrl+f1
```

Tokens are joined with `+` and are case-insensitive:

- **Modifiers**: `ctrl`/`control`, `shift`, `alt`/`option`/`opt`,
  `cmd`/`command`/`super`/`win`/`meta`.
- **Key** (exactly one): a single ASCII letter/digit (`t`, `1`, …),
  `f1`–`f20`, or one of `space`, `tab`, `enter`/`return`, `esc`/`escape`,
  `up`, `down`, `left`, `right`, `delete`.

The current hotkey is shown next to **Open Stack** in the tray menu.

## Source layout

- `main.go` — wires the tray, hotkey listener, and window together.
- `stack.go` — YAML-backed task store with soft deletes and legacy migrations.
- `settings.go` — window geometry, hotkey, font, and icon-threshold config.
- `hotkey_spec.go` / `hotkey_*.go` — hotkey-spec parser and global listener.
- `icon.go` — generates the tray icon image with the count badge.
- `window.go` / `stackview.go` / `entry.go` / `theme.go` — the GUI.
- `tray.go` — system tray icon and menu.

## Notes on parity with the Python version

This port aims for behavioral and on-disk parity. A few platform-specific
helpers from the Python build are not needed in Go and are intentionally
omitted: the macOS Accessibility / Input Monitoring prompts and the Tcl/Tk
discovery shim (the global hotkey uses `golang.design/x/hotkey` and the UI uses
Fyne rather than Tk). Absolute window *position* is not restored because Fyne
does not expose it portably; window *size* is persisted.
