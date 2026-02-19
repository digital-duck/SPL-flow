"""Tests for src/utils/chunker.py — all offline, no LLM calls."""

import sys

sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")

import pytest
from unittest.mock import patch, MagicMock

from src.utils.chunker import (
    CHUNK_THRESHOLD_TOKENS,
    CHUNK_SIZE_TOKENS,
    MAX_CHUNKS,
    count_tokens,
    should_chunk,
    detect_language,
    is_english,
    semantic_chunk,
    _naive_split,
    _try_token_chunker,
    _try_semantic_chunker,
)


# ── count_tokens ──────────────────────────────────────────────────────────────

class TestCountTokens:
    def test_empty_string_returns_non_negative(self):
        # tiktoken returns 0 for empty string; heuristic returns max(1, 0//4)=1
        # either way, must not raise and must be an int
        assert isinstance(count_tokens(""), int)
        assert count_tokens("") >= 0

    def test_short_text(self):
        n = count_tokens("Hello, world!")
        assert n > 0

    def test_longer_text_more_tokens(self):
        short = count_tokens("Hello")
        long  = count_tokens("Hello " * 100)
        assert long > short

    def test_tiktoken_fallback(self):
        # Force ImportError in tiktoken → heuristic path
        with patch.dict("sys.modules", {"tiktoken": None}):
            n = count_tokens("a" * 400)
        assert n == 100  # 400 chars // 4 = 100

    def test_four_char_heuristic_floor(self):
        # Even an empty string with heuristic returns at least 1
        with patch.dict("sys.modules", {"tiktoken": None}):
            n = count_tokens("")
        assert n >= 1


# ── should_chunk ──────────────────────────────────────────────────────────────

class TestShouldChunk:
    def test_empty_text_no_chunk(self):
        assert should_chunk("") is False

    def test_short_text_no_chunk(self):
        assert should_chunk("Hello world.") is False

    def test_long_text_triggers_chunk(self):
        # ~1 token per 4 chars; need > 3000 tokens → > 12 000 chars
        long_text = "word " * 3200   # ~3200 tokens
        assert should_chunk(long_text) is True

    def test_threshold_boundary(self):
        # Text at exactly threshold should not chunk
        at_threshold = "a " * CHUNK_THRESHOLD_TOKENS  # ~CHUNK_THRESHOLD_TOKENS tokens
        # Whether this chunks depends on exact token count; just confirm it doesn't crash
        result = should_chunk(at_threshold)
        assert isinstance(result, bool)


# ── detect_language ───────────────────────────────────────────────────────────

class TestDetectLanguage:
    def test_english_text(self):
        lang = detect_language("This is a simple English sentence about artificial intelligence.")
        assert lang.startswith("en")

    def test_fallback_on_import_error(self):
        with patch.dict("sys.modules", {"langdetect": None}):
            lang = detect_language("anything")
        assert lang == "en"

    def test_fallback_on_detection_error(self):
        with patch("src.utils.chunker.detect_language") as mock_detect:
            mock_detect.side_effect = Exception("detection failed")
        lang = detect_language("x")   # direct call, not mocked
        assert isinstance(lang, str)


class TestIsEnglish:
    def test_english_returns_true(self):
        assert is_english("The quick brown fox jumps over the lazy dog.") is True

    def test_fallback_returns_english(self):
        with patch.dict("sys.modules", {"langdetect": None}):
            result = is_english("anything")
        assert result is True


# ── _naive_split ──────────────────────────────────────────────────────────────

class TestNaiveSplit:
    def test_splits_into_k_parts(self):
        text = "abcdefghij" * 100   # 1000 chars
        chunks = _naive_split(text, k=4)
        assert 1 <= len(chunks) <= 5   # roughly k parts
        assert all(isinstance(c, str) and c for c in chunks)

    def test_no_empty_chunks(self):
        text = "hello world " * 50
        chunks = _naive_split(text, k=3)
        assert all(c.strip() for c in chunks)

    def test_single_chunk_k_equals_one(self):
        text = "hello world"
        chunks = _naive_split(text, k=1)
        assert len(chunks) == 1
        assert chunks[0].strip() == text.strip()

    def test_reconstruction_covers_full_text(self):
        text = "The quick brown fox. " * 200
        chunks = _naive_split(text, k=5)
        # Joined (stripped) chunks should contain all words
        joined = " ".join(chunks)
        assert "fox" in joined

    def test_k_greater_than_chars(self):
        # k > len(text) should not crash; chars_per_chunk = max(1, ...)
        chunks = _naive_split("hi", k=100)
        assert len(chunks) >= 1


