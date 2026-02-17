"""SPL-Flow evaluation script.

For each question in questions.csv:
  1. api.generate()  →  SPL  (saved to spl/<id>_<domain>.spl)
  2. api.exec_spl()  →  answer
  3. Append row to results.csv

Incremental: already-answered rows are skipped on rerun.

Usage examples
--------------
# Run a single domain (quick smoke-test)
python dataset/eval/run_eval.py --domain movie

# Run multiple domains
python dataset/eval/run_eval.py --domain physics,math

# Run everything except the domains already done
python dataset/eval/run_eval.py --exclude movie

# Skip several domains
python dataset/eval/run_eval.py --exclude movie,physics,math

# Restrict to a question-ID range
python dataset/eval/run_eval.py --start 1 --end 20

# Dry-run: show what would run without calling the API
python dataset/eval/run_eval.py --domain movie --dry-run
"""
import sys
import csv
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module="pocketflow")

import click

# ── sys.path so we can import src.api ─────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent          # SPL-Flow project root
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")

# ── Paths ─────────────────────────────────────────────────────────────────────
# Source files (version-controlled) live in dataset/eval/
QUESTIONS_CSV = _HERE / "questions.csv"

# Runtime outputs (potentially large, gitignored) live in data/eval/
_OUTPUT_DIR = _ROOT / "data" / "eval"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_CSV = _OUTPUT_DIR / "results.csv"
SPL_DIR     = _OUTPUT_DIR / "spl"
SPL_DIR.mkdir(exist_ok=True)

ADAPTER = "claude_cli"

