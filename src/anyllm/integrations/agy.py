from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from .base import CLIIntegration, SCOPE_GLOBAL


def _agy_config_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "agy"
    return Path.home() / ".config" / "agy"


class AgyIntegration(CLIIntegration):
    """Agy AI coding CLI — <agy-config>/commands/<name>.md"""

    name = "Agy"
    key = "agy"
    command_style = "slash"
    binaries = ["agy"]
    config_dirs = [_agy_config_dir()]

    @property
    def global_install_dir(self) -> Optional[Path]:
        return _agy_config_dir() / "commands"

    def _render_command(self, slug: str, cmd: str, description: str, scope: str = SCOPE_GLOBAL) -> tuple[str, str]:
        content = f"---\ndescription: {description}\n---\n!`{cmd}`\n"
        return f"{slug}.md", content
