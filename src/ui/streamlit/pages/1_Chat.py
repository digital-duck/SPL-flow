"""SPL-Flow — Chat page.

Step 1: Describe query → generate SPL (Text2SPL + RAG retrieval)
Step 2: Review & edit generated SPL
Step 3: Execute and view result
"""
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")

from datetime import datetime

import streamlit as st

st.set_page_config(
    page_title="SPL-Flow · Chat",
    page_icon="💬",
    layout="wide",
)

from src import api
from src.db.sqlite_store import save_session
from src.utils.page_helpers import init_pipeline_state, render_footer, render_sidebar, reset_pipeline_state

spl_explain = None
try:
    from spl import explain as spl_explain
    SPL_AVAILABLE = True
except ImportError:
    SPL_AVAILABLE = False

try:
    from src.utils.chunker import should_chunk, count_tokens
    CHUNKER_AVAILABLE = True
except ImportError:
    CHUNKER_AVAILABLE = False

# ── Sample queries for UI testing ─────────────────────────────────────────────

_SAMPLE_QUERIES = [
    (
        "Chinese water-radical characters",
        "List 10 Chinese characters that contain the water radical — "
        "show decomposition formula, pinyin, English meaning, and German translation",
    ),
    (
        "Summarise an article",
        "Summarize the key findings of this document in 3 bullet points, "
        "highlighting the most important insights",
    ),
    (
        "Quantum vs classical computing",
        "Compare quantum computing and classical computing in a structured "
        "markdown table with dimensions: speed, error rate, use cases, maturity",
    ),
    (
        "Python code review",
        "Review this Python function for bugs, performance issues, and style "
        "improvements — provide a severity-ranked list with suggested fixes",
    ),
]

# ── Init & sidebar ────────────────────────────────────────────────────────────
init_pipeline_state()

# Transfer any pending sample query into the text-area state BEFORE the widget
# is instantiated.  Streamlit forbids writing a widget key after the widget has
# rendered in the same script run, so the sample buttons store their value in a
# one-shot buffer key ("_sample_pending") and rerun; on the next run this block
# moves the value into the widget key before the text_area is created.
if "_sample_pending" in st.session_state:
    st.session_state.user_input_area = st.session_state.pop("_sample_pending")

settings = render_sidebar()

adapter       = settings["adapter"]
provider      = settings["provider"]
context_text  = settings["context_text"]
cache_enabled = settings["cache_enabled"]
spl_params    = settings["spl_params"]

# Warn when pasted document exceeds the chunking threshold.
# The Chat page's generate→review→execute flow uses api.exec_spl (no chunking).
# For long-doc use cases, the CLI `splflow run` command uses api.run() which
# does trigger run_chunking_flow automatically.
if CHUNKER_AVAILABLE and context_text and should_chunk(context_text):
    doc_tokens = count_tokens(context_text)
    st.sidebar.warning(
        f"⚠️ Document is large (~{doc_tokens:,} tokens). "
        "The Chat page generates SPL for review first; "
        "the auto-chunking Map-Reduce path is available via "
        "`splflow run` in the CLI."
    )

# ── Header ────────────────────────────────────────────────────────────────────
st.title("💬 Chat")
st.caption("Describe your query in plain English — SPL-Flow translates, routes, and composes the answer.")
st.divider()

# ── STEP 1: Query Input — 2-column layout ─────────────────────────────────────
st.subheader("Step 1 — Describe your query")

col_input, col_samples = st.columns([3, 2])

with col_input:
    user_input = st.text_area(
        "What do you want to generate?",
        height=170,
        placeholder=(
            "Describe your query in plain English.\n"
            "SPL-Flow translates it to a structured SPL query\n"
            "and routes sub-tasks to specialist models."
        ),
        key="user_input_area",
    )

    btn_col, reset_col, _ = st.columns([2, 1, 4])
    with btn_col:
        generate_clicked = st.button("Generate SPL", type="primary", use_container_width=True)
    with reset_col:
        if st.button("Reset", use_container_width=True):
            reset_pipeline_state()
            st.rerun()

with col_samples:
    st.caption("**Sample queries** — click to load:")
    for label, query in _SAMPLE_QUERIES:
        if st.button(label, key=f"sample_{label}", use_container_width=True):
            st.session_state["_sample_pending"] = query
            st.rerun()


