from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from .base import (
    CLIIntegration, COMMANDS, SCOPE_GLOBAL, SCOPE_PROJECT,
    IntegrationStatus, _skill_dir_install, _skill_dir_uninstall, _skill_dir_installed,
)


_SKILL_TEMPLATE = """\
---
name: {slug}
description: >
  Activate this skill when the user mentions "{slug}" or asks to {description_lower}.
  Also activate when the user types "{slug}" as a message.
---

Run the following shell command exactly as shown and display its output to the user:

```bash
{cmd}
```

Do not add any extra commentary. Run the command and show the result.
"""


class GeminiIntegration(CLIIntegration):
    """Antigravity / Agy CLI — global: ~/.gemini/config/skills/  project: .agents/skills/

    Agy (agy.exe) IS the Antigravity CLI. Skills are AI-triggered context documents,
    not slash commands. Users type the skill name as a plain message (no / prefix).
    """

    name = "Antigravity"
    key = "gemini"
    command_style = "message"
    binaries = ["gemini", "antigravity", "agy"]
    config_dirs = [Path.home() / ".gemini"]

    @property
    def global_install_dir(self) -> Optional[Path]:
        return Path.home() / ".gemini" / "config" / "skills"

    @property
    def project_install_dir(self) -> Optional[Path]:
        return Path.cwd() / ".agents" / "skills"

    def _render_command(self, slug: str, cmd: str, description: str, scope: str = SCOPE_GLOBAL) -> tuple[str, str]:
        return slug, _SKILL_TEMPLATE.format(
            slug=slug, cmd=cmd, description=description,
            description_lower=description.lower(), scope=scope,
        )

    def install(self, scope: str = SCOPE_GLOBAL) -> None:
        d = self.project_install_dir if scope == SCOPE_PROJECT else self.global_install_dir
        if d is None:
            raise RuntimeError(f"{self.name} not detected — is it installed?")
        _skill_dir_install(d, COMMANDS, _SKILL_TEMPLATE, scope)

    def uninstall(self, scope: str = SCOPE_GLOBAL) -> None:
        d = self.project_install_dir if scope == SCOPE_PROJECT else self.global_install_dir
        if d:
            _skill_dir_uninstall(d, COMMANDS)

    def status(self) -> IntegrationStatus:
        return IntegrationStatus(
            name=self.name,
            key=self.key,
            detected=self.detect(),
            global_installed=_skill_dir_installed(self.global_install_dir),
            project_installed=_skill_dir_installed(self.project_install_dir),
            global_dir=self.global_install_dir,
            project_dir=self.project_install_dir,
        )
