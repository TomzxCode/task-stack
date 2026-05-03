# Tray Menu

The system tray icon provides quick access to common actions.

| Item | Description |
|---|---|
| **\<current task\>** | Non-clickable label showing the active task text, or "No tasks" when the stack is empty. |
| **Open Stack (\<hotkey\>)** | Shows the stack window and brings it to focus. Displays the configured hotkey. |
| **Mark Done (pop)** | Removes the current task from the top of the stack (soft-delete). Disabled when the stack is empty. |
| **Keyboard Shortcuts** | Opens the keyboard shortcuts help dialog. |
| **Quit** | Exits the application. |

The tray icon and menu update automatically whenever the task stack changes.

## Icon Colors

The tray icon circle changes color based on the number of active tasks:

| Tasks | Color |
|---|---|
| 0 | Grey |
| 1-5 | Blue |
| 6-10 | Yellow |
| 11+ | Red |

Colors are configurable via
[icon thresholds in settings](configuration.md#icon-thresholds).

The task count (up to 99) is displayed as text inside the circle.
