"""SPL-Flow — Run page.

Paste or upload a .spl script and execute it directly.
No NL→SPL generation step — useful for pre-written scripts,
experiments, and direct SPL testing.
"""
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-flow")

from datetime import datetime

import streamlit as st

st.set_page_config(
    page_title="SPL-Flow · Run",
    page_icon="⚡",
    layout="wide",
)

from src import api
from src.utils.page_helpers import render_sidebar, render_footer, strip_think_blocks

spl_explain = None
try:
    from spl import explain as spl_explain
    SPL_AVAILABLE = True
except ImportError:
    SPL_AVAILABLE = False

# ── Session state ──────────────────────────────────────────────────────────────

for _k, _v in [("run_executed", False), ("run_result", {})]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

# File-upload: move pending content into the text-area key before the widget
# is instantiated (same pattern as Chat page's sample queries).
if "_run_spl_pending" in st.session_state:
    st.session_state.run_spl_input = st.session_state.pop("_run_spl_pending")

# ── Sidebar ────────────────────────────────────────────────────────────────────

settings      = render_sidebar()
adapter       = settings["adapter"]
provider      = settings["provider"]
cache_enabled = settings["cache_enabled"]
spl_params    = settings["spl_params"]
strip_think   = settings["strip_think"]

# ── Header ─────────────────────────────────────────────────────────────────────

st.title("▶ Run")
st.caption(
    "Paste or upload a `.spl` script and execute it directly — "
    "adapter and params are taken from the sidebar."
)
st.divider()

# ── File upload ────────────────────────────────────────────────────────────────

uploaded = st.file_uploader(
    "Upload a .spl file (optional — or just paste below)",
    type=["spl", "txt"],
    label_visibility="visible",
)
if uploaded is not None and uploaded.name != st.session_state.get("_run_last_upload"):
    st.session_state["_run_last_upload"] = uploaded.name
    st.session_state["_run_spl_pending"] = uploaded.read().decode("utf-8", errors="replace")
    st.rerun()

# ── SPL editor ─────────────────────────────────────────────────────────────────

spl_input: str = st.text_area(
    "SPL Script",
    height=320,
    placeholder=(
        "Paste your .spl script here, e.g.:\n\n"
        "PROMPT my_query\n"
        "WITH BUDGET 4000 tokens\n"
        'USING MODEL "claude-sonnet-4-5"\n\n'
        "SELECT\n"
        '    system_role("You are an expert.")\n\n'
        "GENERATE\n"
        '    answer("Your question here")\n'
        "WITH OUTPUT BUDGET 2000 tokens, FORMAT markdown;"
    ),
    label_visibility="collapsed",
    key="run_spl_input",
)

# ── Action buttons ─────────────────────────────────────────────────────────────

has_script = bool((spl_input or "").strip())

btn_exec, btn_clear, btn_dl, _ = st.columns([2, 1, 1, 4])

with btn_exec:
    execute_clicked = st.button(
        "▶ Execute",
        type="primary",
        use_container_width=True,
        disabled=not has_script,
    )

with btn_clear:
    if st.button("Clear", use_container_width=True):
        st.session_state.run_spl_input  = ""
        st.session_state.run_executed   = False
        st.session_state.run_result     = {}
        st.session_state.pop("_run_last_upload", None)
        st.rerun()

with btn_dl:
    _ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    st.download_button(
        "⬇ .spl",
        data=spl_input or "",
        file_name=f"script-{_ts}.spl",
        mime="text/plain",
        use_container_width=True,
        disabled=not has_script,
    )

# ── EXPLAIN plan ───────────────────────────────────────────────────────────────

if SPL_AVAILABLE and spl_explain and has_script:
    with st.expander("Execution Plan — EXPLAIN (token budget & cost estimate)"):
        try:
            st.text(spl_explain(spl_input))
        except Exception as ex:
            st.caption(f"Could not generate EXPLAIN plan: {ex}")

# ── Execute ────────────────────────────────────────────────────────────────────

if execute_clicked:
    with st.spinner("Executing SPL (may call multiple LLMs in parallel)…"):
        result = api.exec_spl(
            spl_input,
            adapter=adapter,
            spl_params=spl_params,
            cache_enabled=cache_enabled,
            provider=provider,
        )
    st.session_state.run_result   = result
    st.session_state.run_executed = True

# ── Result ─────────────────────────────────────────────────────────────────────

if st.session_state.run_executed:
    st.divider()

    result  = st.session_state.run_result
    error   = result.get("error", "")
    results = result.get("execution_results", [])
    primary = result.get("primary_result", "")
    final   = results[-1] if results else {}

    if error:
        st.error(f"Execution error: {error}")
    else:
        col_result, _gap, col_metrics = st.columns([15, 1, 3])

        with col_result:
            if primary:
                st.markdown(strip_think_blocks(primary) if strip_think else primary)
            else:
                st.info("No result content was returned.")

            if len(results) > 1:
                with st.expander(f"CTE Sub-Results ({len(results) - 1} intermediate)"):
                    for r in results[:-1]:
                        st.markdown(f"**{r['prompt_name']}** — model: `{r['model']}`")
                        preview = r["content"]
                        if strip_think:
                            preview = strip_think_blocks(preview)
                        if len(preview) > 600:
                            preview = preview[:600] + "…"
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
                st.write("")
                _ts2   = datetime.now().strftime("%Y%m%d-%H%M%S")
                _cost2 = final.get("cost_usd")
                _cost_str = f"${_cost2:.5f}" if _cost2 is not None else "—"
                _dl_content = (
                    f"# SPL-Flow Result\n\n"
                    f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"---\n\n"
                    f"## Metrics\n\n"
                    f"| Metric  | Value |\n"
                    f"|---------|-------|\n"
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
                    file_name=f"splflow-{_ts2}.md",
                    mime="text/markdown",
                    type="primary",
                    use_container_width=True,
                )

render_footer()
