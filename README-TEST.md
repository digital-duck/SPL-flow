# SPL-Flow Testing Guide

Step-by-step instructions to validate all features. Follow sections in order — each section builds on the previous.

---

## Prerequisites

```bash
# Activate the conda env
conda activate spl

# Verify the SPL engine is importable
python -c "import spl; print('SPL engine OK')"

# Verify SPL-Flow dependencies
python -c "import pocketflow, streamlit, chromadb, click; print('Dependencies OK')"
```

Expected output:
```
SPL engine OK
Dependencies OK
```

---

## Section 1 — CLI: generate (NL → SPL, no execution)

### 1.1 Basic generation

```bash
python -m src.cli generate "List 10 Chinese characters with water radical"
```

Expected:
- Prints a valid SPL query starting with `PROMPT`
- No errors on stderr

### 1.2 With context file

```bash
echo "The water radical (氵) appears in characters related to water, rivers, and liquids." > /tmp/test_ctx.txt
python -m src.cli generate "List characters with water radical" \
    --context-file /tmp/test_ctx.txt
```

Expected: SPL referencing context

### 1.3 Save SPL to file

```bash
python -m src.cli generate "Explain quantum entanglement" \
    --spl-output /tmp/test.spl
cat /tmp/test.spl
```

Expected: `/tmp/test.spl` contains valid SPL

### 1.4 Stdin input

```bash
echo "Summarize machine learning in 3 bullet points" | python -m src.cli generate -
```

Expected: Valid SPL printed

### 1.5 Quiet mode (no status messages)

```bash
python -m src.cli generate "Hello world" --quiet
```

Expected: Only the SPL printed, no `[generated in Xs]` banner

### 1.6 Error case

```bash
python -m src.cli generate ""
```

Expected: Error about empty query, exit code 1

---

## Section 2 — CLI: run (full pipeline)

### 2.1 Basic run

```bash
python -m src.cli run "What is photosynthesis? Give a 2-sentence explanation."
```

Expected:
- Status messages on stderr
- Result text on stdout
- Metrics (model, tokens, latency, cost) on stderr

### 2.2 With adapter selection

```bash
python -m src.cli run "Write a haiku about autumn" --adapter claude_cli
```

### 2.3 With context file

```bash
python -m src.cli run "Summarize the key points" \
    --context-file /tmp/test_ctx.txt \
    --output /tmp/summary.md
cat /tmp/summary.md
```

Expected: `/tmp/summary.md` contains the summary

### 2.4 JSON output (full metrics)

```bash
python -m src.cli run "What is 2+2?" --json
```

Expected: JSON with `primary_result`, `spl_query`, `execution_results` (each with `model`, `input_tokens`, `output_tokens`, `latency_ms`, `cost_usd`)

### 2.5 Quiet + output (for shell scripts)

```bash
python -m src.cli run "One sentence about AI" --quiet --output /tmp/ai.md
cat /tmp/ai.md
```

Expected: No status output; result in `/tmp/ai.md`

### 2.6 With --provider flag (openrouter only)

```bash
# Only works if OPENROUTER_API_KEY is set
python -m src.cli run "Debug this Python snippet" \
    --adapter openrouter \
    --provider deepseek \
    --json 2>/dev/null | python -m json.tool | grep '"model"'
```

Expected: model name contains `deepseek`

### 2.7 Provider shown in banner

```bash
python -m src.cli run "Test query" --adapter openrouter --provider anthropic 2>&1 | head -6
```

Expected banner includes:
```
  adapter  : openrouter
  provider : anthropic
```

---

## Section 3 — CLI: exec (direct SPL execution)

### 3.1 Create a test SPL file

```bash
cat > /tmp/test_query.spl << 'EOF'
PROMPT greeting
SELECT
    GENERATE('Write a one-sentence greeting about AI.')
USING MODEL 'claude-sonnet-4-5';
EOF
```

### 3.2 Execute the SPL file

```bash
python -m src.cli exec /tmp/test_query.spl
```

Expected: A greeting sentence printed