if generate_clicked:
    if not user_input.strip():
        st.warning("Please enter a query before generating SPL.")
    else:
        with st.spinner("Translating to SPL (Text2SPL + RAG retrieval)..."):
            result = api.generate(user_input, context_text=context_text, adapter=adapter)
        if result["error"]:
            st.error(f"SPL generation failed: {result['error']}")
        elif result["spl_query"]:
            st.session_state.spl_query = result["spl_query"]
            # Force the editor to show the newly generated SPL.
            # st.text_area ignores value= once its key exists in session_state,
            # so we overwrite the key directly here before the widget renders.
            st.session_state.spl_editor = result["spl_query"]
            st.session_state.spl_generated = True
            st.session_state.flow_state = result
            st.session_state.executed = False
            st.session_state.execution_results = []
            st.session_state.user_input_saved = user_input
            if result["retry_count"] > 1:
                st.info(f"Generated after {result['retry_count']} attempt(s).")
        else:
            st.warning("No SPL was generated — try rephrasing your query.")

# ── STEP 2: SPL Preview & Edit — 2-column layout ──────────────────────────────
if st.session_state.spl_generated and st.session_state.spl_query:
    st.divider()
    st.subheader("Step 2 — Review & edit SPL")

    for w in st.session_state.flow_state.get("spl_warnings", []):
        st.warning(f"Warning: {w}")

    original_spl = st.session_state.spl_query or ""

    col_edit, col_view = st.columns(2)

    with col_edit:
        st.caption("Edit SPL — run your version (edits apply immediately on Execute)")
        edited_spl = st.text_area(
            "Edit SPL",
            height=280,
            label_visibility="collapsed",
            key="spl_editor",
        )
        btn_exec_edited, btn_dl = st.columns([3, 2])
        with btn_exec_edited:
            exec_edited = st.button(
                "▶ Execute edited", key="exec_edited",
                type="primary", use_container_width=True,
            )
        with btn_dl:
            _spl_filename = f"spl-{datetime.now().strftime('%Y%m%d-%H%M%S')}.spl"
            st.download_button(
                "⬇ Download SPL",
                data=edited_spl or original_spl,
                file_name=_spl_filename,
                mime="text/plain",
                use_container_width=True,
            )

    with col_view:
        st.caption("Generated SPL — original (read-only)")
        st.text_area(
            "SPL view",
            value=original_spl,
            height=280,
            disabled=True,
            label_visibility="collapsed",
            key="spl_view",
        )
        btn_exec_orig, btn_save = st.columns([3, 2])
        with btn_exec_orig:
            exec_original = st.button(
                "▶ Execute original", key="exec_original", use_container_width=True
            )
        with btn_save:
            if st.button("📌 Save to Benchmark", key="save_to_bench", use_container_width=True,
                         help="Pin this SPL so you can load it on the Benchmark page"):
                _entry = {
                    "label": st.session_state.get("user_input_saved", "")[:80] or "SPL script",
                    "query": st.session_state.get("user_input_saved", ""),
                    "spl":   original_spl,
                    "ts":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                if "saved_spls" not in st.session_state:
                    st.session_state.saved_spls = []
                # avoid exact duplicates
                if not any(e["spl"] == original_spl for e in st.session_state.saved_spls):
                    st.session_state.saved_spls.append(_entry)
                st.toast("SPL pinned to Benchmark session ✓", icon="📌")

    # Determine which SPL to run and whether a button was clicked
    spl_to_run: str | None = None
    run_label = ""
    if exec_original:
        spl_to_run = original_spl
        run_label  = "original"
    elif exec_edited:
        spl_to_run = edited_spl or original_spl
        run_label  = "edited"

    if SPL_AVAILABLE and spl_explain is not None:
        with st.expander("Execution Plan — EXPLAIN (token budget & cost estimate)"):
            try:
                plan_text = spl_explain(spl_to_run or original_spl)
                st.text(plan_text)
            except Exception as ex:
                st.caption(f"Could not generate EXPLAIN plan: {ex}")

    execute_clicked = spl_to_run is not None

    if execute_clicked:
        with st.spinner(f"Executing {run_label} SPL (may call multiple LLMs in parallel)..."):
            exec_result = api.exec_spl(
                spl_to_run or "",
                adapter=adapter,
                spl_params=spl_params,
                cache_enabled=cache_enabled,
                provider=provider,
            )
        st.session_state.flow_state = exec_result
        st.session_state.execution_results = exec_result.get("execution_results", [])
        st.session_state.executed = True
        if exec_result.get("error"):
            st.error(f"Execution error: {exec_result['error']}")
        else:
            _primary = exec_result.get("primary_result", "")
            _results = exec_result.get("execution_results", [])
            _final   = _results[-1] if _results else {}
            if _primary:
                try:
                    save_session(
                        original_query   = st.session_state.get("user_input_saved", ""),
                        generated_spl    = original_spl,
                        edited_spl       = edited_spl if edited_spl != original_spl else "",
                        result_markdown  = _primary,
                        model            = _final.get("model", ""),
                        total_tokens     = _final.get("total_tokens", 0),
                        latency_ms       = _final.get("latency_ms", 0.0),
                        cost_usd         = _final.get("cost_usd"),
                    )
                    st.toast("Request saved to database ✓", icon="💾")
                except Exception:
                    pass  # never break the UI on a DB write failure

# ── STEP 3: Result ────────────────────────────────────────────────────────────
if st.session_state.executed:
    st.divider()
    st.subheader("Step 3 — Result")

    flow_state = st.session_state.flow_state
    results    = st.session_state.execution_results
    error      = flow_state.get("error", "")

    if error:
        st.error(error)
    else:
        primary = flow_state.get("primary_result", "")
        final   = results[-1] if results else {}

        col_result, _col_gap, col_metrics = st.columns([15, 1, 3])

        with col_result:
            if primary:
                st.markdown(primary)
            else:
                st.info("No result content was returned.")

            if len(results) > 1:
                with st.expander(f"CTE Sub-Results ({len(results) - 1} intermediate)"):
                    for r in results[:-1]:
                        st.markdown(f"**{r['prompt_name']}** — model: `{r['model']}`")
                        preview = r["content"]
                        if len(preview) > 600:
                            preview = preview[:600] + "..."
                        st.text(preview)
                        c1, c2, c3 = st.columns(3)
                        c1.caption(f"Tokens: {r.get('total_tokens', 0):,}")
                        c2.caption(f"Latency: {r.get('latency_ms', 0) / 1000:.1f}s")
                        _rc = r.get("cost_usd")
                        c3.caption(f"Cost: ${_rc:.5f}" if _rc is not None else "Cost: —")
                        st.divider()

        with col_metrics:
            if final:
                _cost = final.get("cost_usd")
                st.metric("Model",   final.get("model", "—"))
                st.metric("Tokens",  f"{final.get('total_tokens', 0):,}")
                st.metric("Latency", f"{final.get('latency_ms', 0) / 1000:.1f}s")
                st.metric("Cost",    f"${_cost:.5f}" if _cost is not None else "—")

            if primary:
                st.write("")  # small gap between metrics and download button
                _ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                _result_filename = f"splflow-{_ts}.md"
                _cost_str = f"${_cost:.5f}" if (_cost := final.get("cost_usd")) is not None else "—"
                _dl_content = (
                    f"# SPL-Flow Result\n\n"
                    f"**Query:** {st.session_state.get('user_input_saved', '')}\n\n"
                    f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"---\n\n"
                    f"## Metrics\n\n"
                    f"| Metric | Value |\n"
                    f"|--------|-------|\n"
                    f"| Model   | {final.get('model', '—')} |\n"
                    f"| Tokens  | {final.get('total_tokens', 0):,} |\n"
                    f"| Latency | {final.get('latency_ms', 0) / 1000:.1f}s |\n"
                    f"| Cost    | {_cost_str} |\n\n"
                    f"---\n\n"
                    f"## Result\n\n"
                    f"{primary}\n"
                )
                st.download_button(
                    label="⬇ Download Result",
                    data=_dl_content,
                    file_name=_result_filename,
                    mime="text/markdown",
                    type="primary",
                    use_container_width=True,
                )

render_footer()
