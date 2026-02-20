#!/usr/bin/env python3
"""
SPL Runner — general-purpose CLI automation for SPL-flow experiments.

Three modes (combinable):
  1. Default  : use the three built-in queries (English / Chinese / Arabic)
  2. --query  : one or more custom NL queries → Phase 1 (generate) + Phase 2 (exec)
  3. --scripts: one or more pre-written .spl files → Phase 2 only (skip generation)

Output layout:
    spl-runner-<TIMESTAMP>/
    ├── summary.json
    ├── <name>/                  ← query name or script stem
    │   ├── generated.spl        ← only when generated from NL
    │   ├── generate.log         ← only when generated from NL
    │   ├── claude_cli/  { result.json, result.md, exec.log }
    │   ├── openrouter/  { ... }
    │   └── ollama/      { ... }
    └── ...

Usage examples:
    # Built-in 3 queries × all adapters
    env -u CLAUDECODE python experiments/spl_runner.py

    # Single custom question, claude_cli only
    env -u CLAUDECODE python experiments/spl_runner.py \\
        -q "Explain quantum entanglement" --adapters claude_cli

    # Multiple custom questions
    env -u CLAUDECODE python experiments/spl_runner.py \\
        -q "Question one" -q "Question two" --adapters openrouter

    # Execute pre-written .spl scripts across adapters (no generation)
    python experiments/spl_runner.py \\
        --scripts examples/radical_ri.spl,examples/llm_compare.spl \\
        --adapters openrouter,ollama

    # Mix: generate from a query AND run a pre-written script
    env -u CLAUDECODE python experiments/spl_runner.py \\
        -q "My new question" \\
        --scripts examples/baseline.spl \\
        --adapters claude_cli,openrouter

Note: claude_cli cannot be used inside an active Claude Code session.
      Run from a regular terminal, or prefix with: env -u CLAUDECODE
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import click

# ── Paths (portable — no hardcoded $HOME) ──────────────────────────────────────

SPLFLOW_DIR = Path(__file__).parent.parent.resolve()

TIMESTAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
DEFAULT_OUTPUT_DIR = (
    Path.home() / "Downloads" / "Zinets" / "spl-experiments" / f"spl-runner-{TIMESTAMP}"
)

# ── Built-in queries (used when no --query or --scripts flags are given) ────────

BUILTIN_QUERIES: dict[str, str] = {
    "english": (
        "Generate a multilingual table of Chinese characters containing the radical 日 (rì), "
        "including character decomposition formula, pinyin, English meaning, Chinese explanation, "
        "German translation, and natural insight."
    ),
    "chinese": (
        "用中文解释大型语言模型的工作原理，从参数知识、上下文知识和推理能力三个维度分析，"
        "并对比GPT、Claude和开源模型（如Qwen）的主要异同。"
    ),
    "arabic": (
        "ما هي أبرز إسهامات العلماء العرب في تطوير علم الرياضيات والفلك خلال العصر الذهبي الإسلامي، "
        "وكيف أثّرت هذه الإسهامات على العلوم الحديثة؟"
    ),
}

DEFAULT_ADAPTERS = ["claude_cli", "openrouter", "ollama"]

SEP = "=" * 64

# ── Helpers ────────────────────────────────────────────────────────────────────

def _run(args: list[str], label: str) -> tuple[int, str, str, float]:
    """Execute *args* in SPLFLOW_DIR; return (rc, stdout, stderr, elapsed_s)."""
    print(f"    → {label}")
    t0 = time.perf_counter()
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(SPLFLOW_DIR),
    )
    elapsed = time.perf_counter() - t0
    icon = "✓" if proc.returncode == 0 else "✗"
    print(f"      {icon}  {elapsed:.1f}s   rc={proc.returncode}")
    if proc.returncode != 0 and proc.stderr:
        print(f"      STDERR: {proc.stderr[-400:]}")
    return proc.returncode, proc.stdout, proc.stderr, elapsed


def _extract_metrics(json_path: Path) -> dict:
    """Parse result.json from `splflow exec --output`; return flat summary + per-CTE rows."""
    if not json_path.exists():
        return {"error": "output json missing"}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"error": f"json parse error: {exc}"}

    runs = data.get("execution_results", [])
    cte_rows = [
        {
            "prompt_name":   r.get("prompt_name", "?"),
            "model":         r.get("model", "?"),
            "input_tokens":  r.get("input_tokens", 0),
            "output_tokens": r.get("output_tokens", 0),
            "total_tokens":  r.get("total_tokens", 0),
            "latency_s":     round(r.get("latency_ms", 0) / 1_000, 2),
            "cost_usd":      r.get("cost_usd"),
        }
        for r in runs
    ]

    return {
        "cte_runs":        cte_rows,
        "total_tokens":    sum(r.get("total_tokens", 0) for r in runs),
        "total_cost_usd":  round(sum(r.get("cost_usd") or 0 for r in runs), 6),
        "total_latency_s": round(sum(r.get("latency_ms", 0) for r in runs) / 1_000, 2),
        "elapsed_s":       data.get("elapsed_s"),
        "spl_query":       data.get("spl_query", ""),
    }


def _print_table(headers: list[str], rows: list[list[str]], indent: int = 2) -> None:
    pad = " " * indent
    widths = [max(len(h), max((len(str(r[i])) for r in rows), default=0))
              for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(pad + fmt.format(*headers))
    print(pad + "  ".join("─" * w for w in widths))
    for row in rows:
        print(pad + fmt.format(*[str(c) for c in row]))


# ── Main ───────────────────────────────────────────────────────────────────────

def main(
    adapters:  list[str],
    output_dir: Path,
    queries:   dict[str, str],   # name → NL text  (may be empty)
    pre_spl:   dict[str, Path],  # name → .spl path (may be empty)
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{SEP}")
    print(f"  SPL Runner   {TIMESTAMP}")
    print(f"  SPL-flow dir : {SPLFLOW_DIR}")
    print(f"  Output       : {output_dir}")
    print(f"  Adapters     : {', '.join(adapters)}")
    if queries:
        print(f"  Queries      : {', '.join(queries)}")
    if pre_spl:
        print(f"  Scripts      : {', '.join(pre_spl)}")
    print(SEP)

    spl_files: dict[str, Path] = {}
    gen_summary: dict[str, dict] = {}

    # ── Phase 1: NL → SPL (only when there are queries to generate) ────────────
    if queries:
        print(f"\n── Phase 1: NL → SPL  (Text2SPL, claude_cli) ────────────────────────\n")
        for name, query in queries.items():
            name_dir = output_dir / name
            name_dir.mkdir(exist_ok=True)

            spl_out = name_dir / "generated.spl"
            log_out = name_dir / "generate.log"

            print(f"  [{name}]  {query[:70]}{'...' if len(query) > 70 else ''}")

            rc, _stdout, stderr, elapsed = _run(
                [
                    sys.executable, "-m", "src.cli", "generate",
                    query,
                    "--spl-output", str(spl_out),
                    "--log", str(log_out),
                    "--log-level", "info",
                ],
                label="generate (NL → SPL)",
            )

            if rc == 0 and spl_out.exists():
                content   = spl_out.read_text(encoding="utf-8")
                spl_lines = len([l for l in content.splitlines() if l.strip()])
                spl_files[name]  = spl_out
                gen_summary[name] = {
                    "status":    "generated",
                    "spl_lines": spl_lines,
                    "elapsed_s": round(elapsed, 2),
                    "spl_file":  str(spl_out),
                    "log_file":  str(log_out),
                }
                print(f"      SPL: {spl_lines} lines  →  {spl_out.name}")
            else:
                gen_summary[name] = {
                    "status":    "error",
                    "elapsed_s": round(elapsed, 2),
                    "error":     stderr[-400:],
                }
                print(f"      FAILED – skipping execution for [{name}]")
    else:
        print(f"\n── Phase 1: skipped (--scripts mode) ────────────────────────────────\n")

    # ── Add pre-written .spl files directly (no generation needed) ─────────────
    for name, path in pre_spl.items():
        if not path.exists():
            print(f"  [WARN] script not found, skipping: {path}")
            gen_summary[name] = {"status": "not_found", "spl_file": str(path)}
            continue
        content   = path.read_text(encoding="utf-8")
        spl_lines = len([l for l in content.splitlines() if l.strip()])
        spl_files[name] = path
        gen_summary[name] = {
            "status":    "pre-built",
            "spl_lines": spl_lines,
            "spl_file":  str(path),
        }
        print(f"  [script] {name}  ({spl_lines} lines)  ←  {path}")

    # ── Phase 2: SPL exec × adapters ───────────────────────────────────────────
    print(f"\n── Phase 2: SPL Execution  ({len(spl_files)} scripts × {len(adapters)} adapters) ──\n")

    exec_summary: dict[str, dict] = {}

    for name, spl_file in spl_files.items():
        for adapter in adapters:
            key     = f"{name}/{adapter}"
            run_dir = output_dir / name / adapter
            run_dir.mkdir(parents=True, exist_ok=True)

            result_json = run_dir / "result.json"
            result_md   = run_dir / "result.md"
            log_file    = run_dir / "exec.log"

            print(f"  [{key}]")

            rc, _stdout, stderr, wall_time = _run(
                [
                    sys.executable, "-m", "src.cli", "exec",
                    str(spl_file),
                    "--adapter",   adapter,
                    "--output",    str(result_json),
                    "--log",       str(log_file),
                    "--log-level", "debug",
                ],
                label=f"exec --adapter {adapter}",
            )

            if rc == 0 and result_json.exists():
                try:
                    data    = json.loads(result_json.read_text(encoding="utf-8"))
                    primary = data.get("primary_result", "")
                    if primary:
                        result_md.write_text(primary, encoding="utf-8")
                except Exception:
                    pass

            metrics = _extract_metrics(result_json)
            metrics["returncode"]  = rc
            metrics["wall_time_s"] = round(wall_time, 2)
            metrics["status"]      = "ok" if rc == 0 else "error"
            if rc != 0 and "error" not in metrics:
                metrics["error"] = stderr[-400:]

            exec_summary[key] = metrics

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("  RESULTS SUMMARY")
    print(SEP)

    # Phase 1 table
    if gen_summary:
        print("\n  Phase 1 — Generation / Scripts\n")
        _print_table(
            ["Name", "Status", "SPL Lines", "Time"],
            [
                [
                    name,
                    r.get("status", "?"),
                    str(r.get("spl_lines", "—")),
                    f"{r.get('elapsed_s', 0):.1f}s" if "elapsed_s" in r else "—",
                ]
                for name, r in gen_summary.items()
            ],
        )

    # Phase 2 execution metrics table
    print("\n  Phase 2 — Execution Metrics\n")
    rows = []
    for name in spl_files:
        for adapter in adapters:
            key = f"{name}/{adapter}"
            r   = exec_summary.get(key, {})
            if r.get("status") == "ok":
                cost = r.get("total_cost_usd")
                rows.append([
                    key,
                    f"{r.get('total_tokens', 0):,}",
                    f"{r.get('total_latency_s', 0):.1f}s",
                    f"${cost:.5f}" if cost else "$0.00000",
                    "✓",
                ])
            else:
                rows.append([key, "—", "—", "—", "✗ ERROR"])
    if rows:
        _print_table(["Experiment", "Tokens", "Latency", "Cost", "Status"], rows)
    else:
        print("  (no results)")

    # Per-CTE model routing table
    print("\n  Per-CTE Model Routing (MoM evidence)\n")
    printed_any = False
    for name in spl_files:
        for adapter in adapters:
            key  = f"{name}/{adapter}"
            ctes = exec_summary.get(key, {}).get("cte_runs", [])
            if not ctes:
                continue
            printed_any = True
            print(f"    ┌─ [{key}]")
            for cte in ctes:
                cost   = cte.get("cost_usd")
                cost_s = f"${cost:.5f}" if cost is not None else "    n/a"
                print(
                    f"    │  {cte['prompt_name']:<28} "
                    f"model={cte['model']:<22} "
                    f"tok={cte['total_tokens']:>5}  "
                    f"lat={cte['latency_s']:>5.1f}s  "
                    f"cost={cost_s}"
                )
            print("    └" + "─" * 60)
    if not printed_any:
        print("  (no CTE routing data)")

    # Persist full summary
    summary = {
        "experiment":  "spl-runner",
        "timestamp":   TIMESTAMP,
        "output_dir":  str(output_dir),
        "adapters":    adapters,
        "queries":     {k: v[:80] + "…" for k, v in queries.items()},
        "pre_spl":     {k: str(v) for k, v in pre_spl.items()},
        "generation":  gen_summary,
        "execution":   exec_summary,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n  Full results : {output_dir}")
    print(f"  Summary JSON : {summary_path}")
    print(f"\n{SEP}\n")


# ── CLI (click) ────────────────────────────────────────────────────────────────

@click.command()
@click.option(
    "--adapters", "-a",
    default=",".join(DEFAULT_ADAPTERS),
    show_default=True,
    help="Comma-separated adapter list (claude_cli, openrouter, ollama).",
)
@click.option(
    "--query", "-q",
    multiple=True,
    metavar="TEXT",
    help=(
        "Natural-language query to translate → SPL → execute. "
        "Repeatable: -q 'Q1' -q 'Q2'. "
        "If neither --query nor --scripts is given, the 3 built-in queries are used."
    ),
)
@click.option(
    "--scripts", "-s",
    default=None,
    metavar="FILE[,FILE...]",
    help=(
        "Comma-separated .spl file paths to execute directly (Phase 2 only, "
        "no NL→SPL generation)."
    ),
)
@click.option(
    "--output-dir", "-o",
    default=str(DEFAULT_OUTPUT_DIR),
    show_default=True,
    type=click.Path(path_type=Path),
    help="Root directory for all output files.",
)
def cli(adapters: str, query: tuple[str, ...], scripts: str | None, output_dir: Path) -> None:
    """SPL Runner: automate NL→SPL→exec experiments across adapters.

    \b
    Three modes (combinable):
      default   No flags          → built-in 3 queries (EN / ZH / AR) × adapters
      --query   Custom NL query   → generate SPL then execute × adapters
      --scripts Pre-written .spl  → execute directly × adapters (skip generation)

    \b
    Note: claude_cli cannot be used inside an active Claude Code session.
    Run from a regular terminal, or prepend:  env -u CLAUDECODE
    """
    adapter_list = [a.strip() for a in adapters.split(",") if a.strip()]

    # Resolve which queries to use
    if query:
        # Name custom queries q1, q2, … (or just "q1" if only one)
        if len(query) == 1:
            queries = {"q1": query[0]}
        else:
            queries = {f"q{i + 1}": q for i, q in enumerate(query)}
    elif not scripts:
        # No --query and no --scripts → fall back to built-in set
        queries = BUILTIN_QUERIES
    else:
        queries = {}

    # Resolve pre-written .spl files
    pre_spl: dict[str, Path] = {}
    if scripts:
        for raw in scripts.split(","):
            p = Path(raw.strip()).expanduser().resolve()
            pre_spl[p.stem] = p

    if not queries and not pre_spl:
        raise click.UsageError("Nothing to run. Provide --query and/or --scripts.")

    main(
        adapters=adapter_list,
        output_dir=output_dir,
        queries=queries,
        pre_spl=pre_spl,
    )


if __name__ == "__main__":
    cli()
