# Data Files

The app stores everything in your home directory.

## File Locations

| File | Purpose |
|---|---|
| `~/.task-stack.yaml` | Active tasks and soft-deleted history |
| `~/.task-stack.settings.yaml` | Window geometry, hotkey, font, and icon configuration |

Both data files use atomic writes (write to a temp file, then rename) to
prevent corruption.

## Task Format

Each task in `~/.task-stack.yaml` is a YAML mapping:

```yaml
- text: Write README
  created_at: '2026-05-01T15:00:00+00:00'
  description: Draft the initial README with install and usage sections
  events:
    - started_at: '2026-05-01T15:00:00+00:00'
      ended_at: '2026-05-01T15:30:00+00:00'
- text: Old task
  created_at: '2026-04-30T10:00:00+00:00'
  deleted_at: '2026-04-30T12:00:00+00:00'
  events:
    - started_at: '2026-04-30T10:00:00+00:00'
      ended_at: '2026-04-30T11:15:00+00:00'
```

### Task Fields

| Field | Description |
|---|---|
| `text` | Task title |
| `created_at` | When the task was created |
| `description` | Optional notes for the task |
| `events` | List of session records (see below) |
| `deleted_at` | When the task was removed (only present for soft-deleted tasks) |

### Events

Each task has an `events` list tracking every session where it was the active task
(position 0). Each event has:

| Field | Description |
|---|---|
| `started_at` | When the task moved to position 0 |
| `ended_at` | When the task left position 0 (absent if still active) |

The following properties are derived from events:

- **`started_at`** (task level) — the first event's `started_at`
- **`last_current`** — the last event's `ended_at`, or `started_at` if the task is
  still active
- **`duration`** — total seconds at position 0, computed as the sum of
  `ended_at - started_at` across all closed events

Active tasks come first in stack order. Soft-deleted tasks are appended at the
end, each with a `deleted_at` timestamp.

