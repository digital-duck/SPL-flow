"""SPL-Flow — Settings page.

Configure which models are active for each adapter.  Changes are persisted
immediately to data/model_settings.json and survive Streamlit restarts.

Active models appear in:
  • Model Zoo on the Benchmark page
  • Auto-routing suggestions

Inactive models are hidden from selection but remain in the catalog — you
can re-enable them at any time.
"""
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")

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

with st.expander("🌐 OpenRouter"):
    st.markdown(
        "Set `OPENROUTER_API_KEY` environment variable before starting the server.\n\n"
        "```bash\nexport OPENROUTER_API_KEY=sk-or-...\n```\n\n"
        "Supports 100+ models through a single API endpoint. "
        "Pricing varies per model — see [openrouter.ai/models](https://openrouter.ai/models)."
    )

with st.expander("🦙 Ollama (local)"):
    st.markdown(
        "Start the Ollama server before using local models:\n\n"
        "```bash\nollama serve\n```\n\n"
        "Pull models as needed:\n\n"
        "```bash\nollama pull qwen2.5\nollama pull mistral\nollama pull deepseek-coder\n```\n\n"
        "Ollama runs fully offline — no API key required."
    )

with st.expander("🤖 Claude CLI"):
    st.markdown(
        "Install the Claude CLI and authenticate:\n\n"
        "```bash\nnpm install -g @anthropic-ai/claude-code\nclaude auth\n```\n\n"
        "No API key management needed — Claude CLI handles authentication. "
        "This is the default adapter for SPL-Flow."
    )

render_footer()
