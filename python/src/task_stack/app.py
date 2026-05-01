from __future__ import annotations

import os
import queue
import sys
from typing import Callable

import pystray
from pynput import keyboard

from . import hotkey as hk
from . import settings as cfg
from . import stack as st
from .icon import make_icon


class TrayApp:
    def __init__(
        self,
        on_open: Callable[[], None],
        on_quit: Callable[[], None],
        hotkey_label: str | None = None,
    ) -> None:
        self._on_open = on_open
        self._on_quit = on_quit
        self._hotkey_label = hotkey_label
        self._icon: pystray.Icon | None = None

    def _create_icon(self) -> pystray.Icon:
        tasks = st.load()
        image = make_icon(len(tasks))
        current_text = tasks[0].text if tasks else "No tasks"
        return pystray.Icon(
            "task-stack",
            image,
            title=current_text,
            menu=self._build_menu(tasks),
        )

    def start(self) -> None:
        self._icon = self._create_icon()
        self._icon.run()  # blocks — must be called from its own thread

    def start_detached(self) -> None:
        """Create and run the icon on the *current* thread without blocking.

        Required on macOS, where the NSStatusItem must be created on the main
        thread; pystray's run_detached spins up the Cocoa event source for us.
        """
        self._icon = self._create_icon()
        self._icon.run_detached()

    def update(self, tasks: list[st.Task]) -> None:
        if self._icon is None:
            return
        self._icon.icon = make_icon(len(tasks))
        self._icon.title = tasks[0].text if tasks else "No tasks"
        self._icon.menu = self._build_menu(tasks)

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()

    # ------------------------------------------------------------------

    def _build_menu(self, tasks: list[st.Task]) -> pystray.Menu:
        current_label = tasks[0].text if tasks else "No tasks"
        open_label = "Open Stack"
        if self._hotkey_label:
            open_label = f"Open Stack ({self._hotkey_label})"
        items = [
            pystray.MenuItem(current_label, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(open_label, lambda icon, item: self._on_open()),
            pystray.MenuItem(
                "Mark Done (pop)",
                lambda icon, item: self._pop_and_update(),
                enabled=bool(tasks),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda icon, item: self._on_quit()),
        ]
        return pystray.Menu(*items)

    def _pop_and_update(self) -> None:
        _, tasks = st.pop()
        self.update(tasks)


class HotkeyListener:
    """Global hotkey listener configured from `Settings.hotkey`.

    Matches by `KeyCode.char` AND by `KeyCode.vk` so combos like Ctrl+Shift+T
    keep working on macOS, where Ctrl masks the character translation.
    """

    def __init__(
        self,
        callback: Callable[[], None],
        spec: hk.HotkeySpec | None = None,
    ) -> None:
        self._callback = callback
        if spec is None:
            spec = hk.parse_or_default(cfg.load().hotkey, cfg.DEFAULT_HOTKEY)
        self._spec = spec
        self._listener: keyboard.Listener | None = None
        self._held: dict[str, bool] = {"ctrl": False, "shift": False, "alt": False, "cmd": False}

    @property
    def pretty(self) -> str:
        return self._spec.pretty

    def start(self) -> None:
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()
        if os.environ.get("TASK_STACK_DEBUG_HOTKEY"):
            sys.stderr.write(
                f"[task-stack] hotkey listener registered for {self._spec.pretty}\n"
            )
            sys.stderr.flush()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()

    # ------------------------------------------------------------------

    @staticmethod
    def _modifier_for_key(key: object) -> str | None:
        for mod in ("ctrl", "shift", "alt", "cmd"):
            if key in hk.modifier_keys(mod):
                return mod
        return None

    def _on_press(self, key: object) -> None:
        if os.environ.get("TASK_STACK_DEBUG_HOTKEY"):
            sys.stderr.write(f"[task-stack] key press: {key!r}\n")
            sys.stderr.flush()
        mod = self._modifier_for_key(key)
        if mod is not None:
            self._held[mod] = True
            return
        held_set = {m for m, v in self._held.items() if v}
        if held_set != self._spec.modifiers:
            return
        if not self._spec.matches_key(key):
            return
        if os.environ.get("TASK_STACK_DEBUG_HOTKEY"):
            sys.stderr.write("[task-stack] hotkey fired\n")
            sys.stderr.flush()
        try:
            self._callback()
        except Exception as exc:
            sys.stderr.write(f"[task-stack] hotkey callback error: {exc!r}\n")
            sys.stderr.flush()

    def _on_release(self, key: object) -> None:
        mod = self._modifier_for_key(key)
        if mod is not None:
            self._held[mod] = False


class AppCoordinator:
    """Wires together the tray, hotkey listener, and tkinter window via a thread-safe queue."""

    def __init__(self, tk_after: Callable, tk_quit: Callable, window_show: Callable, window_refresh: Callable) -> None:
        self._tk_after = tk_after
        self._tk_quit = tk_quit
        self._window_show = window_show
        self._window_refresh = window_refresh
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._tray: TrayApp | None = None

    def set_tray(self, tray: TrayApp) -> None:
        self._tray = tray

    def request_show(self) -> None:
        self._queue.put("show")
        self._tk_after(0, self._drain)

    def request_quit(self) -> None:
        self._queue.put("quit")
        self._tk_after(0, self._drain)

    def notify_stack_changed(self) -> None:
        tasks = st.load()
        if self._tray:
            self._tray.update(tasks)

    def _drain(self) -> None:
        while not self._queue.empty():
            msg = self._queue.get_nowait()
            if msg == "show":
                self._window_refresh()
                self._window_show()
            elif msg == "quit":
                self._tk_quit()
