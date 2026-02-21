#!/usr/bin/env python3
"""
Text2SPL E2E Experiment Runner
================================
Phase 1 : NL → SPL  (once per language, via claude_cli Text2SPL)
Phase 2 : SPL exec  (each .spl × N adapters)

Output layout:
    text2spl-<TIMESTAMP>/
    ├── summary.json
    ├── english/
    │   ├── generated.spl
    │   ├── generate.log
    │   ├── claude_cli/  { result.json, result.md, exec.log }
    │   ├── openrouter/  { ... }
    │   └── ollama/      { ... }
    ├── chinese/  (same)
    └── arabic/   (same)

Usage:
    cd <SPL-flow root>
    python experiments/run_text2spl.py
    python experiments/run_text2spl.py --adapters claude_cli,openrouter
    python experiments/run_text2spl.py --output-dir /tmp/my-run

Note: claude_cli adapter cannot run inside an active Claude Code session.
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

# The script lives at <repo>/experiments/run_text2spl.py
SPLFLOW_DIR = Path(__file__).parent.parent.resolve()

TIMESTAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
DEFAULT_OUTPUT_DIR = (
    Path.home() / "Downloads" / "Zinets" / "spl-experiments" / f"text2spl-{TIMESTAMP}"
)

# ── Queries ────────────────────────────────────────────────────────────────────

QUERIES: dict[str, str] = {
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

DEFAULT_LANGS: list[str] = []   # empty = run all languages

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
    """
    Parse the JSON saved by `splflow exec --output result.json` and return
    a flat summary plus per-CTE routing details.
    """
    if not json_path.exists():
        return {"error": "output json missing"}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"error": f"json parse error: {exc}"}

    runs = data.get("execution_results", [])

    cte_rows = []
    for r in runs:
        cte_rows.append({
            "prompt_name":   r.get("prompt_name", "?"),
            "model":         r.get("model", "?"),
            "input_tokens":  r.get("input_tokens", 0),
            "output_tokens": r.get("output_tokens", 0),
            "total_tokens":  r.get("total_tokens", 0),
            "latency_s":     round(r.get("latency_ms", 0) / 1_000, 2),
            "cost_usd":      r.get("cost_usd"),
        })

    total_tokens  = sum(r.get("total_tokens", 0) for r in runs)
    total_cost    = sum(r.get("cost_usd") or 0  for r in runs)
    total_latency = sum(r.get("latency_ms", 0)  for r in runs) / 1_000

    return {
        "cte_runs":        cte_rows,
        "total_tokens":    total_tokens,
        "total_cost_usd":  round(total_cost,    6),
        "total_latency_s": round(total_latency, 2),
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

def main(adapters: list[str], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{SEP}")
    print(f"  Text2SPL E2E Experiment   {TIMESTAMP}")
    print(f"  SPL-flow dir : {SPLFLOW_DIR}")
    print(f"  Output       : {output_dir}")
    print(f"  Adapters     : {', '.join(adapters)}")
    print(SEP)

    # ── Phase 1: NL → SPL (once per language) ─────────────────────────────────
    print(f"\n── Phase 1: NL → SPL  (Text2SPL, claude_cli) ────────────────────────\n")

    spl_files: dict[str, Path] = {}   # lang → generated .spl path
    gen_summary: dict[str, dict] = {}

    for lang, query in QUERIES.items():
        if DEFAULT_LANGS and lang not in DEFAULT_LANGS:
            print(f"  [{lang}]  SKIPPED (not in DEFAULT_LANGS)")
            continue
        
        lang_dir = output_dir / lang
        lang_dir.mkdir(exist_ok=True)

        spl_out = lang_dir / "generated.spl"
        log_out = lang_dir / "generate.log"

        print(f"  [{lang}]  {query[:70]}{'...' if len(query) > 70 else ''}")

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
            spl_files[lang]  = spl_out
            gen_summary[lang] = {
                "status":     "ok",
                "spl_lines":  spl_lines,
                "elapsed_s":  round(elapsed, 2),
                "spl_file":   str(spl_out),
                "log_file":   str(log_out),
            }
            print(f"      SPL: {spl_lines} lines  →  {spl_out.name}")
        else:
            gen_summary[lang] = {
                "status":    "error",
                "elapsed_s": round(elapsed, 2),
                "error":     stderr[-400:],
            }
            print(f"      FAILED – skipping execution for {lang}")

    # ── Phase 2: SPL exec × adapters ──────────────────────────────────────────
    print(f"\n── Phase 2: SPL Execution  ({len(spl_files)} languages × {len(adapters)} adapters) ──\n")

    exec_summary: dict[str, dict] = {}  # "lang/adapter" → metrics

    for lang, spl_file in spl_files.items():
        for adapter in adapters:
            key     = f"{lang}/{adapter}"
            run_dir = output_dir / lang / adapter
            run_dir.mkdir(exist_ok=True)

            result_json = run_dir / "result.json"
            result_md   = run_dir / "result.md"
            log_file    = run_dir / "exec.log"

            print(f"  [{key}]")

            rc, _stdout, stderr, wall_time = _run(
                [
                    sys.executable, "-m", "src.cli", "exec",
                    str(spl_file),
                    "--adapter", adapter,
                    "--output",  str(result_json),
                    "--log",     str(log_file),
                    "--log-level", "debug",
                ],
                label=f"exec --adapter {adapter}",
            )

            # Save markdown result for human reading
            if rc == 0 and result_json.exists():
                try:
                    data = json.loads(result_json.read_text(encoding="utf-8"))
                    primary = data.get("primary_result", "")
                    if primary:
                        result_md.write_text(primary, encoding="utf-8")
                except Exception:
                    pass

            metrics = _extract_metrics(result_json)
            metrics["returncode"]  = rc
            metrics["wall_time_s"] = round(wall_time, 2)
            if rc != 0:
                metrics["status"] = "error"
                if "error" not in metrics:
                    metrics["error"] = stderr[-400:]
            else:
                metrics["status"] = "ok"

            exec_summary[key] = metrics

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("  RESULTS SUMMARY")
    print(SEP)

    # Phase 1 table
    print("\n  Phase 1 — Text2SPL Generation\n")
    _print_table(
        ["Language", "Status", "SPL Lines", "Time"],
        [
            [
                lang,
                r.get("status", "?"),
                str(r.get("spl_lines", "—")),
                f"{r.get('elapsed_s', 0):.1f}s",
            ]
            for lang, r in gen_summary.items()
        ],
    )

    # Phase 2 table
    print("\n  Phase 2 — Execution Metrics\n")
    rows = []
    for lang in QUERIES:
        for adapter in adapters:
            key = f"{lang}/{adapter}"
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
    _print_table(["Experiment", "Tokens", "Latency", "Cost", "Status"], rows)

    # MoM routing table (most important for the paper)
    print("\n  Per-CTE Model Routing (MoM evidence)\n")
    for lang in QUERIES:
        for adapter in adapters:
            key = f"{lang}/{adapter}"
            r   = exec_summary.get(key, {})
            ctes = r.get("cte_runs", [])
            if not ctes:
                continue
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

    # Persist full summary
    summary = {
        "experiment":  "text2spl",
        "timestamp":   TIMESTAMP,
        "output_dir":  str(output_dir),
        "adapters":    adapters,
        "queries":     {k: v[:80] + "…" for k, v in QUERIES.items()},
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
    "--adapters",
    default=",".join(DEFAULT_ADAPTERS),
    show_default=True,
    help="Comma-separated list of adapters to test (claude_cli, openrouter, ollama).",
)
@click.option(
    "--output-dir",
    default=str(DEFAULT_OUTPUT_DIR),
    show_default=True,
    type=click.Path(path_type=Path),
    help="Root directory for all output files.",
)
def cli(adapters: str, output_dir: Path) -> None:
    """Run Text2SPL E2E experiments: NL → SPL (Phase 1) then exec × adapters (Phase 2).

    \b
    Must be run from the SPL-flow repo root, or the script resolves it
    automatically from its own location.

    \b
    Note: claude_cli cannot be used inside an active Claude Code session.
    Run from a regular terminal, or prepend:  env -u CLAUDECODE
    """
    adapter_list = [a.strip() for a in adapters.split(",") if a.strip()]
    main(adapters=adapter_list, output_dir=output_dir)


if __name__ == "__main__":
    cli()
