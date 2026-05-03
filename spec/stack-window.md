# Stack Window

The main application window that displays the task stack and provides keyboard- and mouse-driven editing.

## Requirements

### Window behavior

- The window MUST be hidden on startup and shown only when triggered by the hotkey or the tray "Open Stack" menu item.
- The window MUST be a topmost window that appears above other application windows.
- Closing the window MUST hide it rather than quit the application.
- The window MUST have a minimum size of 320x160 pixels.
- The window SHOULD persist its size and position across launches via the settings.

### Theming

- The window MUST support a light theme and a dark theme.
- The application SHOULD detect the operating system's color scheme preference at startup and whenever it changes.
- On Windows, the application SHOULD watch for live theme changes and react immediately.
- On macOS and Linux, the application SHOULD periodically poll the OS theme preference.
- The window MUST apply the active theme to all UI elements: background, text, entry field, canvas, description panel, drag handles, and selection highlight.

### Font configuration

- The window MUST use font family and font size values from the application settings.
- The default font size MUST be 11.

### Input field

- The window MUST display a text entry field at the top for adding new tasks.
- Pressing Enter in the entry field MUST add the task to the top of the stack (push) and clear the field.
- Pressing Shift+Enter in the entry field MUST add the task as the next item (position 1) and clear the field.
- Pressing Home in the entry field MUST add the task to the top of the stack (push) and clear the field.
- Pressing End in the entry field MUST add the task to the bottom of the active list (push_last) and clear the field.
- Pressing Escape while the entry is focused during editing MUST cancel the edit and return focus to the task list.

### Task list display

- The window MUST render tasks as rows, with the current task (position 0) displayed in bold.
- Each row MUST display: a drag handle, the task index, a status indicator, the task text, a started-at timestamp, a last-current timestamp, and a duration.
- Rows for tasks that have a description MUST display a note indicator next to the task text.
- The current task (position 0) MUST show a fire status indicator.
- Non-current tasks MUST show a sleep status indicator.
- Every task row MUST display `started_at` as the first timestamp column and `last_current` as the second timestamp column.
- The duration for the current task MUST update live every second.
- Timestamp and duration column widths MUST adapt to the configured font.
- When the stack is empty, the window MUST display "No tasks — type above and press Enter".

### Description panel

- When a task is selected, a description panel MUST be shown below the task list.
- The description panel MUST contain an editable multi-line text area.
- If the selected task has a description, the panel MUST display it. Otherwise, the panel MUST display a placeholder prompt.
- The placeholder MUST be cleared when the description area receives focus.
- The description MUST be saved automatically when the description area loses focus.
- The description MUST be saved when Escape is pressed in the description area, and focus MUST return to the task list.
- The description panel MUST be hidden when no task is selected.

### Keyboard navigation

- Digit keys (0-9, including numpad) MUST save any pending description edit, select the corresponding row by index, and refresh the description panel.
- Up/Down arrow keys MUST save any pending description edit, move the selection up or down by one row, and refresh the description panel.
- Left/Right arrow keys with a row selected MUST reorder that row by one position.
- The Home key with a row selected MUST promote that row to the top of the stack.
- The End key with a row selected MUST send that row to the bottom of the stack.
- Backspace/Delete with a row selected MUST remove (soft-delete) that task. After deletion, the selection SHOULD move to the nearest remaining row.
- The `?` key MUST open a keyboard shortcuts help dialog.
- Escape MUST hide the window (or close the help dialog if open).
- Enter/Return with a row selected MUST begin editing that task's text in the entry field.
- Pressing Enter while editing MUST save the updated text. Pressing Escape MUST cancel.
- Typing a printable character while the task list is focused MUST redirect focus to the entry field and begin typing.

### Keyboard shortcuts help dialog

- The application MUST provide a help dialog listing all available keyboard shortcuts.
- The help dialog MUST be openable via the `?` key and via the tray menu.
- The help dialog SHOULD be positioned relative to the main window if visible, otherwise centered on screen.
- Pressing Escape or `?` inside the help dialog MUST close it.

### Drag and drop

- The window MUST support mouse drag-and-drop to reorder tasks.
- Initiating a drag MUST save any pending description edit.
- Dragging a row MUST immediately reorder the stack and persist the change.
- Releasing a drag on the same row where it started (no movement) MUST select that row.

### Refresh behavior

- The window MUST reload tasks from disk, clear the selection, hide the description panel, cancel any in-progress edit, and redraw whenever refreshed.
- The window SHOULD notify the tray and coordinator whenever the stack changes.
