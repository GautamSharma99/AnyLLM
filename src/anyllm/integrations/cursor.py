from __future__ import annotations

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


class CursorIntegration(CLIIntegration):
    """Cursor — ~/.cursor/skills-cursor/<name>/SKILL.md"""

    name = "Cursor"
    key = "cursor"
    command_style = "slash"
    binaries = ["cursor"]
    config_dirs = [Path.home() / ".cursor"]

    @property
    def global_install_dir(self) -> Optional[Path]:
        if self.detect():
            return Path.home() / ".cursor" / "skills-cursor"
        return None

    def _render_command(self, slug: str, cmd: str, description: str, scope: str = SCOPE_GLOBAL) -> tuple[str, str]:
        return slug, _SKILL_TEMPLATE.format(slug=slug, cmd=cmd, description=description)

    def install(self, scope: str = SCOPE_GLOBAL) -> None:
        d = self.global_install_dir
        if d is None:
            raise RuntimeError(f"{self.name} not detected — is it installed?")
        _skill_dir_install(d, COMMANDS, _SKILL_TEMPLATE, scope)

    def uninstall(self, scope: str = SCOPE_GLOBAL) -> None:
        d = self.global_install_dir
        if d:
            _skill_dir_uninstall(d, COMMANDS)

    def status(self) -> IntegrationStatus:
        return IntegrationStatus(
            name=self.name,
            key=self.key,
            detected=self.detect(),
            global_installed=_skill_dir_installed(self.global_install_dir),
            project_installed=False,
            global_dir=self.global_install_dir,
            project_dir=None,
        )
