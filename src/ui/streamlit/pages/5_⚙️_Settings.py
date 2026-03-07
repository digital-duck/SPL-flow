"""SPL-Flow — Settings page.

Configure which models are active for each adapter.  Changes are persisted
immediately to data/model_settings.json and survive Streamlit restarts.

Active models appear in:
  • Model Zoo on the Benchmark page
  • Auto-routing suggestions

Inactive models are hidden from selection but remain in the catalog — you
can re-enable them at any time.
"""
import os
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-flow")

import streamlit as st

st.set_page_config(
    page_title="SPL-Flow · Settings",
    page_icon="⚙️",
    layout="wide",
)

from src.utils.model_catalog import MODEL_CATALOG, set_active, save_overrides
from src.utils.page_helpers import render_footer, render_sidebar

# ── Sidebar ───────────────────────────────────────────────────────────────────
render_sidebar()

# ── Header ────────────────────────────────────────────────────────────────────
st.title("⚙️ Settings")
st.caption(
    "Toggle models on/off for each adapter. "
    "Changes are saved immediately and persist across sessions."
)
st.divider()

# ── Model Management ──────────────────────────────────────────────────────────
st.subheader("Model Zoo")
st.markdown(
    "Active models appear in the Benchmark Model Zoo and auto-routing. "
    "Inactive models are hidden but not deleted — re-enable any time."
)

_STATUS_BADGE = {
    "stable":       "🟢",
    "experimental": "🟡",
    "deprecated":   "🔴",
    "blocked":      "⛔",
}

_ADAPTER_LABELS = {
    "openrouter": "🌐 OpenRouter",
    "ollama":     "🦙 Ollama (local)",
    "claude_cli": "🤖 Claude CLI",
    "cloud_direct": "☁️ Cloud Direct",
}

adapters = list(MODEL_CATALOG.keys())
tabs = st.tabs([_ADAPTER_LABELS.get(a, a) for a in adapters])

for tab, adapter in zip(tabs, adapters):
    with tab:
        models = MODEL_CATALOG[adapter]

        # Summary counts
        total  = len(models)
        active = sum(1 for m in models.values() if m.get("is_active", True))
        st.caption(f"**{active}** of **{total}** models active")

        # Column headers
        h_cols = st.columns([3, 2, 2, 2, 1])
        h_cols[0].markdown("**Model**")
        h_cols[1].markdown("**Provider**")
        h_cols[2].markdown("**Strengths**")
        h_cols[3].markdown("**Status**")
        h_cols[4].markdown("**Active**")

        st.divider()

        for model_id, info in models.items():
            is_active  = info.get("is_active", True)
            status     = info.get("status", "stable")
            badge      = _STATUS_BADGE.get(status, "")
            strengths  = ", ".join(info.get("strengths", []))
            notes      = info.get("notes", "")
            name       = info.get("name", model_id)
            provider   = info.get("provider", "")

            row = st.columns([3, 2, 2, 2, 1])

            # Model name + ID
            with row[0]:
                st.markdown(f"**{name}**")
                st.caption(f"`{model_id}`")
                if info.get("reasoning_model"):
                    st.caption("🧠 reasoning model")

            row[1].markdown(provider)
            row[2].markdown(strengths)

            with row[3]:
                st.markdown(f"{badge} {status}")
                if notes:
                    with st.popover("ℹ️ notes"):
                        st.markdown(notes)

            # Toggle — key must be unique per model
            with row[4]:
                new_val = st.toggle(
                    "active",
                    value=is_active,
                    key=f"toggle_{adapter}_{model_id}",
                    label_visibility="collapsed",
                )
                if new_val != is_active:
                    set_active(adapter, model_id, new_val)
                    st.toast(
                        f"{'Enabled' if new_val else 'Disabled'} `{model_id}`",
                        icon="✅" if new_val else "🚫",
                    )
                    st.rerun()

        st.divider()

        # Bulk actions
        bcol1, bcol2, _ = st.columns([1, 1, 3])
        with bcol1:
            if st.button("Enable all", key=f"enable_all_{adapter}"):
                for mid in MODEL_CATALOG[adapter]:
                    MODEL_CATALOG[adapter][mid]["is_active"] = True
                save_overrides()
                st.rerun()
        with bcol2:
            if st.button("Disable all", key=f"disable_all_{adapter}"):
                for mid in MODEL_CATALOG[adapter]:
                    MODEL_CATALOG[adapter][mid]["is_active"] = False
                save_overrides()
                st.rerun()

