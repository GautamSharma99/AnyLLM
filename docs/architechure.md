# anyllm — Architecture

> *Git for LLM context. Snapshot a dying session, brief the next LLM in 30 seconds.*

---

## Overview

anyllm is a CLI tool that solves the LLM session handoff problem: when a session dies (context limit, credits, provider outage), you run `anyllm pack` + `anyllm prime` (or `anyllm push`), and keep going in the next tool — no re-explaining.

The core insight: the hard problem isn't storage, it's **distillation** (compressing 50k-token transcripts into 2k-token instructional briefings) and **cross-provider framing** (every target LLM has different formatting preferences).

Slash commands (`/anyllm-pack`, `/anyllm-repack`, etc.) are Claude Code-specific conveniences. The underlying `anyllm` CLI works in any terminal.

---

## Pipeline

```
┌──────────────┐   ┌────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   Ingestor   │──▶│  Distiller │──▶│   Storage    │──▶│   Composer   │──▶│   Adapter    │
│ (per source) │   │   (LLM)    │   │  (.anyllm/)  │   │  (framing)   │   │ (per target) │
└──────────────┘   └────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
  raw transcript  →  facts/decisions → snapshot.md    → briefing JSON   → final primer
```

Five stages, each with one job. Adding a new source = new ingestor. Adding a new target = new adapter. The middle three never change.

Push adds a sixth stage (Injector) that delivers the primer directly to the target browser tab without printing it to the terminal.

---

## Stages

### 1. Ingestor — `src/anyllm/ingestors/`

Reads from one source, outputs a normalized `NormalizedTranscript`.

**Implemented:** `claude-code` (`ingestors/claude_code.py`)
- Reads JSONL transcripts from `~/.claude/projects/<project-slug>/*.jsonl`
- Project slug: path with `/`, `\`, `:` replaced by `-` (handles Windows paths)
- Parses user/assistant turns, tool calls (`Edit`, `Write`, `Read`, etc.), extracts files touched
- Accumulates token counts from usage fields
- **`since_ts` filter** — `latest_session(root, since_ts=)` and `session_by_id(root, id, since_ts=)` accept an ISO timestamp; turns at or before that timestamp are excluded. Used by `repack` to ingest only the delta since the last pack.

**Normalized transcript schema:**
```json
{
  "source": "claude-code",
  "session_id": "abc123",
  "started_at": "...",
  "ended_at": "...",
  "turns": [
    { "role": "user", "text": "...", "ts": "..." },
    { "role": "assistant", "text": "...", "tool_calls": [...], "ts": "..." }
  ],
  "files_touched": ["src/auth.py"],
  "metadata": { "model": "claude-sonnet-4-6", "token_count": 48230 }
}
```

**Planned:** `chatgpt` (export ZIPs), `cursor` (SQLite), `clipboard` (paste-in fallback).

---

### 2. Distiller — `src/anyllm/distiller/`

The brain. Calls an LLM to compress the transcript into a structured snapshot.

**Implementation:** `distiller/distiller.py`
- Uses OpenRouter API via the `openai` SDK (compatible base URL)
- Default model: `gpt-4o-mini` (configurable via `OPENROUTER_MODEL`/`OPENAI_MODEL` env or `config.yaml`)
- Priority: `OPENROUTER_API_KEY` → `OPENAI_API_KEY` → offline fallback
- Soft input cap: 180,000 chars of rendered turns before truncation
- Offline fallback: if no API key, produces a minimal skeleton snapshot flagged low-confidence everywhere
- **`prompt_version` param** — `distill(transcript, project, prompt_version="v1-delta")` loads an alternate system prompt from `distiller/prompts/<version>.md` at call time. Used by `repack`.

**Versioned system prompts:**

| File | Used by | Purpose |
|---|---|---|
| `prompts/v1.md` | `pack` | Full session distillation — all sections required |
| `prompts/v1-delta.md` | `repack` | Delta distillation — only what changed since last pack; sections may be sparse; Task section omitted if unchanged |

**Frontmatter the distiller emits:**
```yaml
anyllm_version: "0.1"
project: <name>
generated_at: <ISO timestamp>
distilled_from:
  - source: claude-code
    session_id: <id>
    turn_count: 37
    token_count: 12000
budget_tokens: 2000
distiller_model: gpt-4o-mini
prompt_version: v1          # or v1-delta for repack
```

---

### 3. Storage — `src/anyllm/storage.py` + `.anyllm/`

Plain files. No database. All formats are markdown or JSON — hand-editable by design.

```
.anyllm/
├── config.yaml                                          # project settings
├── index.json                                           # session log
├── current.md                                           # rolling project snapshot
└── sessions/
    ├── 2026-06-29-<id>.transcript.json                  # normalized raw
    └── 2026-06-29-<id>.snapshot.md                      # distilled
