from __future__ import annotations

import signal
import sys
import threading

from .tcl_tk_env import ensure_tcl_tk_env

ensure_tcl_tk_env()

import tkinter as tk

from . import hotkey as hk
from . import settings as cfg
from .app import AppCoordinator, HotkeyListener, TrayApp
from .macos_permissions import ensure_hotkey_permissions
from .window import StackWindow


def main() -> None:
    try:
        root = tk.Tk()
    except tk.TclError as e:
        if sys.platform == "darwin" and "init.tcl" in str(e):
            sys.stderr.write(
                "task-stack: Tkinter could not load Tcl/Tk. On macOS with uv-managed Python, install Tcl/Tk:\n"
                "  brew install tcl-tk\n"
                "Then run again. Paths are set automatically when Homebrew's tcl-tk is present.\n"
            )
        raise
    root.withdraw()  # hidden until opened

    def _sigint(*_) -> None:
        root.quit()

    signal.signal(signal.SIGINT, _sigint)

    def _poll_signals() -> None:
        root.after(200, _poll_signals)

    root.after(200, _poll_signals)

    coordinator: AppCoordinator | None = None

    def on_stack_change() -> None:
        if coordinator:
            coordinator.notify_stack_changed()

    win = StackWindow(root, on_stack_change=on_stack_change)

    coordinator = AppCoordinator(
        tk_after=root.after,
        tk_quit=root.quit,
        window_show=win.show,
        window_hide=win.hide,
        window_refresh=win.refresh,
        window_is_visible=win.is_visible,
    )

    settings = cfg.load()
    try:
        hotkey_spec = hk.parse(settings.hotkey)
    except hk.HotkeyParseError as exc:
        sys.stderr.write(
            f"task-stack: invalid hotkey {settings.hotkey!r} in {cfg.SETTINGS_FILE} ({exc}); "
            f"falling back to {cfg.DEFAULT_HOTKEY!r}.\n"
        )
        hotkey_spec = hk.parse(cfg.DEFAULT_HOTKEY)

    tray = TrayApp(
        on_open=coordinator.request_show,
        on_quit=coordinator.request_quit,
        hotkey_label=hotkey_spec.pretty,
    )
    coordinator.set_tray(tray)

    if sys.platform == "darwin" and not ensure_hotkey_permissions():
        sys.stderr.write(
            "task-stack: global hotkey requires Accessibility (and Input Monitoring) access.\n"
            "Opened System Settings → Privacy & Security. Enable task-stack/your terminal,\n"
            "then quit and relaunch task-stack.\n"
        )

    hotkey = HotkeyListener(callback=coordinator.request_toggle, spec=hotkey_spec)
    hotkey.start()

    if sys.platform == "darwin":
        tray.start_detached()
    else:
        tray_thread = threading.Thread(target=tray.start, daemon=True, name="tray")
        tray_thread.start()

    try:
        root.mainloop()
    finally:
        tray.stop()
        hotkey.stop()


if __name__ == "__main__":
    main()
