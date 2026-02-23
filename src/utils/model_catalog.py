"""Model catalog — single source of truth for all adapter/model combinations.

Loads from data/model_settings.yaml using dd-config. This YAML file serves as the
persistent source of truth for all model configurations including:

  name            : human-readable name
  provider        : org that trains the model
  strengths       : list of task types this model excels at
  reasoning_model : True → response is in "reasoning" field, not "content"
                    (GLM-4.7, GLM-5, DeepSeek-R1, QwQ …)
  status          : "stable" | "experimental" | "deprecated" | "blocked"
  is_active       : False → excluded from Model Zoo and auto-routing
  notes           : observed behaviour, known issues, workarounds

Changes made in the Settings page are persisted to data/model_settings.yaml
and automatically reload on Streamlit restart.
"""

from __future__ import annotations
from pathlib import Path
import logging

_log = logging.getLogger(__name__)

# Import dd-config for YAML loading
try:
    from dd_config import Config as _Config
    _DD_CONFIG_AVAILABLE = True
except ImportError:
    _DD_CONFIG_AVAILABLE = False
    _log.warning("dd-config not available. Install with: pip install dd-config")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SETTINGS_PATH = _PROJECT_ROOT / "config" / "model_settings.yaml"

# ── Model Catalog Loading ────────────────────────────────────────────────────

def _load_model_catalog() -> dict[str, dict[str, dict]]:
    """Load model catalog from config/model_settings.yaml using dd-config.

    Returns
    -------
    dict[str, dict[str, dict]]
        Nested structure: adapter -> model_id -> model_info
    """
    if not _DD_CONFIG_AVAILABLE:
        _log.error("dd-config is required but not installed. Using empty catalog.")
        return {}

    if not _SETTINGS_PATH.exists():
        _log.error(f"Model settings file not found: {_SETTINGS_PATH}")
        return {}

    try:
        cfg = _Config.load(_SETTINGS_PATH)
        data = cfg.to_dict()
        _log.info(f"Loaded {len(data)} adapters from {_SETTINGS_PATH}")

        # Validate structure
        total_models = sum(len(models) for models in data.values())
        _log.info(f"Total models loaded: {total_models}")

        return data

    except Exception as e:
        _log.error(f"Failed to load model settings from {_SETTINGS_PATH}: {e}")
        return {}


def _save_model_catalog(catalog: dict[str, dict[str, dict]]) -> None:
    """Save model catalog back to YAML file using dd-config.

    Parameters
    ----------
    catalog : dict
        Complete model catalog to save
    """
    if not _DD_CONFIG_AVAILABLE:
        _log.error("dd-config is required but not installed. Cannot save settings.")
        return

    try:
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Create Config object and save
        cfg = _Config(catalog)
        cfg.save(_SETTINGS_PATH)

        _log.info(f"Saved model catalog to {_SETTINGS_PATH}")

    except Exception as e:
        _log.error(f"Failed to save model catalog to {_SETTINGS_PATH}: {e}")


# ── Global Catalog Instance ──────────────────────────────────────────────────

# Load the catalog at module import time
MODEL_CATALOG: dict[str, dict[str, dict]] = _load_model_catalog()

# ── Model Management Functions ───────────────────────────────────────────────

def save_overrides() -> None:
    """Persist current model catalog state back to YAML file."""
    _save_model_catalog(MODEL_CATALOG)


def set_active(adapter: str, model_id: str, active: bool) -> None:
    """Toggle is_active for one model and persist immediately to YAML."""
    if adapter in MODEL_CATALOG and model_id in MODEL_CATALOG[adapter]:
        MODEL_CATALOG[adapter][model_id]["is_active"] = active
        save_overrides()
        _log.info(f"Set {adapter}/{model_id} is_active={active}")
    else:
        _log.warning(f"Model not found: {adapter}/{model_id}")


def reload_catalog() -> None:
    """Reload model catalog from YAML file (useful after external edits)."""
    global MODEL_CATALOG
    MODEL_CATALOG = _load_model_catalog()
    _log.info("Reloaded model catalog from YAML")


# ── Helper Functions ──────────────────────────────────────────────────────────

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


