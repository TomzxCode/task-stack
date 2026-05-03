# Task Management (Stack)

Manages a LIFO task stack with push, push_next, push_last, pop, promote, reorder, remove, soft-delete, and description editing operations. Data is persisted to the user's home directory.

## Requirements

- The system MUST persist active tasks and soft-deleted tasks to a file in the user's home directory.
- The system MUST use atomic writes to prevent data corruption.
- The system MUST store each task with the following fields: `text`, `created_at`, `started_at`, `last_current`, `duration`, `description`, and optionally `deleted_at`.
- Active (non-deleted) tasks MUST be listed first in the file, followed by soft-deleted tasks appended at the end.
- The `push` operation MUST insert a new task at position 0, set `created_at` and `started_at` to the current time, set `last_current` to the current time, and end the current stint of the previous top task.
- The `push_next` operation MUST insert a new task at position 1 (immediately after the current task) without making it current. If no tasks exist, it MUST behave like `push`.
- The `push_last` operation MUST insert a new task at the bottom of the active list. If no tasks exist, it MUST mark the new task as current.
- The `pop` operation MUST remove the task at position 0, record its `deleted_at` timestamp, end its current stint, move it to the deleted history, and mark the new top task as current.
- The `remove` operation MUST soft-delete the task at the given index, recording `deleted_at` and ending its stint if it was at position 0. If the removed task was at position 0, the new top task MUST be marked current.
- The `promote` operation MUST move the task at the given index to position 0 and mark it as current.
- The `reorder` operation MUST move a task from one index to another, correctly managing stint transitions when tasks enter or leave position 0.
- The `update_text` operation MUST update the text of the task at the given index in place. Empty or whitespace-only text MUST be rejected (no change applied).
- The `update_description` operation MUST update the description of the task at the given index in place.
- The system MUST track cumulative active duration per task via the `duration` field, accumulating elapsed time whenever a task leaves position 0.
- The `live_duration` computation MUST return the stored `duration` plus the elapsed time since `last_current` for the task currently at position 0.
- The system MUST automatically migrate the legacy data file format to the current format on first load, preserving the original as a backup.
- The system SHOULD backfill `duration` for legacy entries that lack it by using `last_current - started_at` as the cumulative active duration.
- The system MAY support `format_timestamp` with adaptive precision (year, month, day, hour, minute) based on proximity to the current time.
- The system MAY support `format_duration` with two-unit human-readable output (e.g. `2h 05m`, `3d 04h`).
