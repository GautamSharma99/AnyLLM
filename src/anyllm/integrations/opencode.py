from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .base import CLIIntegration, SCOPE_GLOBAL, SCOPE_PROJECT, IntegrationStatus


def _global_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "opencode" / "commands"
    return Path.home() / ".config" / "opencode" / "commands"


class OpenCodeIntegration(CLIIntegration):
    """OpenCode (sst.dev).

    Global scope  → ~/.config/opencode/commands/<name>.md
    Project scope → .opencode/commands/<name>.md
    """

    name = "OpenCode"
    key = "opencode"
    command_style = "slash"
    binaries = ["opencode"]
    config_dirs = [Path.home() / ".config" / "opencode"]

    @property
    def global_install_dir(self) -> Optional[Path]:
        return _global_dir()

    @property
    def project_install_dir(self) -> Optional[Path]:
        return Path.cwd() / ".opencode" / "commands"

    def _render_command(self, slug: str, cmd: str, description: str, scope: str = SCOPE_GLOBAL) -> tuple[str, str]:
        content = f"---\ndescription: {description}\n---\n!`{cmd}`\n"
        return f"{slug}.md", content
