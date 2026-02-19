"""Build a multi-CTE SPL script directly from document chunks.

No LLM is involved in generating the SPL structure — the template is
deterministic.  The LLM is only called during *execution* of each CTE.

Generated structure (k=3 example):

    PROMPT synthesize_document
    WITH BUDGET <outer_budget> tokens
    USING MODEL "<model>"

    WITH chunk_1_summary AS (
        PROMPT analyze_chunk_1
        WITH BUDGET 4000 tokens
        USING MODEL "<model>"

        SELECT
            system_role("Expert analyst. Process this section for: <intent>"),
            context.chunk_1 AS text LIMIT 2800 tokens

        GENERATE section_summary(text)
        WITH OUTPUT BUDGET 800 tokens
    ),
    chunk_2_summary AS ( ... ),
    chunk_3_summary AS ( ... )

    SELECT
        system_role("Synthesize all section analyses for: <intent>"),
        chunk_1_summary AS summary_1,
        chunk_2_summary AS summary_2,
        chunk_3_summary AS summary_3

    GENERATE comprehensive_synthesis(summary_1, summary_2, summary_3)
    WITH OUTPUT BUDGET 2000 tokens, FORMAT markdown

    STORE RESULT IN memory.chunked_result;
"""

from __future__ import annotations

from src.utils.logging_config import get_logger

_log = get_logger("utils.chunk_spl_builder")

# ── Budget constants (mirror chunker.py) ──────────────────────────────────────

BUDGET_PER_CHUNK: int = 4_000      # total per CTE: 2800 content + 800 out + 400 overhead
CONTENT_LIMIT_PER_CHUNK: int = 2_800
OUTPUT_PER_CHUNK: int = 800
FINAL_OUTPUT_BUDGET: int = 2_000


# ── Per-adapter model selection ───────────────────────────────────────────────

_GENERAL_MODELS: dict[str, str] = {
    "openrouter": "anthropic/claude-sonnet-4-5-20250929",
    "ollama":     "qwen3",
    "claude_cli": "claude-sonnet-4-5",
}


def _general_model(adapter: str) -> str:
    return _GENERAL_MODELS.get(adapter, _GENERAL_MODELS["openrouter"])


# ── SPL builder ───────────────────────────────────────────────────────────────

def build_chunking_spl(
    chunks: list[str],
    user_intent: str,
    adapter: str = "claude_cli",
    synthesis_model: str | None = None,
) -> tuple[str, dict[str, str]]:
    """Build a multi-CTE SPL script for the given document chunks.

    Args:
        chunks:          List of document chunks (already in English).
        user_intent:     The user's original request (in English), used in
                         system_role descriptions.
        adapter:         Execution adapter — determines model names.
        synthesis_model: Override the reduce-phase model (defaults to same
                         as chunk model).

    Returns:
        (spl_query, params) where params maps "chunk_1" … "chunk_k" to
        the chunk text strings.  Pass params as spl_params to run_spl_flow.
    """
    k = len(chunks)
    if k == 0:
        raise ValueError("build_chunking_spl: chunks list is empty")

    model = _general_model(adapter)
    reduce_model = synthesis_model or model

    # Outer budget: receives k CTE outputs + overhead + final output
    outer_budget = max(8_000, k * OUTPUT_PER_CHUNK + FINAL_OUTPUT_BUDGET + 1_000)

    # Sanitize user_intent for use inside SPL string literals
    intent_safe = user_intent.replace('"', "'").replace("\n", " ")[:200]

    lines: list[str] = []

    # ── Outer PROMPT header ───────────────────────────────────────────────────
    lines += [
        f'PROMPT synthesize_document',
        f'WITH BUDGET {outer_budget} tokens',
        f'USING MODEL "{reduce_model}"',
        "",
    ]

    # ── CTE block ─────────────────────────────────────────────────────────────
    cte_parts: list[str] = []
    for i in range(1, k + 1):
        cte_lines = [
            f"    chunk_{i}_summary AS (",
            f"        PROMPT analyze_chunk_{i}",
            f"        WITH BUDGET {BUDGET_PER_CHUNK} tokens",
            f'        USING MODEL "{model}"',
            "",
            f"        SELECT",
            f'            system_role("Expert analyst. Process this section for: {intent_safe}"),',
            f"            context.chunk_{i} AS text LIMIT {CONTENT_LIMIT_PER_CHUNK} tokens",
            "",
            f"        GENERATE section_summary(text)",
            f"        WITH OUTPUT BUDGET {OUTPUT_PER_CHUNK} tokens",
            f"    )",
        ]
        cte_parts.append("\n".join(cte_lines))

    # "WITH" keyword on its own line, CTEs indented below
    lines.append("WITH")
    lines.append(",\n".join(cte_parts))
    lines.append("")

    # ── Outer SELECT ──────────────────────────────────────────────────────────
    lines.append("SELECT")
    lines.append(
        f'    system_role("Synthesize all section analyses into a comprehensive'
        f' response for: {intent_safe}"),'
    )
    for i in range(1, k + 1):
        comma = "," if i < k else ""
        lines.append(f"    chunk_{i}_summary AS summary_{i}{comma}")
    lines.append("")

    # ── Outer GENERATE ────────────────────────────────────────────────────────
    summary_args = ", ".join(f"summary_{i}" for i in range(1, k + 1))
    lines += [
        f"GENERATE comprehensive_synthesis({summary_args})",
        f"WITH OUTPUT BUDGET {FINAL_OUTPUT_BUDGET} tokens, FORMAT markdown",
        "",
        "STORE RESULT IN memory.chunked_result;",
    ]

    spl_query = "\n".join(lines)
    params = {f"chunk_{i}": chunks[i - 1] for i in range(1, k + 1)}

    _log.info(
        "build_chunking_spl: k=%d  model=%s  outer_budget=%d  spl_lines=%d",
        k, model, outer_budget, len(spl_query.splitlines()),
    )
    return spl_query, params
