from __future__ import annotations

import platform
import threading
import tkinter as tk
import tkinter.font as tkFont
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable

from PIL import Image, ImageDraw, ImageFont, ImageTk

from . import settings as cfg
from . import stack as st


class _InsertPosition(Enum):
    FIRST = "first"
    NEXT = "next"
    LAST = "last"


@dataclass(frozen=True)
class _Theme:
    bg: str
    bg_frame: str
    selected_bg: str
    fg: str
    fg_dim: str
    fg_muted: str
    entry_bg: str
    entry_fg: str
    entry_cursor: str
    entry_disabled_fg: str
    entry_highlight_bg: str
    entry_highlight_active: str
    drag_handle: str
    btn_bg: str
    btn_fg: str
    btn_active_bg: str


_LIGHT = _Theme(
    bg="#ffffff",
    bg_frame="#f0f0f0",
    selected_bg="#d0e4ff",
    fg="#111111",
    fg_dim="#444444",
    fg_muted="#888888",
    entry_bg="white",
    entry_fg="#111111",
    entry_cursor="#111111",
    entry_disabled_fg="#888888",
    entry_highlight_bg="#aaaaaa",
    entry_highlight_active="#4a90e2",
    drag_handle="#aaaaaa",
    btn_bg="#4a90e2",
    btn_fg="white",
    btn_active_bg="#357abd",
)

_DARK = _Theme(
    bg="#1e1e1e",
    bg_frame="#2d2d2d",
    selected_bg="#1a3a5c",
    fg="#e0e0e0",
    fg_dim="#b0b0b0",
    fg_muted="#707070",
    entry_bg="#3c3c3c",
    entry_fg="#e0e0e0",
    entry_cursor="#e0e0e0",
    entry_disabled_fg="#707070",
    entry_highlight_bg="#555555",
    entry_highlight_active="#4a90e2",
    drag_handle="#666666",
    btn_bg="#2a6099",
    btn_fg="#e0e0e0",
    btn_active_bg="#1f4d7a",
)

_THEME_POLL_MS = 30_000  # macOS fallback only


def _os_prefers_dark() -> bool:
    if platform.system() == "Windows":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 0
        except Exception:
            return False
    if platform.system() == "Darwin":
        try:
            import subprocess

            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
            )
            return result.stdout.strip().lower() == "dark"
        except Exception:
            return False
    return False


def _watch_windows_theme(callback: Callable[[], None], stop: threading.Event) -> None:
    """Block on registry change notifications and call callback on each change."""
    try:
        import ctypes
        import winreg

        _REG_NOTIFY_CHANGE_LAST_SET = 0x00000004

        advapi32 = ctypes.windll.advapi32
        kernel32 = ctypes.windll.kernel32

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            access=winreg.KEY_NOTIFY | winreg.KEY_READ,
        )
        # Create a manual-reset event so we can also wake on stop
        stop_event = kernel32.CreateEventW(None, True, False, None)

        # Wire the threading.Event to the Win32 event via a helper thread
        def _set_stop() -> None:
            stop.wait()
            kernel32.SetEvent(stop_event)

        threading.Thread(target=_set_stop, daemon=True).start()

        reg_event = kernel32.CreateEventW(None, True, False, None)
        try:
            while not stop.is_set():
                kernel32.ResetEvent(reg_event)
                advapi32.RegNotifyChangeKeyValue(
                    key.handle, False, _REG_NOTIFY_CHANGE_LAST_SET, reg_event, True
                )
                handles = (ctypes.c_void_p * 2)(reg_event, stop_event)
                # Wait for either registry change or stop signal
                kernel32.WaitForMultipleObjects(2, handles, False, 0xFFFFFFFF)
                if not stop.is_set():
                    callback()
        finally:
            kernel32.CloseHandle(reg_event)
            kernel32.CloseHandle(stop_event)
            key.Close()
    except Exception:
        pass


