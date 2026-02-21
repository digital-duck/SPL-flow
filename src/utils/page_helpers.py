"""Shared Streamlit utilities used by every page.

Import and call render_sidebar() at the top of each page to get a
consistent settings dict.  get_rag_store() is cached at the process
level so all pages share the same ChromaDB client.
"""
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")

import re

import streamlit as st

# ── Think-block stripping ─────────────────────────────────────────────────────

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_think_blocks(text: str) -> str:
    """Remove <think>…</think> reasoning tokens from model output.

    Qwen3 and some Ollama-hosted reasoning models emit their chain-of-thought
    inline in the content field wrapped in <think> tags.  This helper strips
    those blocks so only the final answer is shown.  The raw content in
    execution_results is never modified — stripping is display-only.
    """
    return _THINK_RE.sub("", text).strip()


# ── Logging — one session log file per server process ─────────────────────────

@st.cache_resource
def _init_streamlit_logging():
    """Set up logging once per Streamlit server process.

    Writes to logs/streamlit/<timestamp>.log (absolute path, never relative).
    Both spl_flow.* (orchestration) and spl.* (engine / adapters) are routed
    to the same file so raw HTTP responses and adapter debug output are visible.

    @st.cache_resource ensures this runs exactly once — Streamlit re-runs the
    page script on every interaction, but the cached resource persists.
    """
    from src.utils.logging_config import (
        setup_logging, bridge_spl_logger, STREAMLIT_LOG_DIR,
    )
    STREAMLIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = setup_logging(
        "streamlit",
        log_level="debug",
        log_dir=STREAMLIT_LOG_DIR,
    )
    bridge_spl_logger(log_path, log_level="debug")
    return str(log_path)


# Trigger logging setup as soon as any page imports page_helpers.
_streamlit_log_path: str = _init_streamlit_logging()


# ── RAG store — one ChromaDB client per server process ────────────────────────

@st.cache_resource
def get_rag_store():
    """Return the shared ChromaDB store (created once, reused across reruns)."""
    from src.rag.factory import get_store
    return get_store("chroma")


# ── Session state ─────────────────────────────────────────────────────────────

_PIPELINE_DEFAULTS = {
    "spl_generated": False,
    "spl_query": "",
    "spl_editor": "",
    "spl_view": "",     # read-only right panel — must stay in sync with spl_editor
    "execution_results": [],
    "flow_state": {},
    "executed": False,
    "user_input_saved": "",
    "saved_spls": [],   # list of {label, query, spl, ts} saved for Benchmark
}


