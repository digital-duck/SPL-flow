"""SPL-Flow Click CLI — thin wrapper over src.api for batch/scripting use.

All business logic lives in src/api.py.  This module handles only:
  - CLI argument parsing and validation
  - Reading files / stdin
  - Formatting and printing output
  - Saving results to disk

Usage:
    python -m src.cli generate "List 10 Chinese characters with water radical"
    python -m src.cli run "Summarize this article" --context-file article.txt
    python -m src.cli exec query.spl --adapter ollama --param radical=水

    python -m src.cli run "Explain X" --json > result.json
    python -m src.cli run "Explain X" --quiet --output answer.md
"""
import sys
import json
import re
import time
import asyncio

from pathlib import Path
sys.path.insert(0, Path.home() / "projects/digital-duck/SPL")
sys.path.insert(0, Path.home() / "projects/digital-duck/SPL-flow")
import click



from src import api
from src.utils.logging_config import setup_logging, bridge_spl_logger


# ── Helpers ────────────────────────────────────────────────────────────────────

def _init_logging(
    run_name: str,
    *,
    log_file: str | None,
    adapter: str = "",
    log_level: str = "debug",
) -> Path:
    """Configure dd_logging and return the path of the created log file.

    Configures both the spl_flow.* logger hierarchy (SPL-Flow orchestration)
    AND the spl.* hierarchy (SPL engine / adapters) so that adapter-level
    debug output (e.g. raw HTTP responses) lands in the same log file.

    If *log_file* is given its stem becomes the run_name and its parent the
    log_dir, so the auto-timestamped file lands where the user expects.
    """
    if log_file:
        p = Path(log_file)
        log_path = setup_logging(
            p.stem,
            adapter=adapter,
            log_level=log_level,
            log_dir=p.parent if str(p.parent) not in (".", "") else None,
        )
    else:
        log_path = setup_logging(run_name, adapter=adapter, log_level=log_level)

    # Bridge the spl.* logger (SPL engine + adapters) to the same file handler.
    # setup_logging() configures spl_flow.* only; openrouter.py logs to
    # spl.adapters.openrouter which is a different hierarchy and would otherwise
    # go nowhere.
    bridge_spl_logger(log_path, log_level)
    return log_path


# ── Shared option decorators ───────────────────────────────────────────────────

def adapter_option(f):
    from src.config import get_default_adapter
    return click.option(
        "--adapter", "-a",
        default=get_default_adapter,   # callable: re-evaluated at runtime from splflow.yaml
        show_default=True,
        type=click.Choice(["ollama", "openrouter", "cloud_direct", "claude_cli"]),
        help="LLM adapter to use for execution.",
    )(f)


def param_option(f):
    return click.option(
        "--params", "-p",
        default="",
        metavar="K=V,...",
        help=(
            "SPL context params as comma-separated key=value pairs. "
            "E.g. --params 'radical=水,topic=AI'  "
            "Both comma and space delimiters are accepted."
        ),
    )(f)


def context_file_option(f):
    return click.option(
        "--context-file", "-c",
        type=click.Path(exists=True, readable=True),
        default=None,
        help="Path to a reference document to inject as context.document.",
    )(f)


def provider_option(f):
    return click.option(
        "--provider",
        default="",
        metavar="PROVIDER",
        type=click.Choice(
            ["", "anthropic", "google", "meta", "mistral", "alibaba", "deepseek", "openai"],
            case_sensitive=False,
        ),
        help=(
            "LLM provider preference for USING MODEL auto (openrouter adapter only). "
            "E.g. --provider anthropic pins every auto-routed PROMPT to the best Anthropic model."
        ),
    )(f)


def cache_option(f):
    return click.option(
        "--cache",
        is_flag=True,
        default=False,
        help="Enable SQLite result cache (off by default).",
    )(f)


def output_option(f):
    return click.option(
        "--output", "-o",
        type=click.Path(writable=True),
        default=None,
        help="Save result to this file. Format inferred from extension: "
             ".json → full JSON, anything else → markdown.",
    )(f)



def quiet_flag(f):
    return click.option(
        "--quiet", "-q",
        is_flag=True,
        default=False,
        help="Suppress banners and status messages; print only the result.",
    )(f)


def log_options(f):
    """Attach --log and --log-level options."""
    f = click.option(
        "--log",
        "log_file",
        default=None,
        metavar="FILE",
        help=(
            "Log file path — stem used as run label, timestamped file created. "
            "Omit to auto-generate under logs/. "
            "E.g. --log ./runs/benchmark.log"
        ),
    )(f)
    f = click.option(
        "--log-level",
        default="debug",
        show_default=True,
        type=click.Choice(["debug", "info", "warning", "error"], case_sensitive=False),
        help="Log verbosity level.",
    )(f)
    return f


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_params(params_str: str) -> dict:
    """Parse ``'k1=v1,k2=v2,...'`` (comma *or* space delimited) into a dict."""
    if not params_str:
        return {}
    result: dict[str, str] = {}
    parts = [p.strip() for p in params_str.replace(",", " ").split() if p.strip()]
    for part in parts:
        if "=" not in part:
            raise click.BadParameter(
                f"Expected key=value pair, got: {part!r}", param_hint="--params"
            )
        k, _, v = part.partition("=")
        result[k.strip()] = v.strip()
    return result


def _read_context(context_file: str | None) -> str:
    if not context_file:
        return ""
    with open(context_file, encoding="utf-8") as f:
        return f.read()


def _print_metrics(results: list, quiet: bool) -> None:
    if quiet or not results:
        return
    final = results[-1]
    cost = final.get("cost_usd")
    cost_str = f"${cost:.5f}" if cost is not None else "n/a"
    click.echo(
        f"\n--- Metrics ---\n"
        f"  model    : {final.get('model', '—')}\n"
        f"  tokens   : {final.get('total_tokens', 0):,}  "
        f"(in={final.get('input_tokens', 0):,} / out={final.get('output_tokens', 0):,})\n"
        f"  latency  : {final.get('latency_ms', 0) / 1000:.2f}s\n"
        f"  cost     : {cost_str}",
        err=True,
    )
    if len(results) > 1:
        click.echo(f"  sub-prompts: {len(results) - 1} CTE(s) executed", err=True)


