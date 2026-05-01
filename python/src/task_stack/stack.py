from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

STACK_FILE = Path.home() / ".task-stack.yaml"
_TMP = STACK_FILE.with_suffix(".yaml.tmp")
_LEGACY_JSON_FILE = Path.home() / ".task-stack.json"


@dataclass
class Task:
    text: str
    last_current: datetime | None = field(default=None)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "last_current": self.last_current.isoformat() if self.last_current else None,
        }

    @staticmethod
    def from_dict(d: dict) -> "Task":
        lc = d.get("last_current")
        return Task(
            text=d["text"],
            last_current=datetime.fromisoformat(lc) if lc else None,
        )


def _parse_tasks(data: object) -> list[Task]:
    if not isinstance(data, list):
        return []
    out: list[Task] = []
    for item in data:
        if isinstance(item, dict):
            try:
                out.append(Task.from_dict(item))
            except Exception:
                continue
    return out


def _migrate_legacy_json() -> list[Task] | None:
    """Read the old JSON file (if any) and write it back as YAML. Returns the tasks."""
    if not _LEGACY_JSON_FILE.exists():
        return None
    try:
        data = json.loads(_LEGACY_JSON_FILE.read_text())
    except Exception:
        return None
    tasks = _parse_tasks(data)
    try:
        save(tasks)
    except Exception:
        return tasks
    try:
        _LEGACY_JSON_FILE.rename(_LEGACY_JSON_FILE.with_suffix(".json.bak"))
    except OSError:
        pass
    return tasks


def load() -> list[Task]:
    if not STACK_FILE.exists():
        migrated = _migrate_legacy_json()
        if migrated is not None:
            return migrated
        return []
    try:
        data = yaml.safe_load(STACK_FILE.read_text())
    except Exception:
        return []
    return _parse_tasks(data)


def save(tasks: list[Task]) -> None:
    data = yaml.safe_dump(
        [t.to_dict() for t in tasks],
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    _TMP.write_text(data)
    os.replace(_TMP, STACK_FILE)


def push(text: str) -> list[Task]:
    tasks = load()
    task = Task(text=text.strip(), last_current=datetime.now(tz=timezone.utc))
    tasks.insert(0, task)
    save(tasks)
    return tasks


def pop() -> tuple[Task | None, list[Task]]:
    tasks = load()
    if not tasks:
        return None, []
    removed = tasks.pop(0)
    if tasks:
        tasks[0].last_current = datetime.now(tz=timezone.utc)
    save(tasks)
    return removed, tasks


def reorder(from_idx: int, to_idx: int) -> list[Task]:
    tasks = load()
    if from_idx == to_idx or not (0 <= from_idx < len(tasks)) or not (0 <= to_idx < len(tasks)):
        return tasks
    task = tasks.pop(from_idx)
    tasks.insert(to_idx, task)
    if to_idx == 0:
        tasks[0].last_current = datetime.now(tz=timezone.utc)
    save(tasks)
    return tasks


def promote(idx: int) -> list[Task]:
    return reorder(idx, 0)


def remove(idx: int) -> list[Task]:
    tasks = load()
    if not (0 <= idx < len(tasks)):
        return tasks
    tasks.pop(idx)
    if tasks and idx == 0:
        tasks[0].last_current = datetime.now(tz=timezone.utc)
    save(tasks)
    return tasks


def format_timestamp(dt: datetime | None, now: datetime | None = None) -> str:
    if dt is None:
        return "—"
    if now is None:
        now = datetime.now(tz=timezone.utc)
    # Normalize both to UTC-aware for comparison
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if dt.year != now.year:
        return dt.strftime("%Y-%m-%d %H:%M")
    if dt.month != now.month:
        return dt.strftime("%m-%d %H:%M")
    if dt.day != now.day:
        return dt.strftime("%d %H:%M")
    if dt.hour != now.hour:
        return dt.strftime("%H:%M")
    return dt.strftime("%M")