def _keycode_digit(keycode: int) -> int | None:
    """Return 0-9 if keycode is a main-row or numpad digit key, else None.

    Keycodes are OS-level and unaffected by modifier keys like Shift, so
    this correctly identifies digit intent even when Shift turns '4' into '$'.
    Main row: 48-57 (Windows/Linux/macOS all agree).
    Numpad:   96-105 on Windows/Linux; 82-91 on macOS.
    """
    if 48 <= keycode <= 57:
        return keycode - 48
    if 96 <= keycode <= 105:
        return keycode - 96
    if platform.system() == "Darwin" and 82 <= keycode <= 91:  # macOS numpad only
        return keycode - 82
    return None


# On Windows with Num Lock on, Shift+numpad strips the Shift bit and remaps
# the keycode to the nav-key equivalent. The extended-key bit (0x40000) is set
# for real nav keys but NOT for numpad keys, making them distinguishable.
#   numpad 0 → VK_INSERT (45)
#   numpad 1 → VK_END    (35)
#   numpad 2 → VK_DOWN   (40)
#   numpad 3 → VK_NEXT   (34)
#   numpad 4 → VK_LEFT   (37)
#   numpad 5 → VK_CLEAR  (12)
#   numpad 6 → VK_RIGHT  (39)
#   numpad 7 → VK_HOME   (36)
#   numpad 8 → VK_UP     (38)
#   numpad 9 → VK_PRIOR  (33)
_WIN_SHIFTED_NUMPAD: dict[int, int] = {
    45: 0, 35: 1, 40: 2, 34: 3, 37: 4,
    12: 5, 39: 6, 36: 7, 38: 8, 33: 9,
}


def _keysym_digit(keysym: str) -> int | None:
    """Return 0-9 if keysym names a digit key (after Shift-normalization), else None."""
    if keysym.isdigit():
        return int(keysym)
    if keysym.startswith("KP_") and keysym[3:].isdigit():
        return int(keysym[3:])
    return None


_EMOJI_CACHE: dict[str, ImageTk.PhotoImage] = {}
_ROW_HEIGHT = 28
_DEFAULT_WIDTH = 480
_DEFAULT_HEIGHT = 360
_GEOMETRY_SAVE_DEBOUNCE_MS = 400
_DURATION_TICK_MS = 1_000


