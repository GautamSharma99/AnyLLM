from __future__ import annotations

from dataclasses import dataclass, field


class Confidence:
    """Public confidence levels for code anchors."""
    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    UNCERTAIN = "UNCERTAIN"
    MISSING = "MISSING"


@dataclass
class Dependency:
    source: str
    target: str
    kind: str = "depends_on"


@dataclass
class RepositoryContext:
    modules: list[dict]
    key_symbols: list[dict]
    dependencies: list[Dependency]
    total_nodes: int
    total_edges: int
