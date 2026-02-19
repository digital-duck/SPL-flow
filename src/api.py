"""SPL-Flow public API — first-class interface for system/agent/CLI/UI integration.

All public functions return plain dicts with consistent, documented keys.
PocketFlow graph wiring and shared-store internals are implementation details.

Functions
---------
generate(query, context_text="", *, save_to_rag, user_id)  -> GenerateResult
run(query, *, ...)                                          -> RunResult
exec_spl(spl_query, *, ...)                                 -> ExecResult

Return shapes
-------------
GenerateResult:
    spl_query     : str
    spl_warnings  : list[str]
    retry_count   : int
    error         : str

RunResult:
    spl_query        : str
    spl_warnings     : list[str]
    primary_result   : str
    execution_results: list[PromptResult]
    output_file      : str          # async mode only
    email_sent       : bool
    delivered        : bool
    error            : str

ExecResult:
    primary_result   : str
    execution_results: list[PromptResult]
    error            : str

PromptResult (each item in execution_results):
    prompt_name  : str
    content      : str
    model        : str
    input_tokens : int
    output_tokens: int
    total_tokens : int
    latency_ms   : float
    cost_usd     : float | None
"""
import sys
import asyncio
import hashlib
import warnings
from datetime import datetime, timezone

sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")

from src.flows.spl_flow import generate_spl_only
from src.flows.chunking_flow import run_chunking_flow
from src.utils.logging_config import get_logger

_log = get_logger("api")


# ── RAG store singleton ────────────────────────────────────────────────────────

_rag_store = None   # lazy-initialised on first capture


def _get_rag_store():
    """Return the module-level RAG store, creating it on first access."""
    global _rag_store
    if _rag_store is None:
        from src.rag.factory import get_store
        _rag_store = get_store("chroma")
    return _rag_store


def configure_rag_store(store) -> None:
    """Override the default RAG store.

    Useful for tests (inject an in-memory mock) or for directing writes to a
    per-user collection:
        configure_rag_store(get_store("chroma", collection_name="spl_rag_alice"))
    """
    global _rag_store
    _rag_store = store


# ── internal helpers ──────────────────────────────────────────────────────────

def _record_id(nl_query: str) -> str:
    """Deterministic ID from the normalised query text.

    Upsert semantics: same query → same ID → overwrites previous record,
    so the store always holds the *latest* validated SPL for each unique query.
    """
    return hashlib.sha256(nl_query.strip().lower().encode()).hexdigest()[:32]


def _capture(
    nl_query: str,
    spl_query: str,
    source: str,
    adapter: str,
    spl_warnings: list,
    user_id: str,
) -> None:
    """Save a valid (NL query, SPL) pair to the RAG store.

    Failures are swallowed as warnings — RAG storage must never break the
    main pipeline.
    """
    try:
        from src.rag.store import RAGRecord
        record = RAGRecord(
            id=_record_id(nl_query),
            nl_query=nl_query,
            spl_query=spl_query,
            source=source,
            adapter=adapter,
            spl_warnings=spl_warnings,
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_id=user_id,
            active=True,
        )
        _get_rag_store().upsert(record)
    except Exception as exc:
        warnings.warn(f"RAG auto-capture failed (non-fatal): {exc}")


# ── public API ────────────────────────────────────────────────────────────────

def generate(
    query: str,
    context_text: str = "",
    *,
    adapter: str = "claude_cli",
    save_to_rag: bool = True,
    user_id: str = "",
) -> dict:
    """Translate a natural language query to SPL (no LLM execution).

    Runs Text2SPL + Validate only. Safe to call without consuming execution
    tokens — useful for preview, testing, and human-review workflows.

    Every valid result is automatically saved to the RAG context store
    (save_to_rag=True by default) so the store grows with every real session.
    This is the gold-standard human-labeled data that improves future retrieval.

    Parameters
    ----------
    query        : free-form natural language query
    context_text : optional reference document injected into the Text2SPL prompt
    adapter      : execution adapter the user intends to use — controls which
                   model IDs appear in the routing table ("claude_cli" |
                   "openrouter" | "ollama").  Text2SPL itself always runs
                   on claude_cli; this only shapes the generated SPL.
    save_to_rag  : persist the (query, SPL) pair to the RAG store on success
    user_id      : scope the RAG record to a specific user ("" = shared store)

    Returns
    -------
    GenerateResult dict
    """
    _log.info("api.generate  adapter=%s  query_len=%d  context_len=%d  save_to_rag=%s",
              adapter, len(query), len(context_text), save_to_rag)
    result = generate_spl_only(user_input=query, context_text=context_text, adapter=adapter)
    spl = result.get("spl_query", "")
    error = result.get("error", "")

    if error:
        _log.error("api.generate error: %s", error)
    else:
        _log.info("api.generate done  spl_lines=%d  retries=%d  warnings=%d",
                  len(spl.splitlines()), result.get("retry_count", 0),
                  len(result.get("spl_warnings", [])))

    if save_to_rag and spl and not error:
        _capture(
            nl_query=query,
            spl_query=spl,
            source="human",
            adapter="claude_cli",   # Text2SPL is always claude_cli
            spl_warnings=result.get("spl_warnings", []),
            user_id=user_id,
        )

    return {
        "spl_query": spl,
        "spl_warnings": result.get("spl_warnings", []),
        "retry_count": result.get("retry_count", 0),
        "error": error,
    }