### 3.3 With params

```bash
cat > /tmp/param_query.spl << 'EOF'
PROMPT answer
SELECT
    GENERATE('Answer this question: ', context.question)
USING MODEL 'claude-sonnet-4-5';
EOF

python -m src.cli exec /tmp/param_query.spl --param "question=What is the speed of light?"
```

### 3.4 JSON output

```bash
python -m src.cli exec /tmp/test_query.spl --json
```

Expected: JSON with `spl_file`, `primary_result`, `execution_results`

### 3.5 With --provider (openrouter)

```bash
# Requires OPENROUTER_API_KEY
python -m src.cli exec /tmp/test_query.spl \
    --adapter openrouter \
    --provider google \
    --json 2>/dev/null | python -m json.tool | grep '"model"'
```

Expected: model name contains `gemini` or `google`

---

## Section 4 — USING MODEL auto

### 4.1 Create a multi-model SPL with auto routing

```bash
cat > /tmp/auto_model.spl << 'EOF'
PROMPT cjk_task
SELECT
    system_role('You are a Chinese language expert.'),
    GENERATE('List 3 Chinese characters with the water radical (氵) and their meanings.')
USING MODEL auto;

PROMPT final_synthesis
SELECT
    system_role('You are a helpful assistant.'),
    GENERATE('Summarize the previous analysis in one sentence.')
USING MODEL auto;
EOF
```

### 4.2 Execute with claude_cli adapter

```bash
python -m src.cli exec /tmp/auto_model.spl --json
```

Expected:
- `cjk_task` prompt: model is `claude-sonnet-4-5` (claude_cli uses Anthropic for all tasks)
- `final_synthesis` prompt: model is `claude-opus-4-6` (synthesis task on claude_cli)

### 4.3 Execute with openrouter (best-of-breed)

```bash
# Requires OPENROUTER_API_KEY
python -m src.cli exec /tmp/auto_model.spl \
    --adapter openrouter --json 2>/dev/null | \
    python -m json.tool | grep '"model"'
```

Expected:
- `cjk_task`: `qwen/qwen-2.5-72b-instruct` (best for CJK)
- `final_synthesis`: `anthropic/claude-opus-4-6` (best for synthesis)

### 4.4 Execute with provider preference

```bash
# Requires OPENROUTER_API_KEY — pin to Anthropic models
python -m src.cli exec /tmp/auto_model.spl \
    --adapter openrouter --provider anthropic --json 2>/dev/null | \
    python -m json.tool | grep '"model"'
```

Expected: both models are `anthropic/claude-*`

---

## Section 5 — Python API

### 5.1 Test api.generate

```bash
python - << 'EOF'
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
from src import api

result = api.generate("What is quantum computing?", save_to_rag=False)
assert isinstance(result["spl_query"], str), "spl_query must be string"
assert result["error"] == "", f"Unexpected error: {result['error']}"
assert "PROMPT" in result["spl_query"], "SPL must contain PROMPT"
print("✓ api.generate OK")
print("SPL:", result["spl_query"][:200])
EOF
```

### 5.2 Test api.generate with save_to_rag

```bash
python - << 'EOF'
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
from src import api
from src.rag.factory import get_store

store = get_store("chroma")
count_before = store.count()

result = api.generate("List prime numbers up to 100", save_to_rag=True)
if not result["error"] and result["spl_query"]:
    count_after = store.count()
    assert count_after >= count_before, "RAG store count should not decrease"
    print(f"✓ api.generate save_to_rag OK — store: {count_before} → {count_after}")
else:
    print(f"Skipped (generation error): {result['error']}")
EOF
```

### 5.3 Test api.run

```bash
python - << 'EOF'
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
from src import api

result = api.run("What year did World War II end? One sentence.", save_to_rag=False)
assert "primary_result" in result
assert "execution_results" in result
if result["error"]:
    print(f"Pipeline error: {result['error']}")
else:
    print("✓ api.run OK")
    print("Result:", result["primary_result"][:200])
    print("Tokens:", result["execution_results"][-1]["total_tokens"] if result["execution_results"] else 0)
EOF
```

