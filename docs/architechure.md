# anyllm — Architecture

> *Git for LLM context. Snapshot a dying session, brief the next LLM in 30 seconds.*

---

## Overview

anyllm is a CLI tool that solves the LLM session handoff problem: when a session dies (context limit, credits, provider outage), you run `anyllm pack` + `anyllm prime`, paste the output into the next tool, and keep going — no re-explaining.
Are you on the version of Claude Code that supports .claude/commands/*.md custom slash commands, or are you using a different mechanism?
The core insight: the hard problem isn't storage, it's **distillation** (compressing 50k-token transcripts into 2k-token instructional briefings) and **cross-provider framing** (every target LLM has different formatting preferences).

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

---

## Stages

### 1. Ingestor — `src/anyllm/ingestors/`

Reads from one source, outputs a normalized `NormalizedTranscript`.

**Implemented:** `claude-code` (`ingestors/claude_code.py`)
- Reads JSONL transcripts from `~/.claude/projects/<project-slug>/*.jsonl`
- Project slug: path with `/`, `\`, `:` replaced by `-` (handles Windows paths)
- Parses user/assistant turns, tool calls (`Edit`, `Write`, `Read`, etc.), extracts files touched
- Accumulates token counts from usage fields

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
- Default model: `qwen/qwen3-coder:free` (configurable via `OPENROUTER_MODEL` env or `config.yaml`)
- Versioned system prompt: `distiller/prompts/v1.md`
- Soft input cap: 180,000 chars of rendered turns before truncation
- Offline fallback: if no API key, produces a minimal skeleton snapshot flagged low-confidence everywhere

**Output:** A markdown snapshot (YAML frontmatter + structured sections). See *Snapshot Format* below.

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
distiller_model: qwen/qwen3-coder:free
prompt_version: v1
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

- `current.md` is what `anyllm prime` reads — the canonical "what's going on now"
- `index.json` tracks all packed sessions with merge stats
- Project root is found by walking up from cwd looking for `.anyllm/`

**`config.yaml` defaults:**
```yaml
distiller:
  model: qwen/qwen3-coder:free
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
```

---

### 4. Merge Engine — `src/anyllm/merger.py`

After distillation, the new snapshot is merged into `current.md` rather than overwriting it. This is the "git for context" property — each session appends a delta.

**Decision state machine:**
- **CONFIRMED** — decision appeared in both old and new snapshots (or graph says EXTRACTED)
- **ADDED** — new decision not in previous snapshot
- **STALE** — decision absent from new snapshot; graph confidence is INFERRED or AMBIGUOUS
- **ORPHANED** — absent for `stale_threshold` sessions and graph says MISSING/AMBIGUOUS
- **SUPERSEDED** — wording changed significantly (bigram similarity < 0.85); old version archived

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

## CLI Commands — `src/anyllm/cli.py`

| Command | What it does |
|---|---|
| `anyllm init` | Creates `.anyllm/` with default `config.yaml` and `index.json` |
| `anyllm pack [--source] [--session]` | Ingest → Distill → Merge → write `current.md` |
| `anyllm prime [--target] [--copy] [--write]` | Compose + Adapt → emit briefing |
| `anyllm status` | Show `current.md` summary (task, next step, confidence report, graph info) |
| `anyllm log` | Table of all packed sessions |
| `anyllm diff <session-id>` | Print snapshot for one session |

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

## Data Flow Diagram

```
anyllm pack
    │
    ├─ ClaudeCodeIngestor.latest_session()
    │       reads ~/.claude/projects/<slug>/*.jsonl
    │       → NormalizedTranscript
    │
    ├─ storage.write_transcript()
    │       → .anyllm/sessions/<date>-<id>.transcript.json
    │
    ├─ Distiller.distill()
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
    └─ storage.append_index_entry()
            → .anyllm/index.json

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
| Default model `qwen/qwen3-coder:free` | Zero cost for initial users; swap via env var or config |
| Merge engine instead of overwrite | Accumulates project knowledge across sessions (git-like) |
| Bigram similarity (not embeddings) for decision matching | No embedding model dependency, fast, good enough for short decision strings |
| graphify is optional / subprocess-only | No hard dependency; anyllm works offline without it |
| Plain markdown for all snapshots | Hand-editable, diff-friendly, no lock-in |
| Offline fallback in distiller | `anyllm pack` never hard-fails; low-confidence skeleton better than nothing |
| `chatgpt` adapter first (not `claude`) | Cross-provider portability is the whole value proposition |
