"""SPL-Flow Click CLI — batch testing and scripting interface.

Usage:
    python -m src.cli generate "List 10 Chinese characters with water radical"
    python -m src.cli run "Summarize this article" --context-file article.txt
    python -m src.cli exec query.spl --adapter ollama --param radical=水
"""
import sys
import json
import time
import asyncio

sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")

import click

from src.flows.spl_flow import generate_spl_only, run_spl_flow


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
@click.option(
    "--spl-output",
    type=click.Path(writable=True),
    default=None,
    help="Save generated SPL to this file.",
)
def generate(query: str, context_file, quiet: bool, spl_output):
    """Translate QUERY to SPL (Text2SPL + Validate, no execution).

    QUERY can be a string or '-' to read from stdin.

    \b
    Examples:
      spl-flow generate "List 10 Chinese characters with water radical"
      echo "Summarize this doc" | spl-flow generate -
      spl-flow generate "Code review" --spl-output review.spl
    """
    if query == "-":
        query = click.get_text_stream("stdin").read().strip()
    if not query:
        raise click.UsageError("Query cannot be empty.")

    context_text = _read_context(context_file)

    if not quiet:
        click.echo(f"Generating SPL for: {query[:80]}{'...' if len(query) > 80 else ''}", err=True)

    t0 = time.perf_counter()
    result = generate_spl_only(user_input=query, context_text=context_text)
    elapsed = time.perf_counter() - t0

    if result.get("error"):
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)

    spl = result.get("spl_query", "")
    if not spl:
        click.echo("Error: No SPL generated — try rephrasing the query.", err=True)
        sys.exit(1)

    # Warnings
    for w in result.get("spl_warnings", []):
        click.echo(f"Warning: {w}", err=True)

    # Print SPL to stdout
    click.echo(spl)

    if not quiet:
        retries = result.get("retry_count", 0)
        click.echo(f"\n[generated in {elapsed:.2f}s, {retries} LLM call(s)]", err=True)

    _save_output(spl_output, spl)


# ── run ────────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("query", default="-")
@adapter_option
@param_option
@context_file_option
@cache_option
@output_option
@json_flag
@quiet_flag
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
def run(query, adapter, param, context_file, cache, output, as_json,
        quiet, async_mode, email, spl_output):
    """Run the full SPL-Flow pipeline: NL → SPL → execute → result.

    QUERY can be a string or '-' to read from stdin.

    \b
    Examples:
      spl-flow run "List 10 Chinese characters with water radical" --param radical=水
      spl-flow run "Summarize" --context-file article.txt --output result.md
      spl-flow run "Code review" --adapter ollama --param code="$(cat myfile.py)"
      echo "Translate to German" | spl-flow run - --adapter openrouter
    """
    if query == "-":
        query = click.get_text_stream("stdin").read().strip()
    if not query:
        raise click.UsageError("Query cannot be empty.")

    context_text = _read_context(context_file)
    spl_params = _parse_params(param)
    if context_text:
        spl_params.setdefault("document", context_text)

    delivery_mode = "async" if async_mode else "sync"

    if not quiet:
        click.echo(
            f"Running SPL-Flow pipeline\n"
            f"  adapter : {adapter}\n"
            f"  mode    : {delivery_mode}\n"
            f"  cache   : {'on' if cache else 'off'}\n"
            f"  query   : {query[:80]}{'...' if len(query) > 80 else ''}",
            err=True,
        )

    t0 = time.perf_counter()
    result = run_spl_flow(
        user_input=query,
        context_text=context_text,
        adapter=adapter,
        delivery_mode=delivery_mode,
        notify_email=email,
        spl_params=spl_params,
        cache_enabled=cache,
    )
    elapsed = time.perf_counter() - t0

    if not quiet:
        click.echo(f"Pipeline finished in {elapsed:.2f}s", err=True)

    # Save generated SPL if requested
    if spl_output and result.get("spl_query"):
        _save_output(spl_output, result["spl_query"])

    if result.get("error"):
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)

    primary = result.get("primary_result", "")
    results = result.get("execution_results", [])

    if as_json:
        click.echo(json.dumps({
            "primary_result": primary,
            "spl_query": result.get("spl_query", ""),
            "execution_results": results,
            "error": result.get("error", ""),
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
@param_option
@cache_option
@output_option
@json_flag
@quiet_flag
@click.option(
    "--async-mode", "async_mode",
    is_flag=True,
    default=False,
    help="Async delivery: save result to /tmp file.",
)
def exec_cmd(spl_file, adapter, param, cache, output, as_json, quiet, async_mode):
    """Execute a pre-written SPL file directly (no Text2SPL step).

    Useful for batch testing: write your .spl file once, run it with
    different adapters or params without going through LLM translation.

    \b
    Examples:
      spl-flow exec query.spl --adapter ollama --param radical=水
      spl-flow exec query.spl --adapter openrouter --json > result.json
      spl-flow exec query.spl --output result.md --quiet
    """
    with open(spl_file, encoding="utf-8") as f:
        spl_query = f.read().strip()

    spl_params = _parse_params(param)
    delivery_mode = "async" if async_mode else "sync"

    if not quiet:
        click.echo(
            f"Executing SPL file: {spl_file}\n"
            f"  adapter : {adapter}\n"
            f"  mode    : {delivery_mode}\n"
            f"  cache   : {'on' if cache else 'off'}",
            err=True,
        )

    # Execute SPL directly via the SPL engine (bypasses Text2SPL)
    try:
        from spl import parse
        from spl.analyzer import Analyzer
        from spl.optimizer import Optimizer
        from spl.executor import Executor
        from spl.ast_nodes import PromptStatement, CreateFunctionStatement
    except ImportError as e:
        click.echo(f"Error: SPL engine not available — {e}", err=True)
        sys.exit(1)

    t0 = time.perf_counter()
    try:
        ast = parse(spl_query)
        analysis = Analyzer().analyze(ast)
        plans = Optimizer().optimize(analysis)

        if not plans:
            click.echo("Error: No PROMPT statements found in SPL file.", err=True)
            sys.exit(1)

        executor = Executor(adapter_name=adapter, cache_enabled=cache)

        for s in ast.statements:
            if isinstance(s, CreateFunctionStatement):
                executor.functions.register(s)

        results = []
        for plan in plans:
            stmt = next(
                (s for s in ast.statements
                 if isinstance(s, PromptStatement) and s.name == plan.prompt_name),
                None,
            )
            r = asyncio.run(executor.execute(plan, params=spl_params, stmt=stmt))
            results.append({
                "prompt_name": plan.prompt_name,
                "content": r.content,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "total_tokens": r.total_tokens,
                "latency_ms": r.latency_ms,
                "cost_usd": r.cost_usd,
            })

        executor.close()

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    elapsed = time.perf_counter() - t0

    if not quiet:
        click.echo(f"Execution finished in {elapsed:.2f}s", err=True)

    primary = results[-1]["content"] if results else ""

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


# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