def run(
    query: str,
    *,
    context_text: str = "",
    adapter: str = "claude_cli",
    delivery_mode: str = "sync",
    notify_email: str = "",
    spl_params: dict | None = None,
    cache_enabled: bool = False,
    provider: str = "",
    save_to_rag: bool = True,
    user_id: str = "",
) -> dict:
    """Full pipeline: NL → SPL → validate → execute → deliver.

    Parameters
    ----------
    query         : free-form natural language query
    context_text  : reference document; injected into the Text2SPL prompt
                    and automatically set as spl_params["document"] for SPL
                    context reference
    adapter       : LLM adapter for execution steps —
                    "claude_cli" | "openrouter" | "ollama"
                    (Text2SPL always uses claude_cli regardless)
    delivery_mode : "sync"  — return primary_result directly
                    "async" — save result to /tmp file; return output_file path
    notify_email  : email address for async notification (SMTP stub in v0.2)
    spl_params    : additional context params injected into the SPL query
    cache_enabled : enable SQLite result cache to avoid redundant LLM calls
    save_to_rag   : persist the (query, SPL) pair to the RAG store on success
    user_id       : scope the RAG record to a specific user

    Returns
    -------
    RunResult dict
    """
    params = dict(spl_params or {})
    if context_text:
        params.setdefault("document", context_text)

    _log.info(
        "api.run  adapter=%s  provider=%s  delivery=%s  cache=%s  query_len=%d",
        adapter, provider or "(best-of-breed)", delivery_mode, cache_enabled, len(query),
    )
    result = run_chunking_flow(
        user_input=query,
        context_text=context_text,
        adapter=adapter,
        delivery_mode=delivery_mode,
        notify_email=notify_email,
        cache_enabled=cache_enabled,
        provider=provider,
    )
    # Merge any caller-supplied spl_params on top (chunking flow builds its
    # own params from chunks, but direct callers may supply extras).
    if params and not result.get("chunking", {}).get("enabled"):
        # Only inject caller params for the non-chunking path;
        # in the chunking path params are chunk_1..chunk_k and must not be
        # overwritten with the raw context_text "document" key.
        result.setdefault("spl_params", {}).update(params)

    spl = result.get("spl_query", "")
    error = result.get("error", "")

    if error:
        _log.error("api.run error: %s", error)
    else:
        exec_results = result.get("execution_results", [])
        total_tokens = sum(r.get("total_tokens", 0) for r in exec_results)
        _log.info(
            "api.run done  prompts=%d  total_tokens=%d  delivered=%s",
            len(exec_results), total_tokens, result.get("delivered", False),
        )

    if save_to_rag and spl and not error:
        _capture(
            nl_query=query,
            spl_query=spl,
            source="human",
            adapter=adapter,
            spl_warnings=result.get("spl_warnings", []),
            user_id=user_id,
        )

    return {
        "spl_query": spl,
        "spl_warnings": result.get("spl_warnings", []),
        "primary_result": result.get("primary_result", ""),
        "execution_results": result.get("execution_results", []),
        "output_file": result.get("output_file", ""),
        "email_sent": result.get("email_sent", False),
        "delivered": result.get("delivered", False),
        "error": error,
        "chunking": result.get("chunking"),  # None for short docs; dict for chunked
    }


