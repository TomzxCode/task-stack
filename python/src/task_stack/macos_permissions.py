"""macOS permission helpers (Accessibility / Input Monitoring) for the global hotkey."""

from __future__ import annotations

import subprocess
import sys

# Settings URLs (Ventura+: System Settings deep links).
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


def request_input_monitoring() -> bool:
    """Ask macOS to show the Input Monitoring prompt; returns True if granted."""
    if sys.platform != "darwin":
        return True
    try:
        import IOKit  # type: ignore
    except ImportError:
        return False
    fn = getattr(IOKit, "IOHIDRequestAccess", None)
    if fn is None:
        return False
    # 1 == kIOHIDRequestTypeListenEvent
    try:
        return bool(fn(1))
    except Exception:
        return False


def ensure_hotkey_permissions(*, open_settings_if_denied: bool = True) -> bool:
    """Best-effort: trigger system prompts and, if the user previously denied, open Settings.

    Returns True if Accessibility access is currently granted.
    """
    if sys.platform != "darwin":
        return True
    request_input_monitoring()
    trusted = prompt_for_accessibility()
    if not trusted and open_settings_if_denied:
        open_accessibility_settings()
    return trusted
