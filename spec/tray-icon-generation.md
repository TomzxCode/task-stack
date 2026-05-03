# Tray Icon Generation

Generates the system tray icon image dynamically, reflecting the current stack state with configurable color thresholds.

## Requirements

- The icon MUST be a 64x64 image with a circular background.
- The icon color MUST be determined by configurable thresholds: the first threshold where the task count >= `min_count` wins, evaluated in descending order of `min_count`.
- When no tasks are present (count 0), the circle MUST be grey (RGB 120, 120, 120).
- Default thresholds MUST be: red (RGB 200, 50, 50) at count >= 11, yellow (RGB 220, 180, 0) at count >= 6, blue (RGB 70, 130, 180) at count >= 1.
- The icon MUST display the task count (capped at 99) as centered text inside the circle.
- Text color MUST be automatically chosen (black or white) based on the background color's relative luminance to ensure contrast.
- When no tasks exist, the icon MUST display no text (empty circle).
- The font size MUST adapt: 42pt for single-digit counts, 30pt for two-digit counts.
- The icon generator SHOULD attempt to load a platform-appropriate font and fall back to a default if unavailable.