def benchmark(
    spl_query: str,
    *,
    models: list | None = None,
    benchmark_name: str = "",
    adapter: str = "claude_cli",
    provider: str = "",
    spl_params: dict | None = None,
    cache_enabled: bool = False,
) -> dict:
    """Run *spl_query* against each model in *models* in parallel.

    Every model receives an identical patched copy of the SPL script with
    its ``USING MODEL`` clauses replaced.  All N copies run concurrently;
    wall-clock time ≈ slowest single model, not N × one model.

    ``"auto"`` is a valid model entry — the router resolves it at execution
    time, so you can benchmark explicit model choices against the auto-router.

    Parameters
    ----------
    spl_query      : valid SPL script (plain, no BENCHMARK wrapper)
    models         : model IDs to run against; default ``["auto"]``
    benchmark_name : label stored in the result JSON
    adapter        : LLM adapter — "claude_cli" | "openrouter" | "ollama"
    provider       : optional provider preference for ``USING MODEL auto``
    spl_params     : extra context params injected into the SPL
    cache_enabled  : enable SQLite result cache

    Returns
    -------
    BenchmarkResult dict::

        {
            "benchmark_name": str,
            "adapter":        str,
            "timestamp":      str,        # ISO 8601 UTC
            "spl_hash":       str,        # sha256[:32] of spl_query
            "params":         dict,
            "winner":         None,       # set after human review
            "runs": [
                {
                    "model_id":       str,
                    "resolved_from":  "explicit" | "auto",
                    "resolved_model": str | None,   # concrete model when auto
                    "input_spl":      str,           # patched SPL actually sent
                    "response":       str,           # final PROMPT output
                    "input_tokens":   int,
                    "output_tokens":  int,
                    "total_tokens":   int,
                    "latency_ms":     float,
                    "cost_usd":       float | None,
                    "prompt_results": list,          # per-CTE breakdown
                    "error":          str,
                },
                ...
            ],
        }
    """
    from src.flows.benchmark_flow import run_benchmark_flow

    _log.info(
        "api.benchmark  models=%d  adapter=%s  provider=%s  cache=%s  spl_len=%d",
        len(models or ["auto"]), adapter, provider or "(best-of-breed)",
        cache_enabled, len(spl_query),
    )
    result = run_benchmark_flow(
        spl_query=spl_query,
        benchmark_name=benchmark_name or _record_id(spl_query)[:8],
        models=models or ["auto"],
        adapter=adapter,
        provider=provider,
        spl_params=spl_params,
        cache_enabled=cache_enabled,
    )

    if result.get("error"):
        _log.error("api.benchmark error: %s", result["error"])
        return {"benchmark_name": benchmark_name, "runs": [], "error": result["error"]}

    bench = result.get("benchmark_result", {})
    runs  = bench.get("runs", [])
    ok    = sum(1 for r in runs if not r.get("error"))
    _log.info("api.benchmark done  runs=%d  ok=%d  failed=%d", len(runs), ok, len(runs) - ok)
    return bench or {
        "benchmark_name": benchmark_name,
        "runs": [],
        "error": "Benchmark produced no result",
    }


def exec_spl(
    spl_query: str,
    *,
    adapter: str = "claude_cli",
    spl_params: dict | None = None,
    cache_enabled: bool = False,
    provider: str = "",
) -> dict:
    """Execute pre-written SPL directly (no Text2SPL step).

    For batch automation, agent-to-agent integration, and testing where the
    SPL query is already known. Bypasses Text2SPL + Validate and runs the SPL
    engine pipeline directly: parse → analyze → optimize → execute.

    Parameters
    ----------
    spl_query     : valid SPL query string
    adapter       : LLM adapter — "claude_cli" | "openrouter" | "ollama"
    spl_params    : context params injected into the SPL execution
    cache_enabled : enable SQLite result cache

    Returns
    -------
    ExecResult dict
    """
    try:
        from spl import parse
        from spl.analyzer import Analyzer
        from spl.optimizer import Optimizer
        from spl.executor import Executor
        from spl.ast_nodes import CreateFunctionStatement
    except ImportError as e:
        return {
            "primary_result": "",
            "execution_results": [],
            "error": f"SPL engine not available: {e}",
        }

    params = dict(spl_params or {})
    try:
        ast = parse(spl_query)
        analysis = Analyzer().analyze(ast)
        plans = Optimizer().optimize(analysis)

        if not plans:
            return {
                "primary_result": "",
                "execution_results": [],
                "error": "No PROMPT statements found in SPL query",
            }

        executor = Executor(adapter_name=adapter, cache_enabled=cache_enabled)

        for s in ast.statements:
            if isinstance(s, CreateFunctionStatement):
                executor.functions.register(s)

        results = []
        for i, plan in enumerate(plans):
            from src.nodes.execute_spl import _find_stmt, _extract_texts
            from src.utils.model_router import auto_route
            stmt = _find_stmt(ast, plan.prompt_name)
            is_final = (i == len(plans) - 1)
            if stmt is not None and (stmt.model or "").strip().lower() == "auto":
                system_role, instruction = _extract_texts(stmt)
                stmt.model = auto_route(
                    adapter=adapter,
                    system_role=system_role,
                    instruction=instruction,
                    provider=provider,
                    is_final_prompt=is_final,
                )
            r = asyncio.run(executor.execute(plan, params=params, stmt=stmt))
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
        return {"primary_result": "", "execution_results": [], "error": str(e)}

    return {
        "primary_result": results[-1]["content"] if results else "",
        "execution_results": results,
        "error": "",
    }
