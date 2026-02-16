#!/usr/bin/env python3
"""Parse `splflow models` terminal output into a clean CSV.

Usage:
    python parse-openrouter-models.py                          # reads openrouter-models-*.txt in same dir
    python parse-openrouter-models.py path/to/file.txt        # explicit input
    python parse-openrouter-models.py file.txt -o models.csv  # explicit output

Output columns:
    model_id, name, input_per_m_usd, output_per_m_usd

"free" pricing is stored as 0.0.
Duplicate model IDs (same model appears in multiple query results) are deduplicated;
the first occurrence wins.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

# ── regex ──────────────────────────────────────────────────────────────────────
# Matches data rows like:
#   anthropic/claude-opus-4.6   Anthropic: Claude Opus 4.6   $5.00   $25.00
#   openrouter/auto             Auto Router                    free     free
#   qwen/qwen3-4b:free          Qwen: Qwen3 4B (free)          free     free
_ROW_RE = re.compile(
    r"^\s{2}"                          # leading 2 spaces (data rows only)
    r"(?P<model_id>\S+)"               # model id (no spaces)
    r"\s{2,}"                          # separator (≥2 spaces)
    r"(?P<name>.+?)"                   # name (non-greedy)
    r"\s{2,}"                          # separator
    r"(?P<inp>\$[\d.]+|free)"          # input price
    r"\s+"
    r"(?P<out>\$[\d.]+|free)"          # output price
    r"\s*$"
)


def _parse_price(raw: str) -> float:
    """'$3.00' → 3.0,  'free' → 0.0"""
    raw = raw.strip()
    if raw.lower() == "free":
        return 0.0
    return float(raw.lstrip("$"))


def parse_file(path: Path) -> list[dict]:
    """Parse one terminal-output file; return list of row dicts."""
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _ROW_RE.match(line)
        if not m:
            continue
        model_id = m.group("model_id")
        # Skip header row (shouldn't match, but guard anyway)
        if model_id.lower() == "model":
            continue
        rows.append({
            "model_id": model_id,
            "name": m.group("name").strip(),
            "input_per_m_usd": _parse_price(m.group("inp")),
            "output_per_m_usd": _parse_price(m.group("out")),
        })
    return rows


def deduplicate(rows: list[dict]) -> list[dict]:
    """Keep first occurrence of each model_id; sort by model_id."""
    seen: set[str] = set()
    deduped: list[dict] = []
    for row in rows:
        if row["model_id"] not in seen:
            seen.add(row["model_id"])
            deduped.append(row)
    return sorted(deduped, key=lambda r: r["model_id"])


def write_csv(rows: list[dict], out_path: Path) -> None:
    fieldnames = ["model_id", "name", "input_per_m_usd", "output_per_m_usd"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} models → {out_path}")


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "inputs", nargs="*",
        help="Input .txt file(s). Defaults to openrouter-models-*.txt in the script directory.",
    )
    parser.add_argument(
        "-o", "--output", default=None,
        help="Output CSV path. Defaults to openrouter-models.csv next to the script.",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).parent

    # Resolve input files
    if args.inputs:
        input_paths = [Path(p) for p in args.inputs]
    else:
        input_paths = sorted(script_dir.glob("openrouter-models-*.txt"))
        if not input_paths:
            print("No openrouter-models-*.txt files found. Pass a filename explicitly.")
            sys.exit(1)

    # Parse + merge all files
    all_rows: list[dict] = []
    for p in input_paths:
        if not p.exists():
            print(f"File not found: {p}", file=sys.stderr)
            sys.exit(1)
        file_rows = parse_file(p)
        print(f"  {p.name}: {len(file_rows)} rows parsed")
        all_rows.extend(file_rows)

    rows = deduplicate(all_rows)
    print(f"  → {len(rows)} unique models after deduplication")

    # Resolve output path
    out_path = Path(args.output) if args.output else script_dir / "openrouter-models.csv"
    write_csv(rows, out_path)


if __name__ == "__main__":
    main()
