"""SPL-Flow application configuration.

Loads splflow.yaml (project root) via dd-config and exposes typed accessors.
Falls back to built-in defaults when the file is absent or a key is missing,
so the app works out-of-the-box with no config file required.

Supported splflow.yaml keys
---------------------------
llm_adapter : str   — default LLM adapter ("ollama" | "openrouter" | "claude_cli" | "cloud_direct")
"""
from pathlib import Path

try:
    from dd_config import Config as _Config
    _DD_CONFIG_AVAILABLE = True
except ImportError:
    _DD_CONFIG_AVAILABLE = False

_YAML_PATH = Path(__file__).resolve().parent.parent / "splflow.yaml"

_VALID_ADAPTERS = {"ollama", "openrouter", "claude_cli", "cloud_direct"}
_BUILTIN_DEFAULTS = {
    "llm_adapter": "ollama",
}


def _load() -> dict:
    """Load splflow.yaml if dd-config is available and the file exists."""
    if not _DD_CONFIG_AVAILABLE or not _YAML_PATH.exists():
        return {}
    try:
        cfg = _Config.load(_YAML_PATH)
        return cfg.to_dict()
    except Exception:
        return {}


_cfg: dict = _load()


def get(key: str, default=None):
    """Return a config value, falling back to built-in defaults."""
    return _cfg.get(key, _BUILTIN_DEFAULTS.get(key, default))


def get_default_adapter() -> str:
    """Return the configured default LLM adapter.

    Reads ``llm_adapter`` from splflow.yaml.  Falls back to ``"ollama"``
    if the key is absent or the value is not a recognised adapter name.
    """
    value = get("llm_adapter", "ollama")
    if value not in _VALID_ADAPTERS:
        return "ollama"
    return value


def reload() -> None:
    """Re-read splflow.yaml from disk (useful after the file is edited)."""
    global _cfg
    _cfg = _load()
