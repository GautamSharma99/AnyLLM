from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import CLIIntegration, _write_file, COMMANDS


class ClaudeIntegration(CLIIntegration):
    name = "Claude Code"
    key = "claude"
    binaries = ["claude"]
    config_dirs = [Path.home() / ".claude"]

    @property
    def install_dir(self) -> Optional[Path]:
        return Path.home() / ".claude" / "commands"

    def _render_command(self, slug: str, cmd: str, description: str) -> tuple[str, str]:
        filename = f"{slug}.md"
        # Strip $ARGUMENTS from commands that don't take args for the allowed-tools pattern
        base_cmd = cmd.split(" $ARGUMENTS")[0]
        content = (
            f"---\n"
            f"description: {description}\n"
            f"allowed-tools: Bash({base_cmd}*)\n"
            f"disable-model-invocation: true\n"
            f"---\n"
            f"!`{cmd}`\n"
        )
        return filename, content
