from __future__ import annotations

import subprocess
import time


_BROWSER_PRIORITY = ["Arc", "Google Chrome", "Safari", "Firefox"]


def _find_codex_app(browser: str = "auto") -> str | None:
    """Return the browser app name that has a Codex tab open."""
    candidates = [browser] if browser != "auto" else _BROWSER_PRIORITY
    script = """
tell application "System Events"
    set appList to name of every application process whose visible is true
end tell
return appList
"""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True,
    )
    running = {a.strip() for a in result.stdout.split(",")}
    for app in candidates:
        if app in running:
            return app
    return None


class MacOSInjector:
    def focus_target(self, target: str, push_cfg) -> bool:
        """Activate the browser window that has Codex open via AppleScript."""
        app = _find_codex_app(push_cfg.browser)
        if not app:
            return False

        script = f"""
tell application "{app}"
    activate
    set theWindows to every window
    repeat with w in theWindows
        set theURL to URL of active tab of w
        if theURL contains "codex" or theURL contains "openai" then
            set index of w to 1
            return true
        end if
    end repeat
end tell
return false
"""
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True,
        )
        return "true" in result.stdout.lower()

    def open_url(self, url: str) -> None:
        subprocess.Popen(["open", url])

    def inject_and_send(self, briefing: str, delay_ms: int = 500) -> None:
        import pyperclip
        pyperclip.copy(briefing)
        time.sleep(delay_ms / 1000)

        script = """
tell application "System Events"
    keystroke "v" using command down
    delay 0.1
    key code 36
end tell
"""
        subprocess.run(["osascript", "-e", script], check=True)
