# PRD: Zero-Token Claude Code Slash Commands for anyllm

**Status:** Ready to implement  
**Scope:** `~/.claude/commands/` — four global slash command files  
**Token budget:** 0 Claude tokens per invocation (hard requirement)

---

## Problem

Running `anyllm pack` inside a Claude Code session today means either:

1. Typing `!anyllm pack` in the bash tool — Claude sees the output, may summarize or process it, burning tokens
2. Opening a separate terminal — friction, breaks flow

The entire value of anyllm is that the distillation happens *outside* the active LLM. If Claude Code reads the transcript and output, the tool defeats itself.

---

## Goal

Four slash commands — `/anyllm-init`, `/anyllm-pack`, `/anyllm-prime`, `/anyllm-status` — that run the anyllm CLI as a pure subprocess. Claude Code displays terminal output to the user but **never reads it, never processes it, never spends a token on it**.

---

## Mechanism

Claude Code slash commands support a `disable-model-invocation: true` frontmatter key. When set:

- The `!` shell injection runs the command
- stdout/stderr stream to the terminal UI
- Claude's context window is not touched
- Token counter does not move

This is the correct primitive. No workarounds needed.

---

## File Layout

All four files go in `~/.claude/commands/` (global, available in every project).

```
~/.claude/commands/
├── anyllm-init.md
├── anyllm-pack.md
├── anyllm-prime.md
└── anyllm-status.md
```

Project-local alternative: `.claude/commands/` in the repo root (committed to git, project-scoped).

---

## Command Specifications

### `/anyllm-init`

**File:** `~/.claude/commands/anyllm-init.md`

```markdown
---
description: Initialize anyllm in the current project (.anyllm/ dir + config.yaml)
allowed-tools: Bash(anyllm init)
disable-model-invocation: true
---
!`anyllm init`
```

**Behavior:** Creates `.anyllm/` with default `config.yaml` and `index.json`. Idempotent — safe to run twice. No arguments.

---

### `/anyllm-pack`

**File:** `~/.claude/commands/anyllm-pack.md`

```markdown
---
description: Pack current session → distill → merge into .anyllm/current.md (no Claude tokens used)
allowed-tools: Bash(anyllm pack*)
disable-model-invocation: true
---
!`anyllm pack $ARGUMENTS`
```

**Behavior:** Runs the full `ingest → distill (OpenRouter/Qwen) → merge` pipeline. Writes `.anyllm/current.md`. Claude Code sees nothing.

**Argument passthrough:** `$ARGUMENTS` forwards any flags the user types after the command name.

| Invocation | Shell command run |
|---|---|
| `/anyllm-pack` | `anyllm pack ` |
| `/anyllm-pack --source chatgpt` | `anyllm pack --source chatgpt` |
| `/anyllm-pack --session abc123` | `anyllm pack --session abc123` |

**Note:** Trailing space when no arguments are given is harmless — `anyllm pack ` behaves identically to `anyllm pack`.

---

### `/anyllm-prime`

**File:** `~/.claude/commands/anyllm-prime.md`

```markdown
---
description: Generate briefing from current.md and copy to clipboard (no Claude tokens used)
allowed-tools: Bash(anyllm prime*)
disable-model-invocation: true
---
!`anyllm prime $ARGUMENTS`
```

**Behavior:** Reads `.anyllm/current.md`, composes + adapts the briefing, outputs to stdout. With `--copy` flag, copies to clipboard. Claude Code displays the output in the terminal panel but does not ingest it.

| Invocation | Shell command run |
|---|---|
| `/anyllm-prime` | `anyllm prime ` |
| `/anyllm-prime --target claude` | `anyllm prime --target claude` |
| `/anyllm-prime --copy` | `anyllm prime --copy` |

---

### `/anyllm-status`

**File:** `~/.claude/commands/anyllm-status.md`

```markdown
---
description: Show current.md summary — task, next step, confidence report (no Claude tokens used)
allowed-tools: Bash(anyllm status*)
disable-model-invocation: true
---
!`anyllm status $ARGUMENTS`
```

**Behavior:** Prints a summary of `.anyllm/current.md` — current task, next step, confidence report, graph info if graphify is installed. Read-only, never modifies state.

---

## Installation

### One-time setup

```bash
mkdir -p ~/.claude/commands

# Copy the four files
cp anyllm-init.md ~/.claude/commands/
cp anyllm-pack.md ~/.claude/commands/
cp anyllm-prime.md ~/.claude/commands/
cp anyllm-status.md ~/.claude/commands/
```

### Verify

Restart Claude Code (or open a new session). Type `/` — all four commands should appear in autocomplete with their descriptions.

### Project-local alternative

If you want the commands checked into the repo (so teammates get them automatically):

```bash
mkdir -p .claude/commands
# Copy files there instead
```

Project-local commands take precedence over global if names collide.

---

## Constraints and Edge Cases

**`$ARGUMENTS` when empty:** Shell receives `anyllm pack ` (trailing space). All anyllm CLI commands use `argparse`, which ignores trailing whitespace. No special handling needed.

**`anyllm` not on PATH:** The shell injection will fail with `command not found`. Output streams to the terminal panel. Claude Code does not see the error — user must resolve PATH themselves. Consider adding a note in `CLAUDE.md`: `# anyllm must be on PATH for /anyllm-* commands`.

**`disable-model-invocation` availability:** Shipped in Claude Code v2.1.101 (April 11, 2026). If running an older version, upgrade: `npm install -g @anthropic-ai/claude-code`.

**Skill vs command naming:** As of Claude Code v2.1.101, if a `.claude/skills/<name>/SKILL.md` and a `.claude/commands/<name>.md` share the same name, the skill takes precedence. The `anyllm-*` names have a hyphen which avoids collision with any potential `anyllm` skill directory.

**stdout volume:** `anyllm pack` may emit several hundred lines (distiller streaming, merge diffs). This all goes to the terminal panel only — no context window impact regardless of output size.

---

## What This Is Not

- This does not modify the anyllm CLI in any way
- This does not change how distillation works
- This does not add Claude Code as a supported ingestor source
- This does not require anyllm to know anything about Claude Code slash commands

The CLI remains fully usable standalone (`anyllm pack` in any terminal). These files are purely a convenience layer.

---

## Acceptance Criteria

- [ ] `/anyllm-init` appears in Claude Code autocomplete with correct description
- [ ] `/anyllm-pack` runs `anyllm pack` and shows output in terminal panel; `/cost` does not increase
- [ ] `/anyllm-pack --source chatgpt` correctly passes the flag through
- [ ] `/anyllm-prime --copy` copies briefing to clipboard; Claude Code context unchanged
- [ ] `/anyllm-status` prints summary; Claude Code context unchanged
- [ ] Running `/anyllm-pack` twice in a row produces a merge (not an overwrite) in `current.md`
- [ ] Commands work from any directory inside a project that has `.anyllm/` initialized

---

## Implementation Checklist

- [ ] Create `~/.claude/commands/anyllm-init.md`
- [ ] Create `~/.claude/commands/anyllm-pack.md`
- [ ] Create `~/.claude/commands/anyllm-prime.md`
- [ ] Create `~/.claude/commands/anyllm-status.md`
- [ ] Restart Claude Code session to pick up new commands
- [ ] Run `/anyllm-init` in a test project, verify `.anyllm/` created
- [ ] Run `/anyllm-pack`, check `/cost` before and after — delta should be ~0 input tokens
- [ ] Add `anyllm on PATH` note to project `CLAUDE.md`