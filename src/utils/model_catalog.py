"""Model catalog — single source of truth for all adapter/model combinations.

Each entry records:
  name            : human-readable name
  provider        : org that trains the model
  strengths       : list of task types this model excels at
  reasoning_model : True → response is in "reasoning" field, not "content"
                    (GLM-4.7, GLM-5, DeepSeek-R1, QwQ …)
  status          : "stable" | "experimental" | "deprecated" | "blocked"
  is_active       : False → excluded from Model Zoo and auto-routing
                    (set via Settings page; persisted to data/model_settings.json)
  notes           : observed behaviour, known issues, workarounds

Runtime overrides (is_active changes made in the Settings page) are persisted
to data/model_settings.json and loaded at import time so changes survive
Streamlit restarts without modifying this source file.
"""

from __future__ import annotations
import json
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SETTINGS_PATH = _PROJECT_ROOT / "data" / "model_settings.json"

# ── Catalog ───────────────────────────────────────────────────────────────────

MODEL_CATALOG: dict[str, dict[str, dict]] = {

    # ══════════════════════════════════════════════════════════════════════════
    "openrouter": {

        # Anthropic
        "anthropic/claude-opus-4-6": {
            "name": "Claude Opus 4.6",
            "provider": "anthropic",
            "strengths": ["synthesis", "reasoning", "long-form"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "anthropic/claude-sonnet-4-5-20250929": {
            "name": "Claude Sonnet 4.5",
            "provider": "anthropic",
            "strengths": ["general", "synthesis", "code"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },

        # OpenAI
        "openai/gpt-4o-2024-11-20": {
            "name": "GPT-4o (Nov 2024)",
            "provider": "openai",
            "strengths": ["general", "reasoning", "code"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "Best token efficiency in benchmark (3,956 tokens, 28.4s).",
        },
        "openai/gpt-4o": {
            "name": "GPT-4o (latest)",
            "provider": "openai",
            "strengths": ["general", "reasoning", "code"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "openai/o3-mini": {
            "name": "o3-mini",
            "provider": "openai",
            "strengths": ["math", "reasoning"],
            "reasoning_model": True,
            "is_active": True,
            "status": "stable",
            "notes": "Reasoning model — response may be in reasoning field.",
        },

        # Google
        "google/gemini-3-flash-preview": {
            "name": "Gemini 3 Flash",
            "provider": "google",
            "strengths": ["general", "speed"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "Fastest in benchmark (26.1s). Good citation accuracy.",
        },
        "google/gemini-3-pro-preview": {
            "name": "Gemini 3 Pro",
            "provider": "google",
            "strengths": ["general", "long-form"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "Verbose — correctly notes 2024 award not yet announced.",
        },
        "google/gemini-2.0-flash-001": {
            "name": "Gemini 2.0 Flash",
            "provider": "google",
            "strengths": ["general", "speed"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "google/gemini-2.0-flash-thinking-exp": {
            "name": "Gemini 2.0 Flash Thinking",
            "provider": "google",
            "strengths": ["math", "reasoning"],
            "reasoning_model": True,
            "is_active": True,
            "status": "experimental",
            "notes": "Reasoning model — extended thinking mode.",
        },
        "google/gemini-2.0-pro-exp": {
            "name": "Gemini 2.0 Pro",
            "provider": "google",
            "strengths": ["reasoning", "long-form"],
            "reasoning_model": False,
            "is_active": True,
            "status": "experimental",
            "notes": "",
        },

        # Mistral
        "mistralai/mistral-large-2411": {
            "name": "Mistral Large (Nov 2024)",
            "provider": "mistral",
            "strengths": ["eu_lang", "reasoning", "general"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "Best-of-breed for European languages.",
        },
        "mistralai/codestral-2501": {
            "name": "Codestral (Jan 2025)",
            "provider": "mistral",
            "strengths": ["code"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },

        # Alibaba / Qwen
        "qwen/qwen-2.5-72b-instruct": {
            "name": "Qwen 2.5 72B",
            "provider": "alibaba",
            "strengths": ["cjk", "general"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "Best-of-breed for CJK tasks. Benchmark: 1,025 tokens, 20.6s.",
        },
        "qwen/qwen-2.5-coder-32b-instruct": {
            "name": "Qwen 2.5 Coder 32B",
            "provider": "alibaba",
            "strengths": ["code"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "qwen/qwen3-235b-a22b": {
            "name": "Qwen3 235B-A22B",
            "provider": "alibaba",
            "strengths": ["general", "reasoning"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "Highest token count in benchmark (9,527) but consistent output.",
        },

        # DeepSeek
        "deepseek/deepseek-r1": {
            "name": "DeepSeek-R1",
            "provider": "deepseek",
            "strengths": ["math", "reasoning"],
            "reasoning_model": True,
            "is_active": True,
            "status": "stable",
            "notes": (
                "Reasoning model — content field may be empty; "
                "answer is in 'reasoning' field. Benchmark: 859 tokens, 89.9s."
            ),
        },
        "deepseek/deepseek-v3": {
            "name": "DeepSeek-V3",
            "provider": "deepseek",
            "strengths": ["general", "eu_lang"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "deepseek/deepseek-coder-v2": {
            "name": "DeepSeek-Coder-V2",
            "provider": "deepseek",
            "strengths": ["code"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "Leads HumanEval and SWE-bench.",
        },

        # Meta / Llama
        "meta-llama/llama-3.3-70b-instruct": {
            "name": "Llama 3.3 70B",
            "provider": "meta",
            "strengths": ["general", "reasoning", "synthesis"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "meta-llama/llama-3.1-70b-instruct": {
            "name": "Llama 3.1 70B",
            "provider": "meta",
            "strengths": ["general"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },

        # Moonshot
        "moonshotai/kimi-k2": {
            "name": "Kimi K2",
            "provider": "moonshotai",
            "strengths": ["general"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "Completes tasks but hedges with 'unable to verify' on citations.",
        },

        # Z.ai / GLM
        "z-ai/glm-4.7": {
            "name": "GLM-4.7",
            "provider": "z-ai",
            "strengths": ["cjk"],
            "reasoning_model": True,
            "is_active": True,
            "status": "experimental",
            "notes": (
                "Reasoning model — 'content' field is EMPTY; answer is in 'reasoning' field. "
                "Hits finish_reason=length during chain-of-thought (7,414 tokens, 134.7s). "
                "Web UI works fine; OpenRouter API requires reasoning-field fallback."
            ),
        },
        "z-ai/glm-5": {
            "name": "GLM-5",
            "provider": "z-ai",
            "strengths": ["cjk"],
            "reasoning_model": True,
            "is_active": False,
            "status": "experimental",
            "notes": (
                "Reasoning model — 'content' field EMPTY; reasoning field populated. "
                "KNOWN BUG: token loop on structured tasks (208K tokens observed). "
                "Apply max_tokens ≤ 10000. Web UI works; API requires reasoning fallback."
            ),
        },
        "z-ai/glm-4.6": {
            "name": "GLM-4.6",
            "provider": "z-ai",
            "strengths": ["cjk"],
            "reasoning_model": False,
            "is_active": False,
            "status": "deprecated",
            "notes": (
                "JSON parse failure — embeds raw ASCII control characters in response body. "
                "3-pass recovery in openrouter.py helps partially but model is unreliable."
            ),
        },
    },

    # ══════════════════════════════════════════════════════════════════════════
    "ollama": {

        # Alibaba / Qwen
        "qwen3": {
            "name": "Qwen3 (Ollama)",
            "provider": "alibaba",
            "strengths": ["general", "reasoning", "cjk"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "qwen2.5": {
            "name": "Qwen 2.5 (Ollama)",
            "provider": "alibaba",
            "strengths": ["cjk", "general"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "qwen2.5-coder": {
            "name": "Qwen 2.5 Coder (Ollama)",
            "provider": "alibaba",
            "strengths": ["code"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "qwen2-math": {
            "name": "Qwen2 Math (Ollama)",
            "provider": "alibaba",
            "strengths": ["math", "reasoning"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },

        # Mistral
        "mistral-nemo": {
            "name": "Mistral Nemo (Ollama)",
            "provider": "mistral",
            "strengths": ["eu_lang", "general", "reasoning"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "mistral": {
            "name": "Mistral (Ollama)",
            "provider": "mistral",
            "strengths": ["eu_lang", "general"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "mathstral": {
            "name": "Mathstral (Ollama)",
            "provider": "mistral",
            "strengths": ["math", "reasoning"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "Mistral specialist for mathematical reasoning.",
        },

        # DeepSeek
        "deepseek-coder-v2": {
            "name": "DeepSeek-Coder V2 (Ollama)",
            "provider": "deepseek",
            "strengths": ["code"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "deepseek-r1": {
            "name": "DeepSeek-R1 (Ollama)",
            "provider": "deepseek",
            "strengths": ["math", "reasoning"],
            "reasoning_model": True,
            "is_active": True,
            "status": "stable",
            "notes": "Reasoning model — response structure varies by Ollama version.",
        },

        # Meta / Llama
        "llama3.2": {
            "name": "Llama 3.2 (Ollama)",
            "provider": "meta",
            "strengths": ["general"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "llama3.1": {
            "name": "Llama 3.1 (Ollama)",
            "provider": "meta",
            "strengths": ["general", "reasoning"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },

        # Google
        "gemma3": {
            "name": "Gemma 3 (Ollama)",
            "provider": "google",
            "strengths": ["general", "reasoning"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "codegemma": {
            "name": "CodeGemma (Ollama)",
            "provider": "google",
            "strengths": ["code"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },

        # Microsoft
        "phi4": {
            "name": "Phi-4 (Ollama)",
            "provider": "microsoft",
            "strengths": ["reasoning", "general"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "phi3.5": {
            "name": "Phi-3.5 (Ollama)",
            "provider": "microsoft",
            "strengths": ["general", "speed"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },

        # BigCode
        "starcoder2:7b": {
            "name": "StarCoder2 7B (Ollama)",
            "provider": "bigcode",
            "strengths": ["code"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
    },

    # ══════════════════════════════════════════════════════════════════════════
    "claude_cli": {
        "claude-opus-4-6": {
            "name": "Claude Opus 4.6",
            "provider": "anthropic",
            "strengths": ["synthesis", "reasoning", "long-form"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "claude-sonnet-4-5": {
            "name": "Claude Sonnet 4.5",
            "provider": "anthropic",
            "strengths": ["general", "synthesis", "code"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "",
        },
        "claude-haiku-4-5": {
            "name": "Claude Haiku 4.5",
            "provider": "anthropic",
            "strengths": ["speed", "general"],
            "reasoning_model": False,
            "is_active": True,
            "status": "stable",
            "notes": "Fastest and cheapest Claude model.",
        },
    },
}

# ── Runtime overrides ─────────────────────────────────────────────────────────

def _load_overrides() -> dict[str, dict[str, bool]]:
    """Load is_active overrides from data/model_settings.json.

    Returns {adapter: {model_id: is_active}} or {} if file absent/invalid.
    """
    try:
        if _SETTINGS_PATH.exists():
            return json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _apply_overrides(overrides: dict[str, dict[str, bool]]) -> None:
    """Mutate MODEL_CATALOG in-place with is_active overrides."""
    for adapter, models in overrides.items():
        for model_id, is_active in models.items():
            if adapter in MODEL_CATALOG and model_id in MODEL_CATALOG[adapter]:
                MODEL_CATALOG[adapter][model_id]["is_active"] = is_active


def save_overrides() -> None:
    """Persist current is_active state of all models to data/model_settings.json."""
    overrides: dict[str, dict[str, bool]] = {}
    for adapter, models in MODEL_CATALOG.items():
        overrides[adapter] = {
            model_id: info.get("is_active", True)
            for model_id, info in models.items()
        }
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(
        json.dumps(overrides, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def set_active(adapter: str, model_id: str, active: bool) -> None:
    """Toggle is_active for one model and persist immediately."""
    if adapter in MODEL_CATALOG and model_id in MODEL_CATALOG[adapter]:
        MODEL_CATALOG[adapter][model_id]["is_active"] = active
        save_overrides()


# Apply any persisted overrides on import
_apply_overrides(_load_overrides())


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_models(
    adapter: str,
    include_statuses: tuple[str, ...] = ("stable", "experimental"),
    active_only: bool = True,
) -> dict[str, dict]:
    """Return catalog entries for adapter, filtered by status and is_active."""
    return {
        model_id: info
        for model_id, info in MODEL_CATALOG.get(adapter, {}).items()
        if info.get("status", "stable") in include_statuses
        and (not active_only or info.get("is_active", True))
    }


def is_reasoning_model(adapter: str, model_id: str) -> bool:
    """Return True if this model stores its answer in the 'reasoning' field."""
    return MODEL_CATALOG.get(adapter, {}).get(model_id, {}).get("reasoning_model", False)


def get_notes(adapter: str, model_id: str) -> str:
    """Return known-issue notes for a model, or empty string."""
    return MODEL_CATALOG.get(adapter, {}).get(model_id, {}).get("notes", "")
