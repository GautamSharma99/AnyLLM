from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .adapters import ADAPTERS
from .banner import print_banner
from .composer import compose, parse_snapshot
from .config import Config
from .distiller import Distiller, DistillerError
from .ingestors import INGESTORS, ClaudeCodeIngestor
from .storage import (
    Paths,
    append_index_entry,
    ensure_initialized,
    find_project_root,
    get_last_pack_entry,
    init_project,
    load_index,
    session_basename,
    write_current,
    write_merged_current,
    write_snapshot,
    write_transcript,
)


app = typer.Typer(
    help="Git for LLM context. Snapshot a session, brief the next LLM.",
    no_args_is_help=False,
    add_completion=False,
)
import sys as _sys
# On Windows, the default console encoding (cp1252) can't render unicode
# glyphs like → that rich's markup and our messages use. Reconfigure stdio
# to UTF-8 so rich renders cleanly.
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

console = Console()
err_console = Console(stderr=True)


def _paths() -> Paths:
    return Paths(root=find_project_root())


def _version_callback(value: bool):
    if value:
        console.print(f"anyllm {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    # No subcommand: show the banner + command help as the TUI home screen.
    if ctx.invoked_subcommand is None:
        print_banner(console)
        console.print(ctx.get_help())
        raise typer.Exit()


@app.command()
def init() -> None:
    """Create a .anyllm/ directory in the current project."""
    print_banner(console)
    root = Path.cwd()
    paths = init_project(root)
    if not paths.config_path.exists():
        Config.write_default(paths.anyllm_dir)
    console.print(f"[green]initialized[/green] {paths.anyllm_dir}")


@app.command()
def pack(
    source: str = typer.Option(
        "claude-code", "--source", "-s",
        help="Ingestor to use. MVP: claude-code.",
    ),
    session_id: Optional[str] = typer.Option(
        None, "--session",
        help="Ingest a specific session id instead of the most recent.",
    ),
) -> None:
    """Snapshot the current/most-recent LLM session into .anyllm/."""
    paths = _paths()
    ensure_initialized(paths)
    config = Config.load(paths.anyllm_dir)

    ingestor_cls = INGESTORS.get(source)
    if ingestor_cls is None:
        err_console.print(f"[red]unknown source:[/red] {source}")
        raise typer.Exit(code=2)
    ingestor = ingestor_cls()

    if session_id and isinstance(ingestor, ClaudeCodeIngestor):
        transcript_obj = ingestor.session_by_id(paths.root, session_id)
    else:
        transcript_obj = ingestor.latest_session(paths.root)

    if transcript_obj is None:
        err_console.print(
            f"[red]no {source} session found[/red] for {paths.root}. "
            "Has this project had a Claude Code session yet?"
        )
        raise typer.Exit(code=1)

    transcript = transcript_obj.to_dict()
    transcript_path = write_transcript(paths, transcript)
    console.print(f"[dim]wrote[/dim] {transcript_path.relative_to(paths.root)}")

    project = paths.root.name
    distiller = Distiller(
        model=config.distiller_model,
        budget_tokens=config.budget_tokens,
    )
    console.print(
        f"distilling {len(transcript.get('turns') or [])} turns "
        f"with {distiller.model} (budget {distiller.budget_tokens})..."
    )
    try:
        snapshot_md = distiller.distill(transcript, project=project)
    except DistillerError as e:
        err_console.print(f"[red]distillation failed:[/red] {e}")
        raise typer.Exit(code=1)

    snapshot_path = write_snapshot(paths, transcript, snapshot_md)

    # --- Merge step (new) ---
    merge_cfg = config.merge
    sid = transcript.get("session_id", "")
    merge_result = None

    if merge_cfg.enabled:
        # Optionally update the graphify graph before merging
        graph_path: str | None = None
        graph_query_fn = None
        if merge_cfg.auto_update_graph:
            from .graph_bridge import graphify_available, update_graph
            if graphify_available():
                console.print("[dim]updating graphify graph...[/dim]")
                update_graph(str(paths.root), timeout=merge_cfg.graphify_timeout)

        # Set up graph query function if graph exists
        resolved_graph = paths.root / merge_cfg.graphify_graph
        if resolved_graph.exists():
            graph_path = str(resolved_graph)
            from .graph_bridge import make_graph_query_fn
            graph_query_fn = make_graph_query_fn(
                graph_path, timeout=merge_cfg.graphify_timeout
            )

        current_path, merge_result = write_merged_current(
            paths,
            snapshot_md,
            session_id=sid,
            graph_path=graph_path,
            stale_threshold=merge_cfg.stale_threshold,
            graph_query_fn=graph_query_fn,
        )
    else:
        current_path = write_current(paths, snapshot_md)

    # Build index entry with merge info
    index_entry: dict = {
        "source": transcript["source"],
        "session_id": transcript["session_id"],
        "started_at": transcript.get("started_at", ""),
        "ended_at": transcript.get("ended_at", ""),
        "last_turn_ts": transcript.get("ended_at", ""),
        "turn_count": len(transcript.get("turns") or []),
        "token_count": (transcript.get("metadata") or {}).get("token_count", 0),
        "snapshot_path": str(snapshot_path.relative_to(paths.root)),
        "transcript_path": str(transcript_path.relative_to(paths.root)),
        "packed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if merge_result is not None:
        index_entry["merge"] = {
            "confirmed": len(merge_result.confirmed),
            "added": len(merge_result.added),
            "stale": len(merge_result.stale),
            "orphaned": len(merge_result.orphaned),
        }

    append_index_entry(paths, index_entry)

    # Print summary
    if merge_result is not None:
        console.print(
            f"[green]packed[/green] → {current_path.relative_to(paths.root)} "
            f"(+{len(merge_result.added)} decisions, "
            f"{len(merge_result.confirmed)} confirmed, "
            f"{len(merge_result.stale)} stale)"
        )
    else:
        console.print(f"[green]packed[/green] → {current_path.relative_to(paths.root)}")


@app.command()
def prime(
    target: Optional[str] = typer.Option(
        None, "--target", "-t",
        help="Target adapter (chatgpt, claude, cursor). Defaults to config.",
    ),
    copy: bool = typer.Option(False, "--copy", help="Copy output to clipboard."),
    write: Optional[Path] = typer.Option(
        None, "--write", help="Write output to this path instead of stdout.",
    ),
) -> None:
    """Emit a copy-pasteable briefing for the next LLM."""
    paths = _paths()
    ensure_initialized(paths)
    config = Config.load(paths.anyllm_dir)

    if not paths.current_path.exists():
        err_console.print(
            f"[red]no current snapshot[/red] at {paths.current_path}. "
            "Run `anyllm pack` first."
        )
        raise typer.Exit(code=1)

    target_name = target or config.default_target
    adapter_cls = ADAPTERS.get(target_name)
    if adapter_cls is None:
        err_console.print(
            f"[red]unknown target:[/red] {target_name}. "
            f"Available: {', '.join(sorted(ADAPTERS))}"
        )
        raise typer.Exit(code=2)

    snapshot = parse_snapshot(paths.current_path.read_text())
    briefing = compose(
        snapshot,
        target=target_name,
        extra_rules=config.extra_rules,
        tone=config.tone,
    )

    # Enrich with graph context if available
    merge_cfg = config.merge
    resolved_graph = paths.root / merge_cfg.graphify_graph
    if resolved_graph.exists():
        from .graph_context import enrich_briefing
        briefing = enrich_briefing(
            briefing,
            str(resolved_graph),
            timeout=merge_cfg.graphify_timeout,
        )

    primer = adapter_cls().render(briefing)

    if write is not None:
        write.write_text(primer)
        console.print(f"[green]wrote[/green] {write}")
        return

    if copy:
        try:
            import pyperclip
            pyperclip.copy(primer)
            console.print(
                f"[green]copied[/green] {len(primer)} chars to clipboard "
                f"(target: {target_name})"
            )
            return
        except Exception as e:
            err_console.print(
                f"[yellow]clipboard unavailable ({e}); falling back to stdout[/yellow]"
            )

    # default: print to stdout
    typer.echo(primer)


@app.command()
def status() -> None:
    """Show what's in the current snapshot."""
    paths = _paths()
    ensure_initialized(paths)
    config = Config.load(paths.anyllm_dir)

    if not paths.current_path.exists():
        console.print("[yellow]no current snapshot[/yellow]. Run `anyllm pack`.")
        raise typer.Exit(code=0)

    snapshot = parse_snapshot(paths.current_path.read_text())
    fm = snapshot.frontmatter or {}
    index = load_index(paths)
    sessions = index.get("sessions", [])

    console.print(f"[bold]Project:[/bold] {fm.get('project', paths.root.name)}")
    console.print(f"  Sessions: {len(sessions)}")
    console.print(f"  Current snapshot: {fm.get('generated_at', '?')}")

    # Merge info
    merged_from = fm.get("merged_from") or []
    if merged_from:
        console.print(f"  Merged from: {len(merged_from)} sessions")

    conf_report = fm.get("confidence_report") or {}
    if conf_report:
        confirmed = conf_report.get("confirmed", 0)
        stale_count = conf_report.get("stale", 0)
        orphaned_count = conf_report.get("orphaned", 0)
        console.print(
            f"  Decisions: {confirmed} confirmed, "
            f"{stale_count} stale, {orphaned_count} orphaned"
        )

    # Graph info
    merge_cfg = config.merge
    resolved_graph = paths.root / merge_cfg.graphify_graph
    if resolved_graph.exists():
        from .graph_bridge import graph_mtime
        mtime = graph_mtime(str(resolved_graph))
        console.print(f"  Graph: {merge_cfg.graphify_graph} (last updated: {mtime or '?'})")
    else:
        console.print(f"  Graph: {merge_cfg.graphify_graph} (not found)")

    # graphify availability
    from .graph_bridge import graphify_available, graphify_version
    if graphify_available():
        ver = graphify_version() or "unknown version"
        console.print(f"  graphify: installed ({ver})")
    else:
        console.print("  graphify: [dim]not installed[/dim]")

    console.print()

    # Show key sections
    sections = snapshot.sections
    for name in ["Task", "Status", "Next step", "Next Step"]:
        if sections.get(name):
            console.print(f"[bold cyan]# {name}[/bold cyan]")
            console.print(sections[name])
            console.print()

    if sections.get("Confidence Report"):
        console.print("[bold magenta]# Confidence Report[/bold magenta]")
        console.print(sections["Confidence Report"])

    if sections.get("Stale / Needs Verification"):
        console.print()
        console.print("[bold yellow]# Stale / Needs Verification[/bold yellow]")
        console.print(sections["Stale / Needs Verification"])


@app.command("log")
def log_cmd() -> None:
    """Show session history packed into this project."""
    paths = _paths()
    ensure_initialized(paths)
    index = load_index(paths)
    sessions = index.get("sessions", [])
    if not sessions:
        console.print("[dim]no sessions packed yet[/dim]")
        return

    table = Table(title="anyllm sessions", show_lines=False)
    table.add_column("packed at")
    table.add_column("type")
    table.add_column("source")
    table.add_column("session id")
    table.add_column("turns", justify="right")
    table.add_column("tokens", justify="right")
    table.add_column("decisions", justify="right")

    for entry in sessions:
        entry_type = entry.get("type", "pack")
        merge_info = entry.get("merge")
        if merge_info:
            added = merge_info.get("added", 0)
            confirmed = merge_info.get("confirmed", 0)
            stale_count = merge_info.get("stale", 0)
            if added and not confirmed and not stale_count:
                decision_str = f"+{added} decisions (initial)"
            else:
                decision_str = f"+{added}, {confirmed} confirmed, {stale_count} stale"
        else:
            decision_str = ""

        turns_val = entry.get("turns_ingested") or entry.get("turn_count") or ""
        table.add_row(
            entry.get("packed_at", ""),
            entry_type,
            entry.get("source", ""),
            entry.get("session_id", ""),
            str(turns_val),
            str(entry.get("token_count", "")),
            decision_str,
        )
    console.print(table)


@app.command()
def diff(session_id: str = typer.Argument(..., help="Session id to inspect.")) -> None:
    """Show the snapshot of a single session."""
    paths = _paths()
    ensure_initialized(paths)
    index = load_index(paths)
    match = next(
        (e for e in index.get("sessions", []) if e.get("session_id") == session_id),
        None,
    )
    if not match:
        err_console.print(f"[red]no session with id[/red] {session_id}")
        raise typer.Exit(code=1)

    snapshot_path = paths.root / match["snapshot_path"]
    if not snapshot_path.exists():
        base = session_basename(match.get("started_at", ""), session_id)
        snapshot_path = paths.sessions_dir / f"{base}.snapshot.md"

    if not snapshot_path.exists():
        err_console.print(f"[red]snapshot missing:[/red] {snapshot_path}")
        raise typer.Exit(code=1)

    # Show snapshot content
    console.print(snapshot_path.read_text())

    # Show merge info if available
    merge_info = match.get("merge")
    if merge_info:
        console.print()
        console.print("[bold]Merge summary for this session:[/bold]")
        console.print(f"  +{merge_info.get('added', 0)} added")
        console.print(f"  {merge_info.get('confirmed', 0)} confirmed")
        console.print(f"  {merge_info.get('stale', 0)} stale")
        console.print(f"  {merge_info.get('orphaned', 0)} orphaned")


@app.command()
def repack(
    source: str = typer.Option(
        "claude-code", "--source", "-s",
        help="Ingestor to use.",
    ),
) -> None:
    """Ingest turns missed since the last pack and merge them into current.md."""
    paths = _paths()
    ensure_initialized(paths)
    config = Config.load(paths.anyllm_dir)

    last_entry = get_last_pack_entry(paths)
    if not last_entry:
        err_console.print(
            "[red]No previous pack found.[/red] Run `anyllm pack` first."
        )
        raise typer.Exit(code=1)

    since_ts = last_entry.get("last_turn_ts") or last_entry.get("ended_at", "")
    session_id = last_entry.get("session_id", "")

    ingestor_cls = INGESTORS.get(source)
    if ingestor_cls is None:
        err_console.print(f"[red]unknown source:[/red] {source}")
        raise typer.Exit(code=2)
    ingestor = ingestor_cls()

    if session_id and isinstance(ingestor, ClaudeCodeIngestor):
        transcript_obj = ingestor.session_by_id(paths.root, session_id, since_ts=since_ts)
    else:
        transcript_obj = ingestor.latest_session(paths.root, since_ts=since_ts)

    if transcript_obj is None or not transcript_obj.turns:
        console.print(
            "Nothing to repack — no new turns since last pack."
        )
        raise typer.Exit(code=0)

    console.print(
        f"Repacking [bold]{len(transcript_obj.turns)}[/bold] missed turn(s) "
        f"since [dim]{since_ts}[/dim]..."
    )

    transcript = transcript_obj.to_dict()
    project = paths.root.name
    distiller = Distiller(
        model=config.distiller_model,
        budget_tokens=config.budget_tokens,
    )
    try:
        snapshot_md = distiller.distill(transcript, project=project, prompt_version="v1-delta")
    except DistillerError as e:
        err_console.print(f"[red]distillation failed:[/red] {e}")
        raise typer.Exit(code=1)

    merge_cfg = config.merge
    sid = transcript.get("session_id", "")
    merge_result = None

    if merge_cfg.enabled:
        graph_path: str | None = None
        graph_query_fn = None
        resolved_graph = paths.root / merge_cfg.graphify_graph
        if resolved_graph.exists():
            graph_path = str(resolved_graph)
            from .graph_bridge import make_graph_query_fn
            graph_query_fn = make_graph_query_fn(
                graph_path, timeout=merge_cfg.graphify_timeout
            )

        current_path, merge_result = write_merged_current(
            paths,
            snapshot_md,
            session_id=sid,
            graph_path=graph_path,
            stale_threshold=merge_cfg.stale_threshold,
            graph_query_fn=graph_query_fn,
        )
    else:
        current_path = write_current(paths, snapshot_md)

    packed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    repack_entry: dict = {
        "type": "repack",
        "source": transcript["source"],
        "session_id": session_id,
        "since_ts": since_ts,
        "turns_ingested": len(transcript.get("turns") or []),
        "packed_at": packed_at,
        "last_turn_ts": transcript.get("ended_at", ""),
    }
    if merge_result is not None:
        repack_entry["merge"] = {
            "confirmed": len(merge_result.confirmed),
            "added": len(merge_result.added),
            "stale": len(merge_result.stale),
            "orphaned": len(merge_result.orphaned),
        }
    append_index_entry(paths, repack_entry)

    if merge_result is not None:
        console.print(
            f"[green]✓ repack done[/green] → {current_path.relative_to(paths.root)} "
            f"(+{len(merge_result.added)} added, "
            f"{len(merge_result.confirmed)} confirmed)"
        )
    else:
        console.print(f"[green]✓ repack done[/green] → {current_path.relative_to(paths.root)}")


@app.command()
def push() -> None:
    """Paste the briefing into Codex and press Send — silent, no briefing text shown."""
    paths = _paths()
    ensure_initialized(paths)
    config = Config.load(paths.anyllm_dir)

    from .push import push as _push
    try:
        _push(paths, config)
    except RuntimeError as e:
        err_console.print(f"[red]push failed:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        err_console.print(f"[red]push error:[/red] {e}")
        raise typer.Exit(code=1)


@app.command("integrations")
def integrations_cmd() -> None:
    """Show status of all supported CLI integrations."""
    from .integrations import ALL_INTEGRATIONS

    console.print("[bold]CLI integrations:[/bold]\n")
    for integration in ALL_INTEGRATIONS:
        st = integration.status()
        detected_icon = "[green]✓[/green]" if st.detected else "[dim]✗[/dim]"
        installed_icon = "[green]✓ installed[/green]" if st.installed else "[dim]not installed[/dim]"
        dir_hint = f"  [dim]{st.install_dir}[/dim]" if st.install_dir and st.installed else ""
        console.print(f"  {detected_icon} [bold]{st.name}[/bold] ({st.key}) — {installed_icon}{dir_hint}")


@app.command()
def install(
    name: Optional[str] = typer.Argument(
        None,
        help="Integration to install (claude, codex, opencode, agy, kiro, kilo, cursor). "
             "Omit to install all detected.",
    ),
    all: bool = typer.Option(False, "--all", help="Install all detected integrations."),
) -> None:
    """Install anyllm slash commands into supported AI coding CLIs."""
    from .integrations import ALL_INTEGRATIONS, detect_all, get_integration

    if name:
        integration = get_integration(name)
        if integration is None:
            keys = ", ".join(i.key for i in ALL_INTEGRATIONS)
            err_console.print(f"[red]unknown integration:[/red] {name}. Available: {keys}")
            raise typer.Exit(code=2)
        targets = [integration]
    elif all:
        targets = detect_all()
        if not targets:
            console.print("[yellow]No supported CLIs detected on this machine.[/yellow]")
            raise typer.Exit(code=0)
        console.print(f"Detected: {', '.join(t.name for t in targets)}\n")
    else:
        # No args: detect and offer to install all
        detected = detect_all()
        if not detected:
            console.print("[yellow]No supported CLIs detected. Use --all or pass a name.[/yellow]")
            raise typer.Exit(code=0)
        console.print("Detected CLIs:")
        for t in detected:
            console.print(f"  [green]✓[/green] {t.name}")
        console.print()
        targets = detected

    for integration in targets:
        try:
            integration.install()
            console.print(f"[green]✓[/green] {integration.name} integration installed")
        except Exception as e:
            err_console.print(f"[red]✗[/red] {integration.name}: {e}")


@app.command()
def uninstall(
    name: str = typer.Argument(..., help="Integration to uninstall (claude, codex, opencode, agy, kiro, kilo, cursor)."),
) -> None:
    """Uninstall anyllm slash commands from a CLI integration."""
    from .integrations import ALL_INTEGRATIONS, get_integration

    integration = get_integration(name)
    if integration is None:
        keys = ", ".join(i.key for i in ALL_INTEGRATIONS)
        err_console.print(f"[red]unknown integration:[/red] {name}. Available: {keys}")
        raise typer.Exit(code=2)

    try:
        integration.uninstall()
        console.print(f"[green]✓[/green] {integration.name} integration removed")
    except Exception as e:
        err_console.print(f"[red]✗[/red] {integration.name}: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