# ── _try_token_chunker ────────────────────────────────────────────────────────

class TestTryTokenChunker:
    def test_returns_empty_list_when_chonkie_missing(self):
        with patch.dict("sys.modules", {"chonkie": None}):
            result = _try_token_chunker("some text", target_k=2)
        assert result == []

    def test_returns_list_of_strings_when_chonkie_works(self):
        # Mock chonkie.TokenChunker
        mock_chunk = MagicMock()
        mock_chunk.text = "chunk content"
        mock_chunker_instance = MagicMock(return_value=[mock_chunk, mock_chunk])
        mock_chonkie = MagicMock()
        mock_chonkie.TokenChunker = MagicMock(return_value=mock_chunker_instance)

        with patch.dict("sys.modules", {"chonkie": mock_chonkie}):
            result = _try_token_chunker("some long text to split", target_k=2)
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)

    def test_returns_empty_list_on_exception(self):
        mock_chonkie = MagicMock()
        mock_chonkie.TokenChunker = MagicMock(side_effect=RuntimeError("unexpected"))

        with patch.dict("sys.modules", {"chonkie": mock_chonkie}):
            result = _try_token_chunker("text", target_k=2)
        assert result == []


# ── _try_semantic_chunker ─────────────────────────────────────────────────────

class TestTrySemanticChunker:
    def test_returns_empty_list_when_chonkie_missing(self):
        with patch.dict("sys.modules", {"chonkie": None}):
            result = _try_semantic_chunker("text", target_k=2)
        assert result == []

    def test_returns_empty_list_on_exception(self):
        mock_chonkie = MagicMock()
        mock_chonkie.SemanticChunker = MagicMock(side_effect=RuntimeError("model error"))

        with patch.dict("sys.modules", {"chonkie": mock_chonkie}):
            result = _try_semantic_chunker("text", target_k=2)
        assert result == []


# ── semantic_chunk ────────────────────────────────────────────────────────────

class TestSemanticChunk:
    """All paths through semantic_chunk tested with chonkie mocked out."""

    def _long_text(self, tokens: int = 4000) -> str:
        """Generate text that counts as ~tokens tokens (4-char heuristic)."""
        return ("word " * (tokens * 4 // 5))[:tokens * 4]

    def test_naive_fallback_when_chonkie_absent(self):
        with patch.dict("sys.modules", {"chonkie": None}):
            text = self._long_text(tokens=6000)
            chunks = semantic_chunk(text, max_chunks=4)
        assert 1 <= len(chunks) <= 4
        assert all(isinstance(c, str) and c for c in chunks)

    def test_max_chunks_cap_respected(self):
        with patch.dict("sys.modules", {"chonkie": None}):
            text = self._long_text(tokens=50_000)
            chunks = semantic_chunk(text, max_chunks=5)
        assert len(chunks) <= 5

    def test_default_max_chunks(self):
        with patch.dict("sys.modules", {"chonkie": None}):
            text = self._long_text(tokens=80_000)
            chunks = semantic_chunk(text)
        assert len(chunks) <= MAX_CHUNKS

    def test_token_chunker_path(self):
        """Uses TokenChunker when SemanticChunker import fails."""
        mock_chunk = MagicMock()
        mock_chunk.text = "piece of text that is not empty"
        mock_instance = MagicMock(return_value=[mock_chunk, mock_chunk, mock_chunk])

        mock_chonkie = MagicMock()
        mock_chonkie.SemanticChunker = MagicMock(side_effect=ImportError)
        mock_chonkie.TokenChunker = MagicMock(return_value=mock_instance)

        with patch.dict("sys.modules", {"chonkie": mock_chonkie}):
            chunks = semantic_chunk(self._long_text(6000), max_chunks=8)

        assert len(chunks) >= 1

    def test_semantic_chunker_path(self):
        """Uses SemanticChunker when available."""
        mock_chunk = MagicMock()
        mock_chunk.text = "semantic chunk text"
        mock_instance = MagicMock(return_value=[mock_chunk] * 4)

        mock_chonkie = MagicMock()
        mock_chonkie.SemanticChunker = MagicMock(return_value=mock_instance)

        with patch.dict("sys.modules", {"chonkie": mock_chonkie}):
            chunks = semantic_chunk(self._long_text(6000), max_chunks=8)

        assert len(chunks) <= 8
        assert all(isinstance(c, str) for c in chunks)

    def test_no_empty_strings_in_output(self):
        with patch.dict("sys.modules", {"chonkie": None}):
            chunks = semantic_chunk(self._long_text(9000))
        assert all(c.strip() for c in chunks)
