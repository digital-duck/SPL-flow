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
import time

sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")

import click

from pathlib import Path

from src import api
from src.utils.logging_config import setup_logging


# ── Helpers ────────────────────────────────────────────────────────────────────

def _init_logging(
    run_name: str,
    *,
    log_file: str | None,
    adapter: str = "",
    log_level: str = "info",
) -> Path:
    """Configure dd_logging and return the path of the created log file.

    If *log_file* is given its stem becomes the run_name and its parent the
    log_dir, so the auto-timestamped file lands where the user expects.
    """
    if log_file:
        p = Path(log_file)
        return setup_logging(
            p.stem,
            adapter=adapter,
            log_level=log_level,
            log_dir=p.parent if str(p.parent) not in (".", "") else None,
        )
    return setup_logging(run_name, adapter=adapter, log_level=log_level)


# ── Shared option decorators ───────────────────────────────────────────────────

def adapter_option(f):
    return click.option(
        "--adapter", "-a",
        default="claude_cli",
        show_default=True,
        type=click.Choice(["claude_cli", "openrouter", "ollama"]),
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
        default="info",
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


def _save_output(path: str | None, content: str) -> None:
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        click.echo(f"Result saved to: {path}", err=True)


# ── CLI group ──────────────────────────────────────────────────────────────────

@click.group()
@click.version_option("0.1.0", prog_name="spl-flow")
def cli():
    """SPL-Flow: Declarative LLM orchestration via Structured Prompt Language.

    \b
    Commands:
      generate   Translate a query to SPL (no LLM execution)
      run        Full pipeline: NL → SPL → execute → result
      exec       Execute a pre-written .spl file directly
    """


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


# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
