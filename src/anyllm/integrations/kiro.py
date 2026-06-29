from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import CLIIntegration, SCOPE_GLOBAL


_STEERING_TEMPLATE = """\
# /{slug}

{description}

When the user types `/{slug}`, run this command and show the output:

```bash
{cmd}
```
"""


class KiroIntegration(CLIIntegration):
    """AWS Kiro — ~/.kiro/steering/<name>.md"""

    name = "Kiro"
    key = "kiro"
    command_style = "slash"
    binaries = ["kiro"]
    config_dirs = [Path.home() / ".kiro"]

    @property
    def global_install_dir(self) -> Optional[Path]:
        if self.detect():
            return Path.home() / ".kiro" / "steering"
        return None

    def _render_command(self, slug: str, cmd: str, description: str, scope: str = SCOPE_GLOBAL) -> tuple[str, str]:
        content = _STEERING_TEMPLATE.format(slug=slug, cmd=cmd, description=description)
        return f"{slug}.md", content
