from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import (
    CLIIntegration, COMMANDS, SCOPE_GLOBAL, SCOPE_PROJECT,
    IntegrationStatus, _write_file,
    _skill_dir_install, _skill_dir_uninstall, _skill_dir_installed,
)


# Project-level skill format ($anyllm-pack invocation)
_SKILL_TEMPLATE = """\
---
name: {slug}
description: |
  anyllm — {description}
  Triggered when the user types ${slug}.
---

Run the following shell command and display its output to the user:

```bash
{cmd}
```

Do not add any extra commentary. Run the command and show the result.
"""

# Global legacy prompts format (/prompts:anyllm-pack invocation)
_PROMPT_TEMPLATE = """\
---
name: {slug}
description: {description}
---

Run this shell command and show the output:

```bash
{cmd}
```
"""


class CodexIntegration(CLIIntegration):
    """OpenAI Codex CLI.

    Global scope  → ~/.codex/prompts/<name>.md  (invoked as /prompts:anyllm-pack)
    Project scope → .agents/skills/<name>/SKILL.md  (invoked as $anyllm-pack)
    """

    name = "Codex"
    key = "codex"
    command_style = "dollar"      # primary invocation is $slug
    binaries = ["codex"]
    config_dirs = [Path.home() / ".codex"]

    @property
    def global_install_dir(self) -> Optional[Path]:
        """Legacy prompts directory — /prompts: namespace."""
        return Path.home() / ".codex" / "prompts"

    @property
    def project_install_dir(self) -> Optional[Path]:
        """Project-level skills — $slug invocation."""
        return Path.cwd() / ".agents" / "skills"

    def _render_command(self, slug: str, cmd: str, description: str, scope: str = SCOPE_GLOBAL) -> tuple[str, str]:
        if scope == SCOPE_PROJECT:
            return slug, _SKILL_TEMPLATE.format(slug=slug, cmd=cmd, description=description)
        return f"{slug}.md", _PROMPT_TEMPLATE.format(slug=slug, cmd=cmd, description=description)

    def install(self, scope: str = SCOPE_GLOBAL) -> None:
        if scope == SCOPE_PROJECT:
            d = self.project_install_dir
            _skill_dir_install(d, COMMANDS, _SKILL_TEMPLATE, scope)
        else:
            d = self.global_install_dir
            d.mkdir(parents=True, exist_ok=True)
            for slug, cmd, description in COMMANDS:
                content = _PROMPT_TEMPLATE.format(slug=slug, cmd=cmd, description=description)
                _write_file(d / f"{slug}.md", content)

    def uninstall(self, scope: str = SCOPE_GLOBAL) -> None:
        if scope == SCOPE_PROJECT:
            _skill_dir_uninstall(self.project_install_dir, COMMANDS)
        else:
            d = self.global_install_dir
            if d and d.is_dir():
                for slug, _, _ in COMMANDS:
                    p = d / f"{slug}.md"
                    if p.exists():
                        p.unlink()

    def status(self) -> IntegrationStatus:
        global_dir = self.global_install_dir
        g_installed = (
            global_dir.is_dir()
            and (global_dir / f"{COMMANDS[0][0]}.md").exists()
        ) if global_dir else False
        return IntegrationStatus(
            name=self.name,
            key=self.key,
            detected=self.detect(),
            global_installed=g_installed,
            project_installed=_skill_dir_installed(self.project_install_dir),
            global_dir=global_dir,
            project_dir=self.project_install_dir,
        )
