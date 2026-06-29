from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import CLIIntegration, COMMANDS, _write_file


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
    """Cursor — installs as skills in ~/.cursor/skills-cursor/<name>/"""

    name = "Cursor"
    key = "cursor"
    binaries = ["cursor"]
    config_dirs = [Path.home() / ".cursor"]

    @property
    def install_dir(self) -> Optional[Path]:
        if self.detect():
            return Path.home() / ".cursor" / "skills-cursor"
        return None

    def _render_command(self, slug: str, cmd: str, description: str) -> tuple[str, str]:
        return slug, _SKILL_TEMPLATE.format(slug=slug, cmd=cmd, description=description)

    def install(self) -> None:
        d = self.install_dir
        if d is None:
            raise RuntimeError(f"{self.name} not detected. Is it installed?")
        d.mkdir(parents=True, exist_ok=True)
        for slug, cmd, description in COMMANDS:
            skill_dir = d / slug
            skill_dir.mkdir(exist_ok=True)
            content = _SKILL_TEMPLATE.format(slug=slug, cmd=cmd, description=description)
            _write_file(skill_dir / "SKILL.md", content)

    def uninstall(self) -> None:
        d = self.install_dir
        if d is None or not d.is_dir():
            return
        import shutil
        for slug, _, _ in COMMANDS:
            skill_dir = d / slug
            if skill_dir.is_dir():
                shutil.rmtree(skill_dir)

    def status(self):
        from .base import IntegrationStatus
        detected = self.detect()
        d = self.install_dir
        installed = False
        if d is not None and d.is_dir():
            first_slug = COMMANDS[0][0]
            installed = (d / first_slug).is_dir()
        return IntegrationStatus(
            name=self.name, key=self.key,
            detected=detected, installed=installed, install_dir=d,
        )
