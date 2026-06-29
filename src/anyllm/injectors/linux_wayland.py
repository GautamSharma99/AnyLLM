from __future__ import annotations

import subprocess
import time


class WaylandInjector:
    def focus_target(self, target: str, push_cfg) -> bool:
        """On Wayland, window focus control is limited. Return True optimistically."""
        return True

    def open_url(self, url: str) -> None:
        subprocess.Popen(["xdg-open", url])

    def inject_and_send(self, briefing: str, delay_ms: int = 500) -> None:
        time.sleep(delay_ms / 1000)
        subprocess.run(
            ["ydotool", "type", "--", briefing],
            check=True,
        )
        subprocess.run(["ydotool", "key", "28:1", "28:0"], check=True)  # Return key
