# PicoFlow — Design & Architecture

**Version:** 0.1.0
**Date:** 2026-02-17
**Status:** Stable — replaces PocketFlow in new code

---

## Why PicoFlow?

PocketFlow's 100-line core is an elegant idea, but four weaknesses surfaced during SPL-Flow development:

| # | Weakness | PicoFlow fix |
|---|----------|-------------|
| 1 | Shared store is a raw dict — no schema, no type safety | `Store` class with optional schema + type-checked writes |
| 2 | Edge API inconsistency — `>>` vs `- "action" >>` causes silent `UserWarning` | Single unambiguous API: `.then("action", next_node)` |
| 3 | No built-in async between nodes — caller must wrap `asyncio.run()` manually | `AsyncNode` base class — implement `exec_async()` and the framework handles the rest |
| 4 | No observability, no checkpointing | Hook system + optional `checkpoint_dir` with `snapshot/restore` |

PicoFlow keeps PocketFlow's best idea — the **nano-ETL abstraction** — while hardening the gaps.

---

## Core Primitives

```
┌─────────────────────────────────────────────────────────┐
│  Store  — typed, observable, checkpointable shared state │
│  Node   — nano-ETL unit: prep | exec | post             │
│  Flow   — directed graph runner with hooks               │
└─────────────────────────────────────────────────────────┘
```

### Store

```python
from src.picoflow import Store

store = Store(
    data={"user_input": "", "adapter": "claude_cli"},
    schema={"user_input": str, "adapter": str},
    name="spl_pipeline",
)
store["user_input"] = "explain quantum entanglement"  # type-checked
store.validate()                                       # raises if required key missing
store.snapshot("/tmp/run_42/step_003.json")            # crash recovery
store2 = Store.restore("/tmp/run_42/step_003.json")    # resume from checkpoint
```

**Observer pattern** — hook into every write for logging or tracing:
```python
store.add_observer(lambda key, old, new: print(f"{key}: {old!r} → {new!r}"))
```

### Node (nano-ETL)

Every node is a three-phase processing unit:

```
prep(store)              → Extract: read what this node needs from the store
exec(prep_result)        → Transform: do the work (pure, no store side-effects)
post(store, prep, exec)  → Load: write results back, return next action string
```

```python
from src.picoflow import Node

class SummariseNode(Node):
    max_retries = 3      # retry exec() up to 3 times on exception
    retry_delay = 1.0    # wait 1 s between retries

    def prep(self, store):
        return store["document"]          # Extract

    def exec(self, text):
        return llm.summarise(text)        # Transform (pure — no store writes)

    def post(self, store, prep, summary):
        store["summary"] = summary        # Load
        return "done"                     # Route: next action
```

**Why the three-phase split?**

| Phase | Purity | Concern |
|-------|--------|---------|
| `prep` | reads store | Decouples what the node needs from how it gets it |
| `exec` | pure function | Isolated, retryable, testable without a store |
| `post` | writes store | Routing logic lives in one place |

### Edge wiring

```python
# Named edge — explicit and unambiguous
a.then("done", b)
a.then("error", c)

# Wildcard — matches any action not covered by a named edge
a.then("*", fallback_node)

# Chained
a.then("ok", b).then("skip", c)
```

No more `>>` shorthand. No more `UserWarning: action not in ['default']`.

### AsyncNode

```python
from src.picoflow import AsyncNode
import asyncio

class FetchNode(AsyncNode):
    async def exec_async(self, urls):
        results = await asyncio.gather(*[fetch(u) for u in urls])
        return results
```

Implement `exec_async()` — the framework calls it via `asyncio.run()`.
The surrounding `Flow` stays synchronous; async is contained inside the node.

### Flow

