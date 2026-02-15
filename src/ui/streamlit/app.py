"""SPL-Flow — Home page (Streamlit UI).

Run:
    streamlit run src/ui/streamlit/app.py
"""
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")

import streamlit as st

st.set_page_config(
    page_title="SPL-Flow",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ SPL-Flow")
st.caption("Declarative LLM Orchestration — MVP Prototype")
st.markdown(
    "Translate any natural language query into "
    "[SPL](https://github.com/digital-duck/SPL) (Structured Prompt Language), "
    "auto-route sub-tasks to specialist models, and receive a composed result."
)
st.divider()

# ── Architecture overview ─────────────────────────────────────────────────────
col_left, col_right = st.columns([3, 2])

with col_left:
    st.subheader("What is SPL-Flow?")
    st.markdown(
        """
SPL-Flow is a **Mixture-of-Models (MoM)** orchestration platform that:

1. **Translates** your free-form query into SPL — a SQL-inspired declarative language
   for LLM context management.
2. **Routes** each sub-task to the best specialist model in parallel:
   - `qwen2.5` for CJK (Chinese / Japanese / Korean)
   - `mistral` for European languages
   - `deepseek-coder` for code review and generation
   - `claude-sonnet` for synthesis and composition
3. **Composes** the parallel results into a single coherent answer.
4. **Learns** from every session — valid (query, SPL) pairs are automatically
   saved to the RAG store and used as dynamic few-shot examples for future queries.
        """
    )

    st.subheader("Getting Started")
    st.markdown(
        """
| Step | Page | Action |
|------|------|--------|
| 1 | **⚡ Pipeline** | Enter a query → Generate SPL → Review → Execute |
| 2 | **🗄 RAG Store** | Review captured pairs · Deactivate noise · Delete errors |
        """
    )

with col_right:
    st.subheader("Pipeline Architecture")
    st.code(
        """\
NL query
  │
  ▼ (Text2SPL + RAG retrieval)
SPL generation ◄── dynamic few-shot examples
  │               from your query history
  ▼
Validate SPL
  │
  ▼
Execute (parallel CTEs)
  ├── qwen2.5    (CJK)
  ├── mistral    (EU lang)
  ├── deepseek   (code)
  └── claude     (synthesis)
  │
  ▼
Composed result
  │
  └──► auto-save to RAG store
        """,
        language="text",
    )

st.divider()

# ── RAG store quick stats ─────────────────────────────────────────────────────
st.subheader("RAG Context Store")
try:
    from src.utils.page_helpers import get_rag_store
    store = get_rag_store()
    all_records = store.list_all()
    total = len(all_records)
    active = sum(1 for r in all_records if r.active)
    human = sum(1 for r in all_records if r.source == "human")
    synth = sum(1 for r in all_records if r.source == "synthetic")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total pairs", total)
    m2.metric("Active (used in retrieval)", active)
    m3.metric("Human-labeled 👤", human)
    m4.metric("Synthetic 🤖", synth)

    if total == 0:
        st.info(
            "No pairs yet — run some queries in the **⚡ Pipeline** page and they will "
            "appear here automatically."
        )
    else:
        # Show the 5 most recent records as a quick preview
        recent = all_records[:5]
        st.caption("Most recent captures:")
        for r in recent:
            icon = "✓" if r.active else "✗"
            src = {"human": "👤", "synthetic": "🤖", "edited": "✏️"}.get(r.source, "?")
            ts = r.timestamp[:16].replace("T", " ") if r.timestamp else "—"
            st.caption(f"{icon} {src} `{ts}` — {r.nl_query[:90]}")

except Exception as e:
    st.warning(f"RAG Store unavailable: {e}  —  `pip install chromadb`")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "**SPL-Flow MVP** — Built on [SPL engine](https://github.com/digital-duck/SPL) "
    "with [PocketFlow](https://github.com/The-Pocket/PocketFlow) orchestration | "
    "Apache 2.0 | human×AI"
)
