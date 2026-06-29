from __future__ import annotations

from pathlib import Path
from typing import Any

from . import _extractor as _ext
from .models import Confidence, Dependency, RepositoryContext

# Map internal extractor confidence → public confidence levels.
_CONFIDENCE_MAP: dict[str, str] = {
    "EXTRACTED": Confidence.CONFIRMED,
    "INFERRED": Confidence.LIKELY,
    "AMBIGUOUS": Confidence.UNCERTAIN,
    "MISSING": Confidence.MISSING,
}

_DEFAULT_GRAPH_SUBPATH = "graphify-out/graph.json"


class RepositoryAnalyzer:
    """Analyzes the repository to enrich context snapshots.

    Usage::

        analyzer = RepositoryAnalyzer(project_root)
        analyzer.analyze()                    # incremental, safe to call always
        conf = analyzer.resolve_symbol("auth.validate_token")
        briefing = analyzer.enrich_briefing(briefing)
    """

    def __init__(self, project_root: Path, timeout: int = 30) -> None:
        self._root = Path(project_root)
        self._timeout = timeout
        self.graph_path = self._root / _DEFAULT_GRAPH_SUBPATH

    def available(self) -> bool:
        """True if repository analysis can produce results."""
        return _ext._available() and self.graph_path.exists()

    def analyze(self) -> bool:
        """Run incremental repository analysis. Safe to call — no-op if unavailable."""
        return _ext._extract(str(self._root), timeout=self._timeout)

    def resolve_symbol(self, anchor: str) -> str:
        """Return a public confidence level for a code anchor.

        Returns one of CONFIRMED / LIKELY / UNCERTAIN / MISSING.
        """
        if not self.available():
            return Confidence.MISSING
        raw = _ext._query(anchor, str(self.graph_path), timeout=self._timeout)
        if not raw.get("exists", False):
            return Confidence.MISSING
        internal = raw.get("confidence", "MISSING").upper()
        return _CONFIDENCE_MAP.get(internal, Confidence.UNCERTAIN)

    def get_related_files(self, anchor: str) -> list[str]:
        if not self.available():
            return []
        raw = _ext._query(anchor, str(self.graph_path), timeout=self._timeout)
        neighbors = raw.get("neighbors", [])
        return [
            (n if isinstance(n, str) else n.get("file", ""))
            for n in neighbors
            if n
        ]

    def get_dependencies(self) -> list[Dependency]:
        graph = _ext._read_graph(str(self.graph_path))
        if not graph:
            return []
        edges = graph.get("edges", graph.get("relationships", []))
        return [
            Dependency(
                source=e.get("source", e.get("from", "")),
                target=e.get("target", e.get("to", "")),
                kind=e.get("type", e.get("relationship", "depends_on")),
            )
            for e in edges[:100]
        ]

    def get_entrypoints(self) -> list[str]:
        graph = _ext._read_graph(str(self.graph_path))
        if not graph:
            return []
        return [
            n.get("file", n.get("path", n.get("name", "")))
            for n in graph.get("nodes", [])
            if n.get("is_entrypoint") or n.get("type", "").lower() == "entrypoint"
        ]

    def get_architecture_summary(self) -> str:
        ctx = self._build_context()
        if not ctx:
            return ""
        lines: list[str] = []
        if ctx.modules:
            lines.append("Modules:")
            for m in ctx.modules[:20]:
                lines.append(f"  {m.get('path') or m.get('name', '?')}")
        if ctx.dependencies:
            lines.append("\nDependencies:")
            for d in ctx.dependencies[:15]:
                lines.append(f"  {d.source} → {d.target}")
        return "\n".join(lines)

    def enrich_briefing(self, briefing: dict[str, Any]) -> dict[str, Any]:
        """Inject repository context into a briefing dict.

        Returns the briefing unchanged if repository analysis is unavailable.
        """
        if not self.available():
            return briefing

        ctx = self._build_context()
        if not ctx:
            return briefing

        # Collect code anchors referenced in decisions for targeted lookup
        from ..merger import parse_decisions
        decisions_text = briefing.get("sections", {}).get("Decisions", "")
        anchors: list[str] = []
        if decisions_text:
            decisions = parse_decisions(f"## Decisions\n{decisions_text}")
            anchors = [d.code_anchor for d in decisions if d.code_anchor]

        repo_md = self._render_context(ctx, anchors)
        if not repo_md:
            return briefing

        sections = dict(briefing.get("sections", {}))
        sections["Repository Context"] = repo_md
        return {**briefing, "sections": sections}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_context(self, max_nodes: int = 50) -> RepositoryContext | None:
        graph = _ext._read_graph(str(self.graph_path))
        if not graph:
            return None

        nodes = graph.get("nodes", [])
        edges = graph.get("edges", graph.get("relationships", []))

        modules: list[dict] = []
        symbols: list[dict] = []
        for node in nodes[: max_nodes * 3]:
            ntype = node.get("type", "").lower()
            if ntype in ("file", "module"):
                modules.append({
                    "name": node.get("name", ""),
                    "path": node.get("file", node.get("path", "")),
                })
            elif ntype in ("function", "class", "method"):
                symbols.append({
                    "name": node.get("name", ""),
                    "type": ntype,
                    "file": node.get("file", ""),
                })

        deps = [
            Dependency(
                source=e.get("source", e.get("from", "")),
                target=e.get("target", e.get("to", "")),
                kind=e.get("type", e.get("relationship", "depends_on")),
            )
            for e in edges[:max_nodes]
        ]

        return RepositoryContext(
            modules=modules[:max_nodes],
            key_symbols=symbols[:max_nodes],
            dependencies=deps,
            total_nodes=len(nodes),
            total_edges=len(edges),
        )

    def _render_context(self, ctx: RepositoryContext, anchors: list[str]) -> str:
        parts: list[str] = []

        if ctx.modules:
            parts.append("### Modules")
            for m in ctx.modules[:30]:
                path = m.get("path") or m.get("name", "?")
                parts.append(f"- `{path}`")
            parts.append("")

        if ctx.key_symbols:
            parts.append("### Key Symbols")
            for s in ctx.key_symbols[:20]:
                file_note = f" in `{s['file']}`" if s.get("file") else ""
                parts.append(f"- `{s['name']}` ({s['type']}){file_note}")
            parts.append("")

        if ctx.dependencies:
            parts.append("### Dependencies")
            for d in ctx.dependencies[:15]:
                parts.append(f"- `{d.source}` → `{d.target}`")
            parts.append("")

        if anchors:
            verified = [(a, self.resolve_symbol(a)) for a in anchors]
            present = [(a, c) for a, c in verified if c != Confidence.MISSING]
            if present:
                parts.append("### Decision Anchors")
                for anchor, conf in present:
                    parts.append(f"- `{anchor}` [{conf}]")
                parts.append("")

        return "\n".join(parts)
