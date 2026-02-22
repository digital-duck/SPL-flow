# SPL-Flow — Feature Log

**Medium blog title**: *"I Asked 9 AI Models the Same Question About Nobel Prize Winners — Here's What a Query Language Revealed"*

---

## Implemented Features — Quick Reference

| Command | What it does | Status |
|:--------|:-------------|:------:|
| `splflow models [KEYWORD]` | Search OpenRouter models by keyword with live pricing | ✅ |
| `splflow benchmark FILE --models M1,M2,...` | Run one SPL against N models in parallel; save JSON | ✅ |
| `splflow winner BENCHMARK_JSON` | Pick best model by latency / cost / tokens / accuracy | ✅ |
| `splflow eval BENCHMARK_JSON --rubric TEXT` | Score each run with a judge LLM (0–10); enables `--by accuracy` | ✅ |
| `splflow report BENCHMARK_JSON` | Generate a markdown / CSV table ready for paper or blog | ✅ |
| `splflow rerun BENCHMARK_JSON --model ID` | Retry a failed run **or** add a brand-new model to existing benchmark | ✅ |
| `splflow cost FILE --models M1,M2,...` | Estimate benchmark cost before running (live OpenRouter pricing) | ✅ |
| OpenRouter robustness fix | Control-char sanitise + retry in `openrouter.py` so GLM-4.6 no longer fails | ✅ |

---

## Precision-Inference Workflow (fully autonomous)

```
1. splflow cost    task.spl  --models "opusX,gpt-4o,glm-5"          → budget check
2. splflow benchmark task.spl --models "opusX,gpt-4o,glm-5" \
       --adapter openrouter --output results/benchmark.json          → parallel runs
3. splflow eval    results/benchmark.json \
       --rubric "Citation accuracy: year, prize, paper title" \
       --judge anthropic/claude-opus-4.6 --adapter openrouter        → 0-10 scores
4. splflow winner  results/benchmark.json                            → full table
   splflow winner  results/benchmark.json --by accuracy              → best quality
   splflow winner  results/benchmark.json --by cost                  → cheapest
5. splflow winner  results/benchmark.json --by accuracy \
       --patch task.spl --out task-prod.spl                         → patch for prod
6. splflow rerun   results/benchmark.json --model z-ai/glm-5 \
       --adapter openrouter                                          → add new model
7. Re-benchmark quarterly as models improve
```

**Goal**: pay Opus prices only when Opus is genuinely needed.
For most tasks a $0.15/M model will suffice once identified via benchmark.

---

## Feature Details

---

### `splflow models` — OpenRouter model search

**Problem**: Finding the exact model ID string for `--models` requires manually browsing openrouter.ai.

**Feature**: Queries `GET https://openrouter.ai/api/v1/models` and filters by keyword — no browser needed.

```bash
splflow models claude
splflow models gemini
splflow models "glm"
splflow models sonnet --top 5

  anthropic/claude-sonnet-4-5          Claude Sonnet 4.5   $3.00  $15.00
  anthropic/claude-sonnet-4-5-20250929 Claude Sonnet 4.5   $3.00  $15.00
```

**Key options**: `KEYWORD` (case-insensitive, matches id/name/description), `--top N`, `--output FILE`

**Status**: ✅ Implemented (`src/cli.py` — `splflow models [KEYWORD] [--top N] [--output FILE]`)

---

### `splflow benchmark` — multi-model parallel execution

**Feature**: Runs the same `.spl` file against N models concurrently via `asyncio.gather`.
Wall-clock time ≈ slowest single model, not N × one model.

```bash
splflow benchmark query.spl \
    --models "anthropic/claude-opus-4.6,openai/gpt-4o,z-ai/glm-5,google/gemini-3-flash-preview" \
    --adapter openrouter \
    --output results/benchmark.json
```

Each run in the JSON captures: `model_id`, `response`, `input_tokens`, `output_tokens`,
`total_tokens`, `latency_ms`, `cost_usd`, `input_spl` (exact patched SPL used), `error`.

**Status**: ✅ Implemented (`src/cli.py`, `src/nodes/benchmark.py`, `src/flows/benchmark_flow.py`)

---

### `splflow winner` — pick best model from benchmark

**Feature**: Analyses `runs[]` and emits winners across four metrics.
Optionally patches a `.spl` file with the winning model.

```bash
# Full summary table (all metrics, ★ markers)
splflow winner results/benchmark.json

# Single metric (shell-script friendly)
splflow winner results/benchmark.json --by latency
splflow winner results/benchmark.json --by accuracy   # requires splflow eval first
BEST=$(splflow winner results/benchmark.json --by cost --quiet)

# Record human choice back into JSON
splflow winner results/benchmark.json --mark anthropic/claude-opus-4.6

# Patch .spl file with winning model
splflow winner results/benchmark.json --by accuracy \
    --patch task_v1.spl --out task_v2.spl
```

