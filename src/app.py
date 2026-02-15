"""SPL-Flow Streamlit UI — main entry point.

Run:
    cd /home/papagame/projects/digital-duck/SPL-Flow
    streamlit run src/app.py
"""
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")

import streamlit as st

from src.flows.spl_flow import generate_spl_only, run_spl_flow

try:
    from spl import explain as spl_explain
    SPL_AVAILABLE = True
except ImportError:
    SPL_AVAILABLE = False

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SPL-Flow",
    page_icon="⚡",
    layout="wide",
)

# ── Session state ─────────────────────────────────────────────────────────────
defaults = {
    "spl_generated": False,
    "spl_query": "",
    "execution_results": [],
    "flow_state": {},
    "executed": False,
    "user_input_saved": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Header ────────────────────────────────────────────────────────────────────
st.title("⚡ SPL-Flow")
st.caption("Declarative LLM Orchestration — MVP Prototype")
st.markdown(
    "Translate any natural language query into "
    "[SPL](https://github.com/digital-duck/SPL) (Structured Prompt Language), "
    "auto-route sub-tasks to specialist models, and receive a composed result."
)
st.divider()

# ── Sidebar ───────────────────────────────────────────────────────────────────
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

    st.divider()

    mode_label = st.radio(
        "Delivery Mode",
        options=["Sync — view result here", "Async — download + email"],
        index=0,
    )
    delivery_mode = "sync" if (mode_label or "").startswith("Sync") else "async"

    notify_email = ""
    if delivery_mode == "async":
        notify_email = st.text_input(
            "Notification Email",
            placeholder="you@example.com",
            help="Result saved to file; email delivery configured in v0.2",
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

# Parse sidebar params
spl_params: dict = {}
if params_text.strip() if 'params_text' in dir() else False:
    for line in params_text.strip().splitlines():
        if "=" in line:
            key, _, val = line.partition("=")
            spl_params[key.strip()] = val.strip()
if context_text.strip():
    spl_params["document"] = context_text

# ── STEP 1: Query Input ───────────────────────────────────────────────────────
st.subheader("Step 1: Describe your query")

user_input = st.text_area(
    "What do you want to generate?",
    height=130,
    placeholder=(
        "Examples:\n"
        "• List 10 Chinese characters with water radical — meanings, formulas, German translations\n"
        "• Summarize this article in 3 bullet points\n"
        "• Review this Python function for bugs, performance, and style\n"
        "• Compare quantum computing and classical computing in a markdown table"
    ),
    key="user_input_area",
)

col_gen, col_reset = st.columns([3, 7])
with col_gen:
    generate_clicked = st.button("Generate SPL", type="primary", use_container_width=True)
with col_reset:
    if st.button("Reset", use_container_width=False):
        for k, v in defaults.items():
            st.session_state[k] = v
        st.rerun()

if generate_clicked:
    if not user_input.strip():
        st.warning("Please enter a query before generating SPL.")
    else:
        with st.spinner("Translating to SPL (Text2SPL pipeline)..."):
            result = generate_spl_only(
                user_input=user_input,
                context_text=context_text,
            )
        if result.get("error"):
            st.error(f"SPL generation failed: {result['error']}")
        elif result.get("spl_query"):
            st.session_state.spl_query = result["spl_query"]
            st.session_state.spl_generated = True
            st.session_state.flow_state = result
            st.session_state.executed = False
            st.session_state.execution_results = []
            st.session_state.user_input_saved = user_input
        else:
            st.warning("No SPL was generated — try rephrasing your query.")

# ── STEP 2: SPL Preview ───────────────────────────────────────────────────────
if st.session_state.spl_generated and st.session_state.spl_query:
    st.divider()
    st.subheader("Step 2: Review & edit SPL")

    warnings = st.session_state.flow_state.get("spl_warnings", [])
    for w in warnings:
        st.warning(f"Warning: {w}")

    # Syntax-highlighted read-only view
    st.code(st.session_state.spl_query, language="sql")

    # Editable version
    edited_spl = st.text_area(
        "Edit SPL (optional — changes take effect on Execute)",
        value=st.session_state.spl_query,
        height=280,
        key="spl_editor",
    )
    if (edited_spl or "").strip() != st.session_state.spl_query.strip():
        st.session_state.spl_query = edited_spl

    # EXPLAIN plan in expander
    if SPL_AVAILABLE:
        with st.expander("Execution Plan — EXPLAIN (token budget & cost estimate)"):
            try:
                plan_text = spl_explain(st.session_state.spl_query or "")
                st.text(plan_text)
            except Exception as ex:
                st.caption(f"Could not generate EXPLAIN plan: {ex}")

    # Execute button
    execute_clicked = st.button("Execute", type="primary")

    if execute_clicked:
        with st.spinner("Executing SPL pipeline (may call multiple LLMs)..."):
            exec_result = run_spl_flow(
                user_input=st.session_state.user_input_saved or user_input,
                context_text=context_text,
                adapter=adapter,
                delivery_mode=delivery_mode,
                notify_email=notify_email,
                spl_params=spl_params,
                cache_enabled=cache_enabled,
            )
        st.session_state.flow_state = exec_result
        st.session_state.execution_results = exec_result.get("execution_results", [])
        st.session_state.executed = True
        if exec_result.get("error"):
            st.error(f"Execution error: {exec_result['error']}")

# ── STEP 3: Result ────────────────────────────────────────────────────────────
if st.session_state.executed:
    st.divider()
    st.subheader("Step 3: Result")

    flow_state = st.session_state.flow_state
    results = st.session_state.execution_results
    error = flow_state.get("error", "")

    if error:
        st.error(error)

    elif delivery_mode == "sync":
        primary = flow_state.get("primary_result", "")
        if primary:
            st.markdown(primary)
        else:
            st.info("No result content was returned.")

        # Execution metadata
        if results:
            final = results[-1]
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Model", final.get("model", "—"))
            col2.metric("Tokens", f"{final.get('total_tokens', 0):,}")
            col3.metric("Latency", f"{final.get('latency_ms', 0) / 1000:.1f}s")
            cost = final.get("cost_usd")
            col4.metric("Cost", f"${cost:.5f}" if cost is not None else "—")

        # CTE / intermediate sub-results
        if len(results) > 1:
            with st.expander(f"CTE Sub-Results ({len(results) - 1} intermediate)"):
                for r in results[:-1]:
                    st.markdown(f"**{r['prompt_name']}** — model: `{r['model']}`")
                    content_preview = r["content"]
                    if len(content_preview) > 600:
                        content_preview = content_preview[:600] + "..."
                    st.text(content_preview)
                    c1, c2, c3 = st.columns(3)
                    c1.caption(f"Tokens: {r.get('total_tokens', 0):,}")
                    c2.caption(f"Latency: {r.get('latency_ms', 0) / 1000:.1f}s")
                    cost = r.get("cost_usd")
                    c3.caption(f"Cost: ${cost:.5f}" if cost is not None else "Cost: —")
                    st.divider()

        # Download button
        primary = flow_state.get("primary_result", "")
        if primary:
            st.download_button(
                label="Download Result (Markdown)",
                data=primary,
                file_name="spl_flow_result.md",
                mime="text/markdown",
            )

    elif delivery_mode == "async":
        output_file = flow_state.get("output_file", "")
        email_sent = flow_state.get("email_sent", False)

        if output_file:
            try:
                with open(output_file, encoding="utf-8") as f:
                    file_content = f.read()
                st.download_button(
                    label="Download Result (Markdown)",
                    data=file_content,
                    file_name="spl_flow_result.md",
                    mime="text/markdown",
                )
                st.success(f"Result saved: `{output_file}`")
            except Exception as ex:
                st.warning(f"Could not read output file: {ex}")

        if email_sent and notify_email:
            st.info(f"Email notification sent to: {notify_email}")
        elif notify_email and not email_sent:
            st.warning("Email delivery not yet configured (SMTP integration in v0.2).")

        primary = flow_state.get("primary_result", "")
        if primary:
            with st.expander("Result Preview"):
                st.markdown(primary)

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "**SPL-Flow MVP** — Built on [SPL engine](https://github.com/digital-duck/SPL) "
    "with [PocketFlow](https://github.com/The-Pocket/PocketFlow) orchestration | "
    "Apache 2.0 | human×AI"
)