```

- `current.md` is what `anyllm prime` and `anyllm push` read — the canonical "what's going on now"
- `index.json` tracks all packed sessions with merge stats; entries are never deleted
- Project root found by walking up from cwd looking for `.anyllm/`

**Key functions:**
- `get_last_pack_entry(paths)` — returns the most recent entry from `index.json` (used by `repack` to get `since_ts`)
- `append_index_entry(paths, entry)` — deduplicates by `(source, session_id)` for normal packs; entries with `"type": "repack"` are always appended without dedup

**`index.json` entry schemas:**

Pack entry:
```json
{
  "source": "claude-code",
  "session_id": "abc123",
  "started_at": "...",
  "ended_at": "...",
  "last_turn_ts": "...",
  "turn_count": 40,
  "token_count": 12000,
  "snapshot_path": ".anyllm/sessions/2026-06-29-abc123.snapshot.md",
  "transcript_path": ".anyllm/sessions/2026-06-29-abc123.transcript.json",
  "packed_at": "2026-06-29T14:00:00Z",
  "merge": { "confirmed": 3, "added": 1, "stale": 0, "orphaned": 0 }
}
```

Repack entry:
```json
{
  "type": "repack",
  "source": "claude-code",
  "session_id": "abc123",
  "since_ts": "2026-06-29T13:58:22Z",
  "turns_ingested": 3,
  "packed_at": "2026-06-29T15:00:00Z",
  "last_turn_ts": "...",
  "merge": { "confirmed": 0, "added": 1, "stale": 1, "orphaned": 0 }
}
```

**`config.yaml` defaults:**
```yaml
distiller:
  model: gpt-4o-mini
  budget_tokens: 2000
targets:
  default: chatgpt
framing:
  extra_rules: []
  tone: direct
merge:
  enabled: true
  graphify_graph: graphify-out/graph.json
  graphify_timeout: 30
  stale_threshold: 3
  auto_update_graph: true
push:
  browser: auto              # auto | chrome | arc | firefox | safari
  codex_url: https://codex.openai.com
  send_delay_ms: 500
  open_if_missing: true
```

---

### 4. Merge Engine — `src/anyllm/merger.py`

After distillation, the new snapshot is merged into `current.md` rather than overwriting it. Both `pack` and `repack` go through the same merge path — the delta snapshot from `repack` is indistinguishable from any other snapshot at this stage.

**Decision state machine:**
- **CONFIRMED** — decision appeared in both old and new snapshots (or graph says EXTRACTED)
- **ADDED** — new decision not in previous snapshot
- **UPDATED** — wording changed significantly (bigram similarity < 0.85); old version archived as Superseded
- **STALE** — decision absent from new snapshot; graph confidence is INFERRED or AMBIGUOUS
- **ORPHANED** — absent for `stale_threshold` sessions and graph says MISSING/AMBIGUOUS

**Matching algorithm:** Jaccard bigram similarity on normalized decision text.
- Threshold: 0.55 (text-only) or 0.40 (when code anchors match)
- Code anchor extracted from backtick-quoted paths/symbols in decision text

**Failed Approaches and Open Questions** are always unioned across sessions (never dropped).

**Frontmatter written to `current.md`:**
```yaml
merged_from: [<session_ids>]
confidence_report:
  confirmed: 3
  added: 1
  stale: 0
  orphaned: 0
decision_provenance:
  <anchor_or_id>:
    introduced: <session_id>
    confirmed_in: [<session_ids>]
    sessions_absent: 0
    confidence: EXTRACTED
```

---

### 5. Graph Bridge — `src/anyllm/graph_bridge.py`

Optional integration with `graphify` (separate CLI, not a hard dependency).

- Checks if `graphify` is on PATH at runtime; no-ops cleanly if not installed
- `update_graph()` — runs `graphify extract <path> --update` (incremental)
- `query_node_confidence()` — runs `graphify query <anchor> --graph <path> --json`
  - Returns: `EXTRACTED` | `INFERRED` | `AMBIGUOUS` | `MISSING`
- Graph confidence feeds the merge engine's decision state machine

---

### 6. Composer — `src/anyllm/composer.py`

Turns the raw snapshot facts into an adapter-agnostic **briefing JSON** by adding instructional framing.

Adds:
- **Role preamble** — "You are continuing an existing coding task..."
- **Anti-repetition guards** — "Do NOT restart. Do NOT re-implement completed parts."
- **Verification hooks** — flags low-confidence sections for human/LLM verification
- **User rules** from `config.yaml` (`extra_rules`, `tone`)

Also enriches with graph context if a graphify graph is available (`graph_context.py`).

Output is a structured dict — one representation, many adapter renderings.

---

### 7. Adapter — `src/anyllm/adapters/`

Each adapter takes the composed briefing JSON and renders it for one target.

**Implemented:** `chatgpt` — markdown with explicit role framing, `## Context` / `## Decisions` / `## Your task` structure.

