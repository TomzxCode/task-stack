# Configuration

Settings are stored in `~/.task-stack.settings.yaml`. Edit the file and restart
the app to apply changes.

## Hotkey

```yaml
hotkey: ctrl+shift+t
# hotkey: alt+space
# hotkey: cmd+shift+space
# hotkey: ctrl+f1
# hotkey: alt+/
```

Tokens are joined with `+` and are case-insensitive.

**Modifiers**: `ctrl`/`control`, `shift`, `alt`/`option`/`opt`,
`cmd`/`command`/`super`/`win`/`meta`.

**Key** (exactly one): a single ASCII letter/digit/punctuation (`t`, `1`, `/`),
`f1`-`f24`, or one of `space`, `tab`, `enter`/`return`, `esc`/`escape`, `up`,
`down`, `left`, `right`, `home`, `end`, `page_up`, `page_down`, `delete`,
`backspace`, `insert`.

The current hotkey is shown next to **Open Stack** in the tray menu.

## Font

```yaml
font_family: TkDefaultFont
font_size: 11
```

`font_size` is clamped to the range 6-72.

## Icon Thresholds

Icon color changes based on the number of active tasks. Configure thresholds
with a list of `min_count` and `color` pairs:

```yaml
icon_thresholds:
  - min_count: 11
    color: "#c83232"    # red
  - min_count: 6
    color: "#dcb400"    # yellow
  - min_count: 1
    color: "#4682b4"    # blue
```

The first threshold where the task count >= `min_count` wins (evaluated in
descending order). When no tasks are present, the icon is always grey.

Text color (black or white) is chosen automatically based on background
luminance for contrast.

## Window Geometry

Window position and size are saved automatically when you move or resize the
window. No manual configuration is needed. To reset, delete the `window` key
from the settings file and restart.
