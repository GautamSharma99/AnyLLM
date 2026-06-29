from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import CLIIntegration


def detect_all(integrations: list["CLIIntegration"]) -> list["CLIIntegration"]:
    """Return all integrations whose CLI is detected on this machine."""
    return [i for i in integrations if i.detect()]


def get_by_key(integrations: list["CLIIntegration"], key: str) -> "CLIIntegration | None":
    """Return the integration matching the given short key (case-insensitive)."""
    key = key.lower()
    for i in integrations:
        if i.key == key:
            return i
    return None
