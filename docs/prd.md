# PRD: anyllm v2 — Universal LLM Context Transfer

**Version:** 2.0  
**Status:** Ready for Implementation  
**Project:** anyllm  
**Scope:** Full platform — universal ingestion, confidence-aware merging, universal delivery

---

## 1. Vision

A session that starts in Claude Code should be continuable in Codex, ChatGPT web, Cursor, Gemini, a local Ollama instance, or a fresh tab — in under 30 seconds, with zero re-explanation.

anyllm v2 is the infrastructure layer that makes that possible. It is three things:

- **A universal ingestor** — reads sessions from every major LLM surface (Claude Code, Codex CLI, ChatGPT export, Gemini, Cursor, raw markdown, any custom JSONL)
- **A confidence-aware merge engine** — accumulates project knowledge across sessions, never clobbers, verifies against the actual codebase
- **A universal delivery layer** — renders the briefing in the exact idiom of wherever you're going next: system prompt, paste block, MCP tool payload, slash command, URL share

The `.anyllm/` directory is the artifact. It belongs in your repo. It is the single source of truth for what this project knows, what it tried, and what's next.

---

## 2. Problem Statement

### 2.1 The Context Transfer Tax

Every time a developer switches LLM surfaces — different model, full context window, different tool — they pay the same tax:

- 5–15 minutes re-explaining architecture decisions already made
- The new model re-explores closed questions, suggests things already tried
- High-confidence decisions ("we use CQRS here, the DB is Postgres, auth lives in `auth.py`") are indistinguishable from uncertain observations
- Work done in one tool (architecture in ChatGPT, implementation in Cursor, review in Claude) is siloed by interface

This is not a minor inconvenience. On a complex project spanning multiple sessions and tools, this tax compounds into hours per week.

### 2.2 What the MVP Got Right (and Wrong)

The MVP's distill → prime pipeline is correct as a concept. Its gaps:

- **One ingestor only** (Claude Code JSONL). ChatGPT, Codex CLI, Cursor, Gemini, raw transcripts — all excluded.
- **Clobbers history** on every `pack`. Three-session-old decisions silently disappear.
- **One adapter only** (ChatGPT paste). No Cursor integration, no Codex system prompt, no MCP payload, no shareable link.
- **No web interface**. The CLI-only surface blocks the majority of users who use LLMs via browser.
- **No real-time capture**. You can only pack after a session ends, not capture in-flight.

### 2.3 The Full Problem Space

```
WHERE CONTEXT LIVES             WHERE YOU WANT TO GO
─────────────────────           ────────────────────
Claude Code (JSONL)     ──┐     ChatGPT web (paste block)
Codex CLI (JSONL)       ──┤     Codex CLI (system prompt flag)
ChatGPT (export JSON)   ──┤     Cursor (Rules file / chat inject)
Gemini (export)         ──┤     Claude Code (CLAUDE.md + /prime)
Cursor chat             ──┤     Gemini (system instruction)
Raw transcript (.md)    ──┤     Windsurf (rules)
Manual paste            ──┤     Local Ollama / LM Studio
Browser conversation    ──┤     Any future model
API session             ──┘     Team member (shared workspace)
```

anyllm v2 covers every cell in this matrix.

---

## 3. Goals

- **G1** — Ingest sessions from all major LLM surfaces with a pluggable ingestor interface
- **G2** — Accumulate project knowledge across sessions without ever clobbering history
- **G3** — Deliver briefings in the exact format each target model expects — not a generic paste
- **G4** — Work from CLI, from browser, and optionally as a background daemon
- **G5** — Support team context sharing so collaborators join mid-session without a catch-up call
- **G6** — Degrade gracefully: every feature optional, core always works offline

---

## 4. Non-Goals

- Not a general-purpose conversation manager or chat client
- Not a vector database or RAG pipeline (embeddings are an optimization, not a requirement)
- Not a billing or model-routing layer (use existing LLM proxies for that)
- Not an IDE plugin in v2 (browser extension and MCP integration cover the use case)

---

## 5. Architecture Overview

