"""SPL-Flow — Benchmark page.

Run one SPL script against multiple models in parallel and compare results
side-by-side.  Real measurements, not estimates:

  • Response quality  — compare outputs directly, mark your winner
  • Token cost        — input + output + total per model
  • Latency           — wall-clock ms per model (all run concurrently)
  • Cost USD          — per-model and aggregate

The USING MODELS loop:  every entry in the model list receives an identical
patched copy of the script with its USING MODEL clause replaced.  "auto"
is a valid entry — the model router resolves it at execution time, letting
you compare your explicit choices against the router's recommendation.
"""
import sys
import json

sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")

import streamlit as st

st.set_page_config(
    page_title="SPL-Flow · Benchmark",
    page_icon="📊",
    layout="wide",
)

from src import api
from src.utils.page_helpers import render_sidebar
from src.utils.model_router import ROUTING_TABLE

# ── Sidebar ───────────────────────────────────────────────────────────────────
settings = render_sidebar()
adapter      = settings["adapter"]
provider     = settings["provider"]
cache_enabled = settings["cache_enabled"]
spl_params   = settings["spl_params"]

# ── Header ────────────────────────────────────────────────────────────────────
st.title("📊 Benchmark")
st.caption(
    "Run one SPL script against multiple models in parallel. "
    "Compare responses, tokens, latency, and cost — "
    "real measurements from live LLM calls."
)
st.divider()

# ── Step 1: SPL Input ─────────────────────────────────────────────────────────
st.subheader("Step 1 — SPL script")

input_mode = st.radio(
    "Input mode",
    ["Inline SPL", "Load .spl file"],
    horizontal=True,
    label_visibility="collapsed",
)

spl_query = ""

if input_mode == "Inline SPL":
    spl_query = st.text_area(
        "SPL query",
        height=200,
        placeholder=(
            "PROMPT analysis\n"
            "SELECT\n"
            "    system_role('You are a helpful expert.'),\n"
            "    GENERATE('Explain quantum entanglement in 2 sentences.')\n"
            "USING MODEL auto;"
        ),
        key="bench_spl_input",
    )
else:
    uploaded = st.file_uploader("Upload .spl file", type=["spl", "sql", "txt"])
    if uploaded:
        spl_query = uploaded.read().decode("utf-8")
        st.code(spl_query, language="sql")

st.divider()

# ── Step 2: Model selection ───────────────────────────────────────────────────
st.subheader("Step 2 — Models to benchmark")

# Build suggested model list from ROUTING_TABLE (unique values) + auto
_suggested: list[str] = ["auto"]
_seen: set = set()
for _task_routes in ROUTING_TABLE.values():
    for _key in ("openrouter", "ollama", "claude_cli"):
        _m = _task_routes.get(_key, "")
        if _m and _m not in _seen:
            _suggested.append(_m)
            _seen.add(_m)

col_select, col_custom = st.columns([3, 2])

with col_select:
    selected_models = st.multiselect(
        "Select from Model Zoo",
        options=_suggested,
        default=["auto"],
        help=(
            "'auto' lets the model router choose the best model for the task. "
            "Combine explicit models with 'auto' to validate the router's recommendation."
        ),
    )

with col_custom:
    custom_model = st.text_input(
        "Add custom model ID",
        placeholder="e.g. mistralai/mistral-large-2411",
        help="Any model ID supported by the selected adapter",
    )
    if custom_model.strip() and custom_model.strip() not in selected_models:
        if st.button("Add", key="add_custom_model"):
            selected_models = selected_models + [custom_model.strip()]

model_list = selected_models or ["auto"]

if model_list:
    st.caption(f"Will run **{len(model_list)}** model(s): " + " · ".join(
        f"`{m}`" for m in model_list
    ))

st.divider()

# ── Run ───────────────────────────────────────────────────────────────────────
run_clicked = st.button(
    f"Run Benchmark ({len(model_list)} model{'s' if len(model_list) != 1 else ''} in parallel)",
    type="primary",
    disabled=not (spl_query or "").strip(),
    use_container_width=True,
)

if run_clicked:
    if not (spl_query or "").strip():
        st.warning("Please enter an SPL query in Step 1.")
    elif not model_list:
        st.warning("Please select at least one model in Step 2.")
    else:
        with st.spinner(
            f"Running benchmark — {len(model_list)} model(s) executing in parallel…"
        ):
            bench_result = api.benchmark(
                spl_query.strip(),
                models=model_list,
                adapter=adapter,
                provider=provider,
                spl_params=spl_params,
                cache_enabled=cache_enabled,
            )
        st.session_state["bench_result"] = bench_result
        st.session_state["bench_winner"] = None