def _emoji_image(emoji: str, size: int = 18) -> ImageTk.PhotoImage:
    if emoji in _EMOJI_CACHE:
        return _EMOJI_CACHE[emoji]
    scale = 4
    render_size = size * scale
    try:
        font = ImageFont.truetype("seguiemj.ttf", render_size)
    except OSError:
        font = ImageFont.load_default()
    canvas_size = render_size * 3
    img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((render_size // 2, render_size // 2), emoji, font=font, embedded_color=True)
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
        self._selected: set[int] = set()
        self._last_selected: frozenset[int] = frozenset()
        self._anchor: int | None = None   # fixed end of range selection
        self._cursor: int | None = None   # moving end of range selection
        self._desc_shown_for: int | None = None
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
        self._theme_poll_after_id: str | None = None
        self._theme_stop = threading.Event()
        self._help_win: tk.Toplevel | None = None
        self._theme: _Theme = _DARK if _os_prefers_dark() else _LIGHT
        self._update_fonts()

        self._build_ui()
        self._apply_initial_geometry()
        self.refresh()
        self._canvas.focus_set()

        root.bind("<Configure>", self._on_root_configure)
        root.bind("<Destroy>", self._on_destroy)
        self._schedule_tick()
        self._start_theme_watcher()

    def _update_fonts(self) -> None:
        ff = self._settings.font_family
        fs = self._settings.font_size
        self._font_normal = (ff, fs)
        self._font_current = (ff, fs, "bold")
        self._font_obj_normal = tkFont.Font(family=ff, size=fs)
        self._font_obj_current = tkFont.Font(family=ff, size=fs, weight="bold")
        f = self._font_obj_normal
        # measure widest representative strings + small padding
        self._dur_col_w = f.measure("00h 00m") + 8
        self._ts_col_w = f.measure("00m ago") + 8
        self._lc_col_w = f.measure("00m ago") + 8
        self._idx_col_w = f.measure("999") + 4

    def _truncate(self, text: str, max_px: int, is_current: bool) -> str:
        font = self._font_obj_current if is_current else self._font_obj_normal
        if font.measure(text) <= max_px:
            return text
        ellipsis = "…"
        for end in range(len(text) - 1, 0, -1):
            candidate = text[:end] + ellipsis
            if font.measure(candidate) <= max_px:
                return candidate
        return ellipsis

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        t = self._theme
        self.root.configure(bg=t.bg_frame)
        pad = {"padx": 8, "pady": 6}

        self._top_frame = tk.Frame(self.root, bg=t.bg_frame)
        self._top_frame.pack(fill=tk.X, **pad)

        self._entry = tk.Entry(
            self._top_frame,
            font=self._font_normal,
            relief=tk.FLAT,
            bg=t.entry_bg,
            fg=t.entry_fg,
            insertbackground=t.entry_cursor,
            disabledforeground=t.entry_disabled_fg,
            readonlybackground=t.entry_bg,
            highlightthickness=1,
            highlightbackground=t.entry_highlight_bg,
            highlightcolor=t.entry_highlight_active,
        )
        self._entry.pack(fill=tk.X, ipady=4)
        self._entry.bind("<Return>", self._on_enter)
        self._entry.bind("<Shift-Return>", self._on_shift_enter)
        self._entry.bind("<Home>", self._on_entry_home)
        self._entry.bind("<End>", self._on_entry_end)
        self._entry.bind("<Escape>", self._on_entry_escape)

        self._canvas = tk.Canvas(
            self.root, bg=t.bg, highlightthickness=0, width=460, height=_ROW_HEIGHT
        )
        self._canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 0))

        self._canvas.configure(takefocus=True)
        self._canvas.bind("<ButtonPress-1>", self._drag_press)
        self._canvas.bind("<B1-Motion>", self._drag_motion)
        self._canvas.bind("<ButtonRelease-1>", self._drag_release)
        self._canvas.bind("<Key>", self._on_key)
        self._canvas.bind("<Escape>", self._on_canvas_escape)
        self._canvas.bind("<Configure>", lambda _e: self._redraw())

        self._desc_frame = tk.Frame(self.root, bg=t.bg_frame)
        self._desc_frame.pack(fill=tk.X, padx=8, pady=(4, 8))

        self._desc_text = tk.Text(
            self._desc_frame,
            font=self._font_normal,
            relief=tk.FLAT,
            bg=t.entry_bg,
            fg=t.entry_fg,
            insertbackground=t.entry_cursor,
            highlightthickness=1,
            highlightbackground=t.entry_highlight_bg,
            highlightcolor=t.entry_highlight_active,
            height=4,
            wrap=tk.WORD,
            undo=True,
        )
        self._desc_text.pack(fill=tk.X)
        self._desc_text.bind("<FocusOut>", self._on_desc_focus_out)
        self._desc_text.bind("<FocusIn>", self._on_desc_focus_in)
        self._desc_text.bind("<Escape>", self._on_desc_escape)
        self._desc_placeholder_active = False
        self._desc_frame.pack_forget()

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
        self._save_after_id = self.root.after(_GEOMETRY_SAVE_DEBOUNCE_MS, self._capture_geometry)

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

    def _start_theme_watcher(self) -> None:
        if platform.system() == "Windows":
            threading.Thread(
                target=_watch_windows_theme,
                args=(self._on_theme_change_from_thread, self._theme_stop),
                daemon=True,
            ).start()
        else:
            self._schedule_theme_poll()

    def _on_theme_change_from_thread(self) -> None:
        # Called from background thread — post to tkinter's event loop
        try:
            self.root.after(0, self._check_theme_change)
        except tk.TclError:
            pass

    def _check_theme_change(self) -> None:
        new_theme = _DARK if _os_prefers_dark() else _LIGHT
        if new_theme is not self._theme:
            self._theme = new_theme
            self._apply_theme()

    def _schedule_theme_poll(self) -> None:
        try:
            self._theme_poll_after_id = self.root.after(_THEME_POLL_MS, self._on_theme_poll)
        except tk.TclError:
            self._theme_poll_after_id = None

    def _on_theme_poll(self) -> None:
        self._theme_poll_after_id = None
        try:
            self._check_theme_change()
        finally:
            self._schedule_theme_poll()

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self.root:
            self._theme_stop.set()

    def _apply_theme(self) -> None:
        t = self._theme
        self.root.configure(bg=t.bg_frame)
        self._top_frame.configure(bg=t.bg_frame)
        self._entry.configure(
            bg=t.entry_bg,
            fg=t.entry_fg,
            insertbackground=t.entry_cursor,
            disabledforeground=t.entry_disabled_fg,
            readonlybackground=t.entry_bg,
            highlightbackground=t.entry_highlight_bg,
            highlightcolor=t.entry_highlight_active,
        )
        self._canvas.configure(bg=t.bg)
        self._desc_frame.configure(bg=t.bg_frame)
        self._desc_text.configure(
            bg=t.entry_bg,
            fg=t.entry_fg,
            insertbackground=t.entry_cursor,
            highlightbackground=t.entry_highlight_bg,
            highlightcolor=t.entry_highlight_active,
        )
        self._redraw()

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
        self._selected = set()
        self._anchor = None
        self._cursor = None
        self._desc_shown_for = None
        self._cancel_edit()
        self._redraw()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _redraw(self) -> None:
        c = self._canvas
        t = self._theme
        c.delete("all")
        now = datetime.now().astimezone()

        width = c.winfo_width()
        if width <= 1:
            width = int(c.cget("width"))
        right_pad = 8
        gap = 8
        dur_x = width - right_pad
        lc_x = dur_x - self._dur_col_w - gap
        ts_x = lc_x - self._lc_col_w - gap
        text_right = ts_x - self._ts_col_w - gap

        for i, task in enumerate(self._tasks):
            y0 = i * _ROW_HEIGHT
            y1 = y0 + _ROW_HEIGHT

            bg = t.selected_bg if i in self._selected else t.bg
            c.create_rectangle(0, y0, width, y1, fill=bg, outline="", tags=f"row{i}")

            for dy in (8, 13, 18):
                c.create_line(8, y0 + dy, 18, y0 + dy, fill=t.drag_handle, width=1.5)

            font = self._font_current if i == 0 else self._font_normal
            idx_x = 22
            c.create_text(
                idx_x, y0 + _ROW_HEIGHT // 2, text=str(i), anchor=tk.W, font=font, fill=t.fg_muted
            )
            indicator_x = idx_x + self._idx_col_w
            indicator = "🔥" if i == 0 else "💤"
            img = _emoji_image(indicator)
            c.create_image(indicator_x, y0 + _ROW_HEIGHT // 2, image=img, anchor=tk.W)

            note_x = indicator_x + 20
            if task.description:
                img_note = _emoji_image("📝")
                c.create_image(note_x, y0 + _ROW_HEIGHT // 2, image=img_note, anchor=tk.W)
                text_x = note_x + 22
            else:
                text_x = note_x + 2
            text_width = max(0, text_right - text_x)
            label = self._truncate(task.text, text_width, i == 0)
            c.create_text(
                text_x,
                y0 + _ROW_HEIGHT // 2,
                text=label,
                anchor=tk.W,
                font=font,
                fill=t.fg,
            )

            if i == 0:
                ts_text = st.format_timestamp(task.started_at, now)
                dur_seconds = task.live_duration(now)
                col_fill = t.fg_dim
            else:
                ts_text = st.format_timestamp(task.started_at, now)
                dur_seconds = task.duration
                col_fill = t.fg_muted
            c.create_text(
                ts_x,
                y0 + _ROW_HEIGHT // 2,
                text=ts_text,
                anchor=tk.E,
                font=self._font_normal,
                fill=col_fill,
            )
            c.create_text(
                lc_x,
                y0 + _ROW_HEIGHT // 2,
                text=st.format_timestamp(task.last_current, now),
                anchor=tk.E,
                font=self._font_normal,
                fill=col_fill,
            )
            c.create_text(
                dur_x,
                y0 + _ROW_HEIGHT // 2,
                text=st.format_duration(dur_seconds),
                anchor=tk.E,
                font=self._font_normal,
                fill=col_fill,
            )

        if not self._tasks:
            c.create_text(
                width // 2,
                _ROW_HEIGHT // 2,
                text="No tasks — type above and press Enter",
                fill=t.fg_muted,
                font=self._font_normal,
            )

        current = frozenset(self._selected)
        if current != self._last_selected:
            self._last_selected = current
            if len(self._selected) == 1:
                (sole,) = self._selected
                if 0 <= sole < len(self._tasks) and self._editing_index is None:
                    self._entry.delete(0, tk.END)
                    self._entry.insert(0, self._tasks[sole].text)
                    self._entry.select_range(0, tk.END)
            elif self._editing_index is None:
                self._entry.delete(0, tk.END)

        if len(self._selected) == 1:
            (sole,) = self._selected
            if 0 <= sole < len(self._tasks):
                self._show_desc_panel(sole)
                return
        self._hide_desc_panel()

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _submit_entry(self, *, position: _InsertPosition = _InsertPosition.FIRST) -> None:
        text = self._entry.get().strip()
        edit_idx = self._editing_index
        if edit_idx is None and len(self._selected) == 1:
            (sole,) = self._selected
            if 0 <= sole < len(self._tasks):
                edit_idx = sole
        if edit_idx is not None:
            idx = edit_idx
            if not text:
                self._cancel_edit()
                self._redraw()
                return
            tasks = st.update_text(idx, text)
            self._editing_index = None
            self._tasks = tasks
            self._selected = {idx} if 0 <= idx < len(tasks) else set()
            self._last_selected = frozenset(self._selected)
            self._anchor = idx if self._selected else None
            self._cursor = self._anchor
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
        self._selected = set()
        self._anchor = None
        self._cursor = None
        self._redraw()
        self.on_stack_change()
        self._canvas.focus_set()

    def _begin_edit(self, idx: int) -> None:
        if not (0 <= idx < len(self._tasks)):
            return
        self._editing_index = idx
        self._selected = {idx}
        self._anchor = idx
        self._cursor = idx
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

    def _show_desc_panel(self, idx: int) -> None:
        if self._desc_shown_for == idx:
            return
        self._desc_shown_for = idx
        task = self._tasks[idx]
        t = self._theme
        self._desc_text.configure(state=tk.NORMAL)
        self._desc_text.delete("1.0", tk.END)
        if task.description:
            self._desc_text.configure(fg=t.entry_fg)
            self._desc_text.insert("1.0", task.description)
            self._desc_placeholder_active = False
        else:
            self._desc_text.configure(fg=t.fg_muted)
            self._desc_text.insert("1.0", "Add a description…")
            self._desc_placeholder_active = True
        self._desc_frame.pack(fill=tk.X, padx=8, pady=(4, 8))

    def _hide_desc_panel(self) -> None:
        if self._desc_shown_for is None:
            return
        self._desc_shown_for = None
        self._desc_frame.pack_forget()

    def _save_desc(self) -> None:
        # Save to whichever task the description panel is currently bound to,
        # not the current selection — selection/index can shift (e.g. during a
        # drag-reorder) while the panel still displays the original task's text.
        idx = self._desc_shown_for
        if idx is None:
            return
        if not (0 <= idx < len(self._tasks)):
            return
        if self._desc_placeholder_active:
            return
        content = self._desc_text.get("1.0", tk.END).rstrip("\n")
        self._tasks = st.update_description(idx, content)
        self._desc_shown_for = None

    def _on_desc_focus_out(self, _event: tk.Event) -> None:
        self._save_desc()

    def _on_desc_escape(self, _event: tk.Event) -> str:
        self._save_desc()
        self._canvas.focus_set()
        return "break"

    def _on_desc_focus_in(self, _event: tk.Event) -> None:
        if self._desc_placeholder_active:
            self._desc_text.delete("1.0", tk.END)
            self._desc_text.configure(fg=self._theme.entry_fg)
            self._desc_placeholder_active = False

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

    def _on_canvas_escape(self, _event: tk.Event) -> str:
        if self._selected:
            self._selected = set()
            self._anchor = None
            self._cursor = None
            if self._editing_index is None:
                self._entry.delete(0, tk.END)
            self._redraw()
            return "break"
        self.hide()
        return "break"

    def _on_entry_escape(self, _event: tk.Event) -> str:
        if self._editing_index is not None:
            self._cancel_edit()
            self._redraw()
        self._canvas.focus_set()
        return "break"

    # When Shift is held, numpad navigation keys report as KP_Up/KP_Down/etc.
    # instead of KP_8/KP_2/etc. Map them back to the digit they represent.
    _SHIFT_KP_DIGIT: dict[str, str] = {
        # KP_ keysyms (Num Lock on, some platforms)
        "KP_Insert": "KP_0",
        "KP_End": "KP_1",
        "KP_Down": "KP_2",
        "KP_Next": "KP_3",
        "KP_Left": "KP_4",
        "KP_Begin": "KP_5",
        "KP_Right": "KP_6",
        "KP_Home": "KP_7",
        "KP_Up": "KP_8",
        "KP_Prior": "KP_9",
    }

    def _on_key(self, event: tk.Event) -> None:
        if event.widget is self._entry:
            return

        # Normalize Shift+numpad nav keys to their digit keysym equivalents.
        # Check Num Lock bit (0x0008) to distinguish numpad from real arrow/nav keys.
        _numlock = bool(event.state & 0x0008)
        if event.state & 0x0001 and _numlock and event.keysym in self._SHIFT_KP_DIGIT:
            event.keysym = self._SHIFT_KP_DIGIT[event.keysym]

        if event.keysym in ("Return", "KP_Enter"):
            if len(self._selected) == 1:
                self._entry.focus_set()
                self._entry.select_range(0, tk.END)
                self._entry.icursor(tk.END)
            return

        # Digit keys select a row. Try keycode first (immune to Shift on main row),
        # then the Win-shifted-numpad table for unambiguous nav keycodes (Num Lock on,
        # Shift stripped by OS), then fall back to keysym for KP_ numpad keys.
        _shift_bit = bool(event.state & 0x0001)
        _kc = _keycode_digit(event.keycode)
        # Win-shifted-numpad: Num Lock on, Shift bit absent (stripped by OS),
        # and extended-key bit (0x40000) absent (real nav keys always have it).
        _extended = bool(event.state & 0x40000)
        _win_kp = _WIN_SHIFTED_NUMPAD.get(event.keycode) if (_numlock and not _shift_bit and not _extended) else None
        digit = _kc if _kc is not None else (_win_kp if _win_kp is not None else _keysym_digit(event.keysym))
        # Treat unambiguous Win-shifted-numpad hits as Shift (the bit was stripped by OS).
        _shift = _shift_bit or _win_kp is not None
        if digit is not None:
            if digit < len(self._tasks):
                self._save_desc()
                if _shift:  # Shift held: extend from anchor
                    if self._anchor is None:
                        self._anchor = digit
                    self._cursor = digit
                    lo, hi = min(self._anchor, self._cursor), max(self._anchor, self._cursor)
                    self._selected = set(range(lo, hi + 1))
                else:
                    self._anchor = digit
                    self._cursor = digit
                    self._selected = {digit}
                self._canvas.focus_set()
                self._redraw()
            return

        if event.char == "?":
            self._show_help()
            return

        # Printable character: redirect to entry and let the user type
        if event.char and event.char.isprintable():
            self._cancel_edit()
            self._entry.delete(0, tk.END)
            self._entry.focus_set()
            self._entry.insert(tk.END, event.char)
            return

        if event.keysym in ("Up", "Down"):
            self._save_desc()
            delta = -1 if event.keysym == "Up" else 1
            if event.state & 0x0001:  # Shift: move cursor, keep anchor fixed
                if self._anchor is None:
                    # Nothing selected yet — pick an edge to anchor on
                    self._anchor = 0 if event.keysym == "Down" else len(self._tasks) - 1
                    self._cursor = self._anchor
                cursor_pos = self._cursor if self._cursor is not None else self._anchor
                new_cursor = max(0, min(len(self._tasks) - 1, cursor_pos + delta))
                self._cursor = new_cursor
                lo, hi = min(self._anchor, self._cursor), max(self._anchor, self._cursor)
                self._selected = set(range(lo, hi + 1))
            else:
                # Plain Up/Down: move single selection
                if not self._selected:
                    pos = 0 if event.keysym == "Down" else len(self._tasks) - 1
                else:
                    cur = self._cursor if self._cursor is not None else min(self._selected)
                    pos = max(0, min(len(self._tasks) - 1, cur + delta))
                self._anchor = pos
                self._cursor = pos
                self._selected = {pos}
            self._canvas.focus_set()
            self._redraw()
            return

        if not self._selected:
            return

        # Single-selection-only operations: require exactly one selected row
        sole: int | None = None
        if len(self._selected) == 1:
            (sole,) = self._selected

        if event.keysym in ("Left", "Right"):
            if sole is None:
                return
            delta = -1 if event.keysym == "Left" else 1
            new_idx = sole + delta
            if 0 <= new_idx < len(self._tasks):
                self._cancel_edit()
                self._tasks = st.reorder(sole, new_idx)
                self._selected = {new_idx}
                self._anchor = new_idx
                self._cursor = new_idx
                self._redraw()
                self.on_stack_change()
            return

        if event.keysym == "Home":
            if sole is None:
                return
            self._cancel_edit()
            tasks = st.promote(sole)
            self._tasks = tasks
            self._selected = set()
            self._anchor = None
            self._cursor = None
            self._redraw()
            self.on_stack_change()

        elif event.keysym == "End":
            if sole is None:
                return
            self._cancel_edit()
            tasks = st.reorder(sole, len(self._tasks) - 1)
            self._tasks = tasks
            self._selected = set()
            self._anchor = None
            self._cursor = None
            self._redraw()
            self.on_stack_change()

        elif event.keysym in ("BackSpace", "Delete"):
            self._cancel_edit()
            min_deleted = min(self._selected)
            tasks = st.remove_many(self._selected)
            self._tasks = tasks
            if tasks:
                next_sel = min(min_deleted, len(tasks) - 1)
                self._selected = {next_sel}
                self._anchor = next_sel
                self._cursor = next_sel
            else:
                self._selected = set()
                self._anchor = None
                self._cursor = None
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

        t = self._theme
        win = tk.Toplevel(self.root)
        self._help_win = win
        win.title("Keyboard Shortcuts")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.configure(bg=t.bg_frame)

        rows = [
            ("Typing", "Focus entry and type"),
            ("Enter", "Add task to bottom"),
            ("Shift+Enter", "Add task to top"),
            ("Home", "Add task to top  /  Promote selected to top"),
            ("End", "Add task to bottom  /  Send selected to bottom"),
            ("0-9", "Select task by index"),
            ("Shift+0-9 / Shift+↑↓", "Extend selection (range)"),
            ("Shift+click", "Extend selection to clicked row"),
            ("Up / Down", "Move selection"),
            ("Left / Right", "Move selected task up / down one position"),
            ("Return", "Edit selected task"),
            ("Escape", "Cancel edit  /  Hide window"),
            ("Backspace / Del", "Delete selected task(s)"),
            ("?", "Show this help"),
        ]

        frame = tk.Frame(win, bg=t.bg_frame, padx=16, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        for i, (key, desc) in enumerate(rows):
            tk.Label(
                frame,
                text=key,
                font=("TkFixedFont", 10, "bold"),
                bg=t.bg_frame,
                anchor=tk.W,
                fg=t.fg_dim,
            ).grid(row=i, column=0, sticky=tk.W, padx=(0, 16), pady=2)
            tk.Label(
                frame, text=desc, font=("TkDefaultFont", 10), bg=t.bg_frame, anchor=tk.W, fg=t.fg
            ).grid(row=i, column=1, sticky=tk.W, pady=2)

        def _close() -> None:
            self._help_win = None
            win.destroy()

        btn = tk.Button(
            win,
            text="Close",
            command=_close,
            relief=tk.FLAT,
            bg=t.btn_bg,
            fg=t.btn_fg,
            activebackground=t.btn_active_bg,
            activeforeground=t.btn_fg,
            padx=12,
            pady=4,
        )
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
        self._save_desc()
        self._canvas.focus_set()
        self._drag_start = self._row_at(event.y)
        self._drag_y0 = event.y

    def _drag_motion(self, event: tk.Event) -> None:
        if self._drag_start is None or len(self._tasks) < 2:
            return
        target = self._row_at(event.y)
        if target == self._drag_start:
            return
        self._cancel_edit()
        src = self._drag_start
        # If the dragged row is part of a multi-selection, the entire selected
        # block moves together (preserving the rows' relative order). Otherwise
        # only the dragged row moves. Either way ``reorder_group`` returns an
        # index map that we use to translate every tracked index (selection,
        # anchor, cursor, description binding) through the reorder, so they
        # keep pointing at the same tasks they pointed at before.
        if src in self._selected and len(self._selected) > 1:
            group = set(self._selected)
        else:
            group = {src}
        self._tasks, index_map = st.reorder_group(group, src, target)

        def remap(i: int) -> int:
            return index_map.get(i, i)

        self._selected = {remap(i) for i in self._selected}
        self._anchor = remap(self._anchor) if self._anchor is not None else None
        self._cursor = remap(self._cursor) if self._cursor is not None else None
        self._desc_shown_for = (
            remap(self._desc_shown_for) if self._desc_shown_for is not None else None
        )
        self._last_selected = frozenset(self._selected)
        new_src = index_map.get(src, src)
        self._drag_start = new_src
        self._redraw()
        self.on_stack_change()

    def _drag_release(self, event: tk.Event) -> None:
        if self._drag_start is not None:
            released_row = self._row_at(event.y)
            if released_row == self._row_at(self._drag_y0):
                if event.state & 0x0001:  # Shift+click: extend selection from anchor
                    if self._anchor is None:
                        self._anchor = released_row
                    self._cursor = released_row
                    lo, hi = min(self._anchor, self._cursor), max(self._anchor, self._cursor)
                    self._selected = set(range(lo, hi + 1))
                else:
                    self._anchor = released_row
                    self._cursor = released_row
                    self._selected = {released_row}
                self._redraw()
        self._drag_start = None
