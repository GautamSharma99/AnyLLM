from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import CLIIntegration, COMMANDS, _write_file


_STEERING_TEMPLATE = """\
# /{slug}

{description}

When the user types `/{slug}`, run this shell command and show the output:

```bash
{cmd}
```
"""


class KiroIntegration(CLIIntegration):
    """AWS Kiro — installs as steering documents in ~/.kiro/steering/"""

    name = "Kiro"
    key = "kiro"
    binaries = ["kiro"]
    config_dirs = [Path.home() / ".kiro"]

    @property
    def install_dir(self) -> Optional[Path]:
        # Kiro uses ~/.kiro/steering/ for custom instructions
        if self.detect():
            return Path.home() / ".kiro" / "steering"
        return None

    def _render_command(self, slug: str, cmd: str, description: str) -> tuple[str, str]:
        filename = f"{slug}.md"
        content = _STEERING_TEMPLATE.format(slug=slug, cmd=cmd, description=description)
        return filename, content
