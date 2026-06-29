"""Internal repository extraction layer.

This is the only file in the codebase that interacts with graphify.
No other module should import from here directly — go through analyzer.py.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

_log = logging.getLogger(__name__)


def _available() -> bool:
    return shutil.which("graphify") is not None


def _extract(project_path: str, *, timeout: int = 30) -> bool:
    if not _available():
        return False
    try:
        r = subprocess.run(
            ["graphify", "extract", project_path, "--update"],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode != 0:
            _log.debug("extraction returned %d: %s", r.returncode, r.stderr.strip())
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        _log.debug("extraction timed out after %ds", timeout)
        return False
    except Exception as exc:
        _log.debug("extraction failed: %s", exc)
        return False


def _query(anchor: str, graph_path: str, *, timeout: int = 30) -> dict:
    if not _available():
        return {}
    try:
        r = subprocess.run(
            ["graphify", "query", anchor, "--graph", graph_path, "--json"],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode == 0:
            return json.loads(r.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as exc:
        _log.debug("query failed for %r: %s", anchor, exc)
    return {}


def _read_graph(graph_path: str) -> dict | None:
    p = Path(graph_path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as exc:
        _log.warning("Failed to read graph at %s: %s", graph_path, exc)
        return None


def _last_updated(graph_path: str) -> str | None:
    p = Path(graph_path)
    if not p.exists():
        return None
    mtime = p.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
