"""SQLite persistence for SPL-Flow sessions and benchmark runs.

Tables
------
sessions
    Full pipeline run: original query, generated SPL, edited SPL (if changed),
    result markdown, and execution metrics.

benchmark_runs
    One row per benchmark execution; individual model runs stored as JSON.

DB location: <project_root>/data/splflow.db
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DB_PATH = _PROJECT_ROOT / "data" / "splflow.db"

_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    original_query  TEXT    NOT NULL,
    generated_spl   TEXT    DEFAULT '',
    edited_spl      TEXT    DEFAULT '',
    result_markdown TEXT    DEFAULT '',
    model           TEXT    DEFAULT '',
    total_tokens    INTEGER DEFAULT 0,
    latency_ms      REAL    DEFAULT 0.0,
    cost_usd        REAL,
    is_active       INTEGER DEFAULT 1,
    created_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    benchmark_name  TEXT    DEFAULT '',
    spl_query       TEXT    DEFAULT '',
    adapter         TEXT    DEFAULT '',
    runs_json       TEXT    DEFAULT '[]',
    created_at      TEXT    NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_DDL)
        # Migration: add is_active to existing DBs that predate this column
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN is_active INTEGER DEFAULT 1")
        except Exception:
            pass  # column already exists — safe to ignore


# ── Sessions ──────────────────────────────────────────────────────────────────

def save_session(
    original_query: str,
    generated_spl: str,
    edited_spl: str,
    result_markdown: str,
    model: str = "",
    total_tokens: int = 0,
    latency_ms: float = 0.0,
    cost_usd: float | None = None,
) -> int:
    """Insert a pipeline session row and return its id."""
    init_db()
    ts = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO sessions
               (original_query, generated_spl, edited_spl, result_markdown,
                model, total_tokens, latency_ms, cost_usd, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (original_query, generated_spl, edited_spl, result_markdown,
             model, total_tokens, latency_ms, cost_usd, ts),
        )
        return cur.lastrowid


def list_sessions(limit: int = 100) -> list[dict]:
    """Return active requests newest-first."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE is_active = 1 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def deactivate_session(session_id: int) -> None:
    """Soft-delete: set is_active = 0 (reversible)."""
    init_db()
    with _connect() as conn:
        conn.execute("UPDATE sessions SET is_active = 0 WHERE id=?", (session_id,))


# ── Benchmark runs ────────────────────────────────────────────────────────────

def save_benchmark(
    benchmark_name: str,
    spl_query: str,
    adapter: str,
    runs: list[dict],
) -> int:
    """Insert a benchmark run row and return its id."""
    init_db()
    ts = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO benchmark_runs
               (benchmark_name, spl_query, adapter, runs_json, created_at)
               VALUES (?,?,?,?,?)""",
            (benchmark_name, spl_query, adapter, json.dumps(runs, ensure_ascii=False), ts),
        )
        return cur.lastrowid


def list_benchmarks(limit: int = 50) -> list[dict]:
    """Return benchmark runs newest-first; runs_json decoded to list."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM benchmark_runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["runs"] = json.loads(d.pop("runs_json", "[]"))
        result.append(d)
    return result


def delete_benchmark(benchmark_id: int) -> None:
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM benchmark_runs WHERE id=?", (benchmark_id,))
