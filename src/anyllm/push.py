from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config, PushConfig
    from .storage import Paths


def _compose_briefing(paths: "Paths", config: "Config") -> str:
    """Compose the briefing string from current.md — never prints to stdout."""
    from .adapters import ADAPTERS
    from .composer import compose, parse_snapshot

    if not paths.current_path.exists():
        raise RuntimeError(
            "No current snapshot found. Run `anyllm pack` first."
        )

    target_name = config.default_target
    adapter_cls = ADAPTERS.get(target_name) or next(iter(ADAPTERS.values()))
    snapshot = parse_snapshot(paths.current_path.read_text())
    briefing = compose(
        snapshot,
        target=target_name,
        extra_rules=config.extra_rules,
        tone=config.tone,
    )
    return adapter_cls().render(briefing)


def push(paths: "Paths", config: "Config") -> None:
    """Push the briefing to Codex — silent, no briefing text to stdout."""
    from .injectors import detect_platform, get_injector

    briefing = _compose_briefing(paths, config)
    push_cfg = config.push
    platform = detect_platform()
    injector = get_injector(platform)

    found = injector.focus_target("codex", push_cfg)

    if not found:
        if push_cfg.open_if_missing:
            import time
            injector.open_url(push_cfg.codex_url)
            time.sleep(3)
            injector.focus_target("codex", push_cfg)
        else:
            print(
                "Codex tab not found and open_if_missing is false. "
                "Open https://codex.openai.com and try again.",
                file=sys.stderr,
            )
            return

    injector.inject_and_send(briefing, delay_ms=push_cfg.send_delay_ms)
    print("✓ pushed to Codex")
