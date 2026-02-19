"""Tests for src/utils/chunk_spl_builder.py — fully offline, no LLM calls."""

import sys

sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")

import pytest

from src.utils.chunk_spl_builder import (
    BUDGET_PER_CHUNK,
    CONTENT_LIMIT_PER_CHUNK,
    OUTPUT_PER_CHUNK,
    FINAL_OUTPUT_BUDGET,
    build_chunking_spl,
    _general_model,
)


# ── _general_model ────────────────────────────────────────────────────────────

class TestGeneralModel:
    def test_known_adapters(self):
        assert "claude" in _general_model("claude_cli").lower()
        assert _general_model("ollama") == "qwen3"
        assert "claude" in _general_model("openrouter").lower()

    def test_unknown_adapter_falls_back_to_openrouter(self):
        model = _general_model("unknown_adapter")
        assert model == _general_model("openrouter")


# ── build_chunking_spl ────────────────────────────────────────────────────────

class TestBuildChunkingSPL:
    def _build(self, k: int = 3, intent: str = "Summarise the document",
               adapter: str = "claude_cli") -> tuple[str, dict]:
        chunks = [f"Chunk {i} content. " * 20 for i in range(1, k + 1)]
        return build_chunking_spl(chunks=chunks, user_intent=intent, adapter=adapter)

    # ── params correctness ────────────────────────────────────────────────────

    def test_raises_on_empty_chunks(self):
        with pytest.raises(ValueError, match="empty"):
            build_chunking_spl(chunks=[], user_intent="test")

    def test_params_keys_match_k(self):
        spl, params = self._build(k=5)
        assert set(params.keys()) == {f"chunk_{i}" for i in range(1, 6)}

    def test_params_values_are_original_chunks(self):
        chunks = ["alpha content", "beta content", "gamma content"]
        _, params = build_chunking_spl(chunks=chunks, user_intent="test")
        assert params["chunk_1"] == "alpha content"
        assert params["chunk_3"] == "gamma content"

    # ── SPL structure ─────────────────────────────────────────────────────────

    def test_outer_prompt_header_present(self):
        spl, _ = self._build(k=2)
        assert "PROMPT synthesize_document" in spl

    def test_with_keyword_present(self):
        spl, _ = self._build(k=2)
        # WITH should appear as a standalone keyword for the CTE block
        assert "\nWITH\n" in spl or spl.startswith("WITH\n") or "\nWITH " in spl

    def test_cte_names_present_for_each_chunk(self):
        spl, _ = self._build(k=4)
        for i in range(1, 5):
            assert f"chunk_{i}_summary AS (" in spl

    def test_outer_select_references_all_summaries(self):
        spl, _ = self._build(k=3)
        for i in range(1, 4):
            assert f"chunk_{i}_summary AS summary_{i}" in spl

    def test_generate_clause_lists_all_summaries(self):
        spl, _ = self._build(k=3)
        assert "GENERATE comprehensive_synthesis(summary_1, summary_2, summary_3)" in spl

    def test_store_result_present(self):
        spl, _ = self._build(k=2)
        assert "STORE RESULT IN memory.chunked_result" in spl

    # ── Budget values ─────────────────────────────────────────────────────────

    def test_cte_budget_uses_constant(self):
        spl, _ = self._build(k=2)
        assert f"WITH BUDGET {BUDGET_PER_CHUNK} tokens" in spl

    def test_cte_content_limit_uses_constant(self):
        spl, _ = self._build(k=2)
        assert f"LIMIT {CONTENT_LIMIT_PER_CHUNK} tokens" in spl

    def test_cte_output_budget_uses_constant(self):
        spl, _ = self._build(k=2)
        assert f"WITH OUTPUT BUDGET {OUTPUT_PER_CHUNK} tokens" in spl

    def test_outer_output_budget_uses_constant(self):
        spl, _ = self._build(k=2)
        assert f"WITH OUTPUT BUDGET {FINAL_OUTPUT_BUDGET} tokens" in spl

    def test_outer_budget_scales_with_k(self):
        _, _ = self._build(k=1)   # min(8000, ...) likely applies
        spl8, _ = self._build(k=8)
        # k=8 outer budget = max(8000, 8*800 + 2000 + 1000) = max(8000, 9400) = 9400
        assert "9400" in spl8

    def test_outer_budget_floor_is_8000(self):
        spl, _ = self._build(k=1)
        # k=1: max(8000, 1*800 + 2000 + 1000) = max(8000, 3800) = 8000
        assert "8000" in spl

    # ── Model selection ───────────────────────────────────────────────────────

    def test_model_from_adapter(self):
        spl, _ = self._build(adapter="ollama")
        assert '"qwen3"' in spl

    def test_synthesis_model_override(self):
        chunks = ["text"] * 2
        spl, _ = build_chunking_spl(
            chunks=chunks,
            user_intent="test",
            adapter="claude_cli",
            synthesis_model="anthropic/claude-opus-4-6",
        )
        assert '"anthropic/claude-opus-4-6"' in spl

    # ── Intent sanitisation ───────────────────────────────────────────────────

    def test_intent_truncated_at_200_chars(self):
        long_intent = "x" * 500
        spl, _ = build_chunking_spl(chunks=["text"], user_intent=long_intent)
        # The full 500-char intent must not appear; only first 200 are used
        assert "x" * 201 not in spl

    def test_intent_quotes_sanitised(self):
        intent_with_quotes = 'Please "summarise" this'
        spl, _ = build_chunking_spl(chunks=["text"], user_intent=intent_with_quotes)
        # Double quotes in intent replaced with single quotes to avoid breaking SPL string
        assert "Please 'summarise' this" in spl

    def test_intent_newlines_sanitised(self):
        intent_with_newlines = "summarise\nthis document\nplease"
        spl, _ = build_chunking_spl(chunks=["text"], user_intent=intent_with_newlines)
        assert "\n" not in spl.split("system_role")[1].split(")")[0]

    # ── Format ────────────────────────────────────────────────────────────────

    def test_format_markdown_in_outer_generate(self):
        spl, _ = self._build(k=2)
        assert "FORMAT markdown" in spl

    def test_single_chunk_works(self):
        spl, params = build_chunking_spl(chunks=["only chunk"], user_intent="test")
        assert "chunk_1_summary" in spl
        assert params == {"chunk_1": "only chunk"}
        assert "GENERATE comprehensive_synthesis(summary_1)" in spl

    def test_max_chunks_16_works(self):
        chunks = [f"chunk {i}" for i in range(1, 17)]
        spl, params = build_chunking_spl(chunks=chunks, user_intent="big doc")
        assert len(params) == 16
        assert "chunk_16_summary" in spl
        assert "summary_16" in spl
