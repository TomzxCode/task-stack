"""Persisted UI settings (window geometry, hotkey)."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

SETTINGS_FILE = Path.home() / ".task-stack.settings.yaml"
_TMP = SETTINGS_FILE.with_suffix(".yaml.tmp")


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
        except KeyError, TypeError, ValueError:
            return None

    def to_geometry_string(self) -> str:
        x_sign = "+" if self.x >= 0 else "-"
        y_sign = "+" if self.y >= 0 else "-"
        return f"{self.width}x{self.height}{x_sign}{abs(self.x)}{y_sign}{abs(self.y)}"


DEFAULT_HOTKEY = "ctrl+shift+t"
DEFAULT_FONT_FAMILY = "TkDefaultFont"
DEFAULT_FONT_SIZE = 11


@dataclass
class IconThreshold:
    min_count: int
    color: tuple[int, int, int]

    @staticmethod
    def from_dict(d: object) -> "IconThreshold | None":
        if not isinstance(d, dict):
            return None
        try:
            mc = int(d["min_count"])
            c = d["color"]
            if isinstance(c, str):
                hex_str = c.lstrip("#")
                if len(hex_str) == 6:
                    r, g, b = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
                    return IconThreshold(min_count=mc, color=(r, g, b))
        except KeyError, TypeError, ValueError:
            pass
        return None

    def to_dict(self) -> dict:
        r, g, b = self.color
        return {"min_count": self.min_count, "color": f"#{r:02x}{g:02x}{b:02x}"}


def _default_icon_thresholds() -> list[IconThreshold]:
    from .icon import DEFAULT_THRESHOLDS

    return [IconThreshold(min_count=mc, color=rgb) for mc, rgb in DEFAULT_THRESHOLDS]


@dataclass
class Settings:
    window: WindowGeometry | None = None
    hotkey: str = DEFAULT_HOTKEY
    font_family: str = DEFAULT_FONT_FAMILY
    font_size: int = DEFAULT_FONT_SIZE
    icon_thresholds: list[IconThreshold] | None = None

    def resolved_icon_thresholds(self) -> list[tuple[int, tuple[int, int, int]]]:
        thresholds = self.icon_thresholds or _default_icon_thresholds()
        return [(t.min_count, t.color) for t in sorted(thresholds, key=lambda t: t.min_count)]

    @staticmethod
    def from_dict(d: dict) -> "Settings":
        if not isinstance(d, dict):
            return Settings()
        win = d.get("window")
        hk = d.get("hotkey")
        ff = d.get("font_family")
        fs = d.get("font_size")
        raw_thresholds = d.get("icon_thresholds")
        icon_thresholds: list[IconThreshold] | None = None
        if isinstance(raw_thresholds, list):
            parsed = [IconThreshold.from_dict(t) for t in raw_thresholds]
            valid = [t for t in parsed if t is not None]
            if valid:
                icon_thresholds = valid
        return Settings(
            window=WindowGeometry.from_dict(win) if isinstance(win, dict) else None,
            hotkey=hk if isinstance(hk, str) and hk.strip() else DEFAULT_HOTKEY,
            font_family=ff if isinstance(ff, str) and ff.strip() else DEFAULT_FONT_FAMILY,
            font_size=int(fs)
            if isinstance(fs, (int, float)) and 6 <= int(fs) <= 72
            else DEFAULT_FONT_SIZE,
            icon_thresholds=icon_thresholds,
        )

    def to_dict(self) -> dict:
        return {
            "window": asdict(self.window) if self.window else None,
            "hotkey": self.hotkey,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "icon_thresholds": [t.to_dict() for t in self.icon_thresholds]
            if self.icon_thresholds
            else None,
        }


def load() -> Settings:
    if not SETTINGS_FILE.exists():
        return Settings()
    try:
        data = yaml.safe_load(SETTINGS_FILE.read_text())
    except Exception:
        return Settings()
    return Settings.from_dict(data) if isinstance(data, dict) else Settings()


def save(settings: Settings) -> None:
    try:
        _TMP.write_text(
            yaml.safe_dump(
                settings.to_dict(),
                sort_keys=False,
                allow_unicode=True,
                default_flow_style=False,
            )
        )
        os.replace(_TMP, SETTINGS_FILE)
    except OSError:
        pass
