from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .base import CLIIntegration, COMMANDS


def _opencode_config_dir() -> Path:
    """Return the opencode config directory (XDG on Linux/Mac, .config on Windows)."""
    # opencode follows XDG_CONFIG_HOME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "opencode"
    return Path.home() / ".config" / "opencode"


class OpenCodeIntegration(CLIIntegration):
    """OpenCode (sst.dev) — installs markdown commands in ~/.config/opencode/commands/"""

    name = "OpenCode"
    key = "opencode"
    binaries = ["opencode"]
    config_dirs = [_opencode_config_dir()]

    @property
    def install_dir(self) -> Optional[Path]:
        return _opencode_config_dir() / "commands"

    def _render_command(self, slug: str, cmd: str, description: str) -> tuple[str, str]:
        filename = f"{slug}.md"
        content = (
            f"---\n"
            f"description: {description}\n"
            f"---\n"
            f"!`{cmd}`\n"
        )
        return filename, content
