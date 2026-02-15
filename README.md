# SPL-Flow

**Declarative LLM Orchestration — powered by SPL + PocketFlow**

SPL-Flow is a Streamlit-based MVP that translates free-form natural language queries into [SPL (Structured Prompt Language)](https://github.com/digital-duck/SPL), routes sub-tasks to specialist language models in parallel, and synthesizes a composed final response — either inline (sync) or saved to file (async).

---

## Architecture

```
User Query (free-form text)
        │
        ▼
  ┌─────────────┐
  │  Text2SPL   │  LLM translates NL → SPL syntax
  │   Node      │◄── retry on parse failure (up to 3x)
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
  │   Node      │  (parallel CTE dispatch via asyncio)
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

*Email delivery: SMTP integration planned for v0.2.

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
```

`requirements.txt`:
```
pocketflow
streamlit>=1.32
httpx>=0.25
spl-llm
```

### 2. Run the Streamlit UI

```bash
streamlit run src/app.py
```

### 3. Use the CLI (for batch testing / scripting)

```bash
# Translate a query to SPL (no LLM execution)
python -m src.cli generate "List 10 Chinese characters with water radical"

# Full pipeline: NL → SPL → execute → result
python -m src.cli run "Summarize this article" --context-file article.txt --output result.md

# Execute a pre-written .spl file directly (best for batch testing)
python -m src.cli exec examples/query.spl --adapter ollama --param radical=水

# Pipe queries from a file
cat queries.txt | python -m src.cli run - --adapter openrouter

# JSON output (structured, includes tokens/latency/cost per sub-prompt)
python -m src.cli exec query.spl --json > result.json

# Quiet mode (result only, no status messages — ideal for shell scripts)
python -m src.cli run "Explain quantum entanglement" --quiet --output answer.md
```

The app expects the SPL engine to be importable. It is resolved via `sys.path` inserts in `app.py`:

```python
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
```

### 3. Use the app

| Step | Action |
|------|--------|
| **Step 1** | Type your query in the text area and click **Generate SPL** |
| **Step 2** | Review the generated SPL, optionally edit it, then click **Execute** |
| **Step 3** | See the composed result with model, tokens, latency, and cost metrics |

---

## LLM Adapters

Select the adapter in the sidebar:

| Adapter | Description | Setup |
|---------|-------------|-------|
| `claude_cli` | Local Claude CLI (subscription) | Install Claude CLI; no API key needed |
| `openrouter` | 100+ models via OpenRouter API | `export OPENROUTER_API_KEY=...` |
| `ollama` | Local models (qwen2.5, mistral, etc.) | `ollama serve` running locally |

SPL auto-routes sub-tasks based on `USING MODEL` directives in the generated SPL:

| Domain | Default model |
|--------|--------------|
| CJK characters | `qwen2.5` |
| European languages | `mistral` |
| Code generation | `deepseek-coder` |
| Synthesis / reasoning | `anthropic/claude-sonnet-4-5` |

---

## Project Structure

```
SPL-Flow/
├── README.md
├── requirements.txt
├── docs/
│   └── startup/
│       └── architecture.md      # Full design doc with roadmap
├── src/
│   ├── app.py                   # Streamlit UI entry point
│   ├── cli.py                   # Click CLI (generate / run / exec)
│   ├── flows/
│   │   └── spl_flow.py          # PocketFlow graph builder + run helpers
│   ├── nodes/
│   │   ├── text2spl.py          # Text2SPL node (NL → SPL)
│   │   ├── validate_spl.py      # Parse + semantic validation node
│   │   ├── execute_spl.py       # SPL engine execution node
│   │   └── deliver.py           # Sync + Async delivery nodes
│   └── utils/
│       └── spl_templates.py     # TEXT2SPL_SYSTEM_PROMPT + few-shot examples
└── tests/
```

---

## Delivery Modes

### Sync mode (default)
Result rendered in the Streamlit UI with full metrics. Download button available.

### Async mode
Result saved to `/tmp/spl_flow_result_<timestamp>.md` with download button.
Email delivery is a placeholder — configure SMTP in v0.2.

---

## Design Philosophy

**human×AI** — multiplicative, not additive.

SPL-Flow separates concerns cleanly:

- **SPL engine** (in `/SPL`): deterministic, tested, no workflow library needed
- **SPL-Flow orchestration** (here): agentic, retry-capable, PocketFlow-based
- **Streamlit UI**: minimal, three-step, no hidden state

---

## Roadmap

| Version | Focus |
|---------|-------|
| **v0.1 MVP** | Text2SPL → Validate → Execute → Sync/Async deliver (current) |
| **v0.2** | SMTP email delivery, result history, OpenRouter cost tracking |
| **v0.3** | Multi-turn conversation, SPL template library, user accounts |
| **Platform** | Team workspaces, scheduled jobs, API gateway |
