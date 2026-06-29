from __future__ import annotations

import os
import sys


def detect_platform() -> str:
    """Return one of: linux_x11 | linux_wayland | macos | windows."""
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    # Linux — check for WSL then Wayland/X11
    if os.environ.get("WAYLAND_DISPLAY"):
        return "linux_wayland"
    return "linux_x11"


def get_injector(platform: str | None = None):
    """Return the right injector for the given (or auto-detected) platform."""
    p = platform or detect_platform()
    if p == "windows":
        from .windows import WindowsInjector
        return WindowsInjector()
    if p == "macos":
        from .macos import MacOSInjector
        return MacOSInjector()
    if p == "linux_wayland":
        from .linux_wayland import WaylandInjector
        return WaylandInjector()
    from .linux_x11 import X11Injector
    return X11Injector()
