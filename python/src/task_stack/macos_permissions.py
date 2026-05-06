"""macOS permission helpers (Accessibility / Input Monitoring) for the global hotkey.

The global hotkey relies on a CGEventTap (via pynput) and macOS guards key
events behind two independent TCC permissions plus a system-wide "Secure Input"
flag:

- Accessibility: required for the tap to be installed at all.
- Input Monitoring: required for the tap to receive non-modifier key events.
  Without it, the tap silently sees only modifier keys (Ctrl/Shift/Alt/Cmd),
  which looks identical to "the hotkey is broken" from the user's POV.
- Secure Input: any process can enable it (typically a password / system
  authorization dialog) and while it is on, *all* taps stop receiving events.
  This is the most common cause of "it worked yesterday and stopped today".

We surface all three so the user can act, instead of just silently failing.
"""

from __future__ import annotations

import os
import subprocess
import sys

_ACCESSIBILITY_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
_INPUT_MONITORING_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
)


def is_accessibility_trusted() -> bool:
    if sys.platform != "darwin":
        return True
    try:
        import HIServices
    except ImportError:
        return True
    try:
        return bool(HIServices.AXIsProcessTrusted())
    except Exception:
        return True


def prompt_for_accessibility() -> bool:
    """Show the system Accessibility prompt if needed.

    Returns True if the process is currently trusted, False otherwise.
    On non-macOS platforms returns True. The prompt only appears when the user
    has not yet answered for this binary; if they previously denied, no dialog
    will be shown — call open_accessibility_settings() in that case.
    """
    if sys.platform != "darwin":
        return True
    try:
        import HIServices
    except ImportError:
        return True
    try:
        opts = {HIServices.kAXTrustedCheckOptionPrompt: True}
        return bool(HIServices.AXIsProcessTrustedWithOptions(opts))
    except Exception:
        return is_accessibility_trusted()


def open_accessibility_settings() -> None:
    if sys.platform != "darwin":
        return
    subprocess.run(["open", _ACCESSIBILITY_URL], check=False)


def open_input_monitoring_settings() -> None:
    if sys.platform != "darwin":
        return
    subprocess.run(["open", _INPUT_MONITORING_URL], check=False)


def is_input_monitoring_trusted() -> bool:
    """Return True if the current process can listen to keyboard events.

    Uses Quartz's CGPreflightListenEventAccess (10.15+); this is the same check
    pynput's CGEventTap effectively performs. Returns True on non-macOS or if
    the API is unavailable so callers don't false-positive on older systems.
    """
    if sys.platform != "darwin":
        return True
    try:
        from Quartz import CGPreflightListenEventAccess
    except Exception:
        return True
    try:
        return bool(CGPreflightListenEventAccess())
    except Exception:
        return True


def request_input_monitoring() -> bool:
    """Ask macOS to show the Input Monitoring prompt; returns True if granted.

    Tries the modern Quartz API first (CGRequestListenEventAccess, 10.15+) and
    falls back to IOKit.IOHIDRequestAccess if available. The prompt only shows
    on the very first call for a given binary; subsequent calls just return the
    current state, so the caller should still open System Settings on denial.
    """
    if sys.platform != "darwin":
        return True
    try:
        from Quartz import CGRequestListenEventAccess
        return bool(CGRequestListenEventAccess())
    except Exception:
        pass
    try:
        import IOKit  # type: ignore
        fn = getattr(IOKit, "IOHIDRequestAccess", None)
        if fn is not None:
            # 1 == kIOHIDRequestTypeListenEvent
            return bool(fn(1))
    except Exception:
        pass
    return is_input_monitoring_trusted()


def secure_input_pid() -> int | None:
    """Return the PID currently holding Secure Input enabled, or None.

    When any process turns Secure Input on (most commonly a system auth
    dialog from `UserNotificationCenter`, or a focused password field),
    macOS suppresses all keystrokes from event taps. Hotkeys then appear
    "dead" even with full Accessibility + Input Monitoring grants.
    """
    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.run(
            ["ioreg", "-l", "-w", "0"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    marker = '"kCGSSessionSecureInputPID"='
    for line in out.splitlines():
        idx = line.find(marker)
        if idx == -1:
            continue
        rest = line[idx + len(marker) :].lstrip()
        digits: list[str] = []
        for ch in rest:
            if ch.isdigit():
                digits.append(ch)
            else:
                break
        if not digits:
            continue
        pid = int("".join(digits))
        return pid if pid > 0 else None
    return None


def secure_input_holder() -> tuple[int, str] | None:
    """Return (pid, command) of the process holding Secure Input, if any."""
    pid = secure_input_pid()
    if pid is None:
        return None
    try:
        out = subprocess.run(
            ["ps", "-o", "comm=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    return pid, out or "<unknown>"


def diagnose_hotkey_environment() -> list[str]:
    """Return human-readable warnings about anything that will break the hotkey.

    Empty list means the environment looks healthy. Each entry is a complete
    sentence suitable for printing on its own line.
    """
    warnings: list[str] = []
    if sys.platform != "darwin":
        return warnings
    if not is_accessibility_trusted():
        warnings.append(
            "Accessibility access is not granted for this Python interpreter "
            f"({os.path.realpath(sys.executable)}); the hotkey listener cannot "
            "install its event tap. Enable it in System Settings → Privacy & "
            "Security → Accessibility."
        )
    if not is_input_monitoring_trusted():
        warnings.append(
            "Input Monitoring is not granted for this Python interpreter "
            f"({os.path.realpath(sys.executable)}); the event tap will only "
            "see modifier keys, so the hotkey will never fire. Enable it in "
            "System Settings → Privacy & Security → Input Monitoring."
        )
    holder = secure_input_holder()
    if holder is not None:
        pid, comm = holder
        warnings.append(
            f"Secure Input is currently enabled by PID {pid} ({comm}); macOS is "
            "suppressing keystrokes for all event taps, so the hotkey will not "
            "fire until that process releases it. This is most often caused by "
            "a pending system auth dialog (UserNotificationCenter) hidden "
            "behind another window or on another Space — find and dismiss it, "
            "or run `kill <pid>` to clear the prompt."
        )
    return warnings


def ensure_hotkey_permissions(*, open_settings_if_denied: bool = True) -> bool:
    """Best-effort: trigger system prompts and, if the user previously denied, open Settings.

    Returns True only if both Accessibility and Input Monitoring are currently
    granted AND no other process is holding Secure Input. Callers that want
    finer-grained reporting should use `diagnose_hotkey_environment()`.
    """
    if sys.platform != "darwin":
        return True
    input_monitoring_ok = request_input_monitoring()
    accessibility_ok = prompt_for_accessibility()
    if open_settings_if_denied:
        if not accessibility_ok:
            open_accessibility_settings()
        elif not input_monitoring_ok:
            open_input_monitoring_settings()
    return accessibility_ok and input_monitoring_ok and secure_input_pid() is None
