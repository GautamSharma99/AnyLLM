# PRD: Internal Graphify-Powered Context Enrichment

## Status

Proposed

## Goal

Leverage Graphify internally to make context transfer significantly better while keeping Graphify completely invisible to end users.

From a user's perspective, `anyllm` should remain:

```bash
anyllm pack
anyllm prime
anyllm push
```

There should be:

* no `graphify` command
* no `graphify` configuration
* no `graphify` terminology in documentation
* no mention of AST extraction or knowledge graphs in user-facing workflows

Graphify becomes an implementation detail of the context engine.

---

# Problem

Pure transcript distillation has limitations:

* models forget earlier decisions
* code structure is inferred from chat history
* hallucinated architecture can leak into snapshots
* receiving models lack actual repository structure
* context handoff quality degrades over multiple sessions

We need structural understanding of the repository without exposing another tool to users.

---

# Product Principle

> Users care about better context transfer, not about knowledge graphs.

Graphify exists solely to improve:

* packing
* merging
* priming
* context fidelity

The user should never need to know it exists.

---

# User Experience

## User installs

```bash
pip install anyllm
```

## User runs

```bash
anyllm init
anyllm pack
anyllm prime
```

That's it.

No:

```bash
graphify extract
graphify query
graphify init
```

ever.

---

# Product Messaging

Market:

```text
Portable context for AI coding agents.
```

Not:

```text
Portable context powered by knowledge graphs.
```

---

# Internal Architecture

```text
Transcript
     ↓
Distillation
     ↓
Repository Analysis
     ↓
Merge Engine
     ↓
Composer
     ↓
Adapter
```

Repository Analysis is implemented using Graphify internally.

---

# Internal Module

```text
src/anyllm/
├── context_graph/
│   ├── __init__.py
│   ├── analyzer.py
│   ├── extractor.py
│   ├── query.py
│   ├── cache.py
│   └── models.py
```

The word "graphify" should not appear outside this module.

---

# Internal Naming

Instead of:

```python
graphify_bridge.py
```

Use:

```python
repository_analyzer.py
context_graph.py
code_intelligence.py
```

Instead of:

```python
update_graph()
query_graph()
```

Use:

```python
analyze_repository()
resolve_anchor()
build_context()
```

---

# Internal Responsibilities

Repository analysis should provide:

```python
class RepositoryAnalyzer:
    def analyze()
    def resolve_symbol()
    def get_related_files()
    def get_dependencies()
    def get_entrypoints()
    def get_architecture_summary()
```

Implementation may use Graphify internally.

The rest of the codebase should not know.

---

# Context Enrichment

During:

```bash
anyllm pack
```

internally:

```text
snapshot
    ↓
repository analysis
    ↓
enriched snapshot
```

Add:

* files touched
* related modules
* symbol relationships
* dependencies
* architecture summary
* confidence scores

---

# During Prime

Current:

```text
Chat transcript
```

Desired:

```text
Chat transcript
+ repository structure
+ dependencies
+ module summaries
+ relevant files
```

The next model receives significantly better context.

---

# Internal Flow

```text
anyllm prime
      ↓
load current.md
      ↓
RepositoryAnalyzer
      ↓
find related files
      ↓
find dependencies
      ↓
find symbols
      ↓
inject architecture context
      ↓
render briefing
```

---

# Context Section Example

Generated internally:

```markdown
## Repository Context

Authentication flow:

auth.py
 └── jwt.py
      └── middleware.py

Used by:

api/users.py
api/admin.py

Related symbols:

validate_token
refresh_session
get_current_user
```

The user never sees:

```text
Graph extracted from graphify.
```

---

# Decision Verification

Repository analysis should answer:

```text
Does this decision still exist?
```

Not:

```text
What does graphify think?
```

Internal confidence levels:

```text
CONFIRMED
LIKELY
UNCERTAIN
MISSING
```

Never expose:

```text
EXTRACTED
INFERRED
AMBIGUOUS
```

Those are implementation details.

---

# Configuration

No:

```yaml
graphify:
```

section.

Instead:

```yaml
repository_analysis:
  enabled: true
  timeout: 30
  auto_refresh: true
```

or hide entirely.

---

# Dependency Strategy

## Option 1 (Preferred)

Bundle Graphify.

```text
pip install anyllm
```

installs:

```text
anyllm
graphify
```

as an internal dependency.

---

## Option 2

Lazy install.

First pack:

```text
Repository analysis unavailable.
Continuing without repository enrichment.
```

No mention of Graphify.

---

# Failure Handling

Repository analysis must never break:

* pack
* prime
* push

Fallback:

```text
Transcript-only mode.
```

No internal implementation details leaked.

---

# Documentation

README should say:

```text
anyllm automatically analyzes your repository structure to improve context transfer.
```

Not:

```text
anyllm uses graphify.
```

---

# Telemetry / Status

Current:

```text
Graph freshness
Graph confidence
```

Remove.

Replace with:

```text
Repository analysis: enabled
Repository context: available
```

---

# Future Features Enabled

Because repository analysis is internal, we can later add:

* semantic file search
* dependency-aware packing
* symbol-level context selection
* architecture diagrams
* auto-relevant file retrieval
* repository summaries
* code-aware context compression

without changing the public API.

---

# Success Criteria

User experience:

```bash
anyllm pack
anyllm prime
```

feels magical because:

* decisions survive across sessions
* architecture is understood
* related files appear automatically
* context quality improves dramatically

while the user never needs to know that Graphify exists.

---

# Product Philosophy

> Users want portable context.

> They do not want another tool to install, configure, or learn.

Repository analysis is an implementation detail.

Graphify is the engine under the hood, not part of the product surface.