def _patch_model(spl: str, model_id: str) -> str:
    """Replace every USING MODEL '...' / USING MODEL auto with *model_id*."""
    if model_id.lower() == "auto":
        replacement = "USING MODEL auto"
    else:
        replacement = f"USING MODEL '{model_id}'"
    return re.sub(
        r"USING\s+MODEL\s+(?:'[^']*'|\"[^\"]*\"|auto)",
        replacement,
        spl,
        flags=re.IGNORECASE,
    )


def _analyze_runs(runs: list[dict]) -> dict:
    """Return {metric: (model_id, value)} for successful runs only.

    Metrics:
        latency  — lowest latency_ms          (always available)
        tokens   — lowest total_tokens        (always available)
        cost     — lowest cost_usd            (only when not null)
        value    — best tokens-per-dollar     (only when cost > 0)
    """
    valid = [r for r in runs if not r.get("error") and r.get("total_tokens", 0) > 0]
    if not valid:
        return {}

    results: dict[str, tuple[str, float]] = {}

    best_latency = min(valid, key=lambda r: r.get("latency_ms", float("inf")))
    results["latency"] = (best_latency["model_id"], best_latency["latency_ms"] / 1000)

    best_tokens = min(valid, key=lambda r: r.get("total_tokens", float("inf")))
    results["tokens"] = (best_tokens["model_id"], float(best_tokens["total_tokens"]))

    costed = [r for r in valid if r.get("cost_usd") is not None]
    if costed:
        best_cost = min(costed, key=lambda r: r["cost_usd"])
        results["cost"] = (best_cost["model_id"], best_cost["cost_usd"])

        positive_cost = [r for r in costed if r["cost_usd"] > 0]
        if positive_cost:
            best_value = max(
                positive_cost,
                key=lambda r: r["total_tokens"] / r["cost_usd"],
            )
            results["value"] = (
                best_value["model_id"],
                best_value["total_tokens"] / best_value["cost_usd"],
            )

    scored = [r for r in valid if r.get("eval", {}).get("score") is not None]
    if scored:
        best_acc = max(scored, key=lambda r: r["eval"]["score"])
        results["accuracy"] = (best_acc["model_id"], float(best_acc["eval"]["score"]))

    return results


async def _judge_response(
    response_text: str,
    rubric: str,
    judge_model: str,
    adapter_name: str,
) -> dict:
    """Call judge LLM; return {"score": float, "reasoning": str}."""
    from spl.adapters import get_adapter

    judge_prompt = (
        "You are an expert evaluator. Score the following AI response on a scale "
        "of 0 to 10 according to the rubric below.\n\n"
        f"Rubric: {rubric}\n\n"
        "Response to evaluate:\n"
        f"{response_text}\n\n"
        'Return ONLY a JSON object with exactly two keys:\n'
        '{"score": <number 0-10>, "reasoning": "<brief explanation>"}\n'
        "No other text, no markdown fences."
    )

    adapter = get_adapter(adapter_name)
    result = await adapter.generate(
        prompt=judge_prompt,
        model=judge_model,
        max_tokens=300,
        temperature=0.0,
    )
    text = result.content.strip()

    # Strip optional markdown fences
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)

    try:
        parsed = json.loads(text)
        return {
            "score":     float(parsed.get("score", 0)),
            "reasoning": str(parsed.get("reasoning", "")),
        }
    except (json.JSONDecodeError, ValueError):
        # Fallback: pull first number out of the text
        m = re.search(r"\b(10|[0-9](?:\.[0-9]+)?)\b", text)
        score = float(m.group(1)) if m else 0.0
        return {"score": score, "reasoning": text[:300]}


def _save_output(path: str | None, content: str) -> None:
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        click.echo(f"Result saved to: {path}", err=True)


# ── CLI group ──────────────────────────────────────────────────────────────────

@click.group()
@click.version_option("0.1.0", prog_name="spl-flow")
def cli():
    """SPL-Flow: Declarative LLM orchestration via Structured Prompt Language."""


# ── generate ───────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("query", default="-")
@context_file_option
@quiet_flag
@log_options
@click.option(
    "--spl-output",
    type=click.Path(writable=True),
    default=None,
    help="Save generated SPL to this file.",
)
def generate(query: str, context_file, quiet: bool, log_file: str | None, log_level: str, spl_output: str | None):
    """Translate QUERY to SPL (Text2SPL + Validate, no execution).

    QUERY can be a string or '-' to read from stdin.

    \b
    Examples:
      splflow generate "List 10 Chinese characters with water radical"
      echo "Summarize this doc" | splflow generate -
      splflow generate "Code review" --spl-output review.spl
    """
    log_path = _init_logging("generate", log_file=log_file, log_level=log_level)
    if not quiet:
        click.echo(f"Logging to: {log_path}  (level={log_level})", err=True)

    if query == "-":
        query = click.get_text_stream("stdin").read().strip()
    if not query:
        raise click.UsageError("Query cannot be empty.")

    context_text = _read_context(context_file)

    if not quiet:
        click.echo(
            f"Generating SPL for: {query[:80]}{'...' if len(query) > 80 else ''}",
            err=True,
        )

    t0 = time.perf_counter()
    result = api.generate(query, context_text=context_text)
    elapsed = time.perf_counter() - t0

    if result["error"]:
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)

    spl = result["spl_query"]
    if not spl:
        click.echo("Error: No SPL generated — try rephrasing the query.", err=True)
        sys.exit(1)

    for w in result["spl_warnings"]:
        click.echo(f"Warning: {w}", err=True)

    click.echo(spl)

    if not quiet:
        click.echo(
            f"\n[generated in {elapsed:.2f}s, {result['retry_count']} LLM call(s)]",
            err=True,
        )

    _save_output(spl_output, spl)


