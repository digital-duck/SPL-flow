"""Chunking-aware SPL-Flow entry point.

run_chunking_flow() is a drop-in replacement for run_spl_flow() that
adds automatic long-document detection and Map-Reduce chunking:

Short document (≤ CHUNK_THRESHOLD_TOKENS):
    Translates user_input to English → delegates to run_spl_flow() as-is.

Long document (> CHUNK_THRESHOLD_TOKENS):
    1. Translate context_text + user_input to English
    2. Split context_text into k semantic chunks (k ≤ MAX_CHUNKS=16)
    3. Build a multi-CTE SPL directly from the chunk template (no LLM needed
       for SPL generation — only for chunk execution and synthesis)
    4. Validate → Execute → Deliver via the existing SPL-Flow pipeline

The generated SPL structure implements declarative Map-Reduce:
  - Map  : each CTE processes one chunk independently (parallel on cloud)
  - Reduce: outer GENERATE synthesizes all chunk summaries
"""

from __future__ import annotations

from src.utils.logging_config import get_logger
from src.utils.chunker import (
    CHUNK_THRESHOLD_TOKENS,
    MAX_CHUNKS,
    count_tokens,
    should_chunk,
    translate_to_english,
    semantic_chunk,
)
from src.utils.chunk_spl_builder import build_chunking_spl
from src.flows.spl_flow import run_spl_flow

_log = get_logger("flows.chunking")


def run_chunking_flow(
    user_input: str,
    context_text: str = "",
    adapter: str = "claude_cli",
    delivery_mode: str = "sync",
    notify_email: str = "",
    cache_enabled: bool = False,
    provider: str = "",
    synthesis_model: str | None = None,
    max_chunks: int = MAX_CHUNKS,
) -> dict:
    """Run SPL-Flow with automatic long-document chunking.

    Args:
        user_input:       Natural language query (any language).
        context_text:     Reference document to process (any language).
        adapter:          LLM adapter ("openrouter", "ollama", "claude_cli").
        delivery_mode:    "sync" or "async".
        notify_email:     Email for async delivery.
        cache_enabled:    Enable SPL prompt cache.
        provider:         Optional provider hint for model routing.
        synthesis_model:  Override the reduce-phase model (defaults to adapter
                          general model; useful for upgrading synthesis to a
                          stronger model e.g. claude-opus).
        max_chunks:       Hard cap on chunks (default 16, DoS protection).

    Returns:
        Shared store dict with all pipeline results populated.
    """
    doc_tokens = count_tokens(context_text) if context_text else 0
    _log.info(
        "chunking_flow start  adapter=%s  doc_tokens=%d  threshold=%d",
        adapter, doc_tokens, CHUNK_THRESHOLD_TOKENS,
    )

    # ── Short document: delegate directly to standard flow ────────────────────
    if not context_text or not should_chunk(context_text):
        _log.info("chunking_flow: doc below threshold — using standard spl_flow")
        english_input = translate_to_english(user_input, adapter)
        return run_spl_flow(
            user_input=english_input,
            context_text=context_text,
            adapter=adapter,
            delivery_mode=delivery_mode,
            notify_email=notify_email,
            cache_enabled=cache_enabled,
            provider=provider,
        )

    # ── Long document: translate → chunk → build SPL → execute ───────────────

    # Step 1: translate both to English (English pivot for chunking reliability)
    _log.info("chunking_flow: doc exceeds threshold — entering chunking path")
    english_intent = translate_to_english(user_input, adapter)
    english_doc = translate_to_english(context_text, adapter)

    # Step 2: semantic split into k chunks
    chunks = semantic_chunk(english_doc, max_chunks=max_chunks)
    k = len(chunks)
    _log.info("chunking_flow: split into k=%d chunks", k)

    if k == 0:
        _log.warning("chunking_flow: semantic_chunk returned 0 chunks, falling back")
        return run_spl_flow(
            user_input=english_intent,
            context_text=english_doc,
            adapter=adapter,
            delivery_mode=delivery_mode,
            notify_email=notify_email,
            cache_enabled=cache_enabled,
            provider=provider,
        )

    # Step 3: build multi-CTE SPL directly from template (no LLM call)
    spl_query, params = build_chunking_spl(
        chunks=chunks,
        user_intent=english_intent,
        adapter=adapter,
        synthesis_model=synthesis_model,
    )
    _log.info(
        "chunking_flow: SPL built  k=%d  params=%s  spl_lines=%d",
        k, list(params.keys()), len(spl_query.splitlines()),
    )

    # Step 4: skip Text2SPL (SPL is pre-built) — run validate → execute → deliver
    # We inject the pre-built SPL directly into the shared store, bypassing
    # the Text2SPLNode, by running from the validate node forward.
    from pocketflow import Flow
    from src.nodes.validate_spl import ValidateSPLNode
    from src.nodes.execute_spl import ExecuteSPLNode
    from src.nodes.deliver import SyncDeliverNode, AsyncDeliverNode

    validate = ValidateSPLNode()
    execute = ExecuteSPLNode()
    sync_deliver = SyncDeliverNode()
    async_deliver = AsyncDeliverNode()

    validate - "execute" >> execute
    validate - "retry" >> sync_deliver    # pre-built SPL shouldn't need retry; surface error
    validate - "error" >> sync_deliver
    execute - "sync" >> sync_deliver
    execute - "async" >> async_deliver
    execute - "error" >> sync_deliver

    flow = Flow(start=validate)

    shared = {
        # Pre-built SPL — bypasses Text2SPLNode
        "spl_query": spl_query,
        "spl_params": params,
        # Standard fields
        "user_input": english_intent,
        "context_text": "",          # chunks are in params
        "adapter": adapter,
        "delivery_mode": delivery_mode,
        "notify_email": notify_email,
        "cache_enabled": cache_enabled,
        "provider": provider,
        # Pipeline state
        "spl_ast": None,
        "spl_warnings": [],
        "last_parse_error": "",
        "retry_count": 0,
        "execution_results": [],
        "primary_result": "",
        "output_file": "",
        "email_sent": False,
        "delivered": False,
        "error": "",
        # Chunking metadata (for callers / UI)
        "chunking": {
            "enabled": True,
            "k": k,
            "doc_tokens": doc_tokens,
            "chunk_tokens": [count_tokens(c) for c in chunks],
        },
    }

    _log.info("chunking_flow: running validate→execute→deliver  k=%d", k)
    flow.run(shared)

    if shared.get("error"):
        _log.error("chunking_flow error: %s", shared["error"])
    else:
        _log.info(
            "chunking_flow done  k=%d  result_chars=%d  warnings=%d",
            k,
            len(shared.get("primary_result", "")),
            len(shared.get("spl_warnings", [])),
        )
    return shared
