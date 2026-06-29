from __future__ import annotations

import subprocess
import time


class X11Injector:
    def focus_target(self, target: str, push_cfg) -> bool:
        """Focus the Codex browser window via xdotool. Return True if found."""
        result = subprocess.run(
            ["xdotool", "search", "--name", "codex"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not result.stdout.strip():
            result = subprocess.run(
                ["xdotool", "search", "--name", "openai"],
                capture_output=True,
                text=True,
            )
        if result.returncode != 0 or not result.stdout.strip():
            return False
        wid = result.stdout.strip().split()[0]
        subprocess.run(["xdotool", "windowfocus", "--sync", wid], check=False)
        return True

    def open_url(self, url: str) -> None:
        subprocess.Popen(["xdg-open", url])

    def inject_and_send(self, briefing: str, delay_ms: int = 500) -> None:
        time.sleep(delay_ms / 1000)
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", "--", briefing],
            check=True,
        )
        subprocess.run(["xdotool", "key", "Return"], check=True)
