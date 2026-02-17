# PocketFlow — Objective Review

**Reviewed:** 2026-02-17
**Version reviewed:** main branch (~100-line core, ~9.8k GitHub stars)
**Context:** Used in SPL-Flow to orchestrate the Text2SPL → Validate → Execute → Deliver pipeline
**Source:** https://github.com/The-Pocket/PocketFlow

---

## What PocketFlow Is

PocketFlow is a minimalist LLM orchestration framework whose entire core is
**100 lines of Python** and has zero external dependencies.  It models
agentic workflows as **directed graphs** of Nodes connected by named action
edges, communicating through a single shared dictionary (the "store").

The three primitives are:

| Primitive | Role |
|-----------|------|
| **Node** | Unit of work — `prep()` reads store, `exec()` does work, `post()` writes store + returns next action |
| **Flow** | Directed graph — wires nodes via `node - "action" >> next_node` |
| **Shared store** | Plain `dict` — all nodes read and write to the same in-memory dict |

Size comparison with alternatives:

| Framework | Lines of code | Install size |
|-----------|--------------|-------------|
| LangChain | ~405 K | +166 MB |
| LangGraph | ~37 K | +51 MB |
| CrewAI | ~15 K | +40 MB |
| **PocketFlow** | **~100** | **+56 KB** |

---

## Strengths

### 1. Radical simplicity — you can read the whole framework in 10 minutes
The entire engine is transparent.  When something goes wrong, there is no
framework black-box to blame: every behaviour is traceable to code you can
read.  This is genuinely rare among LLM frameworks.

### 2. Zero dependencies, zero vendor lock-in
PocketFlow does not import `langchain`, `openai`, `anthropic`, or anything
else.  You bring your own LLM clients.  If Anthropic changes its SDK, only
your adapter needs updating — not the orchestration layer.

### 3. LLM-agnostic by design
The same graph wires work with `claude_cli`, `openrouter`, `ollama`, or
anything else.  The framework is indifferent to which model runs inside a Node.

### 4. Shared-store pattern scales well for linear pipelines
For pipelines where data flows sequentially (A produces → B consumes → C
consumes), the shared dict is a clean and low-friction interface.  SPL-Flow's
Text2SPL → Validate → Execute → Deliver pipeline is an ideal fit.

### 5. Composable flows
A Flow can be nested inside another Flow as if it were a Node.  This enables
sub-pipeline reuse without code duplication.

### 6. Fast to get started
From zero to a working multi-node pipeline is under an hour.  The cookbook
includes Text-to-SQL, RAG, agent-to-agent, and human-in-the-loop examples.

---

## Weaknesses

### 1. Shared store is a raw dict — no type safety, no schema validation
Any node can write any key with any type.  There is no schema declaration, no
validation, no warning when a node reads a key that was never written.  In
SPL-Flow this led to subtle bugs where missing keys (e.g. `adapter` not
populated in `generate_spl_only`) silently fell through to wrong defaults.

**Mitigation:** define a canonical `SHARED_DEFAULTS` dict and validate keys
explicitly in `prep()`.

### 2. Action edge API is inconsistent — `>>` vs `- "action" >>`
The `>>` shorthand creates a `"default"` edge; named edges use
`- "action" >>`.  When a node's `post()` returns an action string that doesn't
match any edge label, PocketFlow silently falls back to `"default"` and emits
a `UserWarning`.  This is confusing: the pipeline *works* but warns, and the
warning only disappears once you know to always use the named-edge syntax.

SPL-Flow hit this exactly:
```python
text2spl >> validate          # created "default" edge
# but Text2SPLNode.post() returned "validate" → UserWarning fired every run
```
**Fix:** always use `node - "action" >> next_node` and never mix `>>` with
explicit action returns from `post()`.

### 3. No built-in async execution between nodes
Each Node's `exec()` is synchronous from the framework's perspective.  If your
node needs to `await` something, you must call `asyncio.run()` inside `exec()`,
which blocks the thread and prevents multiple nodes from running truly in
parallel within a single flow.

SPL-Flow's Benchmark feature (N models in parallel) had to bypass the
PocketFlow graph entirely and use raw `asyncio.gather()` inside a single
`BenchmarkNode`.  This is a workaround, not a framework feature.

### 4. No built-in observability or tracing
There is no span/trace concept, no structured event log, no timeline view.
Debugging a misfiring flow means adding `print()` or wiring your own logger
into every node.  At scale (10+ nodes, long-running agents) this becomes painful.

