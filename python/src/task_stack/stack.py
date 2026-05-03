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
    created_at: datetime | None = field(default=None)
    started_at: datetime | None = field(default=None)
    last_current: datetime | None = field(default=None)
    duration: float = field(default=0.0)
    deleted_at: datetime | None = field(default=None)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def mark_current(self, now: datetime | None = None) -> None:
        """Mark this task as the active one (position 0)."""
        if now is None:
            now = datetime.now().astimezone()
        if self.started_at is None:
            self.started_at = now
        self.last_current = now

    def end_current_stint(self, now: datetime | None = None) -> None:
        """Accumulate the live stint into ``duration``.

        Adds ``now - last_current`` to ``duration``. ``last_current`` is left
        unchanged so it continues to record when the task was most recently
        current.
        """
        if self.last_current is None:
            return
        if now is None:
            now = datetime.now().astimezone()
        elapsed = (now - self.last_current).total_seconds()
        if elapsed > 0:
            self.duration += elapsed

    def live_duration(self, now: datetime | None = None) -> float:
        """Return cumulative active seconds plus the live stint since ``last_current``.

        Use this for the task at position 0 where ``last_current`` represents
        the start of an in-progress stint not yet folded into ``duration``.
        """
        total = self.duration
        if self.last_current is not None:
            if now is None:
                now = datetime.now().astimezone()
            elapsed = (now - self.last_current).total_seconds()
            if elapsed > 0:
                total += elapsed
        return total

    def to_dict(self) -> dict:
        d: dict = {
            "text": self.text,
        }
        if self.created_at is not None:
            d["created_at"] = self.created_at.isoformat()
        if self.started_at is not None:
            d["started_at"] = self.started_at.isoformat()
        d["last_current"] = self.last_current.isoformat() if self.last_current else None
        d["duration"] = round(self.duration, 3)
        if self.deleted_at is not None:
            d["deleted_at"] = self.deleted_at.isoformat()
        return d

    @staticmethod
    def from_dict(d: dict) -> "Task":
        def _parse(v: object) -> datetime | None:
            return datetime.fromisoformat(v) if isinstance(v, str) and v else None

        raw_duration = d.get("duration")
        try:
            duration = float(raw_duration) if raw_duration is not None else 0.0
        except (TypeError, ValueError):
            duration = 0.0

        return Task(
            text=d["text"],
            created_at=_parse(d.get("created_at")),
            started_at=_parse(d.get("started_at")),
            last_current=_parse(d.get("last_current")),
            duration=duration,
            deleted_at=_parse(d.get("deleted_at")),
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


def _migrate_durations(tasks: list[Task]) -> bool:
    """Backfill ``duration`` for legacy entries that lack it.

    For non-row-0 (or deleted) tasks that have ``last_current`` and
    ``started_at`` but ``duration == 0``, treat ``last_current - started_at``
    as the cumulative active duration. ``last_current`` itself is preserved.

    Returns True if any task was modified.
    """
    changed = False
    active_idx = 0
    for t in tasks:
        is_row_zero_active = (not t.is_deleted) and active_idx == 0
        if not t.is_deleted:
            active_idx += 1
        if is_row_zero_active:
            continue
        if (
            t.duration == 0.0
            and t.last_current is not None
            and t.started_at is not None
            and t.last_current > t.started_at
        ):
            t.duration = (t.last_current - t.started_at).total_seconds()
            changed = True
    return changed


def _load_all() -> list[Task]:
    """Load every task from disk, including soft-deleted ones."""
    if not STACK_FILE.exists():
        migrated = _migrate_legacy_json()
        if migrated is not None:
            return migrated
        return []
    try:
        data = yaml.safe_load(STACK_FILE.read_text())
    except Exception:
        return []
    tasks = _parse_tasks(data)
    if _migrate_durations(tasks):
        try:
            _save_all(tasks)
        except Exception:
            pass
    return tasks


def _split(tasks: list[Task]) -> tuple[list[Task], list[Task]]:
    active = [t for t in tasks if not t.is_deleted]
    deleted = [t for t in tasks if t.is_deleted]
    return active, deleted


def _save_all(tasks: list[Task]) -> None:
    data = yaml.safe_dump(
        [t.to_dict() for t in tasks],
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    _TMP.write_text(data)
    os.replace(_TMP, STACK_FILE)


def _commit(active: list[Task], deleted: list[Task]) -> list[Task]:
    """Persist active+deleted (deleted appended at the end) and return the active list."""
    _save_all(active + deleted)
    return active


def load() -> list[Task]:
    """Return the active (non-deleted) task stack."""
    return [t for t in _load_all() if not t.is_deleted]


def save(tasks: list[Task]) -> None:
    """Replace the active task stack on disk, preserving any soft-deleted history."""
    _, deleted = _split(_load_all())
    _save_all(tasks + deleted)


def deleted() -> list[Task]:
    """Return the soft-deleted history, oldest deletions first."""
    history = [t for t in _load_all() if t.is_deleted]
    history.sort(key=lambda t: t.deleted_at or datetime.min.replace(tzinfo=timezone.utc))
    return history


def push(text: str) -> list[Task]:
    now = datetime.now().astimezone()
    active, history = _split(_load_all())
    if active:
        active[0].end_current_stint(now)
    task = Task(text=text.strip(), created_at=now)
    task.mark_current(now)
    active.insert(0, task)
    return _commit(active, history)


def push_next(text: str) -> list[Task]:
    """Insert a new task right after the current one (position 1).

    If there is no current task, the new task is placed at position 0 and
    becomes current (same as ``push``).
    """
    now = datetime.now().astimezone()
    active, history = _split(_load_all())
    task = Task(text=text.strip(), created_at=now)
    if not active:
        task.mark_current(now)
        active.insert(0, task)
    else:
        active.insert(1, task)
    return _commit(active, history)


def push_last(text: str) -> list[Task]:
    """Insert a new task at the bottom of the active list."""
    now = datetime.now().astimezone()
    active, history = _split(_load_all())
    task = Task(text=text.strip(), created_at=now)
    if not active:
        task.mark_current(now)
    active.append(task)
    return _commit(active, history)


def pop() -> tuple[Task | None, list[Task]]:
    now = datetime.now().astimezone()
    active, history = _split(_load_all())
    if not active:
        return None, []
    removed = active.pop(0)
    removed.end_current_stint(now)
    removed.deleted_at = now
    history.append(removed)
    if active:
        active[0].mark_current(now)
    return removed, _commit(active, history)


def reorder(from_idx: int, to_idx: int) -> list[Task]:
    now = datetime.now().astimezone()
    active, history = _split(_load_all())
    if from_idx == to_idx or not (0 <= from_idx < len(active)) or not (0 <= to_idx < len(active)):
        return active
    if from_idx == 0 and to_idx != 0:
        active[0].end_current_stint(now)
    elif to_idx == 0 and from_idx != 0:
        active[0].end_current_stint(now)
    task = active.pop(from_idx)
    active.insert(to_idx, task)
    if to_idx == 0:
        active[0].mark_current(now)
    return _commit(active, history)


def promote(idx: int) -> list[Task]:
    return reorder(idx, 0)


def update_text(idx: int, text: str) -> list[Task]:
    """Update the text of the active task at ``idx`` in place.

    Empty/whitespace text is rejected (returns the active list unchanged).
    Other timestamps (created_at / started_at / last_current) are preserved.
    """
    new_text = text.strip()
    if not new_text:
        return [t for t in _load_all() if not t.is_deleted]
    active, history = _split(_load_all())
    if not (0 <= idx < len(active)):
        return active
    active[idx].text = new_text
    return _commit(active, history)


def remove(idx: int) -> list[Task]:
    now = datetime.now().astimezone()
    active, history = _split(_load_all())
    if not (0 <= idx < len(active)):
        return active
    removed = active.pop(idx)
    if idx == 0:
        removed.end_current_stint(now)
    removed.deleted_at = now
    history.append(removed)
    if active and idx == 0:
        active[0].mark_current(now)
    return _commit(active, history)


def format_timestamp(dt: datetime | None, now: datetime | None = None) -> str:
    if dt is None:
        return "—"
    if now is None:
        now = datetime.now().astimezone()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    dt = dt.astimezone()
    now = now.astimezone()

    if dt.year != now.year:
        return dt.strftime("%Y-%m-%d %H:%M")
    if dt.month != now.month:
        return dt.strftime("%m-%d %H:%M")
    if dt.day != now.day:
        return dt.strftime("%d %H:%M")
    if dt.hour != now.hour:
        return dt.strftime("%H:%M")
    return dt.strftime("%M")


def format_duration(seconds: float | None) -> str:
    """Return a human-readable duration with two units of precision.

    Examples: ``0m 45s``, ``2h 05m``, ``3d 04h``, ``2w 3d``.
    """
    if seconds is None:
        return "—"
    total = int(seconds)
    if total < 0:
        total = 0

    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    weeks, days = divmod(days, 7)

    if weeks > 0:
        return f"{weeks}w {days}d"
    if days > 0:
        return f"{days}d {hours:02d}h"
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {sec:02d}s"
