"""Standalone pynput hotkey listener executed as a subprocess.

On macOS with Python 3.14, running a `pynput` keyboard listener in the same
process as a Tk `mainloop` reliably crashes inside `CFRunLoopRunInMode` with
"PyEval_RestoreThread: ... GIL is released" (see pynput issues #366 / #511 and
related). The crash happens in C, so a join-on-shutdown approach is not
sufficient: the listener thread can lose its Python thread state mid-run.

To work around this, the parent process spawns this module via
`python -m task_stack._hotkey_subprocess <hotkey-spec>`. This child process has
no Tk runloop of its own; it just runs the pynput listener and prints a single
line to stdout each time the hotkey fires. The parent reads stdout in a small
Python-only thread and dispatches via `tk.after`, so no native code runs in the
parent's thread pool alongside Tk.
"""

from __future__ import annotations

import os
import sys

from . import hotkey as hk


def _run(spec_str: str) -> int:
    try:
        spec = hk.parse(spec_str)
    except hk.HotkeyParseError as exc:
        sys.stderr.write(f"[task-stack hotkey] invalid spec {spec_str!r}: {exc}\n")
        return 2

    from pynput import keyboard

    held: dict[str, bool] = {"ctrl": False, "shift": False, "alt": False, "cmd": False}
    debug = bool(os.environ.get("TASK_STACK_DEBUG_HOTKEY"))

    def modifier_for(key: object) -> str | None:
        for mod in ("ctrl", "shift", "alt", "cmd"):
            if key in hk.modifier_keys(mod):
                return mod
        return None

    def emit() -> None:
        try:
            sys.stdout.write("FIRE\n")
            sys.stdout.flush()
        except (BrokenPipeError, ValueError):
            os._exit(0)

    def on_press(key: object) -> None:
        if debug:
            sys.stderr.write(f"[task-stack hotkey] press: {key!r}\n")
            sys.stderr.flush()
        mod = modifier_for(key)
        if mod is not None:
            held[mod] = True
            return
        active = {m for m, v in held.items() if v}
        if active != spec.modifiers:
            return
        if not spec.matches_key(key):
            return
        if debug:
            sys.stderr.write("[task-stack hotkey] fired\n")
            sys.stderr.flush()
        emit()

    def on_release(key: object) -> None:
        mod = modifier_for(key)
        if mod is not None:
            held[mod] = False

    if debug:
        sys.stderr.write(f"[task-stack hotkey] subprocess listening for {spec.pretty}\n")
        sys.stderr.flush()

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.run()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        sys.stderr.write("usage: python -m task_stack._hotkey_subprocess <hotkey-spec>\n")
        return 2
    return _run(args[0])


if __name__ == "__main__":
    raise SystemExit(main())
