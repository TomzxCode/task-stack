# task-stack

A small persistent task-stack tray app. The top of the stack is your current
task; everything below it is queued. A global hotkey opens a compact window
where you can add, reorder, promote, and remove tasks.

State and deletions are kept in YAML files in your home directory, so it's
easy to inspect or back up.

## Features

- Tray icon with the current task as the tooltip and a quick "Mark Done (pop)"
  menu item.
- Compact stack window with keyboard- and mouse-driven editing.
- Configurable global hotkey (default: **Ctrl+Shift+T**) to bring the window
  forward from anywhere.
- Persists window size and position across launches; centers a sensible default
  on first run.
- Soft-deletes: removed/popped tasks are kept in the YAML file with a
  `deleted_at` timestamp, so you have a history.
- Records `created_at`, `started_at` (first time the task became current), and
  `last_current` (most recent time it was at the top) for each task.

## Requirements

- Python **3.14+** (set via `.python-version`)
- macOS, Linux, or Windows
- On macOS, Tk-enabled Python is required. The recommended interpreter is
  Homebrew's `python@3.14` plus `python-tk@3.14`:

  ```bash
  brew install python-tk@3.14
  ```

  uv-managed standalone Python builds do not currently ship a working Tcl/Tk
  on macOS. If you must use one, install `tcl-tk` and rely on the included
  fallback in `task_stack/tcl_tk_env.py`.

## Install

The project is managed with [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

If you bumped Python or just installed `python-tk@3.14`, recreate the venv so
uv picks up the Tk-enabled interpreter:

```bash
rm -rf .venv && uv venv --python /opt/homebrew/bin/python3.14 && uv sync
```

## Run

```bash
uv run task-stack
```

The app starts in the menu bar / system tray and the stack window stays hidden
until you press the hotkey or pick **Open Stack** from the tray menu.

### macOS permissions

The global hotkey listener uses `pynput`, which needs both **Accessibility**
and **Input Monitoring** access. The app prompts for these on first launch and
opens the relevant System Settings pane if you previously denied. Permissions
are tied to the **interpreter binary** (e.g. `/opt/homebrew/opt/python@3.14/bin/python3.14`),
not to "task-stack", so you'll see that entry in the list.

After granting access, quit and relaunch.

## Keyboard shortcuts

In the stack window:

| Action | Shortcut |
| --- | --- |
| Open the window from anywhere | **Ctrl+Shift+T** (configurable) |
| Add task to top (becomes current) | **Enter** in the input field |
| Add task as next (after current) | **Shift+Enter** in the input |
| Edit selected task text | **Enter** with a row selected (then Enter to save, Esc to cancel) |
| Select a row by index | **0**–**9** |
| Move selection up / down | **Up** / **Down** |
| Reorder selected row | **Left** / **Right** |
| Promote selected row to top | **/** |
| Remove selected row | **Backspace** / **Delete** |
| Hide the window | **Esc** |

## Tray menu

- **\<current task\>** — non-clickable label showing the active task.
- **Open Stack (\<hotkey\>)** — show the stack window.
- **Mark Done (pop)** — pop the current task off the top.
- **Quit** — exit.

## Files

The app stores everything in your home directory:

| File | Purpose |
| --- | --- |
| `~/.task-stack.yaml` | Active stack and soft-deleted history (YAML list of tasks). |
| `~/.task-stack.settings.yaml` | Window geometry and hotkey configuration (YAML). |

### Customize the hotkey

Edit `~/.task-stack.settings.yaml` and set the `hotkey` field, then restart
the app. Examples:

```yaml
hotkey: ctrl+shift+t
# hotkey: alt+space
# hotkey: cmd+shift+space
# hotkey: ctrl+f1
# hotkey: alt+/
```

Tokens are joined with `+` and are case-insensitive:

- **Modifiers**: `ctrl`/`control`, `shift`, `alt`/`option`/`opt`,
  `cmd`/`command`/`super`/`win`/`meta`.
- **Key** (exactly one): a single ASCII letter/digit/punctuation
  (`t`, `1`, `/`, …), `f1`–`f24`, or one of `space`, `tab`,
  `enter`/`return`, `esc`/`escape`, `up`, `down`, `left`, `right`,
  `home`, `end`, `page_up`, `page_down`, `delete`, `backspace`,
  `insert` (where the platform supports it).

The current hotkey is shown next to **Open Stack** in the tray menu.

### Task data format

Each task in `~/.task-stack.yaml` is a YAML mapping. Example:

```yaml
- text: Write README
  created_at: '2026-05-01T15:00:00+00:00'
  started_at: '2026-05-01T15:00:00+00:00'
  last_current: '2026-05-01T15:30:00+00:00'
- text: Old task
  created_at: '2026-04-30T10:00:00+00:00'
  started_at: '2026-04-30T10:00:00+00:00'
  last_current: '2026-04-30T11:15:00+00:00'
  deleted_at: '2026-04-30T12:00:00+00:00'
```

Active tasks come first (in stack order); soft-deleted tasks are appended at
the end, each with a `deleted_at` timestamp.

## Debugging

- **Hotkey not firing**: run with `TASK_STACK_DEBUG_HOTKEY=1` to log every
  key event and show when the hotkey matches:

  ```bash
  TASK_STACK_DEBUG_HOTKEY=1 uv run task-stack
  ```

  If you don't see any `key press:` lines when typing, the OS hasn't granted
  Accessibility / Input Monitoring access to the Python binary.

- **Tk errors on macOS**: if you see `Can't find a usable init.tcl`, your
  Python lacks a Tk runtime. Install `python-tk@3.14` (or use Homebrew's
  Python) as described above.

## Development

```bash
uv sync
uv run ruff check .
uv run task-stack
```

The codebase is small:

- `src/task_stack/__main__.py` — wires everything together.
- `src/task_stack/app.py` — tray icon and global hotkey listener.
- `src/task_stack/window.py` — Tk window UI.
- `src/task_stack/stack.py` — YAML-backed task store with soft deletes.
- `src/task_stack/settings.py` — window geometry + hotkey config.
- `src/task_stack/hotkey.py` — hotkey-spec parser and matcher.
- `src/task_stack/macos_permissions.py` — Accessibility / Input Monitoring
  prompts on macOS.
- `src/task_stack/tcl_tk_env.py` — best-effort Tcl/Tk discovery on macOS for
  Python builds with broken default paths.
- `src/task_stack/icon.py` — generates the tray icon image.
