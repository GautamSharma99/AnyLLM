from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import CLIIntegration, SCOPE_GLOBAL


class KiloIntegration(CLIIntegration):
    """Kilocode — ~/.kilocode/commands/<name>.md"""

    name = "Kilocode"
    key = "kilo"
    command_style = "slash"
    binaries = ["kilo", "kilocode"]
    config_dirs = [Path.home() / ".kilocode"]

    @property
    def global_install_dir(self) -> Optional[Path]:
        return Path.home() / ".kilocode" / "commands"

    def _render_command(self, slug: str, cmd: str, description: str, scope: str = SCOPE_GLOBAL) -> tuple[str, str]:
        base_cmd = cmd.split(" $ARGUMENTS")[0]
        content = (
            f"---\n"
            f"description: {description}\n"
            f"allowed-tools: Bash({base_cmd}*)\n"
            f"disable-model-invocation: true\n"
            f"---\n"
            f"!`{cmd}`\n"
        )
        return f"{slug}.md", content