# ── run ────────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("query", default="-")
@adapter_option
@provider_option
@param_option
@context_file_option
@cache_option
@output_option
@quiet_flag
@log_options
@click.option(
    "--async-mode", "async_mode",
    is_flag=True,
    default=False,
    help="Async delivery: save result to /tmp file instead of printing.",
)
@click.option(
    "--email",
    default="",
    help="Notification email for async mode (SMTP placeholder in v0.2).",
)
@click.option(
    "--spl-output",
    type=click.Path(writable=True),
    default=None,
    help="Also save the generated SPL to this file.",
)
def run(query, adapter, provider, params, context_file, cache, output,
        quiet, log_file, log_level, async_mode, email, spl_output):
    """Run the full SPL-Flow pipeline: NL → SPL → execute → result.

    QUERY can be a string or '-' to read from stdin.

    \b
    Examples:
      splflow run "List 10 Chinese characters with water radical" --params "radical=水"
      splflow run "Summarize" --context-file article.txt --output result.md
      splflow run "Code review" --adapter ollama --params "code=$(cat myfile.py)"
      echo "Translate to German" | splflow run - --adapter openrouter
    """
    log_path = _init_logging("run", log_file=log_file, adapter=adapter, log_level=log_level)
    if not quiet:
        click.echo(f"Logging to: {log_path}  (level={log_level})", err=True)

    if query == "-":
        query = click.get_text_stream("stdin").read().strip()
    if not query:
        raise click.UsageError("Query cannot be empty.")

    context_text = _read_context(context_file)
    spl_params = _parse_params(params)
    delivery_mode = "async" if async_mode else "sync"

    if not quiet:
        click.echo(
            f"Running SPL-Flow pipeline\n"
            f"  adapter  : {adapter}\n"
            f"  provider : {provider or '(best-of-breed)'}\n"
            f"  mode     : {delivery_mode}\n"
            f"  cache    : {'on' if cache else 'off'}\n"
            f"  query    : {query[:80]}{'...' if len(query) > 80 else ''}",
            err=True,
        )

    t0 = time.perf_counter()
    result = api.run(
        query,
        context_text=context_text,
        adapter=adapter,
        delivery_mode=delivery_mode,
        notify_email=email,
        spl_params=spl_params,
        cache_enabled=cache,
        provider=provider,
    )
    elapsed = time.perf_counter() - t0

    if not quiet:
        click.echo(f"Pipeline finished in {elapsed:.2f}s", err=True)

    if spl_output and result["spl_query"]:
        _save_output(spl_output, result["spl_query"])

    if result["error"]:
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)

    primary = result["primary_result"]
    results = result["execution_results"]

    click.echo(primary)
    _print_metrics(results, quiet)

    if output:
        ext = Path(output).suffix.lower()
        if ext == ".json":
            _save_output(output, json.dumps({
                "primary_result": primary,
                "spl_query": result["spl_query"],
                "execution_results": results,
                "error": result["error"],
                "elapsed_s": round(elapsed, 3),
            }, indent=2, ensure_ascii=False))
        else:
            _save_output(output, primary)


# ── exec ───────────────────────────────────────────────────────────────────────

@cli.command("exec")
@click.argument("spl_file", type=click.Path(exists=True, readable=True))
@adapter_option
@provider_option
@param_option
@cache_option
@output_option
@quiet_flag
@log_options
def exec_cmd(spl_file, adapter, provider, params, cache, output, quiet, log_file, log_level):
    """Execute a pre-written SPL file directly (no Text2SPL step).

    Useful for batch testing: write your .spl file once, run it with
    different adapters or params without going through LLM translation.

    \b
    Examples:
      splflow exec query.spl --adapter ollama --params "radical=水"
      splflow exec query.spl --adapter openrouter --output result.json
      splflow exec query.spl --output result.md --quiet
    """
    log_path = _init_logging("exec", log_file=log_file, adapter=adapter, log_level=log_level)
    if not quiet:
        click.echo(f"Logging to: {log_path}  (level={log_level})", err=True)

    with open(spl_file, encoding="utf-8") as f:
        spl_query = f.read().strip()

    spl_params = _parse_params(params)

    if not quiet:
        click.echo(
            f"Executing SPL file: {spl_file}\n"
            f"  adapter  : {adapter}\n"
            f"  provider : {provider or '(best-of-breed)'}\n"
            f"  cache    : {'on' if cache else 'off'}",
            err=True,
        )

    t0 = time.perf_counter()
    result = api.exec_spl(
        spl_query, adapter=adapter, spl_params=spl_params,
        cache_enabled=cache, provider=provider,
    )
    elapsed = time.perf_counter() - t0

    if not quiet:
        click.echo(f"Execution finished in {elapsed:.2f}s", err=True)

    if result["error"]:
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)

    primary = result["primary_result"]
    results = result["execution_results"]

    click.echo(primary)
    _print_metrics(results, quiet)

    if output:
        ext = Path(output).suffix.lower()
        if ext == ".json":
            _save_output(output, json.dumps({
                "spl_file": spl_file,
                "primary_result": primary,
                "execution_results": results,
                "elapsed_s": round(elapsed, 3),
            }, indent=2, ensure_ascii=False))
        else:
            _save_output(output, primary)


# ── benchmark ──────────────────────────────────────────────────────────────────