**Planned:** `claude` (MEMORY.md-shaped, XML tags), `cursor` (.cursorrules), `generic` (plain text).

---

### 8. Injector — `src/anyllm/injectors/`

Platform-aware browser automation layer used by `anyllm push`. Delivers the briefing directly into the Codex browser tab without ever printing it to the terminal.

**Factory:** `injectors/__init__.py`
- `detect_platform()` → `linux_x11` | `linux_wayland` | `macos` | `windows`
- `get_injector(platform)` → returns the right injector instance

**Interface (all injectors implement):**
- `focus_target(target, push_cfg)` — find and focus the Codex browser window; returns `True` if found
- `open_url(url)` — open URL in default browser
- `inject_and_send(briefing, delay_ms)` — paste briefing text and send

**Platform implementations:**

| File | Mechanism |
|---|---|
| `injectors/windows.py` | `ctypes` Win32 `EnumWindows`/`SetForegroundWindow`; `pyperclip` for clipboard; `keybd_event` for Ctrl+V + Enter |
| `injectors/macos.py` | `osascript` to enumerate browser windows by URL; `pyperclip` + `keystroke "v"` AppleScript |
| `injectors/linux_x11.py` | `xdotool search/windowfocus/type/key` |
| `injectors/linux_wayland.py` | `ydotool type/key` (requires `ydotoold` daemon) |

**Window detection order:**
1. Search open windows for title containing `codex` or `openai`
2. If not found and `open_if_missing: true` → open `codex_url`, wait 3s, retry focus
3. If still not found → print error to stderr, exit

**Silence guarantee:** the briefing string is held in memory and passed directly to the injector. It is never written to stdout or shown in the Claude Code terminal.

---

### 9. Push — `src/anyllm/push.py`

Orchestrates the push flow:

```
push(paths, config)
  └─ _compose_briefing()   # reads current.md → adapter primer (never printed)
  └─ detect_platform()
  └─ get_injector()
  └─ injector.focus_target()
      └─ if not found and open_if_missing: injector.open_url() → sleep(3) → retry
  └─ injector.inject_and_send(briefing, delay_ms)
  └─ print("✓ pushed to Codex")    # only this line appears in terminal
```

---

## CLI Commands — `src/anyllm/cli.py`

| Command | What it does |
|---|---|
| `anyllm init` | Create `.anyllm/` with default `config.yaml` and `index.json` |
| `anyllm pack [--source] [--session]` | Ingest → Distill (v1) → Merge → write `current.md` |
| `anyllm repack [--source]` | Ingest delta since last pack → Distill (v1-delta) → Merge → update `current.md` |
| `anyllm push` | Compose briefing silently → find Codex tab → paste + Enter |
| `anyllm prime [--target] [--copy] [--write]` | Compose + Adapt → emit briefing to stdout / clipboard / file |
| `anyllm status` | Show `current.md` summary (task, next step, confidence report, graph info) |
| `anyllm log` | Table of all packed sessions with `type` (pack/repack), turns, decisions |
| `anyllm diff <session-id>` | Print snapshot for one session |

### Slash commands (Claude Code only)

Stored in `~/.claude/commands/`. Zero Claude tokens — `disable-model-invocation: true` on all.

| Slash command | Runs |
|---|---|
| `/anyllm-init` | `anyllm init` |
| `/anyllm-pack` | `anyllm pack $ARGUMENTS` |
| `/anyllm-repack` | `anyllm repack $ARGUMENTS` |
| `/anyllm-push` | `anyllm push $ARGUMENTS` |
| `/anyllm-prime` | `anyllm prime $ARGUMENTS` |
| `/anyllm-status` | `anyllm status` |

---

## Snapshot Format (v0.1)

Versioned markdown. Boring on purpose — meant to become a standard.

```markdown
---
anyllm_version: "0.1"
project: myproject
generated_at: 2026-06-29T12:00:00Z
# ... (merge metadata after first merge)
---

# Task
<one paragraph: what the user is trying to accomplish>

# Status
<what's done, what's in progress>

# Decisions
- <decision>. **Why:** <rationale>. _conf: high_

# Code map
- `path/to/file.py` — what it does

# Tried & failed
- <approach> — failed because <reason>. Don't redo.

# Next step
<one concrete action>

# Open questions
- <question>

# Confidence Report
- Overall: medium
- High confidence: task, decisions, next step
- Low confidence: code map (some files inferred)
```

---

## Data Flow Diagrams

### `anyllm pack`