```python
from src.picoflow import Flow

flow = Flow(
    start=summarise_node,
    checkpoint_dir="/tmp/run_42",   # snapshot store after every node
    max_steps=50,                   # guard against infinite loops
)

# Hooks — wire to any logger, metrics sink, or UI progress bar
flow.on("node_start", lambda name, store: print(f"▶ {name}"))
flow.on("node_end",   lambda name, action, elapsed, store:
                          print(f"✓ {name} → {action}  ({elapsed:.2f}s)"))
flow.on("node_error", lambda name, exc, store: alert(name, exc))
flow.on("flow_end",   lambda steps, store: print(f"done in {steps} steps"))

store = Store({"document": "..."})
flow.run(store)

# Resume after crash
store = Store.restore("/tmp/run_42/step_002_SummariseNode.json")
flow.run(store, resume_from=deliver_node)
```

---

## Checkpoint File Naming

```
checkpoint_dir/
  step_000_Text2SPLNode.json
  step_001_ValidateSPLNode.json
  step_002_ExecuteSPLNode.json
  ...
```

Each file is the full store snapshot after that node completes.
To resume from step 2, restore `step_002_*.json` and pass the execute node as `resume_from`.

---

## Comparison with PocketFlow

| Feature | PocketFlow | PicoFlow |
|---------|-----------|----------|
| Core size | ~100 lines | ~320 lines |
| Shared state | raw dict | typed Store with schema |
| Edge API | `>>` and `- "action" >>` (confusing) | `.then("action", node)` only |
| Async nodes | manual `asyncio.run()` per node | `AsyncNode.exec_async()` |
| Observability | none | 4-event hook system |
| Checkpointing | none | `checkpoint_dir` + `snapshot/restore` |
| Retry | none | `max_retries` + `retry_delay` on any Node |
| Wildcard edges | none | `.then("*", fallback)` |
| External deps | 0 | 0 |

---

## Migration Guide (PocketFlow → PicoFlow)

### 1. Replace imports

```python
# Before
from pocketflow import Node, Flow

# After
from src.picoflow import Node, AsyncNode, Flow, Store
```

### 2. Replace edge wiring

```python
# Before — creates "default" edge, causes UserWarning if post() returns "validate"
text2spl >> validate

# After — unambiguous
text2spl.then("validate", validate)
```

### 3. Wrap the shared dict in a Store

```python
# Before
shared = {"user_input": query, "adapter": "claude_cli"}
flow.run(shared)

# After — validates required keys, type-checks writes
shared = Store(
    data={"user_input": query, "adapter": "claude_cli"},
    schema={"user_input": str, "adapter": str},
)
flow.run(shared)
```

### 4. Replace `asyncio.run()` inside exec()

```python
# Before
class FetchNode(Node):
    def exec(self, prep):
        return asyncio.run(self._fetch_async(prep))   # manual

# After
class FetchNode(AsyncNode):
    async def exec_async(self, prep):
        return await self._fetch_async(prep)          # framework handles asyncio.run()
```

### 5. Add hooks instead of print statements

```python
# Before — scattered prints in every node
class MyNode(Node):
    def exec(self, prep):
        print(f"MyNode starting")
        ...

# After — single hook on the flow
flow.on("node_start", lambda name, store: _log.info("▶ %s", name))
flow.on("node_end", lambda name, action, elapsed, s:
    _log.info("✓ %s → %s  %.2fs", name, action, elapsed))
```

---

## File Map

```
picoflow/
  __init__.py    — public API: Store, Node, AsyncNode, Flow
  store.py       — Store implementation (~158 lines)
  node.py        — Node + AsyncNode (~178 lines)
  flow.py        — Flow runner with hooks + checkpointing (~178 lines)
```

---

## Design Principles

1. **Nano-ETL metaphor is sacred** — prep/exec/post maps directly to Extract/Transform/Load.
   Every node is independently testable: call `node.exec(inputs)` without a store.

2. **Zero external dependencies** — same as PocketFlow. stdlib only.

3. **Flow stays synchronous** — async is an implementation detail of individual nodes,
   not of the orchestration layer. This keeps the mental model simple.

4. **Hooks, not inheritance** — observability is added by the caller, not the framework.
   Nodes know nothing about logging, metrics, or UI.

5. **Checkpoints are opt-in** — `checkpoint_dir=None` by default.
   Enabling it requires no changes to nodes.

6. **Fail loudly** — unknown hook names raise `ValueError`, unknown store writes with
   mismatched types raise `TypeError`. Silent fallbacks are a debugging tax.
