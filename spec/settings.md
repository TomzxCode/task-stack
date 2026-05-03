# Settings

Manages persisted application settings including window geometry, global hotkey, font, and icon threshold configuration.

## Requirements

- Settings MUST be persisted to a file in the user's home directory.
- Settings MUST use atomic writes to prevent corruption.
- The settings file MUST store the `hotkey` string, `font_family` string, `font_size` integer, optionally a `window` geometry object, and optionally an `icon_thresholds` list.
- The default hotkey MUST be `ctrl+shift+t`.
- The default font family MUST be the system default font.
- The default font size MUST be 11.
- Font size values MUST be clamped to the range 6–72.
- Window geometry MUST include `width`, `height`, `x`, and `y` fields.
- If no settings file exists, the system MUST return defaults (no saved geometry, default hotkey, default font).
- The system MUST migrate the legacy settings file format to the current format on first load, preserving the original as a backup.
- The system SHOULD silently ignore read/write errors (e.g. permission issues) rather than crashing.
- The application SHOULD save window geometry with a debounce after a resize event to avoid excessive disk writes.
- The application MAY skip saving geometry if the window is minimized or the dimensions have not changed.

### Icon thresholds

- Settings MAY include a list of icon color thresholds, each defined by a `min_count` integer and a `color` hex string.
- When icon thresholds are configured, the icon color MUST be selected by finding the first threshold where the task count is >= `min_count` (evaluated in descending order).
- When no thresholds are configured, the system MUST use default thresholds.
- When the task count is 0, the icon MUST always use the empty state color regardless of thresholds.
