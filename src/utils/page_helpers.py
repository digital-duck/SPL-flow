"""Shared Streamlit utilities used by every page.

Import and call render_sidebar() at the top of each page to get a
consistent settings dict.  get_rag_store() is cached at the process
level so all pages share the same ChromaDB client.
"""
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")

import streamlit as st


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
        context_text, cache_enabled, spl_params
    """
    with st.sidebar:
        st.header("Settings")

        adapter = st.selectbox(
            "LLM Adapter",
            options=["claude_cli", "openrouter", "ollama"],
            index=0,
            help=(
                "claude_cli — uses local Claude CLI (subscription)\n"
                "openrouter — routes to 100+ models via OpenRouter API\n"
                "ollama — local models (qwen2.5, mistral, llama3, etc.)"
            ),
        )
        st.caption("SPL auto-routes CJK/EU/code/synthesis sub-tasks to specialist models.")

        _provider_label = st.selectbox(
            "LLM Provider (USING MODEL auto)",
            options=[
                "(best-of-breed)", "anthropic", "google", "meta",
                "mistral", "alibaba", "deepseek", "openai",
            ],
            index=0,
            help=(
                "Optional: pin USING MODEL auto to models from one provider.\n"
                "Useful when your org has contracted with a specific provider.\n"
                "Only takes effect when adapter = openrouter."
            ),
        )
        provider = "" if (_provider_label or "").startswith("(") else (_provider_label or "")

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
        "provider": provider,
        "delivery_mode": delivery_mode,
        "notify_email": notify_email,
        "context_text": context_text or "",
        "cache_enabled": cache_enabled,
        "spl_params": spl_params,
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
  Apache 2.0<br>
  Built with ❤️ by
  <a href="https://claude.ai/code" target="_blank">Claude</a> and
  <a href="https://github.com/digital-duck" target="_blank">Digital-Duck</a>
  &mdash; Human x AI
</div>
"""


def render_footer() -> None:
    """Render the fixed SPL-Flow footer on every page."""
    st.markdown(_FOOTER_HTML, unsafe_allow_html=True)
