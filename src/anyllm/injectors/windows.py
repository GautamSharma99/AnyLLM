from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import subprocess
import sys
import time


_user32 = ctypes.windll.user32  # type: ignore[attr-defined]
_kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]


# Virtual-key codes
_VK_CONTROL = 0x11
_VK_V = 0x56
_VK_RETURN = 0x0D
_KEYEVENTF_KEYUP = 0x0002


def _find_window(title_fragment: str) -> int | None:
    """Return the HWND of the first visible window whose title contains title_fragment."""
    results: list[int] = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
    )

    def _cb(hwnd: int, _: int) -> bool:
        if not _user32.IsWindowVisible(hwnd):
            return True
        length = _user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(hwnd, buf, length + 1)
            if title_fragment.lower() in buf.value.lower():
                results.append(hwnd)
        return True

    _user32.EnumWindows(EnumWindowsProc(_cb), 0)
    return results[0] if results else None


def _focus_hwnd(hwnd: int) -> None:
    SW_RESTORE = 9
    _user32.ShowWindow(hwnd, SW_RESTORE)
    _user32.SetForegroundWindow(hwnd)
    # Bring to top via AttachThreadInput trick
    foreground_thread = _user32.GetWindowThreadProcessId(_user32.GetForegroundWindow(), None)
    current_thread = _kernel32.GetCurrentThreadId()
    if foreground_thread != current_thread:
        _user32.AttachThreadInput(foreground_thread, current_thread, True)
        _user32.BringWindowToTop(hwnd)
        _user32.SetForegroundWindow(hwnd)
        _user32.AttachThreadInput(foreground_thread, current_thread, False)


def _send_paste_and_enter() -> None:
    """Send Ctrl+V then Enter using keybd_event."""
    _user32.keybd_event(_VK_CONTROL, 0, 0, 0)
    _user32.keybd_event(_VK_V, 0, 0, 0)
    _user32.keybd_event(_VK_V, 0, _KEYEVENTF_KEYUP, 0)
    _user32.keybd_event(_VK_CONTROL, 0, _KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)
    _user32.keybd_event(_VK_RETURN, 0, 0, 0)
    _user32.keybd_event(_VK_RETURN, 0, _KEYEVENTF_KEYUP, 0)


class WindowsInjector:
    def focus_target(self, target: str, push_cfg) -> bool:
        """Focus the Codex browser window. Return True if found."""
        hwnd = _find_window("codex") or _find_window("openai")
        if hwnd:
            _focus_hwnd(hwnd)
            return True
        return False

    def open_url(self, url: str) -> None:
        os.startfile(url)  # type: ignore[attr-defined]

    def inject_and_send(self, briefing: str, delay_ms: int = 500) -> None:
        """Set clipboard to briefing and send Ctrl+V + Enter."""
        try:
            import pyperclip
            pyperclip.copy(briefing)
        except Exception:
            # Fallback: use PowerShell to set clipboard
            _set_clipboard_ps(briefing)

        time.sleep(delay_ms / 1000)
        _send_paste_and_enter()


def _set_clipboard_ps(text: str) -> None:
    # Write to a temp file to avoid shell-quoting issues
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(text)
        tmp = f.name
    try:
        subprocess.run(
            ["powershell", "-NonInteractive", "-Command",
             f"Get-Content -Path '{tmp}' -Raw | Set-Clipboard"],
            check=True,
            capture_output=True,
        )
    finally:
        os.unlink(tmp)