**Mitigation:** SPL-Flow added a logging layer in `logging_config.py` and each
node emits structured `_log.info()` calls manually — effective but boilerplate
every project must write from scratch.

### 5. No persistent state across flow runs
The shared store lives only in memory for one `flow.run()` call.  If the
process crashes mid-flow, all intermediate state is lost.  There is no built-in
checkpoint/resume mechanism.

This matters for long multi-step agentic workflows (web research → analysis →
code generation → review) where a crash at step 5 of 8 should not restart from
zero.

### 6. Small community and limited ecosystem
~9.8k GitHub stars and growing, but the community is orders of magnitude smaller
than LangChain or LangGraph.  Fewer answered questions, fewer ready-made
integrations, lower confidence in long-term maintenance.

### 7. "100 lines" is the engine — not the full framework you ship
The 100-line core is real and impressive, but production use requires:
- Your own retry/back-off logic
- Your own type contracts on the shared store
- Your own logging and tracing
- Your own async coordination between nodes
- Your own error propagation conventions

These are not hard to write, but they are not provided.  PocketFlow is closer
to a **design pattern** than a **batteries-included framework**.

---

## Is It a Good Decision for SPL-Flow?

### Verdict: ✅ Good fit for the current pipeline — with clear caveats

**Why it works well for SPL-Flow now:**

1. The core pipeline is a linear 5-node graph with one retry loop — the exact
   use case PocketFlow is optimised for.
2. The shared store cleanly separates concerns: each node reads what it needs
   and writes what the next node expects, with no tight coupling.
3. Zero-dependency setup fits SPL-Flow's goal of easy local installation —
   no `pip install langchain[all]` surprises.
4. The framework is small enough that the team *owns* it conceptually: any
   PocketFlow bug can be understood and patched in minutes.

**Where it may become limiting:**

| Scenario | Risk level |
|----------|------------|
| More parallel steps (e.g. multi-agent routing) | Medium — requires `asyncio.gather` workarounds |
| Long-running agent loops (10+ steps) | Medium — no checkpointing |
| Distributed execution across processes | High — shared store is in-memory only |
| Production monitoring and alerting | Medium — must build all observability from scratch |

**Compared to alternatives for this use case:**

| Framework | Verdict for SPL-Flow |
|-----------|----------------------|
| **PocketFlow** | ✅ Good MVP choice — simple, transparent, zero dependencies |
| **LangGraph** | ⚠️ More powerful state machine with checkpointing, but 51 MB overhead and steeper learning curve for a 5-node pipeline |
| **CrewAI** | ❌ Role-based model is the wrong abstraction for a compiler-style pipeline |
| **LangChain** | ❌ 166 MB, constant interface churn, significant overkill |
| **Raw Python** | ⚠️ Would work fine; PocketFlow adds just enough structure to be worth the trade |

---

## Recommendations

1. **Keep PocketFlow for the current orchestration layer** — the pipeline fits
   the framework's sweet spot and the cost of switching exceeds the benefit at
   this stage.

2. **Always use named edges** — never use bare `>>` when `post()` returns an
   explicit action string.  Establish this as a team convention:
   ```python
   # Wrong — creates "default" edge but post() returns "validate"
   text2spl >> validate

   # Correct — edge label matches the returned action
   text2spl - "validate" >> validate
   ```

3. **Define a typed shared-store schema** — document the canonical keys and
   expected types at the top of each flow builder to prevent silent
   missing-key bugs.

4. **For parallel work, bypass PocketFlow explicitly** — keep Benchmark and
   any future parallel nodes as standalone `asyncio` functions wrapped inside
   a single PocketFlow node.  Do not fight the framework trying to parallelise
   at the graph level.

5. **Revisit if the pipeline grows beyond ~10 nodes** — at that point,
   LangGraph's explicit state machine semantics, native checkpointing, and
   LangGraph Studio visualisation become genuinely compelling.

---

## Summary

PocketFlow is a genuinely well-designed minimal framework that does exactly what
it claims.  Its 100-line core is not a gimmick — it reflects a coherent and
honest design philosophy: one shared dict, one directed graph, no magic.

For SPL-Flow's current 5-node linear pipeline it is an excellent fit:
transparent, dependency-free, and fast to onboard.  Its weaknesses — untyped
shared store, synchronous node execution, no observability, no checkpointing —
are real but manageable at this scale.  They are known trade-offs of minimalism,
not defects.

A team that understands those limits and writes thin wrappers around them will
be productive and unburdened by the framework churn that plagues heavier
alternatives.

**The decision to use PocketFlow for SPL-Flow's MVP is sound.**
