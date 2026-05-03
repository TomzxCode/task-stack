# App Coordination

A coordinator wires together the tray icon, hotkey listener, and main window via a thread-safe mechanism, ensuring all UI operations run on the main thread.

## Requirements

- The coordinator MUST use a thread-safe queue to receive requests from background threads (tray callbacks, hotkey listener).
- The coordinator MUST drain the queue on the main thread's event loop to ensure thread safety.
- The coordinator MUST support three request types: `show`, `toggle`, and `quit`.
- The `show` request MUST refresh the task list and then show the window.
- The `toggle` request MUST show the window if hidden, or hide it if visible.
- The `quit` request MUST stop the application event loop.
- The coordinator MUST notify the tray to update its icon and menu whenever the task stack changes.
- The coordinator SHOULD reload tasks from disk and pass them to the tray when the stack changes.
- The coordinator SHOULD wire the tray's "Keyboard Shortcuts" menu item to the window's help dialog, dispatching it on the main thread.
