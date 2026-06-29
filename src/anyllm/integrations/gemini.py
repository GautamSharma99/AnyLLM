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
description: |
  anyllm — {description}
  Triggered when the user types /{slug}.
---

Run the following shell command and display its output to the user:

```bash
{cmd}
```

Do not add any extra commentary. Run the command and show the result.
"""


class GeminiIntegration(CLIIntegration):
    """Gemini CLI (Antigravity) — global: ~/.gemini/config/skills/  project: .agents/skills/"""

    name = "Gemini"
    key = "gemini"
    command_style = "slash"
    binaries = ["gemini", "antigravity"]
    config_dirs = [Path.home() / ".gemini"]

    @property
    def global_install_dir(self) -> Optional[Path]:
        return Path.home() / ".gemini" / "config" / "skills"

    @property
    def project_install_dir(self) -> Optional[Path]:
        return Path.cwd() / ".agents" / "skills"

    def _render_command(self, slug: str, cmd: str, description: str, scope: str = SCOPE_GLOBAL) -> tuple[str, str]:
        # For skill-dir integrations we return the dir name; actual writing is in install()
        return slug, _SKILL_TEMPLATE.format(slug=slug, cmd=cmd, description=description, scope=scope)

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
