from __future__ import annotations

from .claude import ClaudeIntegration
from .codex import CodexIntegration
from .cursor import CursorIntegration
from .detector import detect_all, get_by_key
from .gemini import GeminiIntegration
from .kilo import KiloIntegration
from .kiro import KiroIntegration
from .opencode import OpenCodeIntegration

ALL_INTEGRATIONS: list = [
    ClaudeIntegration(),
    GeminiIntegration(),
    OpenCodeIntegration(),
    CodexIntegration(),
    KiroIntegration(),
    KiloIntegration(),
    CursorIntegration(),
]

_BY_KEY = {i.key: i for i in ALL_INTEGRATIONS}


def get_integration(key: str):
    """Return an integration by its short key (e.g. 'claude', 'codex')."""
    return _BY_KEY.get(key.lower())
