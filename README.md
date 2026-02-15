# SPL-Flow

**Declarative LLM Orchestration — AI Symphony via SPL + PocketFlow**

SPL-Flow is a platform that translates free-form natural language into [SPL (Structured Prompt Language)](https://github.com/digital-duck/SPL), routes each sub-task to the world's best specialist language model in parallel, and synthesizes a composed final response — an **AI Symphony** where each model plays the instrument it does best.

---

## The Vision: AI Symphony

Traditional AI tools call a single general-purpose model for every task. SPL-Flow follows a **Mixture-of-Models (MoM)** paradigm — the same way a symphony orchestra assigns each instrument to the right player, SPL-Flow assigns each cognitive sub-task to the right specialist LLM:

| Task | Specialist | Why |
|------|-----------|-----|
| CJK characters (Chinese / Japanese / Korean) | `qwen/qwen-2.5-72b-instruct` | Leads C-Eval, CMMLU, JP-LMEH |
| European languages (translate, etc.) | `mistralai/mistral-large-2411` | Leads EU multilingual MT-Bench |
| Code generation / review / debugging | `deepseek/deepseek-coder-v2` | Leads HumanEval, SWE-bench |
| Math / science / proofs | `deepseek/deepseek-r1` | Leads MATH, AIME, GPQA |
| Long-form reasoning / analysis | `anthropic/claude-opus-4-6` | Leads MMLU-Pro reasoning |
| Synthesis / composition (final output) | `anthropic/claude-opus-4-6` | Coherent long-form writing |

Just write `USING MODEL auto` in your SPL and the system automatically routes to the optimal model.

---

## What's New (2026-02)

### API-First Architecture
`src/api.py` is the **first-class public interface** — enabling system-to-system integration, agent-to-agent workflows, testing, and automation. The CLI and Streamlit UI are thin wrappers over three core functions:

```python
from src import api

# Translate NL to SPL (preview, no execution)
result = api.generate("List 10 Chinese characters with water radical")

# Full pipeline: NL → SPL → validate → execute → deliver
result = api.run("Summarize this article", context_text=doc, adapter="openrouter")

# Execute pre-written SPL directly (batch / agent-to-agent)
result = api.exec_spl(spl_query, adapter="ollama", provider="deepseek")
```

### RAG Context Store (ChromaDB)
Every valid (NL query, SPL) pair from real sessions is automatically captured to a ChromaDB vector store — **gold-standard human-labeled data** that improves future SPL generation via dynamic few-shot retrieval.

- **Digital twin flywheel**: more usage → more captured pairs → better retrieval → better SPL → tighter human-AI partnership
- **Data quality tiers**: `human` (gold, from sessions) > `edited` (gold+, user-corrected) > `synthetic` (silver, generated offline)
- **Human-in-the-loop curation** via the RAG Store Streamlit page: review, deactivate noise, delete errors

### USING MODEL auto + LLM Provider
Write `USING MODEL auto` in any SPL PROMPT and the model router automatically classifies the task (cjk / code / eu_lang / math / reasoning / synthesis) and resolves to the best specialist model.

**LLM Provider preference** lets orgs or users pin auto-routing to a specific provider's models:

```
# Company policy = "we use Anthropic"
api.run(query, adapter="openrouter", provider="anthropic")
# → every USING MODEL auto resolves to the best Claude model for that task
```

Provider preference only takes effect with `openrouter` (which can reach all providers). With `claude_cli` or `ollama`, the adapter-level best is used regardless.

### Multi-Page Streamlit UI
The app now uses Streamlit's `pages/` multi-page pattern:

| Page | Purpose |
|------|---------|
| `app.py` (Home) | Architecture overview, RAG stats, recent captures |
| `1_Pipeline.py` | Three-step pipeline: generate → review → execute |
| `2_RAG_Store.py` | Review, curate, and manage the RAG context store |

---

## Architecture

```
User Query (free-form text)
        │
        ▼
  ┌─────────────┐
  │  Text2SPL   │  claude_cli LLM translates NL → SPL syntax
  │   Node      │  + RAG retrieval (dynamic few-shot examples)
  │             │◄── retry on parse failure (up to 3x)
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │  Validate   │  SPL parse + semantic analysis
  │   Node      │──► retry ──► Text2SPL
  └──────┬──────┘
         │ "execute"
         ▼
  ┌─────────────┐
  │   Execute   │  parse → analyze → optimize → run
  │   Node      │  USING MODEL auto → model router → specialist LLM
  │             │  (parallel CTE dispatch via asyncio)
  └──────┬──────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
  Sync      Async
 Deliver   Deliver
(inline)  (/tmp file
           + email*)
```

*Email: SMTP integration planned for v0.2.

**PocketFlow graph:**

```python
text2spl >> validate
validate - "execute" >> execute
validate - "retry"   >> text2spl
validate - "error"   >> sync_deliver
execute  - "sync"    >> sync_deliver
execute  - "async"   >> async_deliver
execute  - "error"   >> sync_deliver
```

---

## Quickstart

### 1. Install dependencies

```bash
cd /home/papagame/projects/digital-duck/SPL-Flow
pip install -r requirements.txt
# For local dev against the sibling SPL engine repo:
pip install -e /home/papagame/projects/digital-duck/SPL
```

### 2. Run the Streamlit UI

```bash
streamlit run src/app.py
```

### 3. Use the CLI

```bash
# Translate a query to SPL (preview, no LLM execution)
python -m src.cli generate "List 10 Chinese characters with water radical"

# Full pipeline with provider preference
python -m src.cli run "Analyze this article" \
    --context-file article.txt \
    --adapter openrouter \
    --provider anthropic \
    --output result.md

# Execute a pre-written .spl file directly
python -m src.cli exec examples/query.spl \
    --adapter ollama \
    --param radical=水

# JSON output (full metrics: tokens, latency, cost)
python -m src.cli exec query.spl --json > result.json

# Quiet mode (result only — ideal for shell scripts)
python -m src.cli run "Explain X" --quiet --output answer.md

# Pipe from stdin
echo "Summarize the top 3 points" | python -m src.cli run -
```

---

## LLM Adapters

| Adapter | Description | Setup |
|---------|-------------|-------|
| `claude_cli` (default) | Local Claude CLI | Install Claude CLI; no API key needed |
| `openrouter` | 100+ models via OpenRouter API | `export OPENROUTER_API_KEY=...` |
| `ollama` | Local models (qwen2.5, mistral, etc.) | `ollama serve` running locally |

**Note:** `Text2SPLNode` always uses `claude_cli` for NL→SPL translation regardless of adapter selection. The adapter setting controls only the execution step.

---

## Model Router

The routing table (`src/utils/model_router.py`) maps `(task × provider/adapter)` to concrete model names, sourced from HuggingFace Open LLM Leaderboard v2, LMSYS Chatbot Arena, and task-specific benchmarks (2026-02).

### Task classification (heuristic, zero-cost)

| Keyword / signal | Task |
|-----------------|------|
| CJK characters in text, or words like "chinese", "japanese", "kanji" | `cjk` |
| "code", "function", "python", "refactor", "debug", "sql" | `code` |
| "german", "french", "translate", "übersetz" | `eu_lang` |
| "math", "equation", "proof", "calculate", "integral" | `math` |
| "analyze", "compare", "reason", "argue", "infer" | `reasoning` |
| Final PROMPT in a multi-PROMPT query | `synthesis` |
| Everything else | `general` |

### Provider resolution

```
openrouter + provider set → pick provider's best model for task
openrouter + no provider  → pick best-of-breed for task
claude_cli / ollama       → adapter-level best (provider ignored)
```

---

## RAG Context Store

### Auto-capture
Every valid (NL query, SPL) pair is automatically saved to ChromaDB with metadata:
- `source`: `"human"` (from real sessions), `"edited"` (user-corrected), `"synthetic"` (generated offline)
- `user_id`: scope records per user (default: shared store)
- `active`: soft-delete flag — inactive records are excluded from retrieval but not deleted
- `timestamp`: ISO 8601 UTC

### Dynamic few-shot retrieval
When translating a new query, the top-5 most similar historical pairs are retrieved by cosine similarity and injected into the Text2SPL prompt as dynamic few-shot examples — more accurate than static hardcoded examples.

### Streamlit curation UI
The **RAG Store** page lets you:
- View all captured pairs with source, adapter, and timestamp
- Filter by source (human / edited / synthetic), status (active / inactive), and keyword
- **Deactivate** records (soft-delete, reversible) to exclude noise from retrieval
- **Activate** previously deactivated records
- **Delete** records permanently
- Bulk actions: deactivate all shown / delete all shown

### Python API
```python
from src.rag.factory import get_store
store = get_store("chroma")                  # default: ./data/rag

# Search top-5 similar pairs
records = store.search("Chinese characters water radical", k=5)

# Upsert a record
from src.rag.store import RAGRecord
store.upsert(RAGRecord(id="abc", nl_query="...", spl_query="...", source="human"))

# Soft-delete (exclude from retrieval)
store.set_active(record_id, False)

# Per-user store
store = get_store("chroma", collection_name="spl_rag_alice")
```

---

## Project Structure

```
SPL-Flow/
├── README.md
├── README-TEST.md             # Step-by-step testing guide
├── requirements.txt
├── .gitignore
├── data/                      # ChromaDB persist dir (gitignored)
│   └── rag/
├── src/
│   ├── api.py                 # ★ Public API (first-class interface)
│   ├── app.py                 # Streamlit Home page
│   ├── cli.py                 # Click CLI (generate / run / exec)
│   ├── flows/
│   │   └── spl_flow.py        # PocketFlow graph builder
│   ├── nodes/
│   │   ├── text2spl.py        # NL → SPL (+ RAG few-shot retrieval)
│   │   ├── validate_spl.py    # Parse + semantic validation
│   │   ├── execute_spl.py     # SPL engine execution + model auto-routing
│   │   └── deliver.py         # Sync + Async delivery
│   ├── pages/
│   │   ├── 1_Pipeline.py      # Three-step pipeline page
│   │   └── 2_RAG_Store.py     # RAG context store curation page
│   ├── rag/
│   │   ├── store.py           # RAGRecord dataclass + VectorStore ABC
│   │   ├── chroma_store.py    # ChromaDB backend (default)
│   │   ├── faiss_store.py     # FAISS backend (local fallback)
│   │   └── factory.py         # get_store() factory
│   └── utils/
│       ├── model_router.py    # ROUTING_TABLE + detect_task + auto_route
│       ├── page_helpers.py    # Shared sidebar, session state, RAG cache
│       └── spl_templates.py  # Text2SPL few-shot prompt builder
└── tests/                     # (planned — see README-TEST.md)
```

---

## API Reference

### `api.generate(query, context_text="", *, save_to_rag=True, user_id="") → GenerateResult`

Translate NL → SPL without executing. Safe to call for preview and testing.

```python
{
    "spl_query":    str,    # generated SPL
    "spl_warnings": list,   # parser/analyzer warnings
    "retry_count":  int,    # LLM call attempts
    "error":        str,    # non-empty if failed
}
```

### `api.run(query, *, adapter, provider, delivery_mode, ...) → RunResult`

Full pipeline: NL → SPL → validate → execute → deliver.

```python
{
    "spl_query":         str,
    "spl_warnings":      list,
    "primary_result":    str,           # final PROMPT content
    "execution_results": list[dict],    # per-PROMPT metrics
    "output_file":       str,           # async mode only
    "email_sent":        bool,
    "delivered":         bool,
    "error":             str,
}
```

### `api.exec_spl(spl_query, *, adapter, provider, spl_params, cache_enabled) → ExecResult`

Execute pre-written SPL directly (no NL→SPL step).

```python
{
    "primary_result":    str,
    "execution_results": list[dict],
    "error":             str,
}
```

Each `execution_results` entry:
```python
{
    "prompt_name":  str,
    "content":      str,
    "model":        str,
    "input_tokens": int,
    "output_tokens": int,
    "total_tokens": int,
    "latency_ms":   float,
    "cost_usd":     float | None,
}
```

---

## Delivery Modes

| Mode | Behavior |
|------|---------|
| `sync` (default) | Result rendered in UI / printed to stdout immediately |
| `async` | Result saved to `/tmp/spl_flow_result_<timestamp>.md`; download button shown |

---

## Design Philosophy

**human×AI** — multiplicative, not additive.

SPL-Flow is modeled after **Data Copilot** (a RAG app for data professionals), generalized into a platform for any LLM user. The key principles:

- **API-first**: every capability is accessible programmatically — no UI required
- **Declarative**: SPL separates *what* to compute from *how* to compute it
- **Mixture-of-Models**: routing the right task to the right specialist beats a single monolithic model
- **Human-in-the-loop**: real usage data (captured as RAG records) continuously improves the system — the more you use it, the better it gets
- **Digital twin flywheel**: personal usage data → personalized retrieval → personalized responses

---

## Roadmap

| Version | Focus |
|---------|-------|
| **v0.1 MVP** | API-first, Text2SPL+RAG, MoM routing, multi-page UI (current) |
| **v0.2** | SMTP email delivery, result history, OpenRouter cost tracking |
| **v0.3** | Multi-turn conversation, SPL template library, user accounts |
| **v0.4** | Team workspaces, scheduled jobs, API gateway, digital twin profiles |
| **Platform** | Per-user RAG collections, fine-tuned Text2SPL, SPL marketplace |
