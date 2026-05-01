"""Persisted UI settings (window geometry, hotkey)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

SETTINGS_FILE = Path.home() / ".task-stack.settings.yaml"
_TMP = SETTINGS_FILE.with_suffix(".yaml.tmp")
_LEGACY_JSON_FILE = Path.home() / ".task-stack.settings.json"


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


def _migrate_legacy_json() -> Settings | None:
    if not _LEGACY_JSON_FILE.exists():
        return None
    try:
        data = json.loads(_LEGACY_JSON_FILE.read_text())
    except Exception:
        return None
    settings = Settings.from_dict(data)
    try:
        save(settings)
    except Exception:
        return settings
    try:
        _LEGACY_JSON_FILE.rename(_LEGACY_JSON_FILE.with_suffix(".json.bak"))
    except OSError:
        pass
    return settings


def load() -> Settings:
    if not SETTINGS_FILE.exists():
        migrated = _migrate_legacy_json()
        if migrated is not None:
            return migrated
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
