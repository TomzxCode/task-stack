# System Tray

Provides a system tray icon and menu, displaying the current task and offering quick actions.

## Requirements

- The application MUST create a system tray icon on startup.
- The tray icon tooltip MUST display the text of the current (top) task, or "No tasks" when the stack is empty.
- The tray menu MUST display the current task text as a disabled (non-clickable) label.
- The tray menu MUST include an "Open Stack" item that shows the stack window and brings it to focus.
- The tray menu "Open Stack" item SHOULD display the configured hotkey label (e.g. "Open Stack (Ctrl+Shift+T)").
- The tray menu MUST include a "Mark Done (pop)" item that removes the current task via the pop operation.
- The "Mark Done (pop)" item MUST be disabled when the stack is empty.
- The tray menu MUST include a "Keyboard Shortcuts" item that opens the keyboard shortcuts help dialog.
- The tray menu MUST include a "Quit" item that exits the application.
- The tray icon and menu MUST update whenever the task stack changes (task added, removed, promoted, or popped).
- On macOS, the tray icon MUST operate on the main thread.
- On non-macOS platforms, the tray icon MUST run in a dedicated background thread.
- The application MUST stop the tray icon cleanly on exit.
