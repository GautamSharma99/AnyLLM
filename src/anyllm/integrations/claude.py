from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import CLIIntegration, SCOPE_GLOBAL


class ClaudeIntegration(CLIIntegration):
    """Claude Code — ~/.claude/commands/*.md"""

    name = "Claude Code"
    key = "claude"
    command_style = "slash"
    binaries = ["claude"]
    config_dirs = [Path.home() / ".claude"]

    @property
    def global_install_dir(self) -> Optional[Path]:
        return Path.home() / ".claude" / "commands"

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
