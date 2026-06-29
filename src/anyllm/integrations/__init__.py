from __future__ import annotations

from typing import Optional

from .agy import AgyIntegration
from .claude import ClaudeIntegration
from .codex import CodexIntegration
from .cursor import CursorIntegration
from .kilo import KiloIntegration
from .kiro import KiroIntegration
from .opencode import OpenCodeIntegration

ALL_INTEGRATIONS: list = [
    ClaudeIntegration(),
    CodexIntegration(),
    OpenCodeIntegration(),
    AgyIntegration(),
    KiroIntegration(),
    KiloIntegration(),
    CursorIntegration(),
]

_BY_KEY = {i.key: i for i in ALL_INTEGRATIONS}


def get_integration(key: str):
    """Return an integration by its short key (e.g. 'claude', 'codex')."""
    return _BY_KEY.get(key.lower())


def detect_all() -> list:
    """Return all integrations whose CLI is detected on this machine."""
    return [i for i in ALL_INTEGRATIONS if i.detect()]
