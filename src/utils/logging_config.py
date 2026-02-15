"""Logging configuration for SPL-Flow — thin wrapper around dd-logging.

Logger hierarchy (mirrors the spl-llm package pattern):

    spl_flow                    root — all SPL-flow orchestration events
    ├── spl_flow.api            api.py public function entry/exit
    ├── spl_flow.nodes.text2spl Text2SPL generation + RAG retrieval
    ├── spl_flow.nodes.validate parse + validation + retry loop
    ├── spl_flow.nodes.execute  execution summary (model, tokens, latency)
    ├── spl_flow.nodes.deliver  sync / async delivery
    ├── spl_flow.nodes.benchmark benchmark run + per-model results
    └── spl_flow.flows          flow-level entry / exit

Note: the spl-llm package emits its own logs under the "spl" and "spl.executor"
hierarchy (CTE dispatch, LLM calls, response text). SPL-flow does NOT duplicate
those — it logs at the orchestration / flow layer only.

Usage
-----
In each module declare the module-level logger once:

    from src.utils.logging_config import get_logger
    _log = get_logger("nodes.text2spl")   # → spl_flow.nodes.text2spl

Setup (call once per process — CLI entry point or API function):

    from src.utils.logging_config import setup_logging
    log_path = setup_logging("run", adapter="openrouter", log_level="info")

Log file naming:
    logs/<run_name>-<adapter>-<YYYYMMDD-HHMMSS>.log
    e.g.  logs/run-openrouter-20260215-143022.log
          logs/benchmark-claude_cli-20260215-144500.log
          logs/generate-20260215-145001.log
"""
from pathlib import Path

from dd_logging import (
    disable_logging as _disable,
    get_logger as _get,
    setup_logging as _setup,
)

_ROOT   = "spl_flow"
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"


def get_logger(name: str):
    """Return a child logger under the spl_flow hierarchy.

    Parameters
    ----------
    name : dotted sub-path, e.g. ``"nodes.text2spl"`` or ``"api"``

    Returns
    -------
    logging.Logger  named  ``spl_flow.<name>``
    """
    return _get(name, _ROOT)


def setup_logging(
    run_name: str,
    adapter: str = "",
    log_level: str = "info",
    log_dir=None,
    console: bool = False,
) -> Path:
    """Attach a timestamped FileHandler to the spl_flow root logger.

    Safe to call multiple times in one process — stale FileHandlers from
    previous calls are removed before the new one is added.

    Parameters
    ----------
    run_name  : short label for the log filename, e.g. ``"run"``, ``"generate"``,
                ``"benchmark"``, ``"exec"``
    adapter   : LLM adapter name appended to the filename (omitted if empty)
    log_level : ``"debug"`` | ``"info"`` | ``"warning"`` | ``"error"``
    log_dir   : override default ``logs/`` directory
    console   : also attach a StreamHandler (useful in CLI --verbose mode)

    Returns
    -------
    Path  absolute path of the log file created
    """
    return _setup(
        run_name,
        root_name=_ROOT,
        adapter=adapter,
        log_level=log_level,
        log_dir=log_dir or LOG_DIR,
        console=console,
    )


def disable_logging() -> None:
    """Remove all handlers from the spl_flow root logger (no-op log mode)."""
    _disable(_ROOT)
