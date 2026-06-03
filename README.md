# Task Stack

A persistent task-stack tray app, built with [Tauri](https://tauri.app/). The
top of the stack is your current task; everything below it is queued. A
configurable global hotkey opens a compact window where you can add, reorder,
promote, and remove tasks.

## Features

- System tray icon with the current task as tooltip and a quick "Mark Done (pop)"
- Dynamic tray icon whose color reflects the task count (configurable thresholds)
- Compact stack window with keyboard- and mouse-driven editing
- Description panel for adding notes to any task (with clickable links)
- Configurable global hotkey (default: **Ctrl+Shift+T**)
- Dark and light theme, following your OS preference
- Configurable font family and size
- Persists window size and position across launches
- Soft-deletes: removed tasks are kept in a history file with a `deleted_at` timestamp
- Records `created_at`, `started_at`, `last_current`, and cumulative `duration`

## Quick Start

Prerequisites: [Rust](https://www.rust-lang.org/tools/install), Node.js, and the
[Tauri system dependencies](https://tauri.app/start/prerequisites/) for your
platform.

```bash
cd tauri
npm install
npm run dev      # run in development
npm run build    # produce a release bundle
```

The app starts in the menu bar / system tray. Press **Ctrl+Shift+T** to open
the stack window.

## Project Structure

```
tauri/
├── src/                     # Frontend (vanilla HTML/CSS/JS)
│   ├── index.html
│   ├── styles.css
│   └── main.js              # Stack window UI, theming, keyboard/mouse handling
└── src-tauri/               # Rust backend
    ├── src/
    │   ├── lib.rs           # App setup: tray, global hotkey, window, commands
    │   ├── stack.rs         # YAML-backed task store with soft deletes
    │   ├── settings.rs      # Window geometry, hotkey, font, icon config
    │   ├── hotkey.rs        # Hotkey-spec parser → Tauri global Shortcut
    │   └── icon.rs          # Dynamic tray icon generation (tiny-skia)
    ├── capabilities/        # Tauri permission capabilities
    ├── tauri.conf.json
    └── Cargo.toml
```

## Data Files

The app stores everything in your home directory (compatible with the previous
Python implementation):

| File | Purpose |
| --- | --- |
| `~/.task-stack.yaml` | Active task stack (YAML list of tasks). |
| `~/.task-stack.history.yaml` | Soft-deleted task history. |
| `~/.task-stack.settings.yaml` | Window geometry, hotkey, font, and icon config. |

### Customize the hotkey

Edit `~/.task-stack.settings.yaml`, set the `hotkey` field, then restart the
app. Tokens are joined with `+` and are case-insensitive:

- **Modifiers**: `ctrl`/`control`, `shift`, `alt`/`option`/`opt`,
  `cmd`/`command`/`super`/`win`/`meta`.
- **Key** (exactly one): a single ASCII letter/digit/punctuation, `f1`–`f24`,
  or one of `space`, `tab`, `enter`/`return`, `esc`/`escape`, `up`, `down`,
  `left`, `right`, `home`, `end`, `page_up`, `page_down`, `delete`,
  `backspace`, `insert`.

```yaml
hotkey: ctrl+shift+t
# hotkey: alt+space
# hotkey: cmd+shift+space
```

## Keyboard shortcuts

In the stack window:

| Action | Shortcut |
| --- | --- |
| Open the window from anywhere | **Ctrl+Shift+T** (configurable) |
| Add task to top (becomes current) | **Enter** in the input field |
| Add task as next (after current) | **Shift+Enter** in the input |
| Add task to the bottom | **End** in the input |
| Edit selected task text | **Enter** with a row selected (Enter to save, Esc to cancel) |
| Select a row by index | **0**–**9** |
| Extend selection | **Shift+0-9** / **Shift+↑↓** / **Shift+click** |
| Move selection up / down | **Up** / **Down** |
| Reorder selected row | **Left** / **Right** |
| Promote selected row to top | **Home** |
| Send selected row to bottom | **End** |
| Remove selected row(s) | **Backspace** / **Delete** |
| Show keyboard shortcuts | **?** |
| Hide the window | **Esc** |

## Documentation

Additional documentation lives in the [`docs/`](docs/) directory and behavior
specs in [`spec/`](spec/).

## License

See [LICENSE](LICENSE).
