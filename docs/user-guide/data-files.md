# Data Files

The app stores everything in your home directory.

## File Locations

| File | Purpose |
|---|---|
| `~/.task-stack.yaml` | Active tasks and soft-deleted history |
| `~/.task-stack.settings.yaml` | Window geometry, hotkey, font, and icon configuration |
| `~/.task-stack.json.bak` | Backup of the legacy JSON store (written once on migration) |
| `~/.task-stack.settings.json.bak` | Backup of the legacy JSON settings file (written once on migration) |

Both data files use atomic writes (write to a temp file, then rename) to
prevent corruption.

## Task Format

Each task in `~/.task-stack.yaml` is a YAML mapping:

```yaml
- text: Write README
  created_at: '2026-05-01T15:00:00+00:00'
  started_at: '2026-05-01T15:00:00+00:00'
  last_current: '2026-05-01T15:30:00+00:00'
  duration: 1800.0
  description: Draft the initial README with install and usage sections
- text: Old task
  created_at: '2026-04-30T10:00:00+00:00'
  started_at: '2026-04-30T10:00:00+00:00'
  last_current: '2026-04-30T11:15:00+00:00'
  duration: 4500.0
  deleted_at: '2026-04-30T12:00:00+00:00'
```

### Task Fields

| Field | Description |
|---|---|
| `text` | Task title |
| `created_at` | When the task was created |
| `started_at` | When the task first became current (position 0) |
| `last_current` | Most recent time the task was at position 0 |
| `duration` | Cumulative seconds the task spent at position 0 |
| `description` | Optional notes for the task |
| `deleted_at` | When the task was removed (only present for soft-deleted tasks) |

Active tasks come first in stack order. Soft-deleted tasks are appended at the
end, each with a `deleted_at` timestamp.

## Migration

On first launch, the app automatically migrates legacy JSON files to the
current YAML format, preserving the originals as `.json.bak` files.
