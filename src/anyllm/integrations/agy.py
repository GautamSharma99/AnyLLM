from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from .base import CLIIntegration, COMMANDS


def _agy_config_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "agy"
    return Path.home() / ".config" / "agy"


class AgyIntegration(CLIIntegration):
    """Agy AI coding CLI — installs markdown commands in the agy commands directory."""

    name = "Agy"
    key = "agy"
    binaries = ["agy"]
    config_dirs = [_agy_config_dir()]

    @property
    def install_dir(self) -> Optional[Path]:
        return _agy_config_dir() / "commands"

    def _render_command(self, slug: str, cmd: str, description: str) -> tuple[str, str]:
        filename = f"{slug}.md"
        content = (
            f"---\n"
            f"description: {description}\n"
            f"---\n"
            f"!`{cmd}`\n"
        )
        return filename, content
