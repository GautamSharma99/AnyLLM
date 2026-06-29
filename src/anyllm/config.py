from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "distiller": {
        "model": "gpt-4o-mini",
        "budget_tokens": 2000,
    },
    "targets": {
        "default": "chatgpt",
    },
    "framing": {
        "extra_rules": [],
        "tone": "direct",
    },
    "merge": {
        "enabled": True,
        "graphify_graph": "graphify-out/graph.json",
        "graphify_timeout": 30,
        "stale_threshold": 3,
        "auto_update_graph": True,
    },
    "push": {
        "browser": "auto",
        "codex_url": "https://codex.openai.com",
        "send_delay_ms": 500,
        "open_if_missing": True,
    },
}


@dataclass
class MergeConfig:
    """Configuration for the confidence-aware merge engine."""
    enabled: bool = True
    graphify_graph: str = "graphify-out/graph.json"
    graphify_timeout: int = 30
    stale_threshold: int = 3
    auto_update_graph: bool = True


@dataclass
class PushConfig:
    """Configuration for the push command (browser injection)."""
    browser: str = "auto"
    codex_url: str = "https://codex.openai.com"
    send_delay_ms: int = 500
    open_if_missing: bool = True


@dataclass
class Config:
    distiller_model: str = "gpt-4o-mini"
    budget_tokens: int = 2000
    default_target: str = "chatgpt"
    extra_rules: list[str] = field(default_factory=list)
    tone: str = "direct"
    merge: MergeConfig = field(default_factory=MergeConfig)
    push: PushConfig = field(default_factory=PushConfig)

    @classmethod
    def load(cls, anyllm_dir: Path) -> "Config":
        path = anyllm_dir / "config.yaml"
        if not path.exists():
            return cls()
        raw = yaml.safe_load(path.read_text()) or {}
        distiller = raw.get("distiller", {})
        targets = raw.get("targets", {})
        framing = raw.get("framing", {})
        merge_raw = raw.get("merge", {})
        merge_cfg = MergeConfig(
            enabled=bool(merge_raw.get("enabled", MergeConfig.enabled)),
            graphify_graph=str(merge_raw.get("graphify_graph", MergeConfig.graphify_graph)),
            graphify_timeout=int(merge_raw.get("graphify_timeout", MergeConfig.graphify_timeout)),
            stale_threshold=int(merge_raw.get("stale_threshold", MergeConfig.stale_threshold)),
            auto_update_graph=bool(merge_raw.get("auto_update_graph", MergeConfig.auto_update_graph)),
        )
        push_raw = raw.get("push", {})
        push_cfg = PushConfig(
            browser=str(push_raw.get("browser", PushConfig.browser)),
            codex_url=str(push_raw.get("codex_url", PushConfig.codex_url)),
            send_delay_ms=int(push_raw.get("send_delay_ms", PushConfig.send_delay_ms)),
            open_if_missing=bool(push_raw.get("open_if_missing", PushConfig.open_if_missing)),
        )
        return cls(
            distiller_model=distiller.get("model", cls.distiller_model),
            budget_tokens=int(distiller.get("budget_tokens", cls.budget_tokens)),
            default_target=targets.get("default", cls.default_target),
            extra_rules=list(framing.get("extra_rules", []) or []),
            tone=framing.get("tone", cls.tone),
            merge=merge_cfg,
            push=push_cfg,
        )

    @staticmethod
    def write_default(anyllm_dir: Path) -> Path:
        path = anyllm_dir / "config.yaml"
        path.write_text(yaml.safe_dump(DEFAULT_CONFIG, sort_keys=False))
        return path

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
