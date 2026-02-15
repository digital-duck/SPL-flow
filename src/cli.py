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

from src import api
from src.utils.logging_config import setup_logging, disable_logging


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
        "--param", "-p",
        multiple=True,
        metavar="KEY=VALUE",
        help="SPL context params (repeatable). E.g. --param radical=水 --param topic=AI",
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
        help="Save primary result to this file (markdown).",
    )(f)


def json_flag(f):
    return click.option(
        "--json", "as_json",
        is_flag=True,
        default=False,
        help="Output full result as JSON (includes tokens, latency, cost).",
    )(f)


def quiet_flag(f):
    return click.option(
        "--quiet", "-q",
        is_flag=True,
        default=False,
        help="Suppress banners and status messages; print only the result.",
    )(f)


def log_options(f):
    """Attach --log/--no-log and --log-level options (mirrors the spl-llm CLI)."""
    f = click.option(
        "--log/--no-log",
        default=True,
        show_default=True,
        help="Write a timestamped log file to logs/ (default: on).",
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

def _parse_params(param_tuples: tuple) -> dict:
    """Parse ('key=value', ...) tuples into a dict."""
    result = {}
    for p in param_tuples:
        if "=" not in p:
            raise click.BadParameter(
                f"Params must be KEY=VALUE format, got: {p!r}", param_hint="--param"
            )
        k, _, v = p.partition("=")
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
def generate(query: str, context_file, quiet: bool, log: bool, log_level: str, spl_output):
    """Translate QUERY to SPL (Text2SPL + Validate, no execution).

    QUERY can be a string or '-' to read from stdin.

    \b
    Examples:
      spl-flow generate "List 10 Chinese characters with water radical"
      echo "Summarize this doc" | spl-flow generate -
      spl-flow generate "Code review" --spl-output review.spl
    """
    if log:
        log_path = setup_logging("generate", log_level=log_level)
        if not quiet:
            click.echo(f"Logging to: {log_path}  (level={log_level})", err=True)
    else:
        disable_logging()

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
@json_flag
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
def run(query, adapter, provider, param, context_file, cache, output, as_json,
        quiet, log, log_level, async_mode, email, spl_output):
    """Run the full SPL-Flow pipeline: NL → SPL → execute → result.

    QUERY can be a string or '-' to read from stdin.

    \b
    Examples:
      spl-flow run "List 10 Chinese characters with water radical" --param radical=水
      spl-flow run "Summarize" --context-file article.txt --output result.md
      spl-flow run "Code review" --adapter ollama --param code="$(cat myfile.py)"
      echo "Translate to German" | spl-flow run - --adapter openrouter
    """
    if log:
        log_path = setup_logging("run", adapter=adapter, log_level=log_level)
        if not quiet:
            click.echo(f"Logging to: {log_path}  (level={log_level})", err=True)
    else:
        disable_logging()

    if query == "-":
        query = click.get_text_stream("stdin").read().strip()
    if not query:
        raise click.UsageError("Query cannot be empty.")

    context_text = _read_context(context_file)
    spl_params = _parse_params(param)
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

    if as_json:
        click.echo(json.dumps({
            "primary_result": primary,
            "spl_query": result["spl_query"],
            "execution_results": results,
            "error": result["error"],
            "elapsed_s": round(elapsed, 3),
        }, indent=2, ensure_ascii=False))
    else:
        click.echo(primary)
        _print_metrics(results, quiet)

    _save_output(output, primary)


# ── exec ───────────────────────────────────────────────────────────────────────

@cli.command("exec")
@click.argument("spl_file", type=click.Path(exists=True, readable=True))
@adapter_option
@provider_option
@param_option
@cache_option
@output_option
@json_flag
@quiet_flag
@log_options
def exec_cmd(spl_file, adapter, provider, param, cache, output, as_json, quiet, log, log_level):
    """Execute a pre-written SPL file directly (no Text2SPL step).

    Useful for batch testing: write your .spl file once, run it with
    different adapters or params without going through LLM translation.

    \b
    Examples:
      spl-flow exec query.spl --adapter ollama --param radical=水
      spl-flow exec query.spl --adapter openrouter --json > result.json
      spl-flow exec query.spl --output result.md --quiet
    """
    if log:
        log_path = setup_logging("exec", adapter=adapter, log_level=log_level)
        if not quiet:
            click.echo(f"Logging to: {log_path}  (level={log_level})", err=True)
    else:
        disable_logging()

    with open(spl_file, encoding="utf-8") as f:
        spl_query = f.read().strip()

    spl_params = _parse_params(param)

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

    if as_json:
        click.echo(json.dumps({
            "spl_file": spl_file,
            "primary_result": primary,
            "execution_results": results,
            "elapsed_s": round(elapsed, 3),
        }, indent=2, ensure_ascii=False))
    else:
        click.echo(primary)
        _print_metrics(results, quiet)

    _save_output(output, primary)


# ── benchmark ──────────────────────────────────────────────────────────────────

@cli.command("benchmark")
@click.argument("spl_file", type=click.Path(exists=True, readable=True))
@adapter_option
@provider_option
@click.option(
    "--model", "-m",
    "models",
    multiple=True,
    metavar="MODEL_ID",
    help=(
        "Model to benchmark against (repeatable). "
        "Use 'auto' for the model router. "
        "E.g. --model anthropic/claude-opus-4-6 --model auto"
    ),
)
@param_option
@cache_option
@output_option
@json_flag
@quiet_flag
@log_options
def benchmark_cmd(spl_file, adapter, provider, models, param, cache, output, as_json, quiet,
                  log, log_level):
    """Benchmark a .spl file against multiple models in parallel.

    Runs the same SPL script once per MODEL, concurrently.  Each run
    receives an identical patched copy with its USING MODEL clause replaced.
    Wall-clock time ≈ slowest single model, not N × one model.

    \b
    Examples:
      spl-flow benchmark query.spl --model auto --model openai/gpt-4o
      spl-flow benchmark query.spl --model auto --model anthropic/claude-opus-4-6 \\
          --adapter openrouter --provider anthropic --json > results.json
      spl-flow benchmark query.spl --model auto --param doc="$(cat article.txt)"
    """
    if log:
        log_path = setup_logging("benchmark", adapter=adapter, log_level=log_level)
        if not quiet:
            click.echo(f"Logging to: {log_path}  (level={log_level})", err=True)
    else:
        disable_logging()

    with open(spl_file, encoding="utf-8") as f:
        spl_query = f.read().strip()

    model_list = list(models) if models else ["auto"]
    spl_params = _parse_params(param)

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

    if as_json:
        click.echo(
            __import__("json").dumps(result, indent=2, ensure_ascii=False)
        )
    else:
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
        primary = "\n\n".join(
            f"# {r['model_id']}\n\n{r.get('response', '')}"
            for r in runs
        )
        _save_output(output, primary)


# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
