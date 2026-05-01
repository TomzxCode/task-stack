from __future__ import annotations

import tkinter as tk
from datetime import datetime, timezone
from typing import Callable

from . import settings as cfg
from . import stack as st


_FONT_CURRENT = ("TkDefaultFont", 11, "bold")
_FONT_NORMAL = ("TkDefaultFont", 11)
_COLOR_SELECTED_BG = "#d0e4ff"
_COLOR_BG = "#ffffff"
_ROW_HEIGHT = 28
_DEFAULT_WIDTH = 480
_DEFAULT_HEIGHT = 360
_GEOMETRY_SAVE_DEBOUNCE_MS = 400


class StackWindow:
    def __init__(self, root: tk.Tk, on_stack_change: Callable[[], None]) -> None:
        self.root = root
        self.on_stack_change = on_stack_change
        self._tasks: list[st.Task] = []
        self._selected: int | None = None
        self._drag_start: int | None = None
        self._drag_y0: int = 0

        root.title("Task Stack")
        root.resizable(True, True)
        root.minsize(320, 160)
        root.protocol("WM_DELETE_WINDOW", self.hide)
        root.attributes("-topmost", True)

        self._settings = cfg.load()
        self._save_after_id: str | None = None

        self._build_ui()
        self._apply_initial_geometry()
        self.refresh()
        self._canvas.focus_set()

        root.bind("<Configure>", self._on_root_configure)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.root.configure(bg="#f0f0f0")
        pad = {"padx": 8, "pady": 6}

        top = tk.Frame(self.root, bg="#f0f0f0")
        top.pack(fill=tk.X, **pad)

        self._entry = tk.Entry(
            top,
            font=_FONT_NORMAL,
            relief=tk.FLAT,
            bg="white",
            fg="#111",
            insertbackground="#111",
            disabledforeground="#888",
            readonlybackground="white",
            highlightthickness=1,
            highlightbackground="#aaa",
            highlightcolor="#4a90e2",
        )
        self._entry.pack(fill=tk.X, ipady=4)
        self._entry.bind("<Return>", self._on_enter)
        self._entry.bind("<Escape>", lambda _: self._canvas.focus_set())

        self._canvas = tk.Canvas(self.root, bg=_COLOR_BG, highlightthickness=0,
                                 width=460, height=_ROW_HEIGHT)
        self._canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self._canvas.configure(takefocus=True)
        self._canvas.bind("<ButtonPress-1>", self._drag_press)
        self._canvas.bind("<B1-Motion>", self._drag_motion)
        self._canvas.bind("<ButtonRelease-1>", self._drag_release)
        self._canvas.bind("<Key>", self._on_key)
        self._canvas.bind("<Escape>", lambda _: self.hide())
        self._canvas.bind("<Configure>", lambda _e: self._redraw())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self) -> None:
        self.refresh()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self._canvas.focus_set()

    def hide(self) -> None:
        self._capture_geometry()
        self.root.withdraw()

    # ------------------------------------------------------------------
    # Geometry persistence
    # ------------------------------------------------------------------

    def _apply_initial_geometry(self) -> None:
        geom = self._settings.window
        if geom is not None:
            self.root.geometry(geom.to_geometry_string())
            return
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - _DEFAULT_WIDTH) // 2)
        y = max(0, (screen_h - _DEFAULT_HEIGHT) // 3)
        self.root.geometry(f"{_DEFAULT_WIDTH}x{_DEFAULT_HEIGHT}+{x}+{y}")

    def _on_root_configure(self, event: tk.Event) -> None:
        if event.widget is not self.root:
            return
        if self._save_after_id is not None:
            try:
                self.root.after_cancel(self._save_after_id)
            except Exception:
                pass
        self._save_after_id = self.root.after(
            _GEOMETRY_SAVE_DEBOUNCE_MS, self._capture_geometry
        )

    def _capture_geometry(self) -> None:
        self._save_after_id = None
        try:
            if self.root.state() != "normal":
                return
            width = self.root.winfo_width()
            height = self.root.winfo_height()
            x = self.root.winfo_x()
            y = self.root.winfo_y()
        except tk.TclError:
            return
        if width <= 1 or height <= 1:
            return
        geom = cfg.WindowGeometry(width=width, height=height, x=x, y=y)
        if (
            self._settings.window is not None
            and self._settings.window.width == geom.width
            and self._settings.window.height == geom.height
            and self._settings.window.x == geom.x
            and self._settings.window.y == geom.y
        ):
            return
        self._settings.window = geom
        cfg.save(self._settings)

    def refresh(self, tasks: list[st.Task] | None = None) -> None:
        if tasks is not None:
            self._tasks = tasks
        else:
            self._tasks = st.load()
        self._selected = None
        self._redraw()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _redraw(self) -> None:
        c = self._canvas
        c.delete("all")
        now = datetime.now(tz=timezone.utc)

        width = c.winfo_width()
        if width <= 1:
            width = int(c.cget("width"))
        right_pad = 8
        ts_x = width - right_pad
        text_right = ts_x - 70  # leave room for timestamp column

        for i, task in enumerate(self._tasks):
            y0 = i * _ROW_HEIGHT
            y1 = y0 + _ROW_HEIGHT

            if i == self._selected:
                bg = _COLOR_SELECTED_BG
            else:
                bg = _COLOR_BG

            c.create_rectangle(0, y0, width, y1, fill=bg, outline="", tags=f"row{i}")

            # drag handle
            for dy in (8, 13, 18):
                c.create_line(8, y0 + dy, 18, y0 + dy, fill="#aaa", width=1.5)

            # index
            font = _FONT_CURRENT if i == 0 else _FONT_NORMAL
            c.create_text(26, y0 + _ROW_HEIGHT // 2, text=str(i), anchor=tk.W,
                          font=font, fill="#666")

            # indicator
            indicator = "●" if i == 0 else "○"
            c.create_text(44, y0 + _ROW_HEIGHT // 2, text=indicator, anchor=tk.W,
                          font=font, fill="#333")

            text_width = max(40, text_right - 66)
            c.create_text(66, y0 + _ROW_HEIGHT // 2, text=task.text, anchor=tk.W,
                          font=font, fill="#111", width=text_width)

            ts = st.format_timestamp(task.last_current, now)
            c.create_text(ts_x, y0 + _ROW_HEIGHT // 2, text=ts, anchor=tk.E,
                          font=("TkFixedFont", 10), fill="#888")

        if not self._tasks:
            c.create_text(width // 2, _ROW_HEIGHT // 2,
                          text="No tasks — type above and press Enter",
                          fill="#aaa", font=_FONT_NORMAL)

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _on_enter(self, _event: tk.Event) -> None:
        text = self._entry.get().strip()
        if not text:
            return
        self._entry.delete(0, tk.END)
        tasks = st.push(text)
        self._tasks = tasks
        self._selected = None
        self._redraw()
        self.on_stack_change()
        self._canvas.focus_set()

    def _on_key(self, event: tk.Event) -> None:
        if event.widget is self._entry:
            return

        # Digit keys (main row and numpad) select a row
        if event.keysym.isdigit() or (event.keysym.startswith("KP_") and event.keysym[3:].isdigit()):
            digit = int(event.keysym[-1])
            if digit < len(self._tasks):
                self._selected = digit
                self._canvas.focus_set()
                self._redraw()
            return

        # Printable character: redirect to entry and let the user type
        if event.char and event.char.isprintable():
            self._entry.focus_set()
            self._entry.insert(tk.END, event.char)
            return

        if event.keysym in ("Up", "Down"):
            if self._selected is None:
                self._selected = 0 if event.keysym == "Down" else len(self._tasks) - 1
            else:
                delta = -1 if event.keysym == "Up" else 1
                self._selected = max(0, min(len(self._tasks) - 1, self._selected + delta))
            self._canvas.focus_set()
            self._redraw()
            return

        if self._selected is None:
            return

        if event.keysym in ("Left", "Right"):
            delta = -1 if event.keysym == "Left" else 1
            new_idx = self._selected + delta
            if 0 <= new_idx < len(self._tasks):
                self._tasks = st.reorder(self._selected, new_idx)
                self._selected = new_idx
                self._redraw()
                self.on_stack_change()
            return

        if event.keysym in ("slash", "KP_Divide"):
            tasks = st.promote(self._selected)
            self._tasks = tasks
            self._selected = None
            self._redraw()
            self.on_stack_change()

        elif event.keysym in ("BackSpace", "Delete"):
            tasks = st.remove(self._selected)
            self._tasks = tasks
            self._selected = None
            self._redraw()
            self.on_stack_change()

    # ------------------------------------------------------------------
    # Drag and drop
    # ------------------------------------------------------------------

    def _row_at(self, y: int) -> int:
        return max(0, min(len(self._tasks) - 1, y // _ROW_HEIGHT))

    def _drag_press(self, event: tk.Event) -> None:
        if not self._tasks:
            return
        self._canvas.focus_set()
        self._drag_start = self._row_at(event.y)
        self._drag_y0 = event.y

    def _drag_motion(self, event: tk.Event) -> None:
        if self._drag_start is None or len(self._tasks) < 2:
            return
        target = self._row_at(event.y)
        if target != self._drag_start:
            self._tasks = st.reorder(self._drag_start, target)
            self._drag_start = target
            self._redraw()
            self.on_stack_change()

    def _drag_release(self, event: tk.Event) -> None:
        self._drag_start = None
