from __future__ import annotations

import tkinter as tk
import tkinter.font as tkFont
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from PIL import Image, ImageDraw, ImageFont, ImageTk

from . import settings as cfg
from . import stack as st


class _InsertPosition(Enum):
    FIRST = "first"
    NEXT = "next"
    LAST = "last"


_EMOJI_CACHE: dict[str, ImageTk.PhotoImage] = {}
_COLOR_SELECTED_BG = "#d0e4ff"
_COLOR_BG = "#ffffff"
_ROW_HEIGHT = 28
_DEFAULT_WIDTH = 480
_DEFAULT_HEIGHT = 360
_GEOMETRY_SAVE_DEBOUNCE_MS = 400
_DURATION_TICK_MS = 1_000


def _emoji_image(emoji: str, size: int = 18) -> ImageTk.PhotoImage:
    if emoji in _EMOJI_CACHE:
        return _EMOJI_CACHE[emoji]
    try:
        font = ImageFont.truetype("seguiemj.ttf", size)
    except OSError:
        font = ImageFont.load_default()
    # Render into an oversized canvas to avoid clipping, then crop to actual bounds
    canvas_size = size * 3
    img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((size // 2, size // 2), emoji, font=font, embedded_color=True)
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
        img = img.resize((size, size), Image.LANCZOS)
    else:
        img = img.crop((0, 0, size, size))
    photo = ImageTk.PhotoImage(img)
    _EMOJI_CACHE[emoji] = photo
    return photo


class StackWindow:
    def __init__(self, root: tk.Tk, on_stack_change: Callable[[], None]) -> None:
        self.root = root
        self.on_stack_change = on_stack_change
        self._tasks: list[st.Task] = []
        self._selected: int | None = None
        self._editing_index: int | None = None
        self._drag_start: int | None = None
        self._drag_y0: int = 0

        root.title("Task Stack")
        root.resizable(True, True)
        root.minsize(320, 160)
        root.protocol("WM_DELETE_WINDOW", self.hide)
        root.attributes("-topmost", True)

        self._settings = cfg.load()
        self._save_after_id: str | None = None
        self._tick_after_id: str | None = None
        self._help_win: tk.Toplevel | None = None
        self._update_fonts()

        self._build_ui()
        self._apply_initial_geometry()
        self.refresh()
        self._canvas.focus_set()

        root.bind("<Configure>", self._on_root_configure)
        self._schedule_tick()

    def _update_fonts(self) -> None:
        ff = self._settings.font_family
        fs = self._settings.font_size
        self._font_normal = (ff, fs)
        self._font_current = (ff, fs, "bold")
        f = tkFont.Font(family=ff, size=fs)
        # measure widest representative strings + small padding
        self._dur_col_w = f.measure("00h 00m") + 8
        self._ts_col_w = f.measure("00m ago") + 8

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
            font=self._font_normal,
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
        self._entry.bind("<Shift-Return>", self._on_shift_enter)
        self._entry.bind("<Home>", self._on_entry_home)
        self._entry.bind("<End>", self._on_entry_end)
        self._entry.bind("<Escape>", self._on_entry_escape)

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

    def is_visible(self) -> bool:
        try:
            return bool(self.root.winfo_viewable())
        except tk.TclError:
            return False

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

    def _schedule_tick(self) -> None:
        try:
            self._tick_after_id = self.root.after(_DURATION_TICK_MS, self._on_tick)
        except tk.TclError:
            self._tick_after_id = None

    def _on_tick(self) -> None:
        self._tick_after_id = None
        try:
            self._redraw()
        finally:
            self._schedule_tick()

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
        self._cancel_edit()
        self._redraw()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _redraw(self) -> None:
        c = self._canvas
        c.delete("all")
        now = datetime.now().astimezone()

        width = c.winfo_width()
        if width <= 1:
            width = int(c.cget("width"))
        right_pad = 8
        gap = 8
        dur_x = width - right_pad
        ts_x = dur_x - self._dur_col_w - gap
        text_right = ts_x - self._ts_col_w - gap

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
            font = self._font_current if i == 0 else self._font_normal
            c.create_text(26, y0 + _ROW_HEIGHT // 2, text=str(i), anchor=tk.W,
                          font=font, fill="#666")

            # indicator (rendered via Pillow for color emoji support)
            indicator = "🔥" if i == 0 else "💤"
            img = _emoji_image(indicator)
            c.create_image(44, y0 + _ROW_HEIGHT // 2, image=img, anchor=tk.W)

            text_width = max(40, text_right - 66)
            c.create_text(66, y0 + _ROW_HEIGHT // 2, text=task.text, anchor=tk.W,
                          font=font, fill="#111", width=text_width)

            if i == 0:
                ts_text = st.format_timestamp(task.started_at, now)
                dur_seconds = task.live_duration(now)
                col_fill = "#444"
            else:
                ts_text = st.format_timestamp(task.last_current, now)
                dur_seconds = task.duration
                col_fill = "#888"
            c.create_text(ts_x, y0 + _ROW_HEIGHT // 2, text=ts_text, anchor=tk.E,
                          font=self._font_normal, fill=col_fill)
            c.create_text(dur_x, y0 + _ROW_HEIGHT // 2,
                          text=st.format_duration(dur_seconds), anchor=tk.E,
                          font=self._font_normal, fill=col_fill)

        if not self._tasks:
            c.create_text(width // 2, _ROW_HEIGHT // 2,
                          text="No tasks — type above and press Enter",
                          fill="#aaa", font=self._font_normal)

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _submit_entry(self, *, position: _InsertPosition = _InsertPosition.FIRST) -> None:
        text = self._entry.get().strip()
        if self._editing_index is not None:
            idx = self._editing_index
            if not text:
                self._cancel_edit()
                self._redraw()
                return
            tasks = st.update_text(idx, text)
            self._entry.delete(0, tk.END)
            self._editing_index = None
            self._tasks = tasks
            self._selected = idx if 0 <= idx < len(tasks) else None
            self._redraw()
            self.on_stack_change()
            self._canvas.focus_set()
            return
        if not text:
            return
        self._entry.delete(0, tk.END)
        if position == _InsertPosition.NEXT:
            tasks = st.push_next(text)
        elif position == _InsertPosition.LAST:
            tasks = st.push_last(text)
        else:
            tasks = st.push(text)
        self._tasks = tasks
        self._selected = None
        self._redraw()
        self.on_stack_change()
        self._canvas.focus_set()

    def _begin_edit(self, idx: int) -> None:
        if not (0 <= idx < len(self._tasks)):
            return
        self._editing_index = idx
        self._selected = idx
        self._entry.delete(0, tk.END)
        self._entry.insert(0, self._tasks[idx].text)
        self._entry.focus_set()
        self._entry.select_range(0, tk.END)
        self._entry.icursor(tk.END)
        self._redraw()

    def _cancel_edit(self) -> None:
        if self._editing_index is None:
            return
        self._editing_index = None
        self._entry.delete(0, tk.END)

    def _on_enter(self, _event: tk.Event) -> None:
        self._submit_entry(position=_InsertPosition.FIRST)

    def _on_shift_enter(self, _event: tk.Event) -> str:
        self._submit_entry(position=_InsertPosition.NEXT)
        return "break"

    def _on_entry_home(self, _event: tk.Event) -> str:
        self._submit_entry(position=_InsertPosition.FIRST)
        return "break"

    def _on_entry_end(self, _event: tk.Event) -> str:
        self._submit_entry(position=_InsertPosition.LAST)
        return "break"

    def _on_entry_escape(self, _event: tk.Event) -> str:
        if self._editing_index is not None:
            self._cancel_edit()
            self._redraw()
        self._canvas.focus_set()
        return "break"

    def _on_key(self, event: tk.Event) -> None:
        if event.widget is self._entry:
            return

        if event.keysym in ("Return", "KP_Enter"):
            if self._selected is not None:
                self._begin_edit(self._selected)
            return

        # Digit keys (main row and numpad) select a row
        if event.keysym.isdigit() or (event.keysym.startswith("KP_") and event.keysym[3:].isdigit()):
            digit = int(event.keysym[-1])
            if digit < len(self._tasks):
                self._selected = digit
                self._canvas.focus_set()
                self._redraw()
            return

        if event.char == "?":
            self._show_help()
            return

        # Printable character: redirect to entry and let the user type
        if event.char and event.char.isprintable():
            self._cancel_edit()
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
                self._cancel_edit()
                self._tasks = st.reorder(self._selected, new_idx)
                self._selected = new_idx
                self._redraw()
                self.on_stack_change()
            return

        if event.keysym == "Home":
            self._cancel_edit()
            tasks = st.promote(self._selected)
            self._tasks = tasks
            self._selected = None
            self._redraw()
            self.on_stack_change()

        elif event.keysym == "End":
            self._cancel_edit()
            tasks = st.reorder(self._selected, len(self._tasks) - 1)
            self._tasks = tasks
            self._selected = None
            self._redraw()
            self.on_stack_change()

        elif event.keysym in ("BackSpace", "Delete"):
            self._cancel_edit()
            deleted_idx = self._selected
            tasks = st.remove(deleted_idx)
            self._tasks = tasks
            self._selected = min(deleted_idx, len(tasks) - 1) if tasks else None
            self._redraw()
            self.on_stack_change()

    def show_help(self) -> None:
        self._show_help()

    def _show_help(self) -> None:
        if self._help_win is not None:
            try:
                self._help_win.lift()
                self._help_win.focus_force()
                return
            except tk.TclError:
                self._help_win = None

        win = tk.Toplevel(self.root)
        self._help_win = win
        win.title("Keyboard Shortcuts")
        win.resizable(False, False)
        win.attributes("-topmost", True)

        rows = [
            ("Typing",          "Focus entry and type"),
            ("Enter",           "Add task to bottom"),
            ("Shift+Enter",     "Add task to top"),
            ("Home",            "Add task to top  /  Promote selected to top"),
            ("End",             "Add task to bottom  /  Send selected to bottom"),
            ("0-9",             "Select task by index"),
            ("Up / Down",       "Move selection"),
            ("Left / Right",    "Move selected task up / down one position"),
            ("Return",          "Edit selected task"),
            ("Escape",          "Cancel edit  /  Hide window"),
            ("Backspace / Del", "Delete selected task"),
            ("?",               "Show this help"),
        ]

        frame = tk.Frame(win, bg="#f0f0f0", padx=16, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        for i, (key, desc) in enumerate(rows):
            tk.Label(frame, text=key, font=("TkFixedFont", 10, "bold"),
                     bg="#f0f0f0", anchor=tk.W, fg="#333").grid(
                row=i, column=0, sticky=tk.W, padx=(0, 16), pady=2)
            tk.Label(frame, text=desc, font=("TkDefaultFont", 10),
                     bg="#f0f0f0", anchor=tk.W, fg="#111").grid(
                row=i, column=1, sticky=tk.W, pady=2)

        def _close() -> None:
            self._help_win = None
            win.destroy()

        btn = tk.Button(win, text="Close", command=_close,
                        relief=tk.FLAT, bg="#4a90e2", fg="white",
                        activebackground="#357abd", activeforeground="white",
                        padx=12, pady=4)
        btn.pack(pady=(0, 12))

        win.bind("<Escape>", lambda _: _close())
        win.bind("<question>", lambda _: _close())
        win.protocol("WM_DELETE_WINDOW", _close)

        win.update_idletasks()
        if self.is_visible():
            x = self.root.winfo_x() + (self.root.winfo_width() - win.winfo_width()) // 2
            y = self.root.winfo_y() + (self.root.winfo_height() - win.winfo_height()) // 2
        else:
            x = (self.root.winfo_screenwidth() - win.winfo_width()) // 2
            y = (self.root.winfo_screenheight() - win.winfo_height()) // 3
        win.geometry(f"+{x}+{y}")
        win.focus_force()

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
            self._cancel_edit()
            self._tasks = st.reorder(self._drag_start, target)
            self._drag_start = target
            self._redraw()
            self.on_stack_change()

    def _drag_release(self, event: tk.Event) -> None:
        if self._drag_start is not None:
            released_row = self._row_at(event.y)
            if released_row == self._row_at(self._drag_y0):
                self._selected = released_row
                self._redraw()
        self._drag_start = None