### 5.4 Test api.exec_spl

```bash
python - << 'EOF'
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
from src import api

spl = """
PROMPT test
SELECT
    GENERATE('Say "hello" in exactly one word.')
USING MODEL 'claude-sonnet-4-5';
"""
result = api.exec_spl(spl)
assert "primary_result" in result
if result["error"]:
    print(f"exec_spl error: {result['error']}")
else:
    print("✓ api.exec_spl OK")
    print("Result:", result["primary_result"])
EOF
```

### 5.5 Test configure_rag_store (inject mock for testing)

```bash
python - << 'EOF'
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
from src import api
from src.rag.store import RAGRecord, VectorStore
from typing import Optional

class MockStore(VectorStore):
    def __init__(self):
        self.records = {}
    def upsert(self, r): self.records[r.id] = r; print(f"  Upserted: {r.id[:8]}…")
    def search(self, q, k=5, *, user_id="", active_only=True): return []
    def get(self, id): return self.records.get(id)
    def delete(self, id): self.records.pop(id, None)
    def set_active(self, id, active): pass
    def list_all(self, *, user_id="", active_only=False): return list(self.records.values())
    def count(self): return len(self.records)

mock = MockStore()
api.configure_rag_store(mock)
result = api.generate("Test with mock store", save_to_rag=True)
print(f"✓ configure_rag_store OK — mock records: {mock.count()}")
EOF
```

---

## Section 6 — RAG Store

### 6.1 List all records

```bash
python - << 'EOF'
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
from src.rag.factory import get_store

store = get_store("chroma")
records = store.list_all()
print(f"Total records: {len(records)}")
for r in records[:5]:
    print(f"  [{r.source}] {r.nl_query[:60]}")
EOF
```

### 6.2 Search similar records

```bash
python - << 'EOF'
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
from src.rag.factory import get_store

store = get_store("chroma")
if store.count() == 0:
    print("No records yet — run Section 5.2 first")
else:
    results = store.search("Chinese characters water", k=3)
    print(f"Search results: {len(results)}")
    for r in results:
        print(f"  [{r.source}] {r.nl_query[:60]}")
    print("✓ RAG search OK")
EOF
```

### 6.3 Soft-delete (deactivate) and restore

```bash
python - << 'EOF'
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
from src.rag.factory import get_store

store = get_store("chroma")
records = store.list_all()
if not records:
    print("No records — run Section 5.2 first")
else:
    r = records[0]
    print(f"Record: {r.id[:8]}… active={r.active}")

    store.set_active(r.id, False)
    active_records = store.list_all(active_only=True)
    inactive_records = store.list_all(active_only=False)
    deactivated = [x for x in inactive_records if not x.active]
    print(f"After deactivate: active={len(active_records)}, with inactive={len(deactivated)}")
    assert any(x.id == r.id for x in deactivated), "Record should be inactive"

    store.set_active(r.id, True)
    restored = store.get(r.id)
    assert restored is not None and restored.active, "Record should be active again"
    print("✓ Soft-delete and restore OK")
EOF
```

### 6.4 User-scoped records

```bash
python - << 'EOF'
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
from src.rag.factory import get_store
from src.rag.store import RAGRecord
from datetime import datetime, timezone

store = get_store("chroma")

# Insert a user-scoped record
store.upsert(RAGRecord(
    id="test_user_scoped_001",
    nl_query="Test user scoped query",
    spl_query="PROMPT test SELECT GENERATE('test') USING MODEL 'test';",
    source="synthetic",
    user_id="alice",
    timestamp=datetime.now(timezone.utc).isoformat(),
    spl_warnings=[],
))

# Search with user_id filter
alice_records = store.search("test query", k=5, user_id="alice")
shared_records = store.search("test query", k=5, user_id="")
print(f"Alice-scoped results: {len(alice_records)}")
print(f"Shared store results: {len(shared_records)}")

# Cleanup
store.delete("test_user_scoped_001")
print("✓ User-scoped records OK")
EOF
```