# ── Results ───────────────────────────────────────────────────────────────────
if "bench_result" in st.session_state and st.session_state["bench_result"]:
    result = st.session_state["bench_result"]
    st.divider()
    st.subheader("Step 3 — Results")

    top_error = result.get("error", "")
    if top_error:
        st.error(f"Benchmark error: {top_error}")
        st.stop()

    runs = result.get("runs", [])
    if not runs:
        st.warning("No results returned.")
        st.stop()

    # ── Summary metrics table ─────────────────────────────────────────────────
    st.markdown("**Summary**")

    header_cols = st.columns([3, 1, 1, 1, 1])
    header_cols[0].markdown("**Model**")
    header_cols[1].markdown("**Tokens**")
    header_cols[2].markdown("**Latency**")
    header_cols[3].markdown("**Cost**")
    header_cols[4].markdown("**Status**")

    for run in runs:
        cols = st.columns([3, 1, 1, 1, 1])
        label = run["model_id"]
        if run.get("resolved_model"):
            label += f"\n→ `{run['resolved_model']}`"
        run_error = run.get("error", "")
        cols[0].markdown(f"`{label}`")
        if run_error:
            cols[1].markdown("—")
            cols[2].markdown("—")
            cols[3].markdown("—")
            cols[4].markdown("🔴 error")
        else:
            cols[1].markdown(f"{run.get('total_tokens', 0):,}")
            cols[2].markdown(f"{run.get('latency_ms', 0) / 1000:.2f}s")
            cost = run.get("cost_usd")
            cols[3].markdown(f"${cost:.5f}" if cost is not None else "—")
            cols[4].markdown("🟢 ok")

    st.divider()

    # ── Per-model response tabs ───────────────────────────────────────────────
    tab_labels = []
    for run in runs:
        label = run["model_id"]
        if run.get("resolved_model"):
            label = f"{run['model_id']} → {run['resolved_model'][:25]}"
        winner_marker = " 🏆" if st.session_state.get("bench_winner") == run["model_id"] else ""
        tab_labels.append(label + winner_marker)

    tabs = st.tabs(tab_labels)

    for tab, run in zip(tabs, runs):
        with tab:
            run_error = run.get("error", "")
            if run_error:
                st.error(f"This run failed: {run_error}")
                st.code(run.get("input_spl", ""), language="sql")
            else:
                st.markdown(run.get("response", ""))

                # Metrics
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Tokens", f"{run.get('total_tokens', 0):,}")
                m2.metric("Input", f"{run.get('input_tokens', 0):,}")
                m3.metric("Output", f"{run.get('output_tokens', 0):,}")
                lat = run.get("latency_ms", 0)
                m4.metric("Latency", f"{lat / 1000:.2f}s")

                cost = run.get("cost_usd")
                if cost is not None:
                    st.caption(f"Estimated cost: **${cost:.5f}**")

                # Multi-CTE breakdown
                prompt_results = run.get("prompt_results", [])
                if len(prompt_results) > 1:
                    with st.expander(f"CTE breakdown ({len(prompt_results)} prompts)"):
                        for pr in prompt_results:
                            st.markdown(f"**{pr['prompt_name']}** — `{pr['model_id']}`")
                            preview = pr.get("response", "")
                            if len(preview) > 400:
                                preview = preview[:400] + "…"
                            st.text(preview)
                            pc1, pc2, pc3 = st.columns(3)
                            pc1.caption(f"Tokens: {pr.get('total_tokens', 0):,}")
                            pc2.caption(f"Latency: {pr.get('latency_ms', 0) / 1000:.2f}s")
                            pr_cost = pr.get("cost_usd")
                            pc3.caption(f"Cost: ${pr_cost:.5f}" if pr_cost else "Cost: —")
                            st.divider()

                # Patched SPL sent to this model
                with st.expander("Input SPL (patched for this model)"):
                    st.code(run.get("input_spl", ""), language="sql")

                # Mark winner
                is_winner = st.session_state.get("bench_winner") == run["model_id"]
                if is_winner:
                    st.success("🏆 Marked as winner")
                else:
                    if st.button(
                        "Mark as winner",
                        key=f"winner_{run['model_id']}",
                        help="Records this model as your preferred choice for this task",
                    ):
                        st.session_state["bench_winner"] = run["model_id"]
                        # Update the result JSON in session
                        result["winner"] = run["model_id"]
                        st.session_state["bench_result"] = result
                        st.rerun()

    st.divider()

    # ── Download JSON ─────────────────────────────────────────────────────────
    result_json = json.dumps(result, indent=2, ensure_ascii=False)
    st.download_button(
        label="Download full benchmark JSON",
        data=result_json,
        file_name=f"benchmark_{result.get('benchmark_name', 'result')}.json",
        mime="application/json",
    )

    winner = result.get("winner")
    if winner:
        st.info(
            f"Winner marked: **{winner}** — "
            "In a future release, this preference will be saved to the routing store "
            "to personalise `USING MODEL auto` for your domain."
        )

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "**SPL-Flow MVP** — "
    "[SPL engine](https://github.com/digital-duck/SPL) · "
    "[PocketFlow](https://github.com/The-Pocket/PocketFlow) · "
    "Apache 2.0 · human×AI"
)