### 5.1 Layer Map

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI / Web UI / Daemon                   │
├──────────────────┬──────────────────┬───────────────────────┤
│   INGESTOR LAYER │   CORE ENGINE    │    DELIVERY LAYER     │
│                  │                  │                       │
│  ClaudeCode      │  Normalizer      │  ChatGPT adapter      │
│  Codex           │  Distiller       │  Codex adapter        │
│  ChatGPT export  │  Merger          │  Cursor adapter       │
│  Gemini export   │  GraphBridge     │  Claude adapter       │
│  Cursor export   │  Storage         │  Gemini adapter       │
│  Raw markdown    │                  │  Ollama adapter       │
│  Browser ext.    │                  │  MCP adapter          │
│  Manual paste    │                  │  ShareLink adapter    │
│  Custom JSONL    │                  │  Raw adapter          │
└──────────────────┴──────────────────┴───────────────────────┘
                            │
                    .anyllm/
                    ├── current.md          (merged knowledge)
                    ├── sessions/           (raw + distilled)
                    ├── graph.json          (codebase graph)
                    └── config.yaml
```

### 5.2 Data Flow

```
Session source
    │
    ▼
Ingestor.normalize() → NormalizedTranscript
    │
    ▼
Distiller.distill()  → Snapshot { task, decisions, code_map, failed, next, questions }
    │
    ▼
GraphBridge.update() → graph confidence for each decision's code anchor
    │
    ▼
Merger.merge()       → MergeResult { confirmed, added, stale, orphaned }
    │
    ▼
Storage.save()       → .anyllm/current.md  (merged, never clobbered)
    │
    ▼
Adapter.render()     → briefing string in target-model idiom
    │
    ▼
Delivery: clipboard / file / URL / MCP payload / system prompt flag
```

---

## 6. Ingestor Layer (Universal Ingestion)

### 6.1 Interface

Every ingestor implements:

```python
class BaseIngestor:
    source_id: str            # "claude-code", "codex", "chatgpt-export", etc.
    display_name: str

    def detect(self, path: str | None) -> bool:
        """Return True if this ingestor can handle the given path/env."""

    def ingest(self, path: str | None) -> NormalizedTranscript:
        """
        Return a NormalizedTranscript regardless of source format.
        Raise IngestError if the source cannot be read.
        """
```

```python
@dataclass
class NormalizedTranscript:
    session_id: str
    source: str                    # ingestor source_id
    started_at: datetime
    ended_at: datetime
    turns: list[Turn]              # list of {role, content, timestamp}
    metadata: dict                 # source-specific extras