st.divider()

# ── Adapter / API info ────────────────────────────────────────────────────────
st.subheader("Adapter Setup")

with st.expander("🦙 Ollama (local)"):
    st.markdown(
        "Start the Ollama server before using local models:\n\n"
        "```bash\nollama serve\n```\n\n"
        "Pull models as needed:\n\n"
        "```bash\nollama pull qwen2.5\nollama pull mistral\nollama pull deepseek-coder\n```\n\n"
        "Ollama runs fully offline — no API key required."
    )

with st.expander("🌐 OpenRouter"):
    st.markdown(
        "Supports 100+ models through a single API endpoint. "
        "Pricing varies per model — see [openrouter.ai/models](https://openrouter.ai/models)."
    )

    # OpenRouter API Key input
    current_or_key = os.environ.get("OPENROUTER_API_KEY", "")
    or_key = st.text_input(
        "OpenRouter API Key",
        value=current_or_key,
        type="password",
        placeholder="sk-or-...",
        key="openrouter_api_key",
        help="Get your API key from https://openrouter.ai/keys"
    )

    if or_key != current_or_key:
        os.environ["OPENROUTER_API_KEY"] = or_key
        if or_key:
            st.success("✅ OpenRouter API key updated")
        else:
            st.warning("⚠️ OpenRouter API key removed")

    if or_key:
        masked_key = or_key[:8] + "****" if len(or_key) > 8 else "****"
        st.code(f"export OPENROUTER_API_KEY={masked_key}", language="bash")

with st.expander("☁️ Cloud Direct"):
    st.markdown(
        "Direct API access bypasses intermediaries for optimal performance and pricing. "
        "Only the relevant API key is required for each provider you want to use."
    )

    # Anthropic API Key
    st.markdown("**Anthropic Claude:**")
    current_ant_key = os.environ.get("ANTHROPIC_API_KEY", "")
    ant_key = st.text_input(
        "Anthropic API Key",
        value=current_ant_key,
        type="password",
        placeholder="sk-ant-...",
        key="anthropic_api_key",
        help="Get your API key from https://console.anthropic.com/"
    )

    if ant_key != current_ant_key:
        os.environ["ANTHROPIC_API_KEY"] = ant_key
        if ant_key:
            st.success("✅ Anthropic API key updated")
        else:
            st.warning("⚠️ Anthropic API key removed")

    if ant_key:
        masked_key = ant_key[:8] + "****" if len(ant_key) > 8 else "****"
        st.code(f"export ANTHROPIC_API_KEY={masked_key}", language="bash")

    st.divider()

    # Google API Key
    st.markdown("**Google Gemini:**")
    current_google_key = os.environ.get("GOOGLE_API_KEY", "")
    google_key = st.text_input(
        "Google API Key",
        value=current_google_key,
        type="password",
        placeholder="AIza...",
        key="google_api_key",
        help="Get your API key from https://aistudio.google.com/app/apikey"
    )

    if google_key != current_google_key:
        os.environ["GOOGLE_API_KEY"] = google_key
        if google_key:
            st.success("✅ Google API key updated")
        else:
            st.warning("⚠️ Google API key removed")

    if google_key:
        masked_key = google_key[:8] + "****" if len(google_key) > 8 else "****"
        st.code(f"export GOOGLE_API_KEY={masked_key}", language="bash")

    st.divider()

    # OpenAI API Key
    st.markdown("**OpenAI GPT:**")
    current_openai_key = os.environ.get("OPENAI_API_KEY", "")
    openai_key = st.text_input(
        "OpenAI API Key",
        value=current_openai_key,
        type="password",
        placeholder="sk-proj-...",
        key="openai_api_key",
        help="Get your API key from https://platform.openai.com/api-keys"
    )

    if openai_key != current_openai_key:
        os.environ["OPENAI_API_KEY"] = openai_key
        if openai_key:
            st.success("✅ OpenAI API key updated")
        else:
            st.warning("⚠️ OpenAI API key removed")

    if openai_key:
        masked_key = openai_key[:8] + "****" if len(openai_key) > 8 else "****"
        st.code(f"export OPENAI_API_KEY={masked_key}", language="bash")

with st.expander("🤖 Claude CLI"):
    st.markdown(
        "Install the Claude CLI and authenticate:\n\n"
        "```bash\nnpm install -g @anthropic-ai/claude-code\nclaude auth\n```\n\n"
        "No API key management needed — Claude CLI handles authentication."
    )

render_footer()