RESULTS_FIELDS = [
    "id", "domain", "question",
    "spl_generated",      # Y / N
    "spl_file",           # relative path to .spl file
    "answer",             # LLM response
    "latency_s",          # wall-clock seconds for exec
    "total_tokens",
    "error",
    "correct",            # manual: Y / N / ?
    "notes",              # manual: free-form notes
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_questions(
    start: int,
    end: int,
    include_domains: set[str] | None,
    exclude_domains: set[str],
) -> list[dict]:
    with open(QUESTIONS_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    result = []
    for row in rows:
        qid = int(row["id"])
        dom = row["domain"]
        if not (start <= qid <= end):
            continue
        if include_domains and dom not in include_domains:
            continue
        if dom in exclude_domains:
            continue
        result.append(row)
    return result


def _load_done_ids() -> set[int]:
    if not RESULTS_CSV.exists():
        return set()
    with open(RESULTS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {int(row["id"]) for row in reader if row.get("answer", "").strip()}


def _init_results_csv():
    if not RESULTS_CSV.exists():
        with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=RESULTS_FIELDS).writeheader()


def _append_result(row: dict):
    with open(RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RESULTS_FIELDS, extrasaction="ignore")
        w.writerow(row)


def _spl_path(qid: int, domain: str) -> Path:
    return SPL_DIR / f"{qid:03d}_{domain}.spl"


def _comma_set(value: str | None) -> set[str]:
    """Parse a comma-delimited string into a set of stripped tokens."""
    if not value:
        return set()
    return {v.strip() for v in value.split(",") if v.strip()}


# ── Core processing ────────────────────────────────────────────────────────────

def process_question(row: dict, dry_run: bool) -> dict:
    from src import api

    qid    = int(row["id"])
    domain = row["domain"]
    q      = row["question"]
    result = {
        "id":            qid,
        "domain":        domain,
        "question":      q,
        "spl_generated": "N",
        "spl_file":      "",
        "answer":        "",
        "latency_s":     "",
        "total_tokens":  "",
        "error":         "",
        "correct":       "",
        "notes":         "",
    }

    if dry_run:
        click.echo(f"  [dry-run] would process q{qid}: {q[:70]}...")
        return result

    # ── Step 1: Text2SPL ──────────────────────────────────────────────────────
    click.echo(f"  Generating SPL... ", nl=False)
    gen = api.generate(q, adapter=ADAPTER)
    if gen.get("error"):
        result["error"] = f"SPL gen: {gen['error']}"
        click.secho(f"ERROR  {gen['error']}", fg="red")
        return result

    spl = gen.get("spl_query", "").strip()
    if not spl:
        result["error"] = "SPL generation returned empty string"
        click.secho("ERROR  empty SPL", fg="red")
        return result

    spl_file = _spl_path(qid, domain)
    spl_file.write_text(spl, encoding="utf-8")
    result["spl_generated"] = "Y"
    result["spl_file"] = str(spl_file.relative_to(_ROOT))
    click.secho(f"OK  ({len(spl.splitlines())} lines)", fg="green")

    # ── Step 2: Execute SPL ───────────────────────────────────────────────────
    click.echo(f"  Executing SPL...  ", nl=False)
    t0 = time.time()
    exec_res = api.exec_spl(spl, adapter=ADAPTER)
    elapsed = time.time() - t0

    if exec_res.get("error"):
        result["error"]     = f"Exec: {exec_res['error']}"
        result["latency_s"] = f"{elapsed:.1f}"
        click.secho(f"ERROR  {exec_res['error']}", fg="red")
        return result

    answer       = exec_res.get("primary_result", "")
    exec_results = exec_res.get("execution_results", [])
    tokens       = sum(r.get("total_tokens", 0) for r in exec_results)

    result["answer"]       = answer
    result["latency_s"]    = f"{elapsed:.1f}"
    result["total_tokens"] = str(tokens)
    click.secho(
        f"OK  ({tokens} tokens, {elapsed:.1f}s, {len(answer)} chars)", fg="green"
    )
    return result


# ── CLI ────────────────────────────────────────────────────────────────────────

@click.command()
@click.option(
    "--domain",
    default=None,
    metavar="DOMAINS",
    help="Comma-separated list of domains to include, e.g. movie  or  physics,math",
)
@click.option(
    "--exclude",
    default=None,
    metavar="DOMAINS",
    help="Comma-separated list of domains to exclude, e.g. movie  or  movie,physics",
)
@click.option("--start", default=1,   show_default=True, help="First question ID to process")
@click.option("--end",   default=999, show_default=True, help="Last  question ID to process")
@click.option("--dry-run", is_flag=True, help="Show what would run without calling the API")
def main(domain, exclude, start, end, dry_run):
    """SPL-Flow evaluation runner.

    Reads questions.csv, generates SPL via Text2SPL, executes with claude_cli,
    and saves answers to results.csv for manual verification.
    """
    include_domains = _comma_set(domain)
    exclude_domains = _comma_set(exclude)

    questions = _load_questions(start, end, include_domains or None, exclude_domains)
    if not questions:
        click.secho("No questions matched the filter.", fg="yellow")
        return

    _init_results_csv()
    done_ids = _load_done_ids()

    to_process = [q for q in questions if int(q["id"]) not in done_ids]
    skipped    = len(questions) - len(to_process)

    # Print summary header
    click.echo()
    click.secho("SPL-Flow Evaluation", bold=True)
    click.echo(f"  Adapter           : {ADAPTER}")
    if include_domains:
        click.echo(f"  Domains (include) : {', '.join(sorted(include_domains))}")
    if exclude_domains:
        click.echo(f"  Domains (exclude) : {', '.join(sorted(exclude_domains))}")
    click.echo(f"  Questions matched : {len(questions)}")
    click.echo(f"  Already done      : {skipped}  (skipping)")
    click.secho(f"  To process        : {len(to_process)}", bold=True)
    if dry_run:
        click.secho("  Mode              : DRY RUN", fg="yellow")
    click.echo()

    errors = 0
    for i, row in enumerate(to_process, 1):
        click.secho(
            f"[{i}/{len(to_process)}]  id={row['id']}  domain={row['domain']}",
            bold=True,
        )
        click.echo(f"  Q: {row['question'][:80]}{'...' if len(row['question']) > 80 else ''}")
        result = process_question(row, dry_run=dry_run)
        if not dry_run:
            _append_result(result)
            if result["error"]:
                errors += 1
        click.echo()

    click.echo("─" * 64)
    status_color = "red" if errors else "green"
    click.secho(
        f"Done.  Processed {len(to_process)} questions, {errors} errors.",
        fg=status_color, bold=True,
    )
    click.echo(f"Results  → {RESULTS_CSV}")
    click.echo(f"SPL files→ {SPL_DIR}/")
    click.echo()
    click.echo("Fill in the 'correct' column in results.csv (Y / N / ?)")


if __name__ == "__main__":
    main()