**Metrics**: `latency` (fastest), `tokens` (most efficient), `cost` (cheapest),
`value` (tokens per dollar), `accuracy` (highest eval score — requires `splflow eval`).

**Status**: ✅ Implemented (`src/cli.py` — `splflow winner BENCHMARK_JSON [--by METRIC] [--mark MODEL_ID] [--patch FILE] [--out FILE] [--quiet]`)

---

### `splflow eval` — automated accuracy scoring

**Problem**: Latency, cost, and tokens are auto-computed, but **accuracy still requires manual review**.

**Feature**: Sends each model's response to a judge LLM with a task-specific rubric.
Returns a 0–10 score + reasoning. Scores are written back into the benchmark JSON,
enabling `splflow winner --by accuracy` to complete the full autonomous loop.

```bash
splflow eval results/benchmark.json \
    --rubric "Citation accuracy: correct year, correct prize, correct paper title (1 pt each)" \
    --judge anthropic/claude-opus-4.6 \
    --adapter openrouter

# Output
  anthropic/claude-opus-4.6        9.5/10
  google/gemini-3-pro-preview      8.0/10
  openai/gpt-4o-2024-11-20         7.5/10
  google/gemini-3-flash-preview    7.0/10
  moonshotai/kimi-k2               6.0/10
  qwen/qwen3-235b-a22b             5.5/10

Eval scores written to: results/benchmark.json
```

All judge calls run in parallel (`asyncio.gather`) — same wall-clock pattern as benchmark.
Score + reasoning stored under `runs[i]["eval"]` for audit.

**Key options**: `--rubric TEXT`, `--rubric-file FILE`, `--judge MODEL_ID`, `--adapter`, `--quiet`

**Status**: ✅ Implemented (`src/cli.py` — `splflow eval BENCHMARK_JSON --rubric TEXT [--rubric-file FILE] [--judge MODEL_ID] [--adapter]`)

---

### `splflow report` — publication-ready tables

**Feature**: Converts a benchmark JSON into a formatted table for papers, blog posts, or READMEs.
Auto-adds an **Accuracy** column when `splflow eval` has been run.

```bash
splflow report results/benchmark.json
splflow report results/benchmark.json --format csv --output benchmark.csv
splflow report results/benchmark.json --output table.md
```

**Markdown output example**:
```markdown
## Benchmark: 232b425d
**Date**: 2026-02-16  |  **Adapter**: openrouter

| Model | Tokens | Latency | Accuracy | Status |
|:---|---:|---:|---:|---:|
| `anthropic/claude-opus-4.6` | 5,854 | 70.2s | 9.5/10 | ✅ |
| `openai/gpt-4o-2024-11-20` | 3,956 | 28.4s | 7.5/10 | ✅ |
| `z-ai/glm-4.6` | — | — | — | ❌ `parse error` |

**Winners:**
- Fastest: `google/gemini-3-flash-preview` (26.12s)
- Most accurate: `anthropic/claude-opus-4.6` (9.5/10)
```

**Key options**: `--format [markdown|csv]`, `--output FILE`

**Status**: ✅ Implemented (`src/cli.py` — `splflow report BENCHMARK_JSON [--format markdown|csv] [--output FILE]`)

---

### `splflow rerun` — retry or add a model

**Feature**: Two modes in one command:

- **Retry mode** — model already in JSON: re-runs with identical patched SPL, replaces entry.
  Useful after a bug fix (e.g. the GLM control-char fix) without re-running all models.

- **Add-new mode** — model not yet in JSON: patches the SPL from an existing run's template,
  appends a fresh entry. Useful for testing a new model against the same benchmark task.

```bash
# Retry a failed GLM run after the robustness fix
splflow rerun results/benchmark.json --model z-ai/glm-4.6 --adapter openrouter

# Add GLM-5 to an existing benchmark without re-running everyone
splflow rerun results/benchmark.json --model z-ai/glm-5 --adapter openrouter

# Output (add-new mode)
Running z-ai/glm-5  [new model  (patched from template: anthropic/claude-opus-4.6)]
  tokens=4,210  latency=18.3s  cost=n/a  wall=19.1s
Appended run in: results/benchmark.json
```

**Status**: ✅ Implemented (`src/cli.py` — `splflow rerun BENCHMARK_JSON --model MODEL_ID [--adapter] [--provider] [--quiet]`)

---

### `splflow cost` — pre-flight cost estimate

**Feature**: Fetches live pricing from the OpenRouter API and projects cost per model
based on the SPL file's token count plus an expected output token estimate.
Helps budget before a multi-model benchmark run.

```bash
splflow cost query.spl \
    --models "anthropic/claude-opus-4.6,openai/gpt-4o,z-ai/glm-5,google/gemini-3-flash-preview" \
    --output-tokens 4000

  SPL file      : query.spl
  Input tokens  : ~1,273  (prompt estimate)
  Output tokens : ~4,000  (your estimate)

  Model                                         Input $/M  Output $/M    Est. Cost
  ─────────────────────────────────────────────────────────────────────────────────
  anthropic/claude-opus-4.6                         $5.00      $25.00     $0.10637
  openai/gpt-4o-2024-11-20                          $2.50      $10.00     $0.04318
  google/gemini-3-flash-preview                     $0.50       $3.00     $0.01264
  z-ai/glm-5                                        $0.30       $2.55     $0.01101

  Total estimated cost (excluding free/auto): $0.17320
```

