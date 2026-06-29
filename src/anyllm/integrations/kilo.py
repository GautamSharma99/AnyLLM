from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import CLIIntegration, COMMANDS


class KiloIntegration(CLIIntegration):
    """Kilocode — installs markdown commands in ~/.kilocode/commands/"""

    name = "Kilocode"
    key = "kilo"
    binaries = ["kilo", "kilocode"]
    config_dirs = [Path.home() / ".kilocode"]

    @property
    def install_dir(self) -> Optional[Path]:
        return Path.home() / ".kilocode" / "commands"

    def _render_command(self, slug: str, cmd: str, description: str) -> tuple[str, str]:
        filename = f"{slug}.md"
        content = (
            f"---\n"
            f"description: {description}\n"
            f"allowed-tools: Bash({cmd.split(' $')[0]}*)\n"
            f"disable-model-invocation: true\n"
            f"---\n"
            f"!`{cmd}`\n"
        )
        return filename, content
