"""Persisted UI settings (window geometry, etc.)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

SETTINGS_FILE = Path.home() / ".task-stack.settings.json"
_TMP = SETTINGS_FILE.with_suffix(".json.tmp")


@dataclass
class WindowGeometry:
    width: int
    height: int
    x: int
    y: int

    @staticmethod
    def from_dict(d: dict) -> "WindowGeometry | None":
        try:
            return WindowGeometry(
                width=int(d["width"]),
                height=int(d["height"]),
                x=int(d["x"]),
                y=int(d["y"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def to_geometry_string(self) -> str:
        x_sign = "+" if self.x >= 0 else "-"
        y_sign = "+" if self.y >= 0 else "-"
        return f"{self.width}x{self.height}{x_sign}{abs(self.x)}{y_sign}{abs(self.y)}"


DEFAULT_HOTKEY = "ctrl+shift+t"


@dataclass
class Settings:
    window: WindowGeometry | None = None
    hotkey: str = DEFAULT_HOTKEY

    @staticmethod
    def from_dict(d: dict) -> "Settings":
        if not isinstance(d, dict):
            return Settings()
        win = d.get("window")
        hk = d.get("hotkey")
        return Settings(
            window=WindowGeometry.from_dict(win) if isinstance(win, dict) else None,
            hotkey=hk if isinstance(hk, str) and hk.strip() else DEFAULT_HOTKEY,
        )

    def to_dict(self) -> dict:
        return {
            "window": asdict(self.window) if self.window else None,
            "hotkey": self.hotkey,
        }


def load() -> Settings:
    if not SETTINGS_FILE.exists():
        return Settings()
    try:
        return Settings.from_dict(json.loads(SETTINGS_FILE.read_text()))
    except Exception:
        return Settings()


def save(settings: Settings) -> None:
    try:
        _TMP.write_text(json.dumps(settings.to_dict(), indent=2))
        os.replace(_TMP, SETTINGS_FILE)
    except OSError:
        pass
