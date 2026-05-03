"""Parse a user-friendly hotkey spec and match it against pynput key events.

The format supported in settings is a `+`-separated list of tokens, e.g.:

    "ctrl+shift+t"
    "alt+f1"
    "cmd+space"          (macOS-only modifier alias)
    "super+/"            (Windows / Linux super key)

Modifier aliases (case-insensitive):
    ctrl, control          -> Ctrl
    shift                  -> Shift
    alt, option, opt       -> Alt
    cmd, command, super,   -> Cmd / Super (the GUI key)
    win, meta

Non-modifier tokens may be:
    - a single printable character (a–z, 0–9, punctuation): "t", "/", "1"
    - a function key: "f1".."f24"
    - a named key supported by pynput.keyboard.Key: "space", "tab",
      "enter"/"return", "esc"/"escape", "up", "down", "left", "right",
      "home", "end", "page_up", "page_down", "insert", "delete", "backspace"

Matching logic mirrors what `HotkeyListener` does: the listener tracks held
modifiers and, when the non-modifier key is pressed, asks `HotkeySpec.matches()`
whether the pressed key is the configured key.
"""

from __future__ import annotations

import string
import sys
from dataclasses import dataclass, field
from typing import Iterable

from pynput import keyboard


def _vk_to_char(vk: int) -> str | None:
    """Resolve a Windows VK code to a character using ToUnicode (no modifiers)."""
    if sys.platform != "win32":
        return None
    import ctypes
    buf = ctypes.create_unicode_buffer(8)
    state = (ctypes.c_ubyte * 256)()
    n = ctypes.windll.user32.ToUnicode(vk, 0, state, buf, 8, 0)
    return buf.value[0].lower() if n > 0 else None


_MODIFIER_ALIASES: dict[str, str] = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "option": "alt",
    "opt": "alt",
    "cmd": "cmd",
    "command": "cmd",
    "super": "cmd",
    "win": "cmd",
    "meta": "cmd",
}

def _build_named_keys() -> dict[str, keyboard.Key]:
    aliases: dict[str, str] = {
        "space": "space",
        "tab": "tab",
        "enter": "enter",
        "return": "enter",
        "esc": "esc",
        "escape": "esc",
        "up": "up",
        "down": "down",
        "left": "left",
        "right": "right",
        "home": "home",
        "end": "end",
        "page_up": "page_up",
        "pageup": "page_up",
        "page_down": "page_down",
        "pagedown": "page_down",
        "insert": "insert",
        "delete": "delete",
        "backspace": "backspace",
    }
    out: dict[str, keyboard.Key] = {}
    for alias, attr in aliases.items():
        key = getattr(keyboard.Key, attr, None)
        if key is not None:
            out[alias] = key
    return out


_NAMED_KEYS: dict[str, keyboard.Key] = _build_named_keys()

# Apple Virtual Key codes for ASCII letters / digits, used as a fallback when
# Ctrl masks the character translation on macOS. Source: HIToolbox/Events.h.
_APPLE_VK_BY_CHAR: dict[str, int] = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05, "z": 0x06,
    "x": 0x07, "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C, "w": 0x0D, "e": 0x0E,
    "r": 0x0F, "y": 0x10, "t": 0x11, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15,
    "6": 0x16, "5": 0x17, "=": 0x18, "9": 0x19, "7": 0x1A, "-": 0x1B, "8": 0x1C,
    "0": 0x1D, "]": 0x1E, "o": 0x1F, "u": 0x20, "[": 0x21, "i": 0x22, "p": 0x23,
    "l": 0x25, "j": 0x26, "'": 0x27, "k": 0x28, ";": 0x29, "\\": 0x2A, ",": 0x2B,
    "/": 0x2C, "n": 0x2D, "m": 0x2E, ".": 0x2F, "`": 0x32,
}


class HotkeyParseError(ValueError):
    pass


@dataclass(frozen=True)
class HotkeySpec:
    modifiers: frozenset[str]   # subset of {"ctrl","shift","alt","cmd"}
    char: str | None = None     # lowercase, single character (e.g. "t")
    named_key: keyboard.Key | None = None
    vk: int | None = None       # Apple VK fallback for letters/digits/symbols

    pretty: str = field(default="", compare=False)

    def matches_key(self, key: object) -> bool:
        if self.named_key is not None:
            return key == self.named_key
        if isinstance(key, keyboard.KeyCode):
            if self.char is not None:
                kc_char = key.char
                if kc_char and kc_char.lower() == self.char:
                    return True
            if self.vk is not None:
                kc_vk = getattr(key, "vk", None)
                if kc_vk is not None and kc_vk == self.vk:
                    return True
            # On Windows, modifiers suppress char translation so key.char is None.
            # Resolve the pressed VK back to a character and compare.
            if self.char is not None and key.char is None:
                kc_vk = getattr(key, "vk", None)
                if kc_vk is not None:
                    resolved = _vk_to_char(kc_vk)
                    if resolved == self.char:
                        return True
        return False


def parse(spec: str) -> HotkeySpec:
    if not isinstance(spec, str) or not spec.strip():
        raise HotkeyParseError("empty hotkey spec")

    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise HotkeyParseError(f"could not parse hotkey: {spec!r}")

    modifiers: set[str] = set()
    key_token: str | None = None
    pretty_parts: list[str] = []

    for token in parts:
        if token in _MODIFIER_ALIASES:
            mod = _MODIFIER_ALIASES[token]
            modifiers.add(mod)
            pretty_parts.append(mod.title())
            continue
        if key_token is not None:
            raise HotkeyParseError(
                f"hotkey {spec!r} has more than one non-modifier key "
                f"(saw {key_token!r} and {token!r})"
            )
        key_token = token
        pretty_parts.append(token if len(token) == 1 else token.title())

    if key_token is None:
        raise HotkeyParseError(f"hotkey {spec!r} is missing a non-modifier key")

    pretty = "+".join(pretty_parts)

    if key_token in _NAMED_KEYS:
        return HotkeySpec(
            modifiers=frozenset(modifiers),
            named_key=_NAMED_KEYS[key_token],
            pretty=pretty,
        )

    if len(key_token) > 1 and key_token[0] == "f" and key_token[1:].isdigit():
        n = int(key_token[1:])
        if 1 <= n <= 24:
            fn = getattr(keyboard.Key, f"f{n}", None)
            if fn is None:
                raise HotkeyParseError(f"function key {key_token!r} unsupported by pynput")
            return HotkeySpec(
                modifiers=frozenset(modifiers),
                named_key=fn,
                pretty=pretty,
            )

    if len(key_token) == 1 and key_token in (string.ascii_lowercase + string.digits + string.punctuation):
        return HotkeySpec(
            modifiers=frozenset(modifiers),
            char=key_token,
            vk=_APPLE_VK_BY_CHAR.get(key_token),
            pretty=pretty,
        )

    raise HotkeyParseError(
        f"unrecognized key token {key_token!r} in hotkey {spec!r}"
    )


def parse_or_default(spec: str, default: str) -> HotkeySpec:
    try:
        return parse(spec)
    except HotkeyParseError:
        return parse(default)


def modifier_keys(modifier: str) -> Iterable[keyboard.Key]:
    if modifier == "ctrl":
        return (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)
    if modifier == "shift":
        return (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r)
    if modifier == "alt":
        return (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r)
    if modifier == "cmd":
        return (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r)
    return ()