@cli.command("benchmark")
@click.argument("spl_file", type=click.Path(exists=True, readable=True))
@adapter_option
@provider_option
@click.option(
    "--models", "-m",
    default="auto",
    metavar="M1,M2,...",
    help=(
        "Comma-separated list of model IDs to benchmark against. "
        "Use 'auto' for the model router. "
        "E.g. --models 'anthropic/claude-opus-4-6,openai/gpt-4o,auto'"
    ),
)
@param_option
@cache_option
@output_option
@quiet_flag
@log_options
def benchmark_cmd(spl_file, adapter, provider, models, params, cache, output, quiet,
                  log_file, log_level):
    """Benchmark a .spl file against multiple models in parallel.

    Runs the same SPL script once per MODEL, concurrently.  Each run
    receives an identical patched copy with its USING MODEL clause replaced.
    Wall-clock time ≈ slowest single model, not N × one model.

    \b
    Examples:
      splflow benchmark query.spl --models "auto,openai/gpt-4o"
      splflow benchmark query.spl --models "auto,anthropic/claude-opus-4-6" \\
          --adapter openrouter --output results.json
      splflow benchmark query.spl --models auto --params "doc=$(cat article.txt)"
    """
    log_path = _init_logging("benchmark", log_file=log_file, adapter=adapter, log_level=log_level)
    if not quiet:
        click.echo(f"Logging to: {log_path}  (level={log_level})", err=True)

    with open(spl_file, encoding="utf-8") as f:
        spl_query = f.read().strip()

    model_list = [m.strip() for m in models.replace(",", " ").split() if m.strip()] or ["auto"]
    spl_params = _parse_params(params)

    if not quiet:
        click.echo(
            f"Benchmarking SPL file: {spl_file}\n"
            f"  adapter  : {adapter}\n"
            f"  provider : {provider or '(best-of-breed)'}\n"
            f"  models   : {', '.join(model_list)}\n"
            f"  cache    : {'on' if cache else 'off'}",
            err=True,
        )

    t0 = time.perf_counter()
    result = api.benchmark(
        spl_query,
        models=model_list,
        adapter=adapter,
        provider=provider,
        spl_params=spl_params,
        cache_enabled=cache,
    )
    elapsed = time.perf_counter() - t0

    if not quiet:
        click.echo(f"Benchmark finished in {elapsed:.2f}s", err=True)

    error = result.get("error", "")
    if error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    runs = result.get("runs", [])

    # Summary table
    click.echo(f"\n{'Model':<40} {'Tokens':>8} {'Latency':>9} {'Cost':>10}")
    click.echo("-" * 72)
    for run in runs:
        run_error = run.get("error", "")
        if run_error:
            model_label = run["model_id"]
            if run.get("resolved_model"):
                model_label += f" → {run['resolved_model']}"
            click.echo(f"{model_label:<40} {'ERROR':>8}  {run_error[:28]}")
        else:
            model_label = run["model_id"]
            if run.get("resolved_model"):
                model_label += f" → {run['resolved_model'][:20]}"
            cost = run.get("cost_usd")
            cost_str = f"${cost:.5f}" if cost is not None else "n/a"
            click.echo(
                f"{model_label:<40}"
                f" {run.get('total_tokens', 0):>8,}"
                f" {run.get('latency_ms', 0) / 1000:>8.2f}s"
                f" {cost_str:>10}"
            )
    click.echo()

    # Per-model responses
    for run in runs:
        model_label = run["model_id"]
        if run.get("resolved_model"):
            model_label += f" → {run['resolved_model']}"
        click.echo(f"── {model_label} {'─' * max(0, 60 - len(model_label))}")
        if run.get("error"):
            click.echo(f"ERROR: {run['error']}\n")
        else:
            click.echo(run.get("response", "") + "\n")

    if output:
        ext = Path(output).suffix.lower()
        if ext == ".json":
            import json as _json
            _save_output(output, _json.dumps(result, indent=2, ensure_ascii=False))
        else:
            # markdown: one section per model
            primary = "\n\n".join(
                f"# {r['model_id']}\n\n{r.get('response', '')}"
                for r in runs
            )
            _save_output(output, primary)


# ── winner ─────────────────────────────────────────────────────────────────────

_METRIC_LABELS = {
    "latency":  ("Fastest",             lambda v: f"{v:.2f}s"),
    "tokens":   ("Most token-efficient", lambda v: f"{int(v):,} tokens"),
    "cost":     ("Cheapest",            lambda v: f"${v:.5f}"),
    "value":    ("Best value",          lambda v: f"{v:,.0f} tok/$"),
    "accuracy": ("Most accurate",       lambda v: f"{v:.1f}/10"),
}


