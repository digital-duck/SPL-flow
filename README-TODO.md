# SPL-Flow — Feature TODO

## `splflow models` — OpenRouter model search

**Medium blog title**: *"I Asked 9 AI Models the Same Question About Nobel Prize Winners — Here's What a Query Language Revealed"*

---

**Problem**: Finding the exact model ID string for `--models` requires manually browsing openrouter.ai.

**Feature**: Add a `splflow models` subcommand that queries the OpenRouter `/models` endpoint and filters results by keyword — so users can search without leaving the terminal.

```bash
# Search by keyword (case-insensitive, matches id, name, or description)
splflow models claude
splflow models gemini
splflow models "mistral 7b"

# Example output
splflow models sonnet

  anthropic/claude-sonnet-4-5          Claude Sonnet 4.5         $3.00 / $15.00 per M tokens
  anthropic/claude-sonnet-4-5-20250929 Claude Sonnet 4.5 (snap)  $3.00 / $15.00 per M tokens
```

**Implementation sketch**:
- New `splflow models [KEYWORD]` command in `src/cli.py`
- `GET https://openrouter.ai/api/v1/models` (no auth required for listing)
- Filter rows where `KEYWORD` appears in `id`, `name`, or `description` (case-insensitive)
- Display: `id`, `name`, `pricing.prompt` / `pricing.completion` per M tokens
- `--adapter openrouter` flag (default) so the endpoint URL is consistent with the adapter config
- `--json` flag to dump raw filtered JSON for scripting

**Status**: ✅ Implemented (`src/cli.py` — `splflow models [KEYWORD]`)

---

## `splflow winner` — Pick the best model from a benchmark result

**Problem**: After running `splflow benchmark`, the user must manually inspect the JSON to
decide which model to use in production. This should be automated.

**Feature**: `splflow winner <benchmark.json>` reads the benchmark result and emits the
best model ID for a given optimisation metric — then optionally patches the `.spl` file.

```bash
# Print winning model ID for each metric
splflow winner results/spl_benchmark-v2.json

  Metric        Winner                         Value
  ─────────────────────────────────────────────────────
  accuracy      anthropic/claude-opus-4.6      (manual review needed)
  cost          z-ai/glm-4.6                   $0.35/M in
  latency       google/gemini-3-flash-preview  26.1s
  tokens        openai/gpt-4o-2024-11-20       3,956

# Pick by metric
splflow winner results/spl_benchmark-v2.json --by cost
# → z-ai/glm-4.6

splflow winner results/spl_benchmark-v2.json --by latency
# → google/gemini-3-flash-preview

# Patch a .spl file with the winner (replaces every USING MODEL '...')
splflow winner results/spl_benchmark-v2.json --by latency \
    --patch papers-by-top-prize-winners-recently_v1.spl \
    --out papers-by-top-prize-winners-recently_v2.spl
```

**Implementation sketch**:
- New `splflow winner BENCHMARK_JSON` command in `src/cli.py`
- Reads `runs[]` array from the benchmark JSON; skips runs with `"error"` set
- Metrics: `cost` = `cost_usd` (skip `null`), `latency` = `latency_ms`, `tokens` = `total_tokens`
- `--by [cost|latency|tokens]` selects the metric (default: prints all three)
- `--patch FILE` uses `patch_model()` from `src/nodes/benchmark.py` to rewrite the `.spl` file
- `--out FILE` writes the patched SPL (default: stdout)
- Exit code 0 with just the model ID when `--quiet` — useful for shell scripting:
  ```bash
  BEST=$(splflow winner result.json --by cost --quiet)
  splflow exec query.spl --adapter openrouter  # already patched
  ```

**Status**: ✅ Implemented (`src/cli.py` — `splflow winner BENCHMARK_JSON [--by METRIC] [--mark MODEL_ID] [--patch FILE] [--out FILE] [--quiet]`)

---

## `splflow benchmark` — robustness fix: non-JSON LLM responses

**Problem**: Some models (observed: `z-ai/glm-4.6`, Feb 2026) return responses that contain
control characters or truncated content, causing `json.JSONDecodeError` in the executor.
The run fails silently with `latency_ms: 0.0` and a cryptic parse error message.

**Error observed**:
```json
"error": "Expecting value: line 333 column 1 (char 1826)"
```

**Fix**: In `spl/adapters/openrouter.py`, wrap `response.json()` in a
`try/except json.JSONDecodeError`.  On failure, strip ASCII control characters
(U+0000–U+001F except `\t \n \r`, plus U+007F) from the raw response body and
retry `json.loads()` once.  Control characters embedded inside JSON string values
are the common cause — removing them restores a parseable document while preserving
the model's actual text content.

**Status**: ✅ Fixed (`spl/adapters/openrouter.py` — control-char sanitize + retry in `generate()`)

---

## `openrouter/auto` — precision-inference routing

**Observed behaviour** (Feb 2026 benchmark):
- `openrouter/auto` completed in 19.4s, 2,562 tokens, cost: `n/a`
- Correctly refused to fabricate citations; listed Turing winners accurately
- Covered only the CS domain — returned minimal output for physics/math
- Self-identified knowledge gap and suggested academic databases

**Use case**: `openrouter/auto` is best used for **routing benchmarks**, not quality
benchmarks. It picks the cheapest adequate model per call, not the most accurate.
For the prize-papers task (citation recall, domain expertise), it routed to a model
that was honest but incomplete — which is actually the correct failure mode.

**Precision-inference workflow** (planned):
```
1. splflow benchmark task.spl --models "modelA, modelB, modelC"  → benchmark.json
2. splflow winner benchmark.json --by cost                       → cheapest winner
3. Use winner model ID in production .spl file
4. Re-benchmark quarterly as models improve
```
The goal: pay Opus prices only when Opus is genuinely needed. For most tasks,
a $0.15/M model will suffice once identified via benchmark.
