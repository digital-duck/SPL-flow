"""Integration tests for src/flows/chunking_flow.py — all offline via mocks.

These tests verify the routing logic and SPL construction without any real
LLM calls.  All external dependencies (spl engine, adapters, pocketflow)
are mocked at the boundary.

Node classes (ValidateSPLNode etc.) are imported lazily *inside* the function
body in chunking_flow.py, so they must be mocked via sys.modules, not via
patch() attribute access.
"""

import sys
from contextlib import contextmanager
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")

import pytest

from src.utils.chunk_spl_builder import build_chunking_spl


# ── Helpers ───────────────────────────────────────────────────────────────────

def _short_text() -> str:
    """Text well below the chunking threshold (~100 tokens)."""
    return "This is a short document. " * 20


def _long_text(tokens: int = 4000) -> str:
    """Text above the chunking threshold."""
    return ("word " * (tokens * 4 // 5))[:tokens * 4]


def _make_store_runner(error: str = ""):
    """Return a side_effect function that populates shared store like the pipeline would."""
    def _run(shared: dict) -> None:
        shared["primary_result"] = "" if error else "Synthesised result."
        shared["execution_results"] = [] if error else [
            {
                "prompt_name": "synthesize_document",
                "content": "Synthesised result.",
                "model": "test-model",
                "input_tokens": 500,
                "output_tokens": 200,
                "total_tokens": 700,
                "latency_ms": 800.0,
                "cost_usd": 0.002,
            }
        ]
        shared["delivered"] = not bool(error)
        shared["error"] = error
    return _run


@contextmanager
def _mock_long_doc_pipeline(chunks, run_side_effect=None, max_chunks=16):
    """Context manager that mocks everything needed for the long-doc path."""
    mock_validate = MagicMock()
    mock_execute  = MagicMock()
    mock_sync     = MagicMock()
    mock_async    = MagicMock()

    mock_flow_instance = MagicMock()
    if run_side_effect is not None:
        mock_flow_instance.run.side_effect = run_side_effect

    mock_flow_cls = MagicMock(return_value=mock_flow_instance)

    node_modules = {
        "src.nodes.validate_spl": MagicMock(ValidateSPLNode=mock_validate),
        "src.nodes.execute_spl":  MagicMock(ExecuteSPLNode=mock_execute),
        "src.nodes.deliver":      MagicMock(SyncDeliverNode=mock_sync,
                                            AsyncDeliverNode=mock_async),
    }

    with (
        patch("src.flows.chunking_flow.should_chunk",         return_value=True),
        patch("src.flows.chunking_flow.count_tokens",         return_value=5000),
        patch("src.flows.chunking_flow.translate_to_english", side_effect=lambda t, a: t),
        patch("src.flows.chunking_flow.semantic_chunk",       return_value=chunks),
        patch.dict("sys.modules", node_modules),
        patch("pocketflow.Flow", mock_flow_cls),
    ):
        yield mock_flow_instance


# ── build_chunking_spl round-trip ─────────────────────────────────────────────

class TestBuildChunkingSPLRoundTrip:
    """Verify the SPL builder produces parseable structures (no engine needed)."""

    def test_params_keys_match_spl_references(self):
        chunks = ["Alpha text", "Beta text", "Gamma text"]
        spl, params = build_chunking_spl(chunks=chunks, user_intent="Summarise")
        for key in params:
            assert key in spl   # context.chunk_i references key in SELECT

    def test_spl_is_a_non_empty_string(self):
        spl, _ = build_chunking_spl(chunks=["text"], user_intent="test")
        assert isinstance(spl, str)
        assert len(spl) > 100

    def test_k3_spl_contains_three_ctes(self):
        chunks = ["a", "b", "c"]
        spl, _ = build_chunking_spl(chunks=chunks, user_intent="test")
        for i in range(1, 4):
            assert f"chunk_{i}_summary AS (" in spl


# ── run_chunking_flow: short-doc path ─────────────────────────────────────────

class TestRunChunkingFlowShortDoc:
    """Short documents should delegate to run_spl_flow unchanged."""

    def test_short_doc_calls_run_spl_flow(self):
        mock_store = {"primary_result": "result", "error": ""}
        with (
            patch("src.flows.chunking_flow.should_chunk",         return_value=False),
            patch("src.flows.chunking_flow.translate_to_english", side_effect=lambda t, a: t),
            patch("src.flows.chunking_flow.run_spl_flow",         return_value=mock_store) as mock_run,
        ):
            from src.flows.chunking_flow import run_chunking_flow
            result = run_chunking_flow(
                user_input="What is AI?",
                context_text=_short_text(),
                adapter="claude_cli",
            )

        mock_run.assert_called_once()
        assert result is mock_store

    def test_empty_context_calls_run_spl_flow(self):
        mock_store = {"primary_result": "result", "error": ""}
        with patch("src.flows.chunking_flow.run_spl_flow", return_value=mock_store) as mock_run:
            from src.flows.chunking_flow import run_chunking_flow
            result = run_chunking_flow(user_input="What is AI?", context_text="")

        mock_run.assert_called_once()
        assert result is mock_store

    def test_short_doc_chunking_key_absent_or_not_enabled(self):
        mock_store = {"primary_result": "result", "error": ""}
        with (
            patch("src.flows.chunking_flow.should_chunk",         return_value=False),
            patch("src.flows.chunking_flow.translate_to_english", side_effect=lambda t, a: t),
            patch("src.flows.chunking_flow.run_spl_flow",         return_value=mock_store),
        ):
            from src.flows.chunking_flow import run_chunking_flow
            result = run_chunking_flow(user_input="test", context_text=_short_text())

        assert "chunking" not in result or not result.get("chunking", {}).get("enabled")


# ── run_chunking_flow: long-doc path ──────────────────────────────────────────

class TestRunChunkingFlowLongDoc:
    """Long documents should go through translate → chunk → build SPL → execute."""

    def test_long_doc_translates_both_fields(self):
        translate_calls = []

        def fake_translate(text, adapter):
            translate_calls.append(text[:10])
            return text

        with (
            patch("src.flows.chunking_flow.should_chunk",         return_value=True),
            patch("src.flows.chunking_flow.count_tokens",         return_value=5000),
            patch("src.flows.chunking_flow.translate_to_english", side_effect=fake_translate),
            patch("src.flows.chunking_flow.semantic_chunk",       return_value=["c1", "c2"]),
            patch.dict("sys.modules", {
                "src.nodes.validate_spl": MagicMock(ValidateSPLNode=MagicMock()),
                "src.nodes.execute_spl":  MagicMock(ExecuteSPLNode=MagicMock()),
                "src.nodes.deliver":      MagicMock(SyncDeliverNode=MagicMock(),
                                                    AsyncDeliverNode=MagicMock()),
            }),
            patch("pocketflow.Flow") as MockFlow,
        ):
            MockFlow.return_value.run.side_effect = _make_store_runner()
            from src.flows.chunking_flow import run_chunking_flow
            run_chunking_flow(user_input="Please summarise",
                              context_text=_long_text(), adapter="claude_cli")

        # Both user_input and context_text should be translated
        assert len(translate_calls) == 2

    def test_long_doc_chunking_metadata_present(self):
        chunks = ["chunk one text", "chunk two text", "chunk three text"]
        with _mock_long_doc_pipeline(chunks, _make_store_runner()) as flow:
            from src.flows.chunking_flow import run_chunking_flow
            result = run_chunking_flow(user_input="summarise", context_text=_long_text())

        assert result["chunking"]["enabled"] is True
        assert result["chunking"]["k"] == 3
        assert result["chunking"]["doc_tokens"] > 0
        assert len(result["chunking"]["chunk_tokens"]) == 3

    def test_long_doc_spl_injected_into_shared_store(self):
        captured_shared: dict = {}

        def capture_run(shared):
            captured_shared.update(shared)
            _make_store_runner()(shared)

        chunks = ["chunk A", "chunk B"]
        with _mock_long_doc_pipeline(chunks, capture_run):
            from src.flows.chunking_flow import run_chunking_flow
            run_chunking_flow(user_input="summarise", context_text=_long_text())

        # Pre-built SPL should be in the shared store
        assert "spl_query" in captured_shared
        assert "PROMPT synthesize_document" in captured_shared["spl_query"]
        # Chunks should be in params; context_text cleared (chunks are the params now)
        assert captured_shared["context_text"] == ""
        assert "chunk_1" in captured_shared["spl_params"]
        assert "chunk_2" in captured_shared["spl_params"]

    def test_zero_chunks_fallback_to_run_spl_flow(self):
        mock_store = {"primary_result": "result", "error": ""}
        with (
            patch("src.flows.chunking_flow.should_chunk",         return_value=True),
            patch("src.flows.chunking_flow.count_tokens",         return_value=5000),
            patch("src.flows.chunking_flow.translate_to_english", side_effect=lambda t, a: t),
            patch("src.flows.chunking_flow.semantic_chunk",       return_value=[]),
            patch("src.flows.chunking_flow.run_spl_flow",         return_value=mock_store) as mock_run,
        ):
            from src.flows.chunking_flow import run_chunking_flow
            result = run_chunking_flow(user_input="test", context_text=_long_text())

        mock_run.assert_called_once()
        assert result is mock_store

    def test_max_chunks_argument_respected(self):
        captured_k: dict = {}

        def fake_semantic_chunk(text, max_chunks=16):
            captured_k["max_chunks"] = max_chunks
            return [f"chunk {i}" for i in range(min(max_chunks, 4))]

        with (
            patch("src.flows.chunking_flow.should_chunk",         return_value=True),
            patch("src.flows.chunking_flow.count_tokens",         return_value=5000),
            patch("src.flows.chunking_flow.translate_to_english", side_effect=lambda t, a: t),
            patch("src.flows.chunking_flow.semantic_chunk",       side_effect=fake_semantic_chunk),
            patch.dict("sys.modules", {
                "src.nodes.validate_spl": MagicMock(ValidateSPLNode=MagicMock()),
                "src.nodes.execute_spl":  MagicMock(ExecuteSPLNode=MagicMock()),
                "src.nodes.deliver":      MagicMock(SyncDeliverNode=MagicMock(),
                                                    AsyncDeliverNode=MagicMock()),
            }),
            patch("pocketflow.Flow") as MockFlow,
        ):
            MockFlow.return_value.run.side_effect = _make_store_runner()
            from src.flows.chunking_flow import run_chunking_flow
            run_chunking_flow(user_input="test", context_text=_long_text(), max_chunks=6)

        assert captured_k["max_chunks"] == 6

    def test_error_in_shared_store_is_returned(self):
        chunks = ["chunk one", "chunk two"]
        with _mock_long_doc_pipeline(chunks, _make_store_runner(error="Validate failed")):
            from src.flows.chunking_flow import run_chunking_flow
            result = run_chunking_flow(user_input="test", context_text=_long_text())

        assert result["error"] == "Validate failed"