```

`anyllm pack` runs ingestor auto-detection unless `--source` is specified. Detection order is defined in `config.yaml` under `ingestors.priority`.

### 6.2 Ingestor Catalog

#### 6.2.1 `claude-code` (MVP, carry forward)

- Source: `~/.claude/projects/<hash>/*.jsonl`
- Selection: most recently modified file
- Turn extraction: parse JSONL lines with `role: human | assistant`, extract `content[].text`
- Tool use turns: include as assistant turns with `[TOOL USE: <tool_name>]` prefix — they carry context

#### 6.2.2 `codex` (new)

- Source: `~/.codex/sessions/*.jsonl` (OpenAI Codex CLI default path) or path override
- Format: same JSONL schema as Claude Code with minor field differences (`role: user | assistant`)
- Detection: check for `~/.codex/` directory or `--source codex`
- Note: Codex CLI session format is not publicly documented — include a `--raw-dump` flag that accepts any JSONL with `role`/`content` fields as a fallback

#### 6.2.3 `chatgpt-export` (new)

- Source: `conversations.json` from ChatGPT Settings → Export Data
- Format: array of conversation objects, each with `mapping` (tree of nodes)
- Flattening: DFS traversal of node tree, `message.author.role` = `user | assistant | tool`
- Selection: `--conversation-id <id>` or most recent by `create_time`
- Multi-conversation support: `--all` flag packs all conversations into one transcript (useful for research threads)

#### 6.2.4 `gemini-export` (new)

- Source: Google Takeout `Gemini Apps Activity/` folder
- Format: JSON array of activity items with `content.parts[].text`
- Note: Gemini export format may change — wrap in a version-detected parser, warn if unknown schema version

#### 6.2.5 `cursor` (new)

- Source: `~/.cursor/User/workspaceStorage/<hash>/state.vscdb` (SQLite)
- Table: `ItemTable` where key = `aiChat.conversations`
- Extraction: JSON-parse the value, extract `conversation[].bubbles[].rawText`
- Detection: check for `.cursor/` in `~` or `--source cursor`
- Caveat: Cursor stores full conversation in SQLite with no official export API — this is reverse-engineered and may break on Cursor version updates. Include a `cursor-version` config key and a `--dry-run` mode that dumps raw SQL output for debugging.

#### 6.2.6 `windsurf` (new)

- Source: `~/.codeium/windsurf/User/workspaceStorage/<hash>/state.vscdb`
- Same SQLite schema as Cursor (both are VS Code forks)
- Detection: check for `.codeium/windsurf/` in `~`

#### 6.2.7 `raw-markdown` (new)

- Source: any `.md` file passed via `--source raw-markdown --path <file>`
- Parsing: treat lines starting with `**User:**`, `**Human:**`, `You:` as user turns; `**Assistant:**`, `**Claude:**`, `GPT:`, `Gemini:` as assistant turns — configurable via `ingestors.raw_markdown.user_prefixes` and `assistant_prefixes`
- Fallback: if no role markers detected, treat the entire file as a single assistant turn (useful for pasting raw output)

#### 6.2.8 `custom-jsonl` (new)

- Source: any JSONL file with `--source custom-jsonl --path <file>`
- Schema: `{"role": "user|assistant", "content": "..."}` per line (same as OpenAI message format)
- This is the universal escape hatch for any source not explicitly supported

#### 6.2.9 `browser-extension` (new, v2.1)

- Source: HTTP POST from browser extension to local `anyllm daemon` on port 7723
- Payload: `{source: "browser", url: "...", turns: [...], captured_at: "..."}`
- Use case: capture a ChatGPT, Claude.ai, or Gemini conversation directly from the browser without needing an export file
- The extension injects a "Capture to anyllm" button on supported chat UIs

#### 6.2.10 `api-session` (new, v2.1)

- Source: any code that calls the anyllm Python SDK or REST API with turns
- Use case: pack sessions from LLM wrappers, LangChain runs, custom agent loops
- SDK: `anyllm.pack_session(turns=[...], metadata={...})`

### 6.3 Ingestor Selection Logic

```
anyllm pack
    │
    ├── --source <id> specified?  → use that ingestor
    │
    └── auto-detect (in priority order from config):
            1. claude-code     (check ~/.claude/projects/)
            2. codex           (check ~/.codex/sessions/)
            3. cursor          (check ~/.cursor/User/workspaceStorage/)
            4. windsurf        (check ~/.codeium/windsurf/)
            5. chatgpt-export  (check ./conversations.json in CWD)
            6. gemini-export   (check ./Gemini\ Apps\ Activity/ in CWD)
            7. raw-markdown    (requires --path)
            8. custom-jsonl    (requires --path)
```

If no ingestor matches, print a clear error with detected paths and suggest `--source` flag.

---

## 7. Merge Engine (Unchanged from PRD v1.0, Included for Completeness)

See PRD v1.0 §4–5 for full specification. Summary:

- Every `pack` merges new snapshot into existing `current.md` — never overwrites
- Decision state machine: CONFIRMED / ADDED / STALE / ORPHANED
- `Failed Approaches` and `Open Questions` sections never get dropped — union across all sessions
- `graph_bridge.py` wraps graphify CLI for code anchor verification
- Graceful degradation: absent graphify, all non-mentioned decisions go STALE (not ORPHANED)
- `merged_from` frontmatter field tracks provenance across sessions

The merge engine is source-agnostic. It operates on `NormalizedTranscript` regardless of where it came from.

---

## 8. Adapter Layer (Universal Delivery)

### 8.1 Interface

```python
class BaseAdapter:
    target_id: str             # "chatgpt", "codex", "cursor", etc.
    display_name: str

    def render(
        self,
        snapshot: Snapshot,
        merge_result: MergeResult,
        config: AdapterConfig,
    ) -> RenderedBriefing:
        """
        Produce a briefing in the target model's exact expected format.
        """

@dataclass
class RenderedBriefing:
    primary: str               # main content to deliver
    secondary: str | None      # e.g., a system prompt section separate from user turn
    delivery_method: str       # "paste" | "file" | "flag" | "url" | "mcp" | "api"
    instructions: str          # human-readable: "Paste this into the system prompt box"
    metadata: dict
```

### 8.2 Adapter Catalog

#### 8.2.1 `chatgpt` (MVP, update)

- **Format:** A single paste block. Starts with a role assertion (`You are continuing work on <project>.`), followed by the full briefing in Markdown.
- **Anti-repetition guards:** Prepend `Do not re-propose the following approaches, as they have already been tried and rejected:` before the Failed Approaches section.
- **Delivery:** `--copy` copies to clipboard. `--write` saves to file. No new changes from MVP beyond richer content.
- **Custom GPT variant:** `--variant custom-gpt` wraps in the Custom GPT system prompt format with the briefing as a Knowledge file attachment instruction.

#### 8.2.2 `codex` (new)

- **Format:** A system prompt string suitable for `codex --system-prompt "..."` flag or `~/.codex/instructions.md`.
- **Key differences from ChatGPT adapter:** more terse, action-oriented, no prose framing. Codex is optimized for code tasks, not explanation.
- **Delivery:** `--copy` for clipboard, `--write ~/.codex/instructions.md` to write directly to Codex system prompt file, `--flag` to print the exact CLI invocation with `--system-prompt` inline.

```
anyllm prime --target codex --flag

→ Prints:
codex --system-prompt "$(cat .anyllm/prime-codex.md)" <your prompt here>
```

#### 8.2.3 `cursor` (new)

- **Format:** Cursor `.cursorrules` file content OR a chat inject string.
- **`.cursorrules` variant (default):** Writes the briefing as a project rule. `anyllm prime --target cursor --write .cursorrules`
- **Chat inject variant:** `--variant chat` produces a paste block for the Cursor chat panel, starting with `@codebase context:` to trigger Cursor's codebase-awareness.
- **Delivery:** Write to `.cursorrules` in project root or copy for paste.

#### 8.2.4 `windsurf` (new)

- **Format:** `.windsurfrules` file — identical schema to `.cursorrules`.
- **Delivery:** `anyllm prime --target windsurf --write .windsurfrules`

#### 8.2.5 `claude` (new — Claude Code / Claude.ai)

Two sub-variants:

**`claude-code` variant:**
- Writes to `CLAUDE.md` in project root (Claude Code's native context file)
- Includes a custom slash command registration block: `## Custom Commands\n/prime: Resume from anyllm context`
- `anyllm prime --target claude --variant claude-code --write CLAUDE.md`

**`claude-web` variant:**
- Paste block for claude.ai web UI
- Includes a "Project Knowledge" framing for Claude's Projects feature
- If the user has a Claude Project, the briefing is formatted as a Project context document

#### 8.2.6 `gemini` (new)

- **Format:** System instruction string for Gemini Advanced or Gemini API
- **Gemini Advanced (web):** Paste block with `[System instruction]:` prefix — Gemini web UI accepts this in the conversation
- **Gemini API variant:** `--variant api` produces a Python snippet with the briefing as `system_instruction` parameter
- **Delivery:** Copy or write to file

#### 8.2.7 `ollama` / `lm-studio` (new)

- **Format:** Modelfile `SYSTEM` block (Ollama) or system prompt field (LM Studio)
- **Ollama:** `anyllm prime --target ollama --model llama3` writes a temporary Modelfile and prints `ollama create anyllm-session -f ./Modelfile && ollama run anyllm-session`
- **LM Studio:** `--variant lm-studio` produces a JSON object matching LM Studio's preset format
- **Token budget:** Local models often have smaller context windows. Include a `--budget <tokens>` flag that truncates the briefing with an explicit priority order: Task > Status > Decisions (CONFIRMED only) > Next Step > Code Map > Open Questions

#### 8.2.8 `mcp` (new)

- **Format:** A JSON payload suitable for injection via an MCP tool call
- **Use case:** Agents and automated pipelines that need to prime a model programmatically
- **Schema:** `{"role": "system", "content": "<briefing>"}` — can be directly inserted into an MCP `messages` array
- **Delivery:** `--write prime.json` or pipe to stdout for scripting: `anyllm prime --target mcp | jq .`

#### 8.2.9 `share-link` (new, requires anyllm Cloud or self-hosted relay)

- **Use case:** Send context to a teammate without them having the `.anyllm/` directory
- **Format:** A short URL (`anyllm.sh/p/<id>`) that renders the briefing as a web page with copy buttons per target model
- **The share page:** Shows the task, decisions, next step, and per-model "Copy for [Model]" buttons — the teammate clicks the button for their tool and pastes
- **Privacy:** Share links are ephemeral (24h default, configurable) and single-use by default
- **Self-hosted:** `anyllm prime --target share-link --relay https://your-relay.example.com`

#### 8.2.10 `raw` (new)

- **Format:** The raw merged `current.md` with no adapter framing
- **Use case:** Piping into scripts, reading in CI, feeding into custom tooling
- **Delivery:** stdout only — `anyllm prime --target raw`

### 8.3 Adapter Config in `config.yaml`

```yaml
adapters:
  chatgpt:
    max_tokens: 3000
    anti_repetition_guards: true
    failed_approaches_prefix: "Do not re-propose the following:"

  codex:
    max_tokens: 2000
    style: terse          # terse | verbose
    include_code_map: true

  cursor:
    default_variant: rules  # rules | chat
    rules_file: .cursorrules

  claude:
    default_variant: claude-code
    claude_md_file: CLAUDE.md

  ollama:
    default_model: llama3
    budget_tokens: 4096
    priority_order:
      - task
      - decisions_confirmed
      - next_step
      - code_map
      - open_questions

  share_link:
    relay_url: "https://anyllm.sh"
    ttl_hours: 24
    single_use: true
```

---

## 9. Delivery Mechanisms

### 9.1 CLI Flags

```
anyllm prime
  --target <adapter>        # required; chatgpt | codex | cursor | windsurf | claude |
                            #           gemini | ollama | mcp | share-link | raw
  --variant <name>          # optional; adapter-specific sub-format
  --copy                    # copy to system clipboard (uses pyperclip)
  --write <path>            # write to file (path can be . for adapter default)
  --flag                    # print the full CLI invocation for the target tool
  --budget <n>              # max tokens in output (truncates with priority order)
  --share                   # shorthand for --target share-link
  --dry-run                 # print output, don't write or copy
```

### 9.2 Browser Extension (v2.1)

A lightweight extension for Chrome and Firefox that:

- Detects you're on a supported chat UI (chat.openai.com, claude.ai, gemini.google.com, cursor.sh)
- Adds an "anyllm" button to the conversation header
- **Capture mode:** Sends the current conversation to the local daemon (`localhost:7723/capture`) for packing
- **Prime mode:** Fetches the current project's briefing from the daemon and injects it into the new conversation input box
- **Auth:** The extension authenticates to the daemon via a local token stored in the extension storage (not transmitted externally)

The daemon must be running: `anyllm daemon --port 7723`

### 9.3 Daemon Mode

```bash
anyllm daemon [--port 7723] [--project-root <path>]
```

Runs a lightweight HTTP server that:

- `POST /capture` — accepts a session payload and runs the full pack pipeline
- `GET /prime?target=<adapter>` — returns the rendered briefing for the target
- `GET /status` — returns current project status JSON
- `POST /pack` — triggers a manual pack (same as CLI `anyllm pack`)
- `GET /health` — for extension connectivity check

The daemon is optional. CLI and file-based workflows work without it.

### 9.4 Python SDK (v2.1)

```python
import anyllm

# Pack a session from code
anyllm.pack_session(
    turns=[
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "..."},
    ],
    source="my-agent",
    project_root="./my-project",
)

# Get a briefing for the next model
briefing = anyllm.prime(target="codex", project_root="./my-project")
print(briefing.primary)
```

---

## 10. Web UI (New)

A browser-based interface for users who don't use the CLI. Served by the daemon.

**URL:** `localhost:7723/ui` when daemon is running, or hosted at `anyllm.sh/ui` for cloud users.

### 10.1 Pages

**Dashboard** (`/`)
- Current task, status, session count
- Decision summary: N confirmed, N stale, N orphaned
- "Pack latest session" button (with source auto-detect)
- "Prime for model" dropdown with one-click copy per target

**Session Log** (`/log`)
- Table of all sessions: timestamp, source model, decision deltas
- Click a session → diff view (what was added/confirmed/orphaned in that session)

**Briefing Studio** (`/prime`)
- Select target model from a visual grid (logos of ChatGPT, Codex, Cursor, Claude, Gemini, etc.)
- Preview the rendered briefing before copying
- Token count indicator with budget slider
- Copy button / Download button / Share Link button

**Manual Pack** (`/pack`)
- Paste a transcript directly into a textarea
- Select source format
- Pack and see the merge result in real time

**Settings** (`/settings`)
- All `config.yaml` options exposed as form fields
- graphify integration status
- Share link relay configuration

---

## 11. Team Context Sharing

### 11.1 Problem

Two developers on the same project. Developer A did three sessions of architecture work. Developer B needs to implement. Currently: Developer A manually summarizes in Slack. Half the context is lost.

### 11.2 Solution: `anyllm push` / `anyllm pull`

```bash
# Developer A — after packing sessions
anyllm push --workspace my-team/my-project

# Developer B — before starting
anyllm pull --workspace my-team/my-project
anyllm prime --target cursor --write .cursorrules
```

`push` syncs the `.anyllm/` directory to a shared workspace (self-hosted relay or anyllm Cloud). `pull` fetches it.

The workspace is keyed by `--workspace <org>/<project>`. Access is controlled by a shared token in `config.yaml` under `team.workspace_token`.

### 11.3 Sharing Model

- `current.md` is always the source of truth
- Push is non-destructive: the remote merges the incoming `current.md` with whatever is already there using the same merger engine
- Pull is non-destructive: local `current.md` is merged with the remote, not overwritten
- `anyllm status --remote` shows the remote's merge state before pulling

### 11.4 Share Link (Single Use, Ephemeral)

Described in §8.2.9 above. For quick handoffs without workspace setup.

---

## 12. Configuration Reference

```yaml
# .anyllm/config.yaml

project:
  name: "my-api"
  root: "."

ingestors:
  priority:
    - claude-code
    - codex
    - cursor
    - windsurf
    - chatgpt-export
    - gemini-export
  claude_code:
    session_dir: "~/.claude/projects"
  codex:
    session_dir: "~/.codex/sessions"
  cursor:
    workspace_storage: "~/.cursor/User/workspaceStorage"
  chatgpt_export:
    path: null           # auto-detect conversations.json in CWD
  raw_markdown:
    user_prefixes: ["**User:**", "**Human:**", "You:"]
    assistant_prefixes: ["**Assistant:**", "**Claude:**", "GPT:", "Gemini:"]

distiller:
  model: claude-sonnet-4-6
  budget_tokens: 2000
  confidence_threshold: 0.7

merge:
  enabled: true
  graphify_graph: "graphify-out/graph.json"
  graphify_timeout: 30
  stale_threshold: 3
  auto_update_graph: true

adapters:
  default: chatgpt
  chatgpt:
    max_tokens: 3000
    anti_repetition_guards: true
  codex:
    max_tokens: 2000
    style: terse
  cursor:
    default_variant: rules
  claude:
    default_variant: claude-code
  ollama:
    default_model: llama3
    budget_tokens: 4096
  share_link:
    relay_url: "https://anyllm.sh"
    ttl_hours: 24
    single_use: true

team:
  workspace_token: null
  relay_url: "https://anyllm.sh"

daemon:
  port: 7723
  auto_start: false
  browser_extension_token: null  # generated on first daemon start
```

---

## 13. CLI Reference (Full v2)

```
anyllm init                              Create .anyllm/ in current project
anyllm pack [--source <id>] [--path <p>] Ingest + distill + merge
anyllm prime --target <adapter>          Render briefing for target model
  [--variant <name>]
  [--copy] [--write <path>] [--flag]
  [--budget <tokens>] [--dry-run]
anyllm status [--remote]                 Print project state
anyllm log                               Session history table
anyllm diff <session-id>                 What changed in a given session
anyllm push [--workspace <org/proj>]     Sync to shared workspace
anyllm pull [--workspace <org/proj>]     Fetch from shared workspace
anyllm share                             Generate share link
anyllm daemon [--port 7723]              Start local HTTP server + Web UI
anyllm ingestors                         List available ingestors and detection status
anyllm adapters                          List available adapters
anyllm config [--edit]                   Print or edit config
anyllm reset [--sessions] [--graph]      Reset specific state (destructive)
```

---

## 14. Module Map

```
anyllm/
├── cli.py                  # Click command group; entry point
├── config.py               # Config loading and validation
├── storage.py              # Read/write .anyllm/ directory
│
├── ingestors/
│   ├── __init__.py         # Registry and auto-detection
│   ├── base.py             # BaseIngestor, NormalizedTranscript, Turn
│   ├── claude_code.py
│   ├── codex.py
│   ├── chatgpt_export.py
│   ├── gemini_export.py
│   ├── cursor.py
│   ├── windsurf.py
│   ├── raw_markdown.py
│   └── custom_jsonl.py
│
├── distiller.py            # LLM-powered session compression
├── merger.py               # Decision state machine and merge rendering
├── graph_bridge.py         # graphify CLI wrapper
│
├── adapters/
│   ├── __init__.py         # Registry
│   ├── base.py             # BaseAdapter, RenderedBriefing
│   ├── chatgpt.py
│   ├── codex.py
│   ├── cursor.py
│   ├── windsurf.py
│   ├── claude.py
│   ├── gemini.py
│   ├── ollama.py
│   ├── mcp.py
│   ├── share_link.py
│   └── raw.py
│
├── daemon/
│   ├── server.py           # FastAPI app (optional dependency)
│   ├── routes.py
│   └── browser_auth.py
│
├── sdk.py                  # Python SDK surface (pack_session, prime)
│
└── tests/
    ├── fixtures/
    │   ├── claude_code_session.jsonl
    │   ├── codex_session.jsonl
    │   ├── chatgpt_export.json
    │   ├── cursor_state.vscdb
    │   ├── snapshot_v1.md
    │   ├── snapshot_v2.md
    │   └── graph_*.json
    ├── test_ingestors.py
    ├── test_distiller.py
    ├── test_merger.py
    ├── test_graph_bridge.py
    ├── test_adapters.py
    └── test_storage.py
```

---

## 15. Implementation Plan

### Phase 1 — Core Completeness (CLI)

**Scope:** All ingestors, text-only merge (no graphify), adapters for the 5 most common targets.

Deliverables:
- All ingestors in §6.2 except `browser-extension` and `api-session`
- Merger from PRD v1.0 Phase 1 (text-only, no graphify)
- Adapters: `chatgpt`, `codex`, `cursor`, `claude`, `raw`
- Updated `current.md` frontmatter with `merged_from`
- `anyllm ingestors` and `anyllm adapters` commands
- Full test coverage for ingestor normalization and adapter rendering

**Exit criteria:** A session started in Claude Code can be continued in Codex CLI, Cursor, and ChatGPT web with a single `anyllm pack && anyllm prime --target <x> --copy`.

### Phase 2 — Graph Verification + Remaining Adapters

**Scope:** graphify integration, remaining adapters, full decision provenance.

Deliverables:
- `graph_bridge.py` and graphify integration (PRD v1.0 Phase 2)
- Adapters: `gemini`, `windsurf`, `ollama`, `mcp`, `share-link`
- `## Session Provenance` table in `current.md`
- `anyllm log` with per-session decision deltas
- `anyllm diff <session-id>`

**Exit criteria:** A decision about a deleted file is correctly ORPHANED after `stale_threshold` sessions. Share link works and renders per-target copy buttons.

### Phase 3 — Daemon + Web UI

**Scope:** Local server, browser UI, extension capture endpoint.

Deliverables:
- `anyllm daemon` FastAPI server
- Web UI at `localhost:7723/ui` with Dashboard, Log, Briefing Studio, Manual Pack
- Browser extension (Chrome first, Firefox second) with Capture and Prime modes
- `api-session` ingestor (SDK `pack_session()`)

**Exit criteria:** A developer can capture a Claude.ai conversation from the browser and prime a Codex session without touching the CLI.

### Phase 4 — Team Sharing

**Scope:** `push`/`pull`, share links, remote workspace.

Deliverables:
- `anyllm push` / `anyllm pull` with relay backend
- Remote merge (incoming `current.md` merged server-side, not overwritten)
- Share links with per-target copy buttons
- `anyllm status --remote`
- Self-hosted relay Docker image

**Exit criteria:** Two developers on the same project can share context with `anyllm push` and have the other developer briefed in under 60 seconds.

---

## 16. Testing Strategy

### Ingestor Tests

Each ingestor has:
- A fixture in the source format (real session data, anonymized)
- A test asserting `NormalizedTranscript` field correctness: session_id, turn count, role assignments, timestamp parsing
- A test for the `detect()` method (positive and negative cases)
- A test for graceful failure on malformed input (should raise `IngestError`, not crash)

Cursor and Windsurf ingestors get an additional version-compatibility test matrix.

### Adapter Tests

Each adapter has:
- Input: a known `Snapshot` + `MergeResult` fixture
- Output: golden file of the expected rendered briefing
- A test asserting the output contains the task, all CONFIRMED decisions, and the next step
- A test for `--budget` truncation: output must stay under the token budget with correct priority order
- A golden-file diff test: any change to adapter output requires explicit golden file update

### End-to-End Tests

Three fixture projects with pre-built session sequences:

1. **Simple (3 sessions, Claude Code → Codex):** Assert all three sessions' decisions appear in `current.md` after three packs.
2. **Cross-tool (ChatGPT export → Cursor):** Assert normalized transcript has correct turn roles, adapter writes valid `.cursorrules`.
3. **Stale/Orphan (5 sessions, one deleted code anchor):** Assert decision about deleted anchor is ORPHANED after `stale_threshold` packs.

---

## 17. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Cursor/Windsurf SQLite schema changes on tool update | High | High | Version-detect schema; fail with clear error message; include `--dry-run` SQL dump flag |
| ChatGPT export format changes | Medium | Medium | Schema version detection; community-maintained format registry |
| Share link relay becomes a privacy concern | Medium | High | Self-hosted option from day one; ephemeral by default; no PII stored server-side beyond TTL |
| Daemon port 7723 conflicts | Low | Low | Configurable port; fallback port scan |
| LLM paraphrasing breaks decision ID matching | High | High | Phase 1 must validate hash matching on 20+ real session pairs before Phase 2 ships |
| Cursor ingestor breaks TOS | Unknown | High | Flag as "unofficial integration, may break"; document the reverse-engineering caveat clearly in README |
| Token budget conflicts across target models | Medium | Medium | Per-adapter `max_tokens` in config; `--budget` CLI flag overrides; always include task + next step even at minimal budget |

---

## 18. Success Metrics

| Metric | Target |
|---|---|
| Ingestor coverage | 8 source formats at Phase 1 ship |
| Adapter coverage | 10 target formats at Phase 2 ship |
| Cross-tool pack→prime round trip time | < 10 seconds (excluding distillation) |
| Decision retention across 5 sessions | ≥ 90% of EXTRACTED decisions preserved |
| False positive orphan rate | < 5% |
| Share link adoption | Measurable (open telemetry, opt-in) |
| "No redo" rate | Downstream model re-proposes closed decisions < 10% of the time |

---

## 19. Open Questions

1. **Codex CLI session path** — The Codex CLI session path is not officially documented. Should anyllm hardcode `~/.codex/` or make it fully configurable with a detection hint? Recommendation: configurable with documented default, plus `anyllm ingestors` command that shows detected paths.

2. **Cursor reverse-engineering** — The `.vscdb` ingestor is reverse-engineered. Should it be opt-in (behind a `--experimental` flag) until it's proven stable, or ship as default? Recommendation: ship as default with a clear "unofficial" caveat in `anyllm ingestors` output.

3. **Share link relay** — Should anyllm Cloud be the default relay or should self-hosted be the only option for v2? Recommendation: self-hosted only for v2 (relay is a single FastAPI endpoint easy to self-host); anyllm Cloud in v3 once the relay spec is stable.

4. **Daemon always-on vs on-demand** — Should the daemon start on `anyllm init` or only on explicit `anyllm daemon`? Recommendation: explicit only; add `daemon.auto_start: true` config option for users who want it.

5. **Multi-project support** — The current design assumes one `.anyllm/` per project root. Should `anyllm daemon` support multiple simultaneous projects? Recommendation: yes, daemon accepts `--project-root` per request or uses the request's `CWD` header.