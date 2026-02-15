"""Model routing for USING MODEL auto — maps (task × provider) to model names.

Concept
-------
Three orthogonal dimensions determine the final model:

  task      — what the PROMPT is doing (cjk, code, eu_lang, math, reasoning,
               synthesis, general), detected from system_role + GENERATE text.

  provider  — the LLM company a user/org prefers (anthropic, google, meta,
               mistral, alibaba, deepseek, openai).  Optional.  When set, the
               routing table picks the best model FROM THAT PROVIDER for the
               task — even if a different provider would win best-of-breed.
               Example: company policy = "anthropic" → every auto-routed
               PROMPT uses the best Claude model for its task.

  adapter   — the API interface in use (claude_cli, openrouter, ollama).
               When no provider is set, the adapter-level best-of-breed model
               is returned.

Resolution priority
-------------------
  1. provider set + openrouter adapter  → provider's best model for task
  2. provider set + other adapter       → adapter-level best (provider ignored)
  3. no provider + any adapter          → adapter-level best-of-breed for task

Routing table source
--------------------
Populated from HuggingFace Open LLM Leaderboard v2, LMSYS Chatbot Arena, and
task-specific benchmarks (HumanEval, MATH, C-Eval, MT-Bench) as of 2026-02.
Run  scripts/refresh_routing_table.py  to regenerate from latest leaderboard.
"""

# ── Model Zoo: routing table ─────────────────────────────────────────────────
#
# Keys at the provider level  → "anthropic" | "google" | "meta" | "mistral"
#                                "alibaba"  | "deepseek" | "openai"
# Keys at the adapter level   → "openrouter" (best-of-breed)
#                                "ollama"     (local pull names)
#                                "claude_cli" (always Anthropic)
#
ROUTING_TABLE: dict[str, dict[str, str]] = {

    # ── CJK (Chinese / Japanese / Korean) ────────────────────────────────────
    # Best-of-breed: Qwen2.5-72B leads C-Eval, CMMLU, and JP-LMEH.
    "cjk": {
        "anthropic":  "anthropic/claude-sonnet-4-5-20250929",
        "google":     "google/gemini-2.0-flash-001",
        "meta":       "meta-llama/llama-3.1-70b-instruct",
        "mistral":    "mistralai/mistral-large-2411",
        "alibaba":    "qwen/qwen-2.5-72b-instruct",       # best for CJK
        "deepseek":   "deepseek/deepseek-v3",
        "openai":     "openai/gpt-4o",
        # adapter-level (no provider preference)
        "openrouter": "qwen/qwen-2.5-72b-instruct",
        "ollama":     "qwen2.5",
        "claude_cli": "claude-sonnet-4-5",
    },

    # ── Code (generation, review, debugging, refactoring) ────────────────────
    # Best-of-breed: DeepSeek-Coder-V2 leads HumanEval and SWE-bench.
    "code": {
        "anthropic":  "anthropic/claude-sonnet-4-5-20250929",
        "google":     "google/gemini-2.0-flash-001",
        "meta":       "meta-llama/llama-3.1-70b-instruct",
        "mistral":    "mistralai/codestral-2501",
        "alibaba":    "qwen/qwen-2.5-coder-32b-instruct",
        "deepseek":   "deepseek/deepseek-coder-v2",        # best for code
        "openai":     "openai/gpt-4o",
        "openrouter": "deepseek/deepseek-coder-v2",
        "ollama":     "deepseek-coder",
        "claude_cli": "claude-sonnet-4-5",
    },

    # ── European languages (German, French, Spanish, Italian …) ──────────────
    # Best-of-breed: Mistral-Large leads EU multilingual MT-Bench variants.
    "eu_lang": {
        "anthropic":  "anthropic/claude-sonnet-4-5-20250929",
        "google":     "google/gemini-2.0-flash-001",
        "meta":       "meta-llama/llama-3.1-70b-instruct",
        "mistral":    "mistralai/mistral-large-2411",       # best for EU
        "alibaba":    "qwen/qwen-2.5-72b-instruct",
        "deepseek":   "deepseek/deepseek-v3",
        "openai":     "openai/gpt-4o",
        "openrouter": "mistralai/mistral-large-2411",
        "ollama":     "mistral",
        "claude_cli": "claude-sonnet-4-5",
    },

    # ── Math / science (proofs, equations, symbolic reasoning) ───────────────
    # Best-of-breed: DeepSeek-R1 leads MATH, AIME, and GPQA.
    "math": {
        "anthropic":  "anthropic/claude-sonnet-4-5-20250929",
        "google":     "google/gemini-2.0-flash-thinking-exp",
        "meta":       "meta-llama/llama-3.1-70b-instruct",
        "mistral":    "mistralai/mistral-large-2411",
        "alibaba":    "qwen/qwen-2.5-72b-instruct",
        "deepseek":   "deepseek/deepseek-r1",               # best for math
        "openai":     "openai/o3-mini",
        "openrouter": "deepseek/deepseek-r1",
        "ollama":     "deepseek-r1",
        "claude_cli": "claude-sonnet-4-5",
    },

    # ── Long-form reasoning (analysis, debate, multi-step Q&A) ───────────────
    # Best-of-breed: Claude Opus 4.6 + DeepSeek-R1 top MMLU-Pro / reasoning.
    "reasoning": {
        "anthropic":  "anthropic/claude-opus-4-6",          # best Anthropic
        "google":     "google/gemini-2.0-pro-exp",
        "meta":       "meta-llama/llama-3.3-70b-instruct",
        "mistral":    "mistralai/mistral-large-2411",
        "alibaba":    "qwen/qwen-2.5-72b-instruct",
        "deepseek":   "deepseek/deepseek-r1",
        "openai":     "openai/o1",
        "openrouter": "anthropic/claude-opus-4-6",
        "ollama":     "llama3.2",
        "claude_cli": "claude-opus-4-6",
    },

    # ── Synthesis / composition (merge CTEs, writing, summarising) ───────────
    # Best-of-breed: Claude Opus 4.6 excels at coherent long-form composition.
    "synthesis": {
        "anthropic":  "anthropic/claude-opus-4-6",
        "google":     "google/gemini-1.5-pro",
        "meta":       "meta-llama/llama-3.3-70b-instruct",
        "mistral":    "mistralai/mistral-large-2411",
        "alibaba":    "qwen/qwen-2.5-72b-instruct",
        "deepseek":   "deepseek/deepseek-v3",
        "openai":     "openai/gpt-4o",
        "openrouter": "anthropic/claude-opus-4-6",
        "ollama":     "llama3.2",
        "claude_cli": "claude-opus-4-6",
    },

    # ── General / fallback ────────────────────────────────────────────────────
    "general": {
        "anthropic":  "anthropic/claude-sonnet-4-5-20250929",
        "google":     "google/gemini-2.0-flash-001",
        "meta":       "meta-llama/llama-3.3-70b-instruct",
        "mistral":    "mistralai/mistral-large-2411",
        "alibaba":    "qwen/qwen-2.5-72b-instruct",
        "deepseek":   "deepseek/deepseek-v3",
        "openai":     "openai/gpt-4o",
        "openrouter": "anthropic/claude-sonnet-4-5-20250929",
        "ollama":     "llama3.2",
        "claude_cli": "claude-sonnet-4-5",
    },
}

