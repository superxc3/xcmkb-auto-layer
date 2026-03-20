"""
Cross-platform active window detector.
Returns (app_name, window_title) for the currently focused window.
Windows : win32gui + psutil
macOS   : AppKit (pyobjc-framework-Cocoa)
Linux   : not supported (no consistent Wayland/X11 API)
"""

import platform
import sys

_SYSTEM = platform.system()


def get_active_window():
    """Return (app_name: str, title: str) or (None, None) on failure."""
    try:
        if _SYSTEM == "Windows":
            return _get_windows()
        elif _SYSTEM == "Darwin":
            return _get_macos()
        else:
            return None, None
    except Exception:
        return None, None


# ── Windows ──────────────────────────────────────────────────────────────────

def _get_windows():
    import win32gui
    import win32process
    import psutil

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None, None

    title = win32gui.GetWindowText(hwnd)
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    try:
        proc = psutil.Process(pid)
        app = proc.name()          # e.g. "firefox.exe"
        app_bare = proc.name().lower().removesuffix(".exe")   # "firefox"
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        app = None
        app_bare = None

    return app_bare, title.lower() if title else ""


# ── macOS ─────────────────────────────────────────────────────────────────────

def _get_macos():
    from AppKit import NSWorkspace

    ws  = NSWorkspace.sharedWorkspace()
    app = ws.frontmostApplication()
    if app is None:
        return None, None

    app_name = (app.localizedName() or "").lower()
    # Window title requires Accessibility API — use bundle ID as fallback
    bundle   = (app.bundleIdentifier() or "").lower()
    return app_name, bundle
