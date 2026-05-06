from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
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
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self._on_open = on_open
        self._on_quit = on_quit
        self._hotkey_label = hotkey_label
        self._on_help = on_help
        self._icon: pystray.Icon | None = None

    def _create_icon(self) -> pystray.Icon:
        tasks = st.load()
        thresholds = cfg.load().resolved_icon_thresholds()
        image = make_icon(len(tasks), thresholds)
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
        thresholds = cfg.load().resolved_icon_thresholds()
        self._icon.icon = make_icon(len(tasks), thresholds)
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
            pystray.MenuItem(
                "Keyboard Shortcuts",
                lambda icon, item: self._on_help() if self._on_help else None,
                enabled=self._on_help is not None,
            ),
            pystray.MenuItem("Quit", lambda icon, item: self._on_quit()),
        ]
        return pystray.Menu(*items)

    def _pop_and_update(self) -> None:
        _, tasks = st.pop()
        self.update(tasks)


class HotkeyListener:
    """Global hotkey listener configured from `Settings.hotkey`.

    On macOS, the listener runs in a dedicated subprocess (see
    `task_stack._hotkey_subprocess`). Running pynput's CFRunLoop-based listener
    in the same process as Tk's `mainloop` on Python 3.14 reliably crashes with
    "PyEval_RestoreThread: ... GIL is released" — see pynput issues #366 / #511.
    Isolating it in a subprocess removes the offending interaction entirely.

    On other platforms, the listener runs in-process on a background thread.
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
        self._proc: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._held: dict[str, bool] = {"ctrl": False, "shift": False, "alt": False, "cmd": False}

    @property
    def pretty(self) -> str:
        return self._spec.pretty

    def start(self) -> None:
        if sys.platform == "darwin":
            self._start_subprocess()
        else:
            self._start_in_process()
        if os.environ.get("TASK_STACK_DEBUG_HOTKEY"):
            sys.stderr.write(f"[task-stack] hotkey listener registered for {self._spec.pretty}\n")
            sys.stderr.flush()

    def stop(self) -> None:
        if self._proc is not None:
            self._stop_subprocess()
            return
        listener = self._listener
        if listener is None:
            return
        listener.stop()
        if listener.is_alive():
            try:
                listener.join(timeout=2.0)
            except RuntimeError:
                pass
        self._listener = None

    # ------------------------------------------------------------------
    # Subprocess (macOS) implementation
    # ------------------------------------------------------------------

    def _start_subprocess(self) -> None:
        env = os.environ.copy()
        # Ensure the child can find the task_stack package without relying on
        # the parent's cwd. Prepending repo's src dir is unnecessary because we
        # invoke via -m and rely on the installed entry, but keep PYTHONPATH
        # pass-through for editable installs.
        proc = subprocess.Popen(
            [sys.executable, "-m", "task_stack._hotkey_subprocess", self._spec_to_arg()],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=None,  # inherit so debug logs still surface
            text=True,
            bufsize=1,  # line buffered
            env=env,
        )
        self._proc = proc
        self._reader = threading.Thread(
            target=self._read_subprocess,
            args=(proc,),
            name="hotkey-reader",
            daemon=True,
        )
        self._reader.start()

    def _spec_to_arg(self) -> str:
        return self._spec.pretty.lower()

    def _read_subprocess(self, proc: subprocess.Popen[str]) -> None:
        stdout = proc.stdout
        if stdout is None:
            return
        try:
            for line in stdout:
                if line.strip() != "FIRE":
                    continue
                try:
                    self._callback()
                except Exception as exc:
                    sys.stderr.write(f"[task-stack] hotkey callback error: {exc!r}\n")
                    sys.stderr.flush()
        except Exception:
            pass

    def _stop_subprocess(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except OSError:
                    pass
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass
        reader = self._reader
        self._reader = None
        if reader is not None and reader.is_alive():
            reader.join(timeout=1.0)

    # ------------------------------------------------------------------
    # In-process implementation (Linux / Windows)
    # ------------------------------------------------------------------

    def _start_in_process(self) -> None:
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

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
    """Wires together the tray, hotkey listener, and tkinter window via a thread-safe queue.

    Background threads (tray, hotkey listener / subprocess reader) MUST NOT call
    Tk methods directly — Tcl/Tk is not thread-safe and on Python 3.14 + macOS
    invoking `root.after` from a non-main thread reliably crashes with
    "PyEval_RestoreThread: ... GIL is released". Instead, those threads only
    enqueue messages here; the main Tk thread polls via `poll_pending` from a
    repeating `root.after` callback.
    """

    def __init__(
        self,
        tk_quit: Callable,
        window_show: Callable,
        window_hide: Callable,
        window_refresh: Callable,
        window_is_visible: Callable[[], bool],
        window_show_help: Callable | None = None,
    ) -> None:
        self._tk_quit = tk_quit
        self._window_show = window_show
        self._window_hide = window_hide
        self._window_refresh = window_refresh
        self._window_is_visible = window_is_visible
        self._window_show_help = window_show_help
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._tray: TrayApp | None = None

    def set_tray(self, tray: TrayApp) -> None:
        self._tray = tray

    def request_show(self) -> None:
        self._queue.put("show")

    def request_toggle(self) -> None:
        self._queue.put("toggle")

    def request_quit(self) -> None:
        self._queue.put("quit")

    def request_help(self) -> None:
        self._queue.put("help")

    def notify_stack_changed(self) -> None:
        # Called from background threads (tray menu callbacks). Defer all
        # Tk-touching work to the main thread by enqueuing a marker.
        self._queue.put("stack_changed")

    def poll_pending(self) -> None:
        """Drain pending messages. MUST be called from the Tk main thread."""
        self._drain()

    def _drain(self) -> None:
        while not self._queue.empty():
            msg = self._queue.get_nowait()
            if msg == "show":
                self._window_refresh()
                self._window_show()
            elif msg == "toggle":
                if self._window_is_visible():
                    self._window_hide()
                else:
                    self._window_refresh()
                    self._window_show()
            elif msg == "stack_changed":
                tasks = st.load()
                if self._tray:
                    self._tray.update(tasks)
            elif msg == "help":
                if self._window_show_help is not None:
                    self._window_show_help()
            elif msg == "quit":
                self._tk_quit()
