# Installation

## Requirements

- Python **3.14+**
- macOS, Linux, or Windows

## Install with uv

The project is managed with [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Run

```bash
uv run task-stack
```

The app starts in the menu bar / system tray. The stack window stays hidden
until you press the hotkey or pick **Open Stack** from the tray menu.

## macOS

### Tk-enabled Python

Tk-enabled Python is required on macOS. The recommended interpreter is
Homebrew's `python@3.14` plus `python-tk@3.14`:

```bash
brew install python-tk@3.14
```

uv-managed standalone Python builds do not currently ship a working Tcl/Tk.
If you must use one, install `tcl-tk` and the app will attempt to discover it
automatically.

If you bumped Python or just installed `python-tk@3.14`, recreate the venv:

```bash
rm -rf .venv && uv venv --python /opt/homebrew/bin/python3.14 && uv sync
```

### Permissions

The global hotkey listener needs both **Accessibility** and **Input Monitoring**
access. The app prompts for these on first launch and opens the relevant System
Settings pane if you previously denied. Permissions are tied to the interpreter
binary (e.g. `/opt/homebrew/opt/python@3.14/bin/python3.14`), not to
"task-stack".

After granting access, quit and relaunch.