**Key options**: `--models M1,M2,...`, `--input-tokens N` (override auto-count), `--output-tokens N`

**Status**: ✅ Implemented (`src/cli.py` — `splflow cost SPL_FILE [--models M1,M2,...] [--input-tokens N] [--output-tokens N]`)

---

### OpenRouter robustness fix — non-JSON LLM responses

**Problem**: Some models (observed: `z-ai/glm-4.6`, Feb 2026) embed raw control characters
inside their response content. Python's `json` parser rejects these, causing the entire
benchmark run to fail with a cryptic error.

**Error observed**:
```json
"error": "Expecting value: line 333 column 1 (char 1826)"
```

**Fix**: In `spl/adapters/openrouter.py`, wrapped `response.json()` in
`try/except json.JSONDecodeError`. On failure, strips ASCII control chars
(U+0000–U+0008, U+000B–U+000C, U+000E–U+001F, U+007F) from the raw
response body and retries `json.loads()` once. Only raises a clear
`RuntimeError` if sanitised text is still unparseable.

**Status**: ✅ Fixed (`spl/adapters/openrouter.py` — control-char sanitize + retry in `generate()`)

---

### `openrouter/auto` — routing benchmark observations

**Observed behaviour** (Feb 2026 benchmark):
- Completed in 19.4s, 2,562 tokens, cost: `n/a` (billed at underlying model rate)
- Correctly refused to fabricate citations; listed Turing winners accurately
- Covered only CS domain — returned minimal output for physics/math
- Self-identified knowledge gap and suggested academic databases

**Use case**: `openrouter/auto` is best for **routing benchmarks** (cheapest adequate model),
not quality benchmarks. For the prize-papers task it routed to an honest-but-incomplete
model — which is actually the correct failure mode: better to return less than to hallucinate.

---

## Planned Features

### Google SSO — User Login

**Context**: Sessions and benchmark runs are now persisted to SQLite (`data/splflow.db`).
The `sessions` table already records `created_at`, `model`, and all metrics.
Adding per-user identity is a single schema change:

```sql
ALTER TABLE sessions ADD COLUMN user_id TEXT;
ALTER TABLE benchmark_runs ADD COLUMN user_id TEXT;
```

**Approach options**:

| Option | Pros | Cons |
|--------|------|------|
| `streamlit-google-oauth` | Drop-in Streamlit component, minimal boilerplate | Less control over token handling |
| Thin FastAPI auth layer in front of Streamlit | Full control, reusable for future API | More infrastructure |

**Recommended path (v0.2)**:
1. Add `streamlit-google-oauth` for quick MVP login
2. Migrate to FastAPI OAuth proxy when multi-tenant isolation is needed

**Impact on existing code**: All pages import `page_helpers.render_sidebar()` —
user identity can be injected there once and passed down to every `save_session()` /
`save_benchmark()` call. No page-level changes needed beyond reading `user_id` from sidebar context.

**Status**: 📋 Planned — SQLite schema ready for `user_id` column when SSO is wired up.

---

### Model Configuration Verification — Capability & Cost Balance

**Context**: Review `/home/papagame/projects/digital-duck/SPL-flow/data/model_settings.yaml` to ensure balanced model selection across all adapters.

**Verification Matrix**: For each adapter, verify coverage across:

**📋 Capability Dimensions:**
- `general` — General-purpose reasoning and tasks
- `coding` — Software development, programming, code generation
- `math` — Mathematical reasoning, calculations, proofs
- `reasoning` — Complex logical reasoning, chain-of-thought
- `multilingual` — CJK languages, European languages, global support

**💰 Cost Tiers:**
- `top-tier` — Premium flagship models (Claude Opus, GPT-5.2)
- `low-cost` — Affordable older models (GPT-4o Mini, Gemini Flash, Haiku)
- `no-cost` — Free/open-source offerings (Ollama lineup, free API tiers)

**Current Gaps Identified:**
- **cloud_direct**: Missing CJK/EU multilingual specialists, limited math models
- **claude_cli**: Anthropic-only limits math and multilingual coverage
- **openrouter**: Could use more dedicated math specialists
- **ollama**: Good coverage but lacks recent flagship models (by design)

**Action Items:**
1. [ ] Verify each adapter has at least 1 model per capability dimension
2. [ ] Verify each adapter covers all 3 cost tiers (where applicable)
3. [ ] Add missing math models to cloud_direct (consider GPT-4o for math tasks)
4. [ ] Research multilingual model availability for cloud_direct
5. [ ] Document cost tier classifications in YAML comments

**Status**: 📋 Pending Verification — Manual review of model_settings.yaml balance
