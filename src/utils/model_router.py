"""Model routing for USING MODEL auto — uses MODEL_CATALOG as single source of truth.

Concept
-------
Three orthogonal dimensions determine the final model:

  task      — what the PROMPT is doing (cjk, code, eu_lang, math, reasoning,
               synthesis, general), detected from system_role + GENERATE text.

  provider  — the LLM company a user/org prefers (anthropic, google, meta,
               mistral, alibaba, deepseek, openai).  Optional.  When set, the
               model selection picks the best model FROM THAT PROVIDER for the
               task — even if a different provider would win best-of-breed.

  adapter   — the API interface in use (claude_cli, openrouter, ollama).
               Determines which models are available.

Resolution priority
-------------------
  1. provider set + openrouter adapter  → provider's best model for task
  2. provider set + other adapter       → adapter-level best (provider ignored)
  3. no provider + any adapter          → adapter-level best-of-breed for task

Model selection uses MODEL_CATALOG strengths field to find best matches.
"""

from src.utils.model_catalog import get_models

# ── Canonical list of supported providers ────────────────────────────────────

PROVIDERS: list[str] = [
    "anthropic", "google", "meta", "mistral",
    "alibaba", "deepseek", "openai",
]

# ── Task classifier ───────────────────────────────────────────────────────────

_CJK_CHARS = set("中文日本語한국어漢字汉字かなカナ")
_CJK_WORDS = {
    "cjk", "chinese", "japanese", "korean", "kanji", "hanzi",
    "radical", "pinyin", "hiragana", "katakana", "mandarin",
}
_CODE_WORDS = {
    "code", "function", "class", "method", "bug", "debug",
    "python", "javascript", "typescript", "rust", "golang",
    "sql", "refactor", "review", "implement", "algorithm",
}
_EU_WORDS = {
    "german", "french", "spanish", "italian", "portuguese",
    "dutch", "polish", "translate", "übersetz", "traduc",
}
_MATH_WORDS = {
    "math", "mathematics", "equation", "formula", "proof",
    "calculate", "integral", "derivative", "statistics",
    "probability", "theorem", "algebra",
}
_REASONING_WORDS = {
    "reason", "analyze", "analyse", "compare", "argue",
    "debate", "infer", "logic", "conclude", "evaluate", "assess",
}


def detect_task(system_role: str = "", instruction: str = "") -> str:
    """Classify the task from system_role + GENERATE instruction text.

    Heuristic classifier — no model required, runs in microseconds.
    Returns one of: "cjk", "code", "eu_lang", "math", "reasoning",
                    "synthesis", "general".
    """
    text = (system_role + " " + instruction).lower()
    chars = set(system_role + instruction)

    if chars & _CJK_CHARS or any(w in text for w in _CJK_WORDS):
        return "cjk"
    if any(w in text for w in _CODE_WORDS):
        return "code"
    if any(w in text for w in _EU_WORDS):
        return "eu_lang"
    if any(w in text for w in _MATH_WORDS):
        return "math"
    if any(w in text for w in _REASONING_WORDS):
        return "reasoning"
    return "general"


# ── Resolver using MODEL_CATALOG ──────────────────────────────────────────────

def resolve_model(adapter: str, task: str, provider: str = "") -> str:
    """Resolve a (task, adapter, provider) triple to a concrete model name.

    Uses MODEL_CATALOG as single source of truth, filtering by:
    - adapter availability
    - model strengths matching the task
    - provider preference (openrouter only)
    - is_active status

    Parameters
    ----------
    adapter  : "claude_cli" | "openrouter" | "ollama"
    task     : output of detect_task()
    provider : optional org preference — any key in PROVIDERS, or ""

    Returns
    -------
    Concrete model name string ready to pass to the adapter.
    """
    # Get all active models for this adapter
    available_models = get_models(adapter, active_only=True)

    if not available_models:
        # Fallback if no models available for adapter
        return "claude-sonnet-4-5" if adapter == "claude_cli" else "qwen3:latest"

    # Filter models by task strength and provider
    candidates = []
    for model_id, info in available_models.items():
        strengths = info.get("strengths", [])
        model_provider = info.get("provider", "")

        # Provider filtering (only for openrouter)
        if provider and adapter == "openrouter" and model_provider != provider:
            continue

        # Task matching - exact match gets priority 3, general gets priority 1
        if task in strengths:
            priority = 3
        elif "general" in strengths:
            priority = 1
        else:
            continue  # Skip models that don't match task or general

        candidates.append((priority, model_id, info))

    if not candidates:
        # No task-specific matches, fall back to first available model
        return list(available_models.keys())[0]

    # Sort by priority (highest first), then by provider preference
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return candidates[0][1]


def auto_route(
    adapter: str,
    system_role: str = "",
    instruction: str = "",
    provider: str = "",
    is_final_prompt: bool = False,
) -> str:
    """One-call convenience: classify task then resolve to a model name.

    Parameters
    ----------
    adapter          : execution adapter
    system_role      : system_role() text from the SPL SELECT clause
    instruction      : GENERATE instruction string from the SPL
    provider         : optional provider preference
    is_final_prompt  : True if this is the last PROMPT (always synthesis)

    Returns
    -------
    Resolved model name string from MODEL_CATALOG.
    """
    task = "synthesis" if is_final_prompt else detect_task(system_role, instruction)
    return resolve_model(adapter, task, provider)