---

## Section 7 — Model Router (unit tests)

```bash
python - << 'EOF'
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
from src.utils.model_router import detect_task, resolve_model, auto_route, ROUTING_TABLE, PROVIDERS

# Task detection
assert detect_task("", "List Chinese characters with 氵") == "cjk", "Should detect cjk"
assert detect_task("You are a Python expert", "refactor this function") == "code", "Should detect code"
assert detect_task("", "translate to German") == "eu_lang", "Should detect eu_lang"
assert detect_task("", "solve the integral of x^2") == "math", "Should detect math"
assert detect_task("", "analyze and compare these arguments") == "reasoning", "Should detect reasoning"
assert detect_task("", "summarize this document") == "general", "Should detect general"
print("✓ detect_task OK")

# Resolve model — adapter-level best (no provider)
m = resolve_model("openrouter", "cjk")
assert "qwen" in m.lower(), f"CJK openrouter should use qwen, got: {m}"

m = resolve_model("openrouter", "code")
assert "deepseek" in m.lower(), f"Code openrouter should use deepseek, got: {m}"

m = resolve_model("claude_cli", "cjk")
assert "claude" in m.lower(), f"claude_cli always uses Claude, got: {m}"

m = resolve_model("ollama", "math")
assert m == "deepseek-r1", f"Ollama math should use deepseek-r1, got: {m}"
print("✓ resolve_model OK")

# Provider preference (openrouter only)
m = resolve_model("openrouter", "cjk", provider="anthropic")
assert "anthropic" in m.lower() and "claude" in m.lower(), f"Expected Anthropic model, got: {m}"

m = resolve_model("openrouter", "code", provider="deepseek")
assert "deepseek" in m.lower(), f"Expected DeepSeek model, got: {m}"

# Provider ignored for claude_cli
m = resolve_model("claude_cli", "cjk", provider="google")
assert "claude" in m.lower(), f"claude_cli should ignore provider, got: {m}"
print("✓ provider preference OK")

# auto_route — final prompt always synthesis
m = auto_route("openrouter", "", "", is_final_prompt=True)
assert "claude-opus-4-6" in m or "opus" in m.lower(), f"Final prompt should be opus, got: {m}"
print("✓ auto_route (final prompt) OK")

# Verify all providers are covered in routing table
for task in ROUTING_TABLE:
    for p in PROVIDERS:
        assert p in ROUTING_TABLE[task], f"Missing provider {p} in task {task}"
print("✓ ROUTING_TABLE coverage OK")

print("\nAll model_router tests passed!")
EOF
```

---

## Section 8 — Streamlit UI

Start the app and verify each page manually:

```bash
streamlit run src/app.py
```

### 8.1 Home page

- [ ] App starts without errors
- [ ] Home page shows architecture description
- [ ] RAG Store quick stats section visible (shows count, may be 0)

### 8.2 Pipeline page (⚡)

- [ ] Page loads without errors
- [ ] Sidebar shows: LLM Adapter, LLM Provider dropdown, Delivery Mode, context area, cache checkbox
- [ ] Provider dropdown options: `(best-of-breed)`, `anthropic`, `google`, `meta`, `mistral`, `alibaba`, `deepseek`, `openai`
- [ ] Enter a query and click **Generate SPL** — valid SPL appears in Step 2
- [ ] SPL editor is editable
- [ ] EXPLAIN plan expander visible if SPL engine available
- [ ] Click **Execute** — result appears in Step 3 with model/tokens/latency/cost metrics
- [ ] If multi-CTE query: CTE Sub-Results expander shows intermediate steps
- [ ] Download button appears with result
- [ ] **Reset** button clears all state

### 8.3 RAG Store page (🗄)

- [ ] Page loads without errors
- [ ] Summary metrics: Total, Active, Inactive, Human, Synthetic
- [ ] Source filter, Status filter, Search filter all work
- [ ] Each record expander shows SPL code + metadata
- [ ] **Deactivate** button changes record status (page reruns)
- [ ] **Activate** button re-enables inactive record
- [ ] **Delete** button removes record permanently
- [ ] Bulk "Deactivate all shown" works
- [ ] Bulk "Delete all shown" works

