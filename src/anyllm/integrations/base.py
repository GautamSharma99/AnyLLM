from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# All slash commands every integration must install.
# Tuple: (slug, cli-command-with-args, description)
COMMANDS: list[tuple[str, str, str]] = [
    (
        "anyllm-init",
        "anyllm init",
        "Initialize anyllm in the current project",
    ),
    (
        "anyllm-pack",
        "anyllm pack $ARGUMENTS",
        "Pack current session into .anyllm/current.md — no tokens used",
    ),
    (
        "anyllm-repack",
        "anyllm repack $ARGUMENTS",
        "Ingest turns missed since last pack and merge into current.md — no tokens used",
    ),
    (
        "anyllm-prime",
        "anyllm prime $ARGUMENTS",
        "Emit a copy-pasteable briefing for the next LLM",
    ),
    (
        "anyllm-push",
        "anyllm push $ARGUMENTS",
        "Paste briefing into Codex and press Send — silent, no output shown",
    ),
    (
        "anyllm-status",
        "anyllm status",
        "Show what's in the current snapshot",
    ),
    (
        "anyllm-log",
        "anyllm log",
        "Show session history packed into this project",
    ),
    (
        "anyllm-diff",
        "anyllm diff $ARGUMENTS",
        "Show the snapshot of a single session",
    ),
]


@dataclass
class IntegrationStatus:
    name: str
    key: str
    detected: bool
    installed: bool
    install_dir: Optional[Path]


class CLIIntegration(ABC):
    """Base class for per-CLI slash command integrations."""

    name: str   # display name, e.g. "Claude Code"
    key: str    # short key used in CLI args, e.g. "claude"
    binaries: list[str] = []   # binary names to check on PATH
    config_dirs: list[Path] = []  # directories that signal the CLI is installed

    # --- abstract interface ---------------------------------------------------

    @property
    @abstractmethod
    def install_dir(self) -> Optional[Path]:
        """Where to write the command files. None if CLI not detected."""

    @abstractmethod
    def _render_command(self, slug: str, cmd: str, description: str) -> tuple[str, str]:
        """Return (filename, file_content) for one command wrapper."""

    # --- concrete helpers -----------------------------------------------------

    def detect(self) -> bool:
        """Return True if this CLI appears to be installed."""
        try:
            for binary in self.binaries:
                if shutil.which(binary):
                    return True
            for d in self.config_dirs:
                if d.is_dir():
                    return True
        except Exception:
            pass
        return False

    def install(self) -> None:
        """Write all command wrappers into the CLI's commands directory."""
        d = self.install_dir
        if d is None:
            raise RuntimeError(
                f"{self.name} not detected. Is it installed?"
            )
        d.mkdir(parents=True, exist_ok=True)
        for slug, cmd, description in COMMANDS:
            filename, content = self._render_command(slug, cmd, description)
            _write_file(d / filename, content)

    def uninstall(self) -> None:
        """Remove all anyllm command wrappers from the CLI's commands directory."""
        d = self.install_dir
        if d is None or not d.is_dir():
            return
        for slug, _, _ in COMMANDS:
            filename, _ = self._render_command(slug, "", "")
            target = d / filename
            if target.exists():
                target.unlink()
            # Some integrations use directories per command
            target_dir = d / slug
            if target_dir.is_dir():
                import shutil as _shutil
                _shutil.rmtree(target_dir)

    def status(self) -> IntegrationStatus:
        detected = self.detect()
        d = self.install_dir
        installed = False
        if d is not None and d.is_dir():
            slug, cmd, desc = COMMANDS[0]
            filename, _ = self._render_command(slug, cmd, desc)
            installed = (d / filename).exists() or (d / slug).is_dir()
        return IntegrationStatus(
            name=self.name,
            key=self.key,
            detected=detected,
            installed=installed,
            install_dir=d,
        )


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