def init_pipeline_state() -> None:
    """Initialise pipeline session-state keys if not already present."""
    for k, v in _PIPELINE_DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_pipeline_state() -> None:
    """Reset all pipeline session-state keys to defaults."""
    for k, v in _PIPELINE_DEFAULTS.items():
        st.session_state[k] = v


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar() -> dict:
    """Render the shared settings sidebar and return a settings dict.

    Returns
    -------
    dict with keys:
        adapter, provider, delivery_mode, notify_email,
        context_text, cache_enabled, spl_params, selected_model_id

    ``provider`` is the pinned provider string (e.g. "anthropic") or ``""``
    when auto-route is active.  It is safe to pass directly to the model
    router — the router treats ``""`` as "best-of-breed".
    """
    from src.utils.model_catalog import build_adapter_provider_model_map, get_model_info
    from src.config import get_default_adapter

    _default_adapter = get_default_adapter()
    _adapter_options = ["ollama", "openrouter", "claude_cli"]
    _default_index = _adapter_options.index(_default_adapter) if _default_adapter in _adapter_options else 0

    with st.sidebar:
        st.header("Settings")

        adapter = st.selectbox(
            "LLM Adapter",
            options=_adapter_options,
            index=_default_index,
            help=(
                "ollama — local models, zero cost (qwen3, mistral, llama3, etc.)\n"
                "openrouter — routes to 100+ models via OpenRouter API\n"
                "claude_cli — uses local Claude CLI (subscription)"
            ),
        )

        # Clear stale model selection whenever the adapter changes.
        if st.session_state.get("_last_adapter") != adapter:
            st.session_state.pop("selected_model_id", None)
            st.session_state.pop("selected_provider", None)
            st.session_state["_last_adapter"] = adapter

        # Provider → Model cascade
        model_map = build_adapter_provider_model_map(active_only=True)
        adapter_models = model_map.get(adapter, {})
        selected_provider = ""  # "" means auto-route

        if adapter_models:
            available_providers = sorted(adapter_models.keys())
            st.caption(f"Available providers: {', '.join(available_providers)}")

            provider_label = st.selectbox(
                "🏢 Provider",
                options=["(auto-route)"] + available_providers,
                index=0,
                help="Select a specific provider to see their models, or use (auto-route) for intelligent model routing",
                key="direct_model_provider",
            )
            selected_provider = "" if provider_label.startswith("(") else provider_label

            if selected_provider:
                provider_model_ids = adapter_models.get(selected_provider, [])

                if provider_model_ids:
                    # Build display-name → model_id map; guard against duplicate names.
                    model_options: list[str] = []
                    model_id_map: dict[str, str] = {}

                    for model_id in provider_model_ids:
                        info = get_model_info(adapter, model_id)
                        display_name = info.get("name", model_id)

                        status = info.get("status", "stable")
                        if status == "experimental":
                            display_name += " 🟡"
                        elif status == "deprecated":
                            display_name += " 🔴"
                        if info.get("reasoning_model"):
                            display_name += " 🧠"

                        if display_name in model_id_map:
                            display_name = f"{display_name} ({model_id})"

                        model_options.append(display_name)
                        model_id_map[display_name] = model_id

                    st.caption(f"Found {len(model_options)} models for **{selected_provider}**:")
                    selected_model_display = st.selectbox(
                        "🤖 Select Model",
                        options=["(auto-route)"] + model_options,
                        index=0,
                        help=f"Select a specific {selected_provider} model, or use (auto-route) for task-based routing",
                        key="direct_model_selection",
                    )

                    if selected_model_display and not selected_model_display.startswith("("):
                        _mid = model_id_map[selected_model_display]
                        st.session_state["selected_model_id"] = _mid
                        st.session_state["selected_provider"] = selected_provider

                        info = get_model_info(adapter, _mid)
                        strengths = ", ".join(info.get("strengths", []))
                        if strengths:
                            st.caption(f"**Strengths:** {strengths}")
                        if info.get("notes"):
                            st.caption(f"**Notes:** {info['notes']}")
                    else:
                        st.session_state.pop("selected_model_id", None)
                        st.session_state.pop("selected_provider", None)
                else:
                    st.warning(f"No models found for **{selected_provider}** on **{adapter}**")
            else:
                st.session_state.pop("selected_model_id", None)
                st.session_state.pop("selected_provider", None)
                st.info("✨ Auto-route mode: SPL will use intelligent model selection based on task type")
        else:
            st.error(f"No models available for **{adapter}** adapter")

        strip_think = st.checkbox(
            "Strip `<think>` blocks",
            value=True,
            help=(
                "Hide inline reasoning tokens (<think>…</think>) emitted by "
                "models such as Qwen3 and DeepSeek-R1 (Ollama). "
                "Raw content is preserved in session state — this is display-only."
            ),
        )

        st.divider()

        mode_label = st.radio(
            "Delivery Mode",
            options=["Sync — view result here", "Async — download + email"],
            index=0,
        )
        delivery_mode = "sync" if (mode_label or "").startswith("Sync") else "async"

        notify_email = ""
        if delivery_mode == "async":
            st.caption(
                "📧 Email will be provided automatically via SSO login (planned for v0.2). "
                "Result is saved to file in the meantime."
            )

        st.divider()

        context_text = st.text_area(
            "Paste reference document (optional)",
            height=120,
            placeholder=(
                "Paste an article, code snippet, or data you want SPL to reference.\n"
                "Injected as context.document in the generated SPL."
            ),
        )

        cache_enabled = st.checkbox(
            "Enable result cache",
            value=False,
            help="Cache identical prompts to avoid redundant LLM calls (SQLite-backed)",
        )

        with st.expander("SPL Params (advanced)"):
            params_text = st.text_area(
                "Additional params (key=value per line)",
                placeholder="radical=日\ntopic=quantum computing",
                height=80,
                help="Injected as context.key in the generated SPL SELECT clause",
            )

    # Parse params
    spl_params: dict = {}
    for line in (params_text or "").strip().splitlines():
        if "=" in line:
            key, _, val = line.partition("=")
            spl_params[key.strip()] = val.strip()
    if (context_text or "").strip():
        spl_params["document"] = context_text

    return {
        "adapter": adapter or "claude_cli",
        "provider": selected_provider,        # "" = auto-route; real name = pinned provider
        "delivery_mode": delivery_mode,
        "notify_email": notify_email,
        "context_text": context_text or "",
        "cache_enabled": cache_enabled,
        "spl_params": spl_params,
        "selected_model_id": st.session_state.get("selected_model_id"),
        "strip_think": strip_think,
    }


# ── Footer ────────────────────────────────────────────────────────────────────

_FOOTER_HTML = """
<style>
.splflow-footer {
    position: fixed;
    left: 0;
    bottom: 0;
    width: 100%;
    background-color: white;
    border-top: 1px solid #e8e8e8;
    padding: 8px 0 6px;
    text-align: center;
    font-size: 0.78rem;
    color: #6b6b6b;
    z-index: 999;
    line-height: 1.6;
}
.splflow-footer a {
    color: #1a73e8;
    text-decoration: none;
}
.splflow-footer a:hover {
    text-decoration: underline;
}
/* prevent last page element from hiding behind the fixed footer */
.main .block-container {
    padding-bottom: 72px;
}
</style>
<div class="splflow-footer">
  <strong>SPL-Flow</strong> &mdash;
  <a href="https://github.com/digital-duck/SPL" target="_blank">SPL engine</a> &middot;
  <a href="https://github.com/The-Pocket/PocketFlow" target="_blank">PocketFlow</a> &middot;
  Apache 2.0 &mdash; Built with ❤️ by
  <a href="https://github.com/digital-duck" target="_blank">Digital-Duck</a> and
  <a href="https://claude.ai/code" target="_blank">Claude</a> 
  &mdash; Human x AI
</div>
"""


def render_footer() -> None:
    """Render the fixed SPL-Flow footer on every page."""
    st.markdown(_FOOTER_HTML, unsafe_allow_html=True)