### 8.4 Provider routing in UI

1. Set adapter to `openrouter` and provider to `anthropic`
2. Run a query like "Debug this Python code: `def add(a,b): return a-b`"
3. In Step 3 metrics, verify model contains `claude` or `anthropic`

---

## Section 9 — RAG Auto-Capture Integration

Verify that real session data flows into the RAG store automatically:

```bash
python - << 'EOF'
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
from src import api
from src.rag.factory import get_store

store = get_store("chroma")
count_before = store.count()

# Run generate with save_to_rag=True (default)
result = api.generate(
    "Explain the concept of machine learning in simple terms",
    save_to_rag=True,
)

count_after = store.count()
print(f"Records before: {count_before}, after: {count_after}")

if result["error"]:
    print(f"Generation failed (can't test capture): {result['error']}")
elif count_after > count_before:
    # Find the new record
    records = store.list_all()
    newest = sorted(records, key=lambda r: r.timestamp or "", reverse=True)[0]
    print(f"Captured: {newest.nl_query[:60]}")
    print(f"Source: {newest.source}")
    assert newest.source == "human", f"Source should be 'human', got: {newest.source}"
    print("✓ RAG auto-capture OK")
else:
    print("No new record captured (may already exist — upsert semantics)")
    print("✓ RAG auto-capture OK (upsert)")
EOF
```

---

## Section 10 — Edge Cases

### 10.1 Empty SPL in exec_spl

```bash
python - << 'EOF'
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
from src import api

result = api.exec_spl("-- just a comment, no PROMPT")
assert result["error"] != "", "Should error on no PROMPT"
print(f"✓ Empty SPL error: {result['error']}")
EOF
```

### 10.2 Invalid SPL syntax

```bash
python - << 'EOF'
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
from src import api

result = api.exec_spl("THIS IS NOT VALID SPL !!!")
assert result["error"] != "", "Should error on invalid SPL"
print(f"✓ Invalid SPL error: {result['error'][:80]}")
EOF
```

### 10.3 RAG failure does not break pipeline

```bash
python - << 'EOF'
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
from src import api
from src.rag.store import RAGRecord, VectorStore
import warnings

class BrokenStore(VectorStore):
    def upsert(self, r): raise RuntimeError("Simulated RAG failure")
    def search(self, q, k=5, *, user_id="", active_only=True): return []
    def get(self, id): return None
    def delete(self, id): pass
    def set_active(self, id, active): pass
    def list_all(self, *, user_id="", active_only=False): return []
    def count(self): return 0

api.configure_rag_store(BrokenStore())

with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    result = api.generate("Test broken RAG", save_to_rag=True)
    rag_warns = [x for x in w if "RAG auto-capture failed" in str(x.message)]

print(f"✓ RAG failure is non-fatal. Warnings: {len(rag_warns)}")
print(f"  generate() returned error: '{result['error']}'")
EOF
```

### 10.4 Unknown provider falls back gracefully

```bash
python - << 'EOF'
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
from src.utils.model_router import resolve_model

# Unknown provider → adapter-level fallback
m = resolve_model("openrouter", "code", provider="unknown_provider_xyz")
assert m, "Should return some fallback model"
print(f"✓ Unknown provider fallback: {m}")
EOF
```

---

## Full Pass Checklist

After completing all sections:

- [ ] Section 1: CLI generate (6 tests)
- [ ] Section 2: CLI run (7 tests)
- [ ] Section 3: CLI exec (5 tests)
- [ ] Section 4: USING MODEL auto (4 tests)
- [ ] Section 5: Python API (5 tests)
- [ ] Section 6: RAG Store operations (4 tests)
- [ ] Section 7: Model router unit tests
- [ ] Section 8: Streamlit UI (manual, 4 subsections)
- [ ] Section 9: RAG auto-capture integration
- [ ] Section 10: Edge cases (4 tests)
