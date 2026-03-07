"""SPL-Flow — Review page.

Browse every Chat session saved to SQLite: query, generated SPL, and result
are shown side by side.  Use the RAG Context tab to curate the ChromaDB
pairs that power Text2SPL few-shot retrieval.
"""
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-flow")

import streamlit as st

st.set_page_config(
    page_title="SPL-Flow · Review",
    page_icon="👁️",
    layout="wide",
)

from src.db.sqlite_store import deactivate_session, list_sessions
from src.utils.page_helpers import get_rag_store, render_footer

# ── Header ────────────────────────────────────────────────────────────────────
st.title("📋 Review")
st.caption(
    "Browse your Chat sessions — query, SPL, and result side by side. "
    "Curate the RAG context store that powers future SPL generation."
)
st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_sessions, tab_rag = st.tabs(["Sessions", "RAG Context"])

# ══════════════════════════════════════════════════════════════════════════════
# Tab 1: Sessions (SQLite)
# ══════════════════════════════════════════════════════════════════════════════
with tab_sessions:
    sessions = list_sessions(limit=100)

    if not sessions:
        st.info(
            "No sessions yet — run some queries in the **💬 Chat** page "
            "and they will appear here automatically."
        )
    else:
        # ── Summary stats ──────────────────────────────────────────────────
        total_tok  = sum(s.get("total_tokens", 0) for s in sessions)
        total_cost = sum(s.get("cost_usd") or 0.0 for s in sessions)

        s1, s2, s3 = st.columns(3)
        s1.metric("Requests",     len(sessions))
        s2.metric("Total Tokens", f"{total_tok:,}")
        s3.metric("Total Cost",   f"${total_cost:.5f}" if total_cost else "—")
        st.divider()

        # ── Search filter ──────────────────────────────────────────────────
        search = st.text_input(
            "Search",
            placeholder="Filter by keyword in query…",
            key="review_search",
        )
        if search.strip():
            kw = search.strip().lower()
            sessions = [s for s in sessions if kw in s.get("original_query", "").lower()]
            st.caption(f"Showing **{len(sessions)}** matching sessions")

        st.write("")

        # ── Session list ───────────────────────────────────────────────────
        for s in sessions:
            ts  = (s.get("created_at") or "")[:16].replace("T", " ")
            q   = s.get("original_query", "")
            mdl = s.get("model", "—")
            tok = s.get("total_tokens", 0)
            label = f"🕐 `{ts}`   {q}"

            with st.expander(label, expanded=False):
                # Metadata row
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.caption(f"**Model:** {mdl}")
                mc2.caption(f"**Tokens:** {tok:,}")
                lat = s.get("latency_ms", 0)
                mc3.caption(f"**Latency:** {lat / 1000:.1f}s")
                cost = s.get("cost_usd")
                mc4.caption(f"**Cost:** ${cost:.5f}" if cost is not None else "**Cost:** —")

                st.write("")

                # Side-by-side: SPL (left) | gap | Result (right)
                col_spl, _col_gap, col_result = st.columns([2, 0.15, 3])

                with col_spl:
                    st.caption("**Generated SPL**")
                    st.code(s.get("generated_spl", ""), language="sql")
                    edited = s.get("edited_spl", "")
                    if edited and edited != s.get("generated_spl", ""):
                        st.caption("**Edited SPL** (what was executed)")
                        st.code(edited, language="sql")

                with col_result:
                    st.caption("**Result**")
                    result_md = s.get("result_markdown", "")
                    if result_md:
                        st.markdown(result_md)
                    else:
                        st.caption("_(no result recorded)_")

                st.write("")
                if st.button(
                    "Remove",
                    key=f"remove_{s['id']}",
                    help="Hide this request from the list (soft-delete, reversible in DB)",
                ):
                    deactivate_session(s["id"])
                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# Tab 2: RAG Context Store (ChromaDB)
# ══════════════════════════════════════════════════════════════════════════════
with tab_rag:
    st.caption(
        "Every valid (query, SPL) pair is automatically captured here and used as "
        "dynamic few-shot examples for future Text2SPL translations. "
        "Curate noise to improve generation quality."
    )
    st.write("")

    try:
        store = get_rag_store()
        all_records = store.list_all()

        total        = len(all_records)
        active_count = sum(1 for r in all_records if r.active)
        human_count  = sum(1 for r in all_records if r.source == "human")
        edited_count = sum(1 for r in all_records if r.source == "edited")
        synth_count  = sum(1 for r in all_records if r.source == "synthetic")

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total",        total)
        m2.metric("Active",       active_count)
        m3.metric("Inactive",     total - active_count)
        m4.metric("Human 👤",     human_count + edited_count)
        m5.metric("Synthetic 🤖", synth_count)
        st.divider()

        if total == 0:
            st.info(
                "No RAG pairs yet — run some queries in the **💬 Chat** page "
                "and they will appear here automatically."
            )
        else:
            fc1, fc2, fc3 = st.columns([2, 2, 4])
            with fc1:
                source_filter = st.selectbox(
                    "Source", ["All", "human", "edited", "synthetic"], key="rag_src"
                )
            with fc2:
                status_filter = st.selectbox(
                    "Status", ["All", "Active only", "Inactive only"], key="rag_status"
                )
            with fc3:
                search_rag = st.text_input(
                    "Search", placeholder="Filter by keyword…", key="rag_search"
                )

            records = all_records
            if source_filter != "All":
                records = [r for r in records if r.source == source_filter]
            if status_filter == "Active only":
                records = [r for r in records if r.active]
            elif status_filter == "Inactive only":
                records = [r for r in records if not r.active]
            if search_rag.strip():
                kw = search_rag.strip().lower()
                records = [r for r in records if kw in r.nl_query.lower()]

            st.caption(f"Showing **{len(records)}** of **{total}** pairs")

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

                    rc1, rc2, rc3, rc4 = st.columns(4)
                    rc1.caption(f"**Source:** {rec.source}")
                    rc2.caption(f"**Adapter:** {rec.adapter or '—'}")
                    rc3.caption(
                        f"**Captured:** "
                        f"{rec.timestamp[:16].replace('T', ' ') if rec.timestamp else '—'}"
                    )
                    rc4.caption(f"**Status:** {'🟢 active' if rec.active else '🔴 inactive'}")

                    if rec.spl_warnings:
                        for w in rec.spl_warnings:
                            st.warning(w, icon="⚠️")

                    st.write("")
                    ac1, ac2, _ = st.columns([2, 2, 6])
                    with ac1:
                        if rec.active:
                            if st.button("Deactivate", key=f"deact_{rec.id}",
                                         use_container_width=True):
                                store.set_active(rec.id, False)
                                st.rerun()
                        else:
                            if st.button("Activate", key=f"act_{rec.id}",
                                         type="primary", use_container_width=True):
                                store.set_active(rec.id, True)
                                st.rerun()
                    with ac2:
                        if st.button("Delete", key=f"del_{rec.id}",
                                     use_container_width=True):
                            store.delete(rec.id)
                            st.rerun()

    except Exception as rag_err:
        st.error(
            f"RAG Store unavailable: {rag_err}\n\n"
            "`pip install chromadb` if not yet installed."
        )

render_footer()