@cli.command("winner")
@click.argument("benchmark_json", type=click.Path(exists=True, readable=True))
@click.option(
    "--by", "metric",
    type=click.Choice(["latency", "cost", "tokens", "value", "accuracy", "all"], case_sensitive=False),
    default="all", show_default=True,
    help=(
        "Metric to optimise: latency (fastest), cost (cheapest), "
        "tokens (most efficient), value (tokens per dollar), all (summary table)."
    ),
)
@click.option(
    "--mark", "mark_model",
    default=None, metavar="MODEL_ID",
    help="Record MODEL_ID as the human-chosen winner in the benchmark JSON (updates 'winner' field in-place).",
)
@click.option(
    "--patch", "patch_file",
    type=click.Path(readable=True), default=None,
    help="SPL file to patch: replaces every USING MODEL clause with the winning model.",
)
@click.option(
    "--out", "out_file",
    type=click.Path(writable=True), default=None,
    help="Write patched SPL here. Defaults to stdout when --patch is given.",
)
@quiet_flag
def winner_cmd(
    benchmark_json: str,
    metric: str,
    mark_model: str | None,
    patch_file: str | None,
    out_file: str | None,
    quiet: bool,
) -> None:
    """Analyse a benchmark result and pick the best model for production.

    BENCHMARK_JSON is the .json file produced by `splflow benchmark`.

    \b
    Examples:
      # Summary table — winners for every metric
      splflow winner results/spl_benchmark-v2.json

      # Pick the fastest model
      splflow winner results/spl_benchmark-v2.json --by latency

      # Shell scripting: emit only the model ID
      splflow winner results/spl_benchmark-v2.json --by latency --quiet
      BEST=$(splflow winner result.json --by latency --quiet)

      # Record the human-chosen winner back into the JSON
      splflow winner results/spl_benchmark-v2.json --mark anthropic/claude-opus-4.6

      # Patch a .spl file with the fastest model and save it
      splflow winner results/spl_benchmark-v2.json --by latency \\
          --patch query.spl --out query-fast.spl
    """
    with open(benchmark_json, encoding="utf-8") as f:
        data = json.load(f)

    runs: list[dict] = data.get("runs", [])
    if not runs:
        raise click.ClickException("No runs found in benchmark JSON.")

    # ── --mark: write human winner back to JSON ──────────────────────────────
    if mark_model:
        data["winner"] = mark_model
        with open(benchmark_json, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        if not quiet:
            click.echo(f"Winner recorded: {mark_model}  →  {benchmark_json}", err=True)

    # ── analyse runs ─────────────────────────────────────────────────────────
    analysis = _analyze_runs(runs)
    valid_runs = [r for r in runs if not r.get("error") and r.get("total_tokens", 0) > 0]
    failed_runs = [r for r in runs if r.get("error") or r.get("total_tokens", 0) == 0]

    # Determine the winning model for the requested metric
    if metric != "all":
        if metric not in analysis:
            hints = {
                "cost":     "cost/value require cost_usd in the benchmark results",
                "value":    "cost/value require cost_usd in the benchmark results",
                "accuracy": "accuracy requires eval scores — run `splflow eval` first",
            }
            hint = hints.get(metric, f"no {metric} data in the benchmark results")
            raise click.ClickException(f"No data for metric '{metric}': {hint}.")
        winning_model, winning_value = analysis[metric]

        if quiet:
            click.echo(winning_model)
        else:
            label, fmt = _METRIC_LABELS[metric]
            click.echo(f"{winning_model}  ({label}: {fmt(winning_value)})")

    else:
        # Full summary table
        if not quiet:
            name = data.get("benchmark_name", Path(benchmark_json).stem)
            timestamp = data.get("timestamp", "")[:10]
            click.echo(
                f"\n  Benchmark : {name}  ({timestamp})\n"
                f"  File      : {benchmark_json}\n"
                f"  Runs      : {len(valid_runs)} successful, {len(failed_runs)} failed\n"
            )

            # Per-model stats table
            W = 44
            click.echo(f"  {'Model':<{W}} {'Tokens':>8} {'Latency':>9} {'Cost':>10}")
            click.echo("  " + "-" * (W + 31))

            # highlight columns
            winner_lat  = analysis.get("latency", (None,))[0]
            winner_tok  = analysis.get("tokens",  (None,))[0]
            winner_cost = analysis.get("cost",    (None,))[0]

            for run in runs:
                mid = run["model_id"]
                err = run.get("error", "")
                if err:
                    click.echo(f"  {mid:<{W}} {'—ERROR—':>8}  {err[:28]}")
                    continue
                tokens  = run.get("total_tokens", 0)
                latency = run.get("latency_ms", 0) / 1000
                cost    = run.get("cost_usd")
                cost_s  = f"${cost:.5f}" if cost is not None else "n/a"

                lat_mark  = " ★" if mid == winner_lat  else "  "
                tok_mark  = " ★" if mid == winner_tok  else "  "
                cost_mark = " ★" if mid == winner_cost else "  "

                click.echo(
                    f"  {mid:<{W}}"
                    f" {tokens:>7,}{tok_mark}"
                    f" {latency:>7.1f}s{lat_mark}"
                    f" {cost_s:>10}{cost_mark}"
                )

            # Winners summary
            click.echo(f"\n  {'─' * 58}")
            click.echo("  Winners (★ = best in column):\n")
            for m, (label, fmt) in _METRIC_LABELS.items():
                if m in analysis:
                    mid, val = analysis[m]
                    click.echo(f"    {label:<22}  {mid:<44}  {fmt(val)}")
                else:
                    click.echo(f"    {label:<22}  n/a (cost_usd not reported by this adapter)")
            if data.get("winner"):
                click.echo(f"\n    Human choice          :  {data['winner']}")
            click.echo()

        # --quiet + --by all: print all winners one per line
        else:
            for m in ("latency", "tokens", "cost", "value"):
                if m in analysis:
                    click.echo(f"{m}\t{analysis[m][0]}")

    # ── --patch: rewrite .spl with winning model ─────────────────────────────
    if patch_file:
        if metric == "all" and not mark_model:
            raise click.UsageError(
                "Specify --by <metric> or --mark <model_id> to select a model for --patch."
            )
        patch_model_id = mark_model if mark_model else winning_model  # type: ignore[possibly-undefined]
        with open(patch_file, encoding="utf-8") as f:
            original_spl = f.read()
        patched_spl = _patch_model(original_spl, patch_model_id)
        if out_file:
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(patched_spl)
            if not quiet:
                click.echo(f"Patched SPL written to: {out_file}", err=True)
        else:
            click.echo(patched_spl)


# ── eval ───────────────────────────────────────────────────────────────────────

@cli.command("eval")
@click.argument("benchmark_json", type=click.Path(exists=True, readable=True))
@click.option(
    "--rubric", "rubric_text",
    default="",
    help="Evaluation rubric for the judge LLM (plain text).",
)
@click.option(
    "--rubric-file",
    type=click.Path(exists=True, readable=True),
    default=None,
    help="Read rubric from a file instead of --rubric.",
)
@click.option(
    "--judge",
    default="anthropic/claude-opus-4.6",
    show_default=True,
    metavar="MODEL_ID",
    help="Model ID to use as the judge.",
)
@adapter_option
@quiet_flag
def eval_cmd(benchmark_json, rubric_text, rubric_file, judge, adapter, quiet):
    """Score benchmark responses using a judge LLM (0–10 scale).

    Reads BENCHMARK_JSON and asks a judge model to score each successful run
    according to the supplied rubric.  Scores are written back into the JSON
    file under each run's ``eval`` key, enabling ``splflow winner --by accuracy``.

    \b
    Examples:
      splflow eval results/benchmark.json \\
          --rubric "Citation accuracy: correct year, prize, paper title" \\
          --judge anthropic/claude-opus-4.6 --adapter openrouter

      splflow eval results/benchmark.json --rubric-file rubric.txt \\
          --judge openai/gpt-4o --adapter openrouter
    """
    if rubric_file:
        with open(rubric_file, encoding="utf-8") as f:
            rubric = f.read().strip()
    else:
        rubric = rubric_text.strip()

    if not rubric:
        raise click.UsageError("Provide a rubric via --rubric TEXT or --rubric-file FILE.")

    with open(benchmark_json, encoding="utf-8") as f:
        data = json.load(f)

    runs = data.get("runs", [])
    if not runs:
        raise click.ClickException("No runs found in benchmark JSON.")

    valid_runs = [r for r in runs if not r.get("error") and r.get("response")]
    if not valid_runs:
        raise click.ClickException("No successful runs with responses to evaluate.")

    if not quiet:
        click.echo(
            f"Evaluating {len(valid_runs)} run(s)  judge={judge}  adapter={adapter}",
            err=True,
        )

    async def run_evals():
        tasks = [
            _judge_response(r["response"], rubric, judge, adapter)
            for r in valid_runs
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)

    raw_results = asyncio.run(run_evals())

    # Write scores back to runs
    eval_idx = 0
    for run in runs:
        if run.get("error") or not run.get("response"):
            continue
        result = raw_results[eval_idx]
        eval_idx += 1
        if not isinstance(result, dict):
            if not quiet:
                click.echo(f"  {run['model_id']}: ERROR — {result}", err=True)
            run["eval"] = {"score": None, "reasoning": str(result), "judge": judge}
        else:
            run["eval"] = {
                "score":     result["score"],
                "reasoning": result["reasoning"],
                "judge":     judge,
            }
            if not quiet:
                score_val = result["score"]
                click.echo(f"  {run['model_id']}: {score_val:.1f}/10", err=True)

    with open(benchmark_json, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    if not quiet:
        click.echo(f"\nEval scores written to: {benchmark_json}", err=True)

    # Summary table (sorted by score desc)
    if not quiet:
        click.echo(f"\n  {'Model':<44} {'Score':>7}")
        click.echo("  " + "─" * 55)
        for run in sorted(
            runs,
            key=lambda r: (r.get("eval", {}).get("score") or -1),
            reverse=True,
        ):
            ev = run.get("eval", {})
            score = ev.get("score")
            score_s = f"{score:.1f}/10" if score is not None else "n/a"
            click.echo(f"  {run['model_id']:<44} {score_s:>7}")
        click.echo()


# ── report ─────────────────────────────────────────────────────────────────────

@cli.command("report")
@click.argument("benchmark_json", type=click.Path(exists=True, readable=True))
@click.option(
    "--format", "fmt",
    type=click.Choice(["markdown", "csv"], case_sensitive=False),
    default="markdown", show_default=True,
    help="Output format.",
)
@output_option
def report_cmd(benchmark_json, fmt, output):
    """Generate a publication-ready report from a benchmark JSON.

    Produces a table suitable for pasting into a paper, blog post, or README.
    If ``splflow eval`` has been run first, an Accuracy column is included.

    \b
    Examples:
      splflow report results/benchmark.json
      splflow report results/benchmark.json --format csv --output benchmark.csv
      splflow report results/benchmark.json --output benchmark-table.md
    """
    with open(benchmark_json, encoding="utf-8") as f:
        data = json.load(f)

    runs     = data.get("runs", [])
    name     = data.get("benchmark_name", Path(benchmark_json).stem)
    ts       = data.get("timestamp", "")[:10]
    adapter  = data.get("adapter", "")
    has_cost = any(r.get("cost_usd") is not None for r in runs if not r.get("error"))
    has_eval = any(r.get("eval", {}).get("score") is not None for r in runs)

    if fmt == "markdown":
        lines = []
        lines.append(f"## Benchmark: {name}")
        if ts:
            lines.append(f"**Date**: {ts}  |  **Adapter**: {adapter}")
        lines.append("")

        headers = ["Model", "Tokens", "Latency"]
        if has_cost:
            headers.append("Cost")
        if has_eval:
            headers.append("Accuracy")
        headers.append("Status")

        sep = "|" + "|".join(":---" if i == 0 else "---:" for i in range(len(headers))) + "|"
        lines.append("| " + " | ".join(headers) + " |")
        lines.append(sep)

        for run in runs:
            mid = run["model_id"]
            if run.get("resolved_model"):
                mid += f" → {run['resolved_model']}"
            if run.get("error"):
                row = [f"`{mid}`", "—", "—"]
                if has_cost:
                    row.append("—")
                if has_eval:
                    row.append("—")
                row.append(f"❌ `{run['error'][:50]}`")
            else:
                tokens  = f"{run.get('total_tokens', 0):,}"
                latency = f"{run.get('latency_ms', 0) / 1000:.1f}s"
                row     = [f"`{mid}`", tokens, latency]
                if has_cost:
                    cost = run.get("cost_usd")
                    row.append(f"${cost:.4f}" if cost is not None else "n/a")
                if has_eval:
                    ev    = run.get("eval", {})
                    score = ev.get("score")
                    row.append(f"{score:.1f}/10" if score is not None else "—")
                row.append("✅")
            lines.append("| " + " | ".join(row) + " |")

        lines.append("")

        # Winners footer
        analysis = _analyze_runs(runs)
        if analysis:
            lines.append("**Winners:**")
            for metric, (label, fmt_fn) in _METRIC_LABELS.items():
                if metric in analysis:
                    mid, val = analysis[metric]
                    lines.append(f"- {label}: `{mid}` ({fmt_fn(val)})")
            lines.append("")

        report_text = "\n".join(lines)

    else:  # csv
        import csv as _csv
        import io
        buf = io.StringIO()
        fieldnames = ["model_id", "tokens", "latency_s", "cost_usd"]
        if has_eval:
            fieldnames.append("accuracy_score")
        fieldnames.append("error")
        writer = _csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        for run in runs:
            row = {
                "model_id":  run["model_id"],
                "tokens":    run.get("total_tokens", 0),
                "latency_s": round(run.get("latency_ms", 0) / 1000, 2),
                "cost_usd":  run.get("cost_usd", ""),
                "error":     run.get("error", ""),
            }
            if has_eval:
                row["accuracy_score"] = (run.get("eval") or {}).get("score", "")
            writer.writerow(row)
        report_text = buf.getvalue()

    if output:
        _save_output(output, report_text)
    else:
        click.echo(report_text)


# ── rerun ──────────────────────────────────────────────────────────────────────

@cli.command("rerun")
@click.argument("benchmark_json", type=click.Path(exists=True, readable=True))
@click.option(
    "--model", "model_id",
    required=True,
    metavar="MODEL_ID",
    help=(
        "Model ID to run.  If already in the benchmark JSON, retries it. "
        "If new, patches the existing SPL and appends a new run entry."
    ),
)
@click.option(
    "--output", "-o",
    default=None,
    metavar="FILE",
    help=(
        "Write updated benchmark JSON to FILE instead of overwriting "
        "BENCHMARK_JSON in-place.  Useful for keeping the original intact."
    ),
)
@adapter_option
@provider_option
@quiet_flag
@log_options
def rerun_cmd(benchmark_json, model_id, output, adapter, provider, quiet,
              log_file, log_level):
    """Re-run or add a single model in a benchmark JSON.

    Two modes:
      Retry   — model already in the JSON: re-executes with the same patched
                SPL and replaces the existing entry (useful after a bug fix).
      Add new — model not yet in the JSON: patches the SPL from an existing
                run's template and appends a fresh entry (useful for testing
                a new model against the same benchmark task).

    \b
    Examples:
      # Retry a failed run after the GLM control-char fix
      splflow rerun results/benchmark.json --model z-ai/glm-4.6 --adapter openrouter

      # Add GLM-5 to an existing benchmark without re-running all models
      splflow rerun results/benchmark.json --model z-ai/glm-5 --adapter openrouter
    """
    _init_logging("rerun", log_file=log_file, adapter=adapter, log_level=log_level)

    from src.nodes.benchmark import _run_one, patch_model as _patch_model_node

    with open(benchmark_json, encoding="utf-8") as f:
        data = json.load(f)

    runs = data.get("runs", [])
    if not runs:
        raise click.ClickException("No runs found in benchmark JSON.")

    # Locate an existing entry for this model (may be None for a new model)
    existing_run = None
    existing_idx = None
    for i, r in enumerate(runs):
        if r["model_id"] == model_id:
            existing_run = r
            existing_idx = i
            break

    resolved_from = "auto" if model_id.lower() == "auto" else "explicit"

    if existing_run is not None:
        # ── Retry mode ────────────────────────────────────────────────────────
        input_spl = existing_run.get("input_spl", "")
        if not input_spl:
            raise click.ClickException(
                f"No input_spl stored for '{model_id}'. "
                "Cannot re-run without the original patched SPL."
            )
        resolved_from = existing_run.get("resolved_from", resolved_from)
        mode_label = f"retry  (previous: {'FAILED' if existing_run.get('error') else 'ok'})"
    else:
        # ── Add-new mode ──────────────────────────────────────────────────────
        # Grab template SPL from the first run that has one
        template_run = next((r for r in runs if r.get("input_spl")), None)
        if template_run is None:
            raise click.ClickException(
                "No run in the benchmark JSON has an input_spl to use as template."
            )
        input_spl = _patch_model_node(template_run["input_spl"], model_id)
        mode_label = f"new model  (patched from template: {template_run['model_id']})"

    if not quiet:
        click.echo(
            f"Running {model_id}  [{mode_label}]  adapter={adapter}",
            err=True,
        )

    t0 = time.perf_counter()
    new_run = asyncio.run(
        _run_one(
            model_id=model_id,
            resolved_from=resolved_from,
            patched_spl=input_spl,
            adapter=adapter,
            provider=provider,
            params=data.get("params", {}),
            cache_enabled=False,
        )
    )
    elapsed = time.perf_counter() - t0

    if new_run.get("error"):
        click.echo(f"ERROR: {new_run['error']}", err=True)
    else:
        if not quiet:
            cost_s = (f"${new_run['cost_usd']:.5f}"
                      if new_run.get("cost_usd") is not None else "n/a")
            click.echo(
                f"  tokens={new_run.get('total_tokens', 0):,}  "
                f"latency={new_run.get('latency_ms', 0) / 1000:.1f}s  "
                f"cost={cost_s}  wall={elapsed:.1f}s",
                err=True,
            )
        click.echo(new_run.get("response", ""))

    # Replace existing entry or append new one
    if existing_idx is not None:
        runs[existing_idx] = new_run
    else:
        runs.append(new_run)
    data["runs"] = runs

    dest = output or benchmark_json
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    if not quiet:
        action = "replaced" if existing_idx is not None else "appended"
        click.echo(f"\n{action.capitalize()} run in: {dest}", err=True)


# ── cost ───────────────────────────────────────────────────────────────────────

@cli.command("cost")
@click.argument("spl_file", type=click.Path(exists=True, readable=True))
@click.option(
    "--models", "-m",
    default="auto",
    metavar="M1,M2,...",
    help="Comma-separated model IDs to estimate costs for.",
)
@click.option(
    "--input-tokens", "input_tokens_override",
    default=0, type=int, metavar="N",
    help="Override the estimated input token count (default: count SPL file tokens).",
)
@click.option(
    "--output-tokens", "output_tokens",
    default=2000, show_default=True, type=int, metavar="N",
    help="Expected output tokens per run.",
)
@quiet_flag
def cost_cmd(spl_file, models, input_tokens_override, output_tokens, quiet):
    """Estimate benchmark cost before running.

    Fetches live pricing from the OpenRouter API and projects cost per model
    based on the SPL file's token count plus expected output tokens.

    \b
    Examples:
      splflow cost query.spl --models "anthropic/claude-opus-4.6,openai/gpt-4o"
      splflow cost query.spl --models "claude-opus,gpt-4o,z-ai/glm-4.6" \\
          --input-tokens 3000 --output-tokens 2000
    """
    import httpx as _httpx

    with open(spl_file, encoding="utf-8") as f:
        spl_text = f.read()

    model_list = [m.strip() for m in models.replace(",", " ").split() if m.strip()] or ["auto"]

    # Estimate input tokens
    if input_tokens_override > 0:
        est_input = input_tokens_override
    else:
        try:
            from spl.token_counter import TokenCounter
            est_input = TokenCounter("gpt-4").count(spl_text)
        except Exception:
            est_input = max(1, len(spl_text) // 4)  # ~4 chars/token fallback

    # Fetch live pricing from OpenRouter
    pricing: dict[str, tuple[float, float]] = {}
    try:
        resp = _httpx.get(_OPENROUTER_MODELS_URL, timeout=15)
        resp.raise_for_status()
        for m in resp.json().get("data", []):
            mid = m.get("id", "")
            p   = m.get("pricing") or {}
            try:
                inp = float(p.get("prompt", 0)) * 1_000_000
                out = float(p.get("completion", 0)) * 1_000_000
                pricing[mid] = (inp, out)
            except (ValueError, TypeError):
                pass
    except Exception as exc:
        if not quiet:
            click.echo(f"Warning: could not fetch OpenRouter pricing: {exc}", err=True)

    if not quiet:
        click.echo(
            f"\n  SPL file      : {spl_file}\n"
            f"  Input tokens  : ~{est_input:,}  (prompt estimate)\n"
            f"  Output tokens : ~{output_tokens:,}  (your estimate)\n"
        )

    W = 44
    click.echo(f"  {'Model':<{W}} {'Input $/M':>10} {'Output $/M':>11} {'Est. Cost':>12}")
    click.echo("  " + "─" * (W + 37))

    total_cost   = 0.0
    has_pricing  = False

    for mid in model_list:
        if mid.lower() == "auto":
            click.echo(f"  {'openrouter/auto':<{W}} {'routed':>10} {'routed':>11} {'variable':>12}")
            continue

        if mid in pricing:
            inp_pm, out_pm = pricing[mid]
            if inp_pm == 0.0 and out_pm == 0.0:
                cost_str = "free"
                est      = 0.0
            else:
                est      = (est_input / 1_000_000 * inp_pm) + (output_tokens / 1_000_000 * out_pm)
                cost_str = f"${est:.5f}"
                total_cost  += est
                has_pricing  = True
            inp_s = f"${inp_pm:.2f}" if inp_pm > 0 else "free"
            out_s = f"${out_pm:.2f}" if out_pm > 0 else "free"
            click.echo(f"  {mid:<{W}} {inp_s:>10} {out_s:>11} {cost_str:>12}")
        else:
            click.echo(f"  {mid:<{W}} {'n/a':>10} {'n/a':>11} {'n/a (not on OpenRouter)':>24}")

    if has_pricing:
        click.echo(f"\n  Total estimated cost (excluding free/auto): ${total_cost:.5f}")
    click.echo()


# ── models ─────────────────────────────────────────────────────────────────────

_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


@cli.command("models")
@click.argument("keyword", default="", required=False)
@click.option(
    "--top", default=20, show_default=True, metavar="N",
    help="Maximum number of results to display.",
)
@output_option
def models_cmd(keyword: str, top: int, output: str | None):
    """Search available OpenRouter models by KEYWORD.

    KEYWORD is matched case-insensitively against model id, name, and
    description.  Omit KEYWORD to list the first N models alphabetically.

    \b
    Examples:
      splflow models claude
      splflow models gemini
      splflow models "mistral 7b"
      splflow models sonnet --top 5
      splflow models claude --output models.json
    """
    import httpx

    try:
        resp = httpx.get(_OPENROUTER_MODELS_URL, timeout=15)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise click.ClickException(f"OpenRouter API error: {exc}")

    all_models: list[dict] = resp.json().get("data", [])

    if keyword:
        kw = keyword.lower()
        filtered = [
            m for m in all_models
            if kw in m.get("id", "").lower()
            or kw in m.get("name", "").lower()
            or kw in (m.get("description") or "").lower()
        ]
    else:
        filtered = list(all_models)

    filtered.sort(key=lambda m: m.get("id", ""))
    shown = filtered[:top]

    if not shown:
        click.echo(f"No models found matching: {keyword!r}")
        return

    # JSON output
    if output and Path(output).suffix.lower() == ".json":
        _save_output(output, json.dumps(shown, indent=2, ensure_ascii=False))
        return

    # Human-readable table
    W_ID, W_NAME = 48, 32
    click.echo(
        f"\n  {'Model ID':<{W_ID}} {'Name':<{W_NAME}} {'Input $/M':>10} {'Output $/M':>11}"
    )
    click.echo("  " + "-" * (W_ID + W_NAME + 24))
    for m in shown:
        mid = m.get("id", "")
        name = (m.get("name") or "")[:W_NAME]
        pricing = m.get("pricing") or {}
        try:
            inp = float(pricing.get("prompt", 0)) * 1_000_000
            out = float(pricing.get("completion", 0)) * 1_000_000
            inp_str = f"${inp:.2f}" if inp > 0 else "free"
            out_str = f"${out:.2f}" if out > 0 else "free"
        except (ValueError, TypeError):
            inp_str = out_str = "n/a"
        click.echo(
            f"  {mid:<{W_ID}} {name:<{W_NAME}} {inp_str:>10} {out_str:>11}"
        )

    total = len(filtered)
    suffix = f"  ({total - top} more — use --top {total} to see all)" if total > top else ""
    click.echo(f"\n  {len(shown)} of {total} model(s) shown{suffix}\n")

    if output:
        # plain text: just the IDs, one per line (useful for shell scripting)
        _save_output(output, "\n".join(m["id"] for m in shown))


# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
