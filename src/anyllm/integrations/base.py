from __future__ import annotations

import shutil as _shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Every integration installs wrappers for these commands.
# Tuple: (slug, cli-command, description)
COMMANDS: list[tuple[str, str, str]] = [
    ("anyllm-init",   "anyllm init",              "Initialize anyllm in the current project"),
    ("anyllm-pack",   "anyllm pack $ARGUMENTS",   "Pack current session into .anyllm/current.md — no tokens used"),
    ("anyllm-repack", "anyllm repack $ARGUMENTS", "Ingest turns missed since last pack and merge into current.md — no tokens used"),
    ("anyllm-prime",  "anyllm prime $ARGUMENTS",  "Emit a copy-pasteable briefing for the next LLM"),
    ("anyllm-push",   "anyllm push $ARGUMENTS",   "Paste briefing into target and press Send — silent"),
    ("anyllm-status", "anyllm status",             "Show what's in the current snapshot"),
    ("anyllm-log",    "anyllm log",                "Show session history packed into this project"),
    ("anyllm-diff",   "anyllm diff $ARGUMENTS",   "Show the snapshot of a single session"),
]

# Scopes supported by the integrate command.
SCOPE_GLOBAL = "global"
SCOPE_PROJECT = "project"


@dataclass
class IntegrationStatus:
    name: str
    key: str
    detected: bool
    global_installed: bool
    project_installed: bool
    global_dir: Optional[Path]
    project_dir: Optional[Path]

    @property
    def installed(self) -> bool:
        return self.global_installed or self.project_installed


class CLIIntegration(ABC):
    """Base class for per-CLI slash command integrations."""

    name: str            # display name, e.g. "Claude Code"
    key: str             # short key used in CLI args, e.g. "claude"
    command_style: str = "slash"   # "slash" | "dollar" | "prompts"
    binaries: list[str] = []
    config_dirs: list[Path] = []

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    def global_install_dir(self) -> Optional[Path]:
        """User-level install directory (default scope). Override to provide."""
        return None

    @property
    def project_install_dir(self) -> Optional[Path]:
        """Project-relative install directory. Override to provide."""
        return None

    @abstractmethod
    def _render_command(self, slug: str, cmd: str, description: str, scope: str = SCOPE_GLOBAL) -> tuple[str, str]:
        """Return (filename_or_dirname, content) for one command wrapper."""

    # ------------------------------------------------------------------
    # Concrete helpers
    # ------------------------------------------------------------------

    def detect(self) -> bool:
        """Return True if this CLI appears to be installed on this machine."""
        try:
            for binary in self.binaries:
                if _shutil.which(binary):
                    return True
            for d in self.config_dirs:
                if d.is_dir():
                    return True
        except Exception:
            pass
        return False

    def _install_to(self, d: Path, scope: str) -> None:
        """Write all command wrappers into directory d."""
        d.mkdir(parents=True, exist_ok=True)
        for slug, cmd, description in COMMANDS:
            filename, content = self._render_command(slug, cmd, description, scope)
            _write_file(d / filename, content)

    def _uninstall_from(self, d: Path, scope: str) -> None:
        """Remove all anyllm wrappers from directory d."""
        if not d.is_dir():
            return
        for slug, _, _ in COMMANDS:
            filename, _ = self._render_command(slug, "", "", scope)
            target = d / filename
            if target.is_file():
                target.unlink()
            target_dir = d / filename  # for skill-dir integrations filename == dirname
            if target_dir.is_dir():
                _shutil.rmtree(target_dir)

    def install(self, scope: str = SCOPE_GLOBAL) -> None:
        """Install command wrappers for the given scope."""
        if scope == SCOPE_PROJECT:
            d = self.project_install_dir
            if d is None:
                raise RuntimeError(f"{self.name} does not support project-scope installs.")
        else:
            d = self.global_install_dir
            if d is None:
                raise RuntimeError(f"{self.name} not detected — is it installed?")
        self._install_to(d, scope)

    def uninstall(self, scope: str = SCOPE_GLOBAL) -> None:
        """Remove command wrappers for the given scope."""
        if scope == SCOPE_PROJECT:
            d = self.project_install_dir
        else:
            d = self.global_install_dir
        if d and d.is_dir():
            self._uninstall_from(d, scope)

    def _is_installed(self, d: Optional[Path], scope: str) -> bool:
        if d is None or not d.is_dir():
            return False
        slug, cmd, desc = COMMANDS[0]
        filename, _ = self._render_command(slug, cmd, desc, scope)
        return (d / filename).exists()

    def status(self) -> IntegrationStatus:
        return IntegrationStatus(
            name=self.name,
            key=self.key,
            detected=self.detect(),
            global_installed=self._is_installed(self.global_install_dir, SCOPE_GLOBAL),
            project_installed=self._is_installed(self.project_install_dir, SCOPE_PROJECT),
            global_dir=self.global_install_dir,
            project_dir=self.project_install_dir,
        )


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _skill_dir_install(base_dir: Path, commands: list[tuple[str, str, str]], template: str, scope: str) -> None:
    """Helper for skill-directory integrations (one dir per command with SKILL.md)."""
    base_dir.mkdir(parents=True, exist_ok=True)
    for slug, cmd, description in commands:
        skill_dir = base_dir / slug
        skill_dir.mkdir(exist_ok=True)
        try:
            content = template.format(
                slug=slug, cmd=cmd, description=description,
                description_lower=description.lower(), scope=scope,
            )
        except KeyError:
            content = template.format(slug=slug, cmd=cmd, description=description, scope=scope)
        _write_file(skill_dir / "SKILL.md", content)


def _skill_dir_uninstall(base_dir: Path, commands: list[tuple[str, str, str]]) -> None:
    """Helper to remove skill directories."""
    if not base_dir.is_dir():
        return
    for slug, _, _ in commands:
        skill_dir = base_dir / slug
        if skill_dir.is_dir():
            _shutil.rmtree(skill_dir)


def _skill_dir_installed(base_dir: Optional[Path]) -> bool:
    if base_dir is None or not base_dir.is_dir():
        return False
    first_slug = COMMANDS[0][0]
    return (base_dir / first_slug / "SKILL.md").exists()
