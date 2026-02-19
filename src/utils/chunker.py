"""Logical chunking utilities for SPL-Flow.

Handles:
  - Token counting
  - Language detection + English translation (pivot language for chunking)
  - Semantic document splitting via chonkie (fallback: token-based)

Design constants
----------------
CHUNK_THRESHOLD_TOKENS = 3_000
    Smallest popular LLM context denominator is 4 096 tokens (Llama 2,
    original GPT-3.5-turbo).  After reserving ~1 100 tokens for system
    role + question + output overhead, ~2 900 tokens remain.  We use
    3 000 as a round, conservative trigger so even the most constrained
    4 K models can handle each chunk with comfortable headroom.

CHUNK_SIZE_TOKENS = 2_800
    Target size per chunk; leaves ~1 200 tokens of overhead in a 4 K budget.

MAX_CHUNKS = 16
    Hard cap to prevent runaway costs / DoS on adversarially large inputs.
"""

from __future__ import annotations

import asyncio
import math
from typing import TYPE_CHECKING

from src.utils.logging_config import get_logger

if TYPE_CHECKING:
    pass

_log = get_logger("utils.chunker")

# ── Constants ─────────────────────────────────────────────────────────────────

CHUNK_THRESHOLD_TOKENS: int = 3_000   # trigger: documents larger than this get chunked
CHUNK_SIZE_TOKENS: int = 2_800        # target tokens per chunk
MAX_CHUNKS: int = 16                   # hard cap (DoS / cost protection)


# ── Token counting ────────────────────────────────────────────────────────────

def count_tokens(text: str) -> int:
    """Estimate token count using tiktoken (cl100k_base, used by GPT-4 / Claude)."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        # Fallback: rough 4-chars-per-token heuristic
        return max(1, len(text) // 4)


def should_chunk(text: str) -> bool:
    """Return True if *text* exceeds the chunking threshold."""
    return count_tokens(text) > CHUNK_THRESHOLD_TOKENS


# ── Language detection ────────────────────────────────────────────────────────

def detect_language(text: str) -> str:
    """Return ISO 639-1 language code, e.g. 'en', 'zh-cn', 'fr'.
    Falls back to 'en' if langdetect is not installed or detection fails.
    """
    try:
        from langdetect import detect
        return detect(text[:2000])   # sample first 2K chars for speed
    except Exception:
        return "en"


def is_english(text: str) -> bool:
    lang = detect_language(text)
    return lang.startswith("en")


# ── English translation ───────────────────────────────────────────────────────

def translate_to_english(text: str, adapter_name: str = "claude_cli") -> str:
    """Translate *text* to English using the active LLM adapter.

    Uses a fast, cheap model (haiku-class) and only translates if the
    detected language is not already English.  Returns original text on
    any error so the pipeline is never blocked by a translation failure.
    """
    if is_english(text):
        _log.debug("translate_to_english: already English, skipping")
        return text

    lang = detect_language(text)
    _log.info("translate_to_english: detected lang=%s, translating...", lang)

    try:
        from spl.adapters import get_adapter
        adapter = get_adapter(adapter_name)

        prompt = (
            f"Translate the following text to English. "
            f"Output ONLY the translated text, no explanation.\n\n{text}"
        )
        result = asyncio.run(adapter.generate(
            prompt=prompt,
            model="",           # adapter picks cheapest suitable model
            max_tokens=4096,
            temperature=0.1,
            system="You are a professional translator. Translate accurately and completely.",
        ))
        translated = result.content.strip()
        _log.info(
            "translate_to_english: done  orig_chars=%d  trans_chars=%d",
            len(text), len(translated),
        )
        return translated
    except Exception as exc:
        _log.warning("translate_to_english failed (%s), using original text", exc)
        return text


# ── Semantic chunking ─────────────────────────────────────────────────────────

def semantic_chunk(text: str, max_chunks: int = MAX_CHUNKS) -> list[str]:
    """Split *text* into semantically coherent chunks of ≤ CHUNK_SIZE_TOKENS each.

    Strategy (in order of preference):
    1. chonkie.SemanticChunker — meaning-preserving sentence-embedding split
    2. chonkie.TokenChunker    — token-boundary split (no embeddings needed)
    3. Naive character split   — last resort if chonkie is not installed

    Args:
        text:       The document to split (should already be in English).
        max_chunks: Hard cap on the number of chunks returned (default 16).

    Returns:
        List of non-empty chunk strings, len ≤ max_chunks.
    """
    n_tokens = count_tokens(text)
    ideal_k = math.ceil(n_tokens / CHUNK_SIZE_TOKENS)
    k = min(ideal_k, max_chunks)
    _log.info(
        "semantic_chunk: doc_tokens=%d  ideal_k=%d  capped_k=%d",
        n_tokens, ideal_k, k,
    )

    # Try SemanticChunker first (requires chonkie[semantic])
    chunks = _try_semantic_chunker(text, k)
    if chunks:
        _log.info("semantic_chunk: SemanticChunker produced %d chunks", len(chunks))
        return chunks[:max_chunks]

    # Fallback: TokenChunker (core chonkie, no embeddings)
    chunks = _try_token_chunker(text, k)
    if chunks:
        _log.info("semantic_chunk: TokenChunker produced %d chunks", len(chunks))
        return chunks[:max_chunks]

    # Last resort: naive character split
    chunks = _naive_split(text, k)
    _log.info("semantic_chunk: naive split produced %d chunks", len(chunks))
    return chunks[:max_chunks]


def _try_semantic_chunker(text: str, target_k: int) -> list[str]:
    try:
        from chonkie import SemanticChunker  # type: ignore[import]

        chunker = SemanticChunker(
            embedding_model="minishlab/potion-base-8M",
            chunk_size=CHUNK_SIZE_TOKENS,
            threshold=0.5,
        )
        raw = chunker(text)
        return [c.text for c in raw if c.text.strip()]
    except ImportError:
        _log.debug("chonkie[semantic] not installed — skipping SemanticChunker")
        return []
    except Exception as exc:
        _log.warning("SemanticChunker failed: %s", exc)
        return []


def _try_token_chunker(text: str, target_k: int) -> list[str]:
    try:
        from chonkie import TokenChunker  # type: ignore[import]

        chunker = TokenChunker(chunk_size=CHUNK_SIZE_TOKENS, chunk_overlap=50)
        raw = chunker(text)
        return [c.text for c in raw if c.text.strip()]
    except ImportError:
        _log.debug("chonkie not installed — skipping TokenChunker")
        return []
    except Exception as exc:
        _log.warning("TokenChunker failed: %s", exc)
        return []


def _naive_split(text: str, k: int) -> list[str]:
    """Split text into k roughly equal character-based chunks."""
    chars_per_chunk = max(1, len(text) // k)
    chunks = []
    for i in range(0, len(text), chars_per_chunk):
        chunk = text[i: i + chars_per_chunk].strip()
        if chunk:
            chunks.append(chunk)
    return chunks