```
anyllm pack
    │
    ├─ ClaudeCodeIngestor.latest_session(root)
    │       reads ~/.claude/projects/<slug>/*.jsonl (most recent by mtime)
    │       → NormalizedTranscript
    │
    ├─ storage.write_transcript()
    │       → .anyllm/sessions/<date>-<id>.transcript.json
    │
    ├─ Distiller.distill(transcript, project)            # prompt: v1.md
    │       → POST openrouter.ai/api/v1/chat/completions
    │       → snapshot markdown
    │
    ├─ storage.write_snapshot()
    │       → .anyllm/sessions/<date>-<id>.snapshot.md
    │
    ├─ [if merge.enabled]
    │   ├─ graph_bridge.update_graph()   (optional, if graphify installed)
    │   └─ MergeEngine.merge(prev_current, new_snapshot)
    │           → MergeResult (confirmed, added, stale, orphaned, merged_md)
    │           → .anyllm/current.md
    │
    └─ storage.append_index_entry()      # type: pack, includes last_turn_ts
            → .anyllm/index.json
```

### `anyllm repack`

```
anyllm repack
    │
    ├─ storage.get_last_pack_entry()
    │       reads last entry from index.json
    │       → { session_id, last_turn_ts, ... }
    │
    ├─ ClaudeCodeIngestor.session_by_id(root, session_id, since_ts=last_turn_ts)
    │       re-reads same JSONL, filters turns where ts > last_turn_ts
    │       → NormalizedTranscript (delta only)
    │
    │   if transcript.turns == [] → exit "Nothing to repack"
    │
    ├─ Distiller.distill(transcript, project, prompt_version="v1-delta")
    │       → delta snapshot markdown (sparse sections OK)
    │
    ├─ [if merge.enabled]
    │   └─ MergeEngine.merge(prev_current, delta_snapshot)
    │           → updates current.md in place
    │
    └─ storage.append_index_entry()      # type: repack, includes since_ts + turns_ingested
            → .anyllm/index.json         # no dedup — both pack + repack entries are kept
```

### `anyllm push`

```
anyllm push
    │
    ├─ compose_briefing(paths, config)
    │       parse_snapshot(current.md) → compose() → adapter.render()
    │       briefing string held in memory, never printed
    │
    ├─ detect_platform()      # win32 | macos | linux_x11 | linux_wayland
    ├─ get_injector(platform)
    │
    ├─ injector.focus_target("codex", push_cfg)
    │       windows: ctypes EnumWindows → SetForegroundWindow
    │       macos:   osascript enumerate windows by URL
    │       linux:   xdotool search --name codex
    │       if not found and open_if_missing → open_url(codex_url) → sleep(3) → retry
    │
    ├─ injector.inject_and_send(briefing, delay_ms=500)
    │       windows: pyperclip.copy() → keybd_event(Ctrl+V) → keybd_event(Enter)
    │       macos:   pyperclip.copy() → osascript keystroke "v" → key code 36
    │       linux:   xdotool type -- <briefing> → xdotool key Return
    │
    └─ print("✓ pushed to Codex")     # only terminal output
```

### `anyllm prime`

```
anyllm prime
    │
    ├─ parse_snapshot(current.md)
    ├─ compose(snapshot, target, extra_rules, tone)
    │       → briefing JSON (adapter-agnostic)
    ├─ [if graphify graph exists] graph_context.enrich_briefing()
    └─ ChatGPTAdapter.render(briefing)
            → markdown primer → stdout / clipboard / file
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| OpenRouter for distillation (not direct Anthropic/OpenAI) | One API key, model-agnostic, free tier available |
| Default model `gpt-4o-mini` | Fast and cheap; swap via env var or config |
| `v1-delta` prompt for repack | Full-session prompt on 3 turns produces waffle; delta prompt produces sparse, accurate output that merges cleanly |
| `since_ts` filter in ingestor (not a separate file) | The JSONL file is append-only; filtering in-process avoids stale transcript copies |
| Repack entries not deduplicated in index.json | Both the original pack and all repacks are preserved as a complete audit trail |
| Merge engine used for both pack and repack | No special-casing needed; the merge engine doesn't care whether the incoming snapshot is a full distillation or a delta |
| `ctypes` for Windows window focus (not pywin32) | No extra pip dependency for the most common case; pywin32 available as `[push]` optional extra |
| Push briefing never touches stdout | Claude Code captures stdout for context; printing the briefing would leak it back into the Claude context, breaking the "0 token" contract |
| Plain markdown for all snapshots | Hand-editable, diff-friendly, no lock-in |
| Offline fallback in distiller | `anyllm pack` never hard-fails; low-confidence skeleton better than nothing |
| `chatgpt` adapter first (not `claude`) | Cross-provider portability is the whole value proposition |
