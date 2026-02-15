"""SPL-Flow — RAG Store page.

Human-in-the-loop review and curation of the (query, SPL) context store.

Every valid pair captured from real sessions is shown here.  Curating this
data directly improves the dynamic few-shot examples used in future Text2SPL
translations — the more you use and curate, the better the system gets.

Data quality tiers:
    👤 human     — captured from real sessions (gold standard)
    ✏️ edited    — user-corrected SPL (gold+)
    🤖 synthetic — generated offline by data-gen scripts (silver)
"""
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")

import streamlit as st

st.set_page_config(
    page_title="SPL-Flow · RAG Store",
    page_icon="🗄",
    layout="wide",
)

from src.utils.page_helpers import get_rag_store

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🗄 RAG Context Store")
st.caption(
    "Every valid (query, SPL) pair from your sessions is captured here automatically. "
    "Review the data, deactivate noise, and delete errors — "
    "the more you curate, the better future retrieval becomes."
)
st.divider()

# ── Main content ──────────────────────────────────────────────────────────────
try:
    store = get_rag_store()
    all_records = store.list_all()

    # ── Summary metrics ───────────────────────────────────────────────────────
    total        = len(all_records)
    active_count = sum(1 for r in all_records if r.active)
    human_count  = sum(1 for r in all_records if r.source == "human")
    edited_count = sum(1 for r in all_records if r.source == "edited")
    synth_count  = sum(1 for r in all_records if r.source == "synthetic")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total",           total)
    m2.metric("Active",          active_count)
    m3.metric("Inactive",        total - active_count)
    m4.metric("Human 👤",        human_count + edited_count)
    m5.metric("Synthetic 🤖",    synth_count)

    st.divider()

    if total == 0:
        st.info(
            "No records yet — generate some SPL queries in the **⚡ Pipeline** page "
            "and they will appear here automatically."
        )
        st.stop()

    # ── Filters ───────────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns([2, 2, 4])
    with fc1:
        source_filter = st.selectbox(
            "Source",
            ["All", "human", "edited", "synthetic"],
            key="rag_src_filter",
        )
    with fc2:
        status_filter = st.selectbox(
            "Status",
            ["All", "Active only", "Inactive only"],
            key="rag_status_filter",
        )
    with fc3:
        search_text = st.text_input(
            "Search",
            placeholder="Filter by keyword in query text…",
            key="rag_search",
        )

    # Apply client-side filters
    records = all_records
    if source_filter != "All":
        records = [r for r in records if r.source == source_filter]
    if status_filter == "Active only":
        records = [r for r in records if r.active]
    elif status_filter == "Inactive only":
        records = [r for r in records if not r.active]
    if search_text.strip():
        kw = search_text.strip().lower()
        records = [r for r in records if kw in r.nl_query.lower()]

    st.caption(f"Showing **{len(records)}** of **{total}** records")
    st.divider()

    # ── Bulk actions ──────────────────────────────────────────────────────────
    if records:
        ba1, ba2, _ = st.columns([2, 2, 6])
        with ba1:
            if st.button("Deactivate all shown", use_container_width=True):
                for r in records:
                    if r.active:
                        store.set_active(r.id, False)
                st.rerun()
        with ba2:
            if st.button("Delete all shown", use_container_width=True):
                for r in records:
                    store.delete(r.id)
                st.rerun()
        st.divider()

    # ── Record list ───────────────────────────────────────────────────────────
    _SOURCE_ICON = {"human": "👤", "synthetic": "🤖", "edited": "✏️"}

    for rec in records:
        status_icon = "✓" if rec.active else "✗"
        src_icon    = _SOURCE_ICON.get(rec.source, "?")
        label = (
            f"{status_icon} {src_icon}  "
            f"{rec.nl_query[:100]}{'…' if len(rec.nl_query) > 100 else ''}"
        )

        with st.expander(label, expanded=False):
            st.code(rec.spl_query, language="sql")

            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.caption(f"**Source:** {rec.source}")
            mc2.caption(f"**Adapter:** {rec.adapter or '—'}")
            mc3.caption(
                f"**Captured:** "
                f"{rec.timestamp[:16].replace('T', ' ') if rec.timestamp else '—'}"
            )
            mc4.caption(
                f"**Status:** {'🟢 active' if rec.active else '🔴 inactive'}"
            )

            if rec.spl_warnings:
                for w in rec.spl_warnings:
                    st.warning(w, icon="⚠️")

            st.write("")   # spacer
            ac1, ac2, _ = st.columns([2, 2, 6])

            with ac1:
                if rec.active:
                    if st.button(
                        "Deactivate",
                        key=f"deact_{rec.id}",
                        use_container_width=True,
                        help="Exclude from retrieval — soft-delete, reversible",
                    ):
                        store.set_active(rec.id, False)
                        st.rerun()
                else:
                    if st.button(
                        "Activate",
                        key=f"act_{rec.id}",
                        type="primary",
                        use_container_width=True,
                        help="Re-include in retrieval",
                    ):
                        store.set_active(rec.id, True)
                        st.rerun()

            with ac2:
                if st.button(
                    "Delete",
                    key=f"del_{rec.id}",
                    use_container_width=True,
                    help="Hard-delete permanently — cannot be undone",
                ):
                    store.delete(rec.id)
                    st.rerun()

except Exception as rag_err:
    st.error(
        f"RAG Store unavailable: {rag_err}\n\n"
        "Make sure ChromaDB is installed:  `pip install chromadb`"
    )

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "**SPL-Flow MVP** — "
    "[SPL engine](https://github.com/digital-duck/SPL) · "
    "[PocketFlow](https://github.com/The-Pocket/PocketFlow) · "
    "Apache 2.0 · human×AI"
)