# Canonical list of supported providers (for UI dropdowns and validation)
PROVIDERS: list[str] = [
    "anthropic", "google", "meta", "mistral",
    "alibaba", "deepseek", "openai",
]

# ── Task classifier ───────────────────────────────────────────────────────────

_CJK_CHARS = set("中文日本語한국語漢字汉字かなカナ")
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


# ── Resolver ─────────────────────────────────────────────────────────────────

def resolve_model(adapter: str, task: str, provider: str = "") -> str:
    """Resolve a (task, adapter, provider) triple to a concrete model name.

    Parameters
    ----------
    adapter  : "claude_cli" | "openrouter" | "ollama"
    task     : output of detect_task()
    provider : optional org preference — any key in PROVIDERS, or ""

    Returns
    -------
    Concrete model name string ready to pass to the adapter.
    """
    task_routes = ROUTING_TABLE.get(task, ROUTING_TABLE["general"])
    fallback    = ROUTING_TABLE["general"]

    if provider:
        # Provider preference only takes effect when using openrouter
        # (which can reach every provider).  Other adapters fall back to
        # their own adapter-level best.
        if adapter == "openrouter":
            return (
                task_routes.get(provider)
                or fallback.get(provider)
                or fallback.get(adapter, "anthropic/claude-sonnet-4-5-20250929")
            )
        # ollama / claude_cli — honour adapter-level best regardless of provider
        return task_routes.get(adapter) or fallback.get(adapter, "claude-sonnet-4-5")

    # No provider preference — best-of-breed for this adapter
    return task_routes.get(adapter) or fallback.get(adapter, "claude-sonnet-4-5")


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
    Resolved model name string.
    """
    task = "synthesis" if is_final_prompt else detect_task(system_role, instruction)
    return resolve_model(adapter, task, provider)
