# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

SPL-Flow is a Streamlit-based MVP that translates free-form natural language queries into [SPL (Structured Prompt Language)](https://github.com/digital-duck/SPL), routes sub-tasks to specialist LLMs in parallel via PocketFlow, and synthesizes a composed final response. It demonstrates a **Mixture-of-Models (MoM)** paradigm — routing each sub-task to the world's best specialist model (qwen2.5 for CJK, mistral for European languages, deepseek-coder for code, claude-sonnet for synthesis).

## Commands

### Run the Streamlit UI
```bash
streamlit run src/ui/streamlit/app.py
```

### CLI usage
```bash
# Translate NL to SPL (no execution)
python -m src.cli generate "List 10 Chinese characters with water radical"

# Full pipeline: NL → SPL → execute → result
python -m src.cli run "Summarize this article" --context-file article.txt --output result.md

# Execute a pre-written .spl file directly (bypasses Text2SPL)
python -m src.cli exec examples/query.spl --adapter ollama --param radical=水

# JSON output with full metrics
python -m src.cli exec query.spl --json > result.json

# Quiet mode (result only, for shell scripts)
python -m src.cli run "Explain X" --quiet --output answer.md
```

### Dependencies
```bash
pip install -r requirements.txt
# For local dev against the sibling SPL engine repo:
pip install -e /home/papagame/projects/digital-duck/SPL
```

### LLM Adapters
| Adapter | Setup |
|---------|-------|
| `claude_cli` (default) | Install Claude CLI; no API key needed |
| `openrouter` | `export OPENROUTER_API_KEY=...` |
| `ollama` | Run `ollama serve` locally |

## Architecture

### sys.path Dependency
`src/ui/streamlit/app.py`, `cli.py`, and some nodes insert hardcoded paths at startup:
```python
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")
```
The SPL engine (`spl` package) must be importable from one of these paths. It is a separate sibling repo at `/home/papagame/projects/digital-duck/SPL`.

### PocketFlow Graph (`src/flows/spl_flow.py`)
The entire pipeline is a PocketFlow graph with two variants:
- **`build_spl_flow()`** — full pipeline (text2spl → validate → execute → deliver)
- **`build_generate_only_flow()`** — preview only (text2spl → validate, no execution)

```
text2spl ──► validate ──► execute ──► sync_deliver
   ▲             │ "retry"     │ "sync"
   └─────────────┘             └──────► async_deliver
                 └─"error"──► sync_deliver (terminal)
```

### Shared Store
All nodes communicate via a single `shared` dict. Key fields:
- **Input**: `user_input`, `context_text`, `adapter`, `delivery_mode`, `spl_params`, `cache_enabled`
- **Text2SPL output**: `spl_query`, `retry_count`, `last_parse_error`
- **Validate output**: `spl_ast`, `spl_warnings`
- **Execute output**: `execution_results` (list of per-PROMPT dicts), `primary_result` (last PROMPT's content)
- **Delivery output**: `delivered`, `output_file`, `email_sent`
- **Errors**: `error` (fatal, terminates pipeline)

### Node Responsibilities
- **`Text2SPLNode`** (`src/nodes/text2spl.py`): Calls `claude_cli` adapter with few-shot prompt to translate NL → SPL. Always hardwired to `claude_cli` adapter regardless of sidebar selection (sidebar adapter is used for execution only). Strips markdown code fences from LLM output. Returns `"validate"`.
- **`ValidateSPLNode`** (`src/nodes/validate_spl.py`): Calls `spl.parse()` + `Analyzer`. Returns `"execute"` (valid), `"retry"` (invalid, under 3 attempts), or `"error"` (give up).
- **`ExecuteSPLNode`** (`src/nodes/execute_spl.py`): Runs the full SPL engine pipeline (`parse → analyze → optimize → execute`) using `asyncio.run()`. Registers `CREATE FUNCTION` statements before executing plans. Returns `"sync"` or `"async"` based on `delivery_mode`.
- **`SyncDeliverNode`** / **`AsyncDeliverNode`** (`src/nodes/deliver.py`): Sync is a pass-through. Async saves to `/tmp/spl_flow_result_<timestamp>.md`. Email is a placeholder (v0.2).

### SPL Templates (`src/utils/spl_templates.py`)
`get_text2spl_prompt()` builds the full few-shot prompt for the Text2SPL LLM call. It includes: SPL syntax reference, model routing guidelines, 3 worked examples (single-model, multi-CTE CJK+language, code review), and the user's query. On retry, it prepends the parse error with common fix hints.

### Execution Result Format
Each entry in `execution_results`:
```python
{
    "prompt_name": str,
    "content": str,
    "model": str,
    "input_tokens": int,
    "output_tokens": int,
    "total_tokens": int,
    "latency_ms": float,
    "cost_usd": float | None,
}
```
`primary_result` = `execution_results[-1]["content"]` (the final PROMPT's output).

## Important Constraints

- **`Text2SPLNode.exec()` is hardcoded to use `claude_cli`** for NL→SPL translation, regardless of the adapter selected in the UI/CLI. This is intentional — the sidebar adapter controls only the execution step.
- **Async mode email is a stub** — `email_sent` is always `False` in v0.1. SMTP integration is planned for v0.2.
- **`tests/` is empty** — no test suite exists yet. The architecture doc references `tests/test_flows.py` as planned.
- The SPL engine's internal `asyncio.gather()` handles parallel CTE dispatch. PocketFlow is used only at the orchestration layer, not inside the SPL engine.
