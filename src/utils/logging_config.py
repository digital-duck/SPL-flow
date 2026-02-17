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

The spl-llm package emits its own logs under the "spl" and "spl.executor"
hierarchy (adapter-level HTTP, token counts, raw responses).  Call
bridge_spl_logger() after setup_logging() to route those into the same file.

Usage
-----
In each module declare the module-level logger once:

    from src.utils.logging_config import get_logger
    _log = get_logger("nodes.text2spl")   # → spl_flow.nodes.text2spl

Setup (call once per process — CLI entry point or Streamlit app startup):

    from src.utils.logging_config import setup_logging, bridge_spl_logger
    log_path = setup_logging("run", adapter="openrouter", log_level="debug")
    bridge_spl_logger(log_path)   # also capture spl.adapters.* logs

Log file naming:
    logs/<run_name>[-<adapter>]-<YYYYMMDD-HHMMSS>.log
    e.g.  logs/run-openrouter-20260215-143022.log
          logs/streamlit/streamlit-20260216-170000.log
"""
import logging
from pathlib import Path

from dd_logging import (
    disable_logging as _disable,
    get_logger as _get,
    setup_logging as _setup,
)
from dd_logging.core import FORMATTER, LOG_LEVELS

_ROOT            = "spl_flow"
LOG_DIR          = Path(__file__).resolve().parent.parent.parent / "logs"
STREAMLIT_LOG_DIR = LOG_DIR / "streamlit"


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


def bridge_spl_logger(log_path: Path, log_level: str = "debug") -> None:
    """Route the spl.* logger hierarchy (SPL engine + adapters) to *log_path*.

    setup_logging() configures spl_flow.* only.  The SPL engine and its
    adapters (openrouter, ollama, …) log under spl.* — a separate hierarchy
    that would otherwise go nowhere.  Call this once after setup_logging() to
    direct both trees into the same timestamped file.

    Safe to call multiple times — stale FileHandlers are removed before the
    new one is attached.

    Parameters
    ----------
    log_path  : absolute path returned by setup_logging()
    log_level : ``"debug"`` (default) | ``"info"`` | ``"warning"`` | ``"error"``
    """
    level = LOG_LEVELS.get(log_level.lower(), logging.DEBUG)
    spl_root = logging.getLogger("spl")
    spl_root.handlers = [
        h for h in spl_root.handlers if not isinstance(h, logging.FileHandler)
    ]
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(FORMATTER)
    spl_root.addHandler(fh)
    spl_root.setLevel(logging.DEBUG)
    spl_root.propagate = False