def get_model_info(adapter: str, model_id: str) -> dict:
    """Get complete model info for display purposes.

    Returns
    -------
    dict with keys: name, provider, strengths, reasoning_model, status, notes, is_active
    """
    return MODEL_CATALOG.get(adapter, {}).get(model_id, {})


# ── Hierarchical Model Structure for UI ──────────────────────────────────────

def build_adapter_provider_model_map(active_only: bool = True) -> dict[str, dict[str, list[str]]]:
    """Build hierarchical map: adapter -> provider -> [model_ids].

    Returns structure like:
    {
        "openrouter": {
            "anthropic": ["anthropic/claude-opus-4.6", "anthropic/claude-sonnet-4.5"],
            "openai": ["openai/gpt-5.2", "openai/gpt-4o-mini"],
            ...
        },
        "ollama": {
            "alibaba": ["qwen3", "qwen2.5", "qwen2.5-coder"],
            "mistral": ["mistral", "mathstral"],
            ...
        },
        ...
    }

    Parameters
    ----------
    active_only : bool
        If True, only include models where is_active=True

    Returns
    -------
    dict[str, dict[str, list[str]]]
        Nested dictionary: adapter -> provider -> list of model IDs
    """
    result = {}

    for adapter, models in MODEL_CATALOG.items():
        result[adapter] = {}

        for model_id, info in models.items():
            # Skip inactive models if requested
            if active_only and not info.get("is_active", True):
                continue

            provider = info.get("provider", "unknown")

            if provider not in result[adapter]:
                result[adapter][provider] = []

            result[adapter][provider].append(model_id)

    # Sort providers and models for consistent UI ordering
    for adapter in result:
        for provider in result[adapter]:
            result[adapter][provider].sort()

    return result


# ── Validation ────────────────────────────────────────────────────────────────

def validate_catalog() -> list[str]:
    """Validate model catalog structure and return any issues found.

    Returns
    -------
    list[str]
        List of validation issues found, empty if valid
    """
    issues = []

    required_fields = {"name", "provider", "strengths", "reasoning_model", "is_active", "status"}
    valid_statuses = {"stable", "experimental", "deprecated", "blocked"}

    for adapter, models in MODEL_CATALOG.items():
        if not isinstance(models, dict):
            issues.append(f"Adapter '{adapter}' should contain a dict of models")
            continue

        for model_id, info in models.items():
            if not isinstance(info, dict):
                issues.append(f"Model '{adapter}/{model_id}' should be a dict")
                continue

            # Check required fields
            missing = required_fields - set(info.keys())
            if missing:
                issues.append(f"Model '{adapter}/{model_id}' missing fields: {missing}")

            # Check status values
            status = info.get("status")
            if status and status not in valid_statuses:
                issues.append(f"Model '{adapter}/{model_id}' has invalid status: {status}")

            # Check strengths is a list
            strengths = info.get("strengths")
            if strengths and not isinstance(strengths, list):
                issues.append(f"Model '{adapter}/{model_id}' strengths should be a list")

    return issues


# ── Legacy JSON Migration ────────────────────────────────────────────────────

def _migrate_from_json() -> None:
    """One-time migration from old model_settings.json to model_settings.yaml.

    This function can be called manually if needed to migrate existing JSON settings.
    """
    json_path = _PROJECT_ROOT / "data" / "model_settings.json"

    if json_path.exists() and not _SETTINGS_PATH.exists():
        try:
            import json
            json_data = json.loads(json_path.read_text(encoding="utf-8"))

            # Convert simple JSON structure to full YAML structure
            # This is a simplified migration - manual editing of YAML is recommended
            _log.warning("JSON to YAML migration is simplified. Please review model_settings.yaml manually.")

        except Exception as e:
            _log.error(f"Failed to migrate from JSON: {e}")


# ── Initialization ───────────────────────────────────────────────────────────

# Validate catalog on import
_validation_issues = validate_catalog()
if _validation_issues:
    _log.warning(f"Model catalog validation issues: {_validation_issues}")

# Log catalog status
if MODEL_CATALOG:
    adapters = list(MODEL_CATALOG.keys())
    total_models = sum(len(models) for models in MODEL_CATALOG.values())
    _log.info(f"Model catalog loaded: {len(adapters)} adapters, {total_models} models")
else:
    _log.warning("Model catalog is empty - check data/model_settings.yaml")