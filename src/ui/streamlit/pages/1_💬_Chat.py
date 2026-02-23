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
from src.utils.page_helpers import init_pipeline_state, render_footer, render_sidebar, reset_pipeline_state, strip_think_blocks

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
    # ── Core Examples ──────────────────────────────────────────────────────────
    (
        "Hello world in 3 languages",
        """Write a "Hello, world!" program in Python, JavaScript, and Go. For each language, explain the syntax and structure of the code.""",
    ),
    (
        "Chinese water-radical characters",
        """List 10 Chinese characters that contain the water radical —
show decomposition formula, pinyin, English meaning, and German translation""",
    ),
    (
        "用中文解释 LLM",
        """用中文解释大型语言模型的工作原理，从参数知识、上下文知识和推理能力三个维度分析，
并对比GPT、Claude 和开源模型（如 Qwen ）的主要异同。""",
    ),
    (
        "Islamic Golden Age",
        """ما هي أبرز إسهامات العلماء العرب في تطوير علم الرياضيات والفلك خلال العصر الذهبي الإسلامي،
وكيف أثّرت هذه الإسهامات على العلوم الحديثة؟""",
    ),
    # (
    #     "Quantum vs classical computing",
    #     "Compare quantum computing and classical computing in a structured "
    #     "markdown table with dimensions: speed, error rate, use cases, maturity",
    # ),

    # ── Advanced Multi-Model Examples ───────────────────────────────────────────
    (
        "Multi-model research synthesis",
        """Research the recent breakthroughs in protein folding prediction (AlphaFold series).
Use one model for technical analysis, another for medical applications, and a third
for explaining implications to non-scientists. Synthesize into a comprehensive report
with timeline, key innovations, future directions, and societal impact.""",
    ),
    (
        "API documentation",
        """Create comprehensive API documentation for a machine learning library like pytorch. Generate
examples in Python. Include installation guides, authentication
setup, rate limiting considerations, error handling patterns, and performance optimization
tips. Format as interactive documentation with code snippets and expected outputs.""",
    ),
    (
        "Historical linguistics analysis",
        """Trace the etymological evolution of mathematical terms across cultures: analyze how
concepts like 'algebra' (Arabic al-jabr), 'algorithm' (Persian al-Khwarizmi), and
'zero' (Sanskrit śūnya) traveled through languages. Create a timeline showing linguistic
borrowing, semantic shifts, and cultural knowledge transfer patterns.""",
    ),
    (
        "Nobel Prize winners' papers (Benchmark)",
        """List most recent 2 papers published by each nobel prize winner in physics,
field medal winner in math, and turing prize winner in computer science
in past 5 years""",
    ),

    # ── SPL-Flow Architecture Showcase ──────────────────────────────────────────
    (
        "Enterprise Architecture Review",
        """Analyze a microservices architecture for security vulnerabilities, performance
bottlenecks, and cost optimization. Use specialist models for: (1) Security analysis
of authentication flows and data patterns, (2) Performance review of database queries
and API endpoints, (3) Cost analysis of cloud resource utilization. Generate executive
summary with prioritized recommendations and implementation roadmap.""",
    ),
    (
        "Scientific Literature Meta-Analysis",
        """Conduct a systematic review of climate change mitigation strategies published
in 2023-2024. Use domain specialists for: (1) Technology analysis (renewable energy,
carbon capture), (2) Policy evaluation (international agreements, regulations),
(3) Economic impact assessment (costs, market trends). Synthesize into comprehensive
meta-analysis with evidence quality ratings and actionable insights.""",
    ),
    (
        "AI Ethics Impact Assessment",
        """Evaluate the ethical implications of deploying autonomous vehicles in urban areas.
Use specialized analysis for: (1) Technical safety assessment (ML model reliability,
edge cases), (2) Legal framework analysis (liability, regulation compliance),
(3) Social impact evaluation (employment, accessibility, privacy). Create balanced
ethical framework with implementation guidelines.""",
    ),
    (
        "Global Market Intelligence Report",
        """Generate comprehensive market analysis for quantum computing commercialization
across regions. Deploy specialists for: (1) Technology readiness assessment (hardware,
software, algorithms), (2) Competitive landscape mapping (key players, partnerships),
(3) Investment and funding analysis (VC trends, government initiatives). Deliver strategic
recommendations with 3-year market projections.""",
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

adapter            = settings["adapter"]
selected_provider  = settings["provider"]          # "" = auto-route
context_text       = settings["context_text"]
cache_enabled      = settings["cache_enabled"]
spl_params         = settings["spl_params"]
selected_model_id  = settings["selected_model_id"]
strip_think        = settings["strip_think"]

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
st.caption("**Formalized Prompt Engineering**: SPL-Flow translates free-form queries → systematic decomposition → specialist model orchestration")
# st.divider()

# ── Fragment functions for each step ─────────────────────────────────────────

@st.fragment  # Commented out for troubleshooting
def step_1_query_input():
    """Step 1: Query input and SPL generation (fragment)"""
    st.subheader("Step 1 — Describe your query")

    col_input, _, col_samples_core, col_samples_advanced, col_samples_showcase = st.columns([7, 0.2, 3, 3, 3])

    with col_input:
        user_input = st.text_area(
            "What do you want to generate?",
            height=200,
            placeholder=(
                "Describe your query in plain English.\n"
                "SPL-Flow formalizes prompt engineering by:\n"
                "• Translating free-form queries → structured SPL scripts\n"
                "• Breaking complex tasks → manageable CTE pipelines\n"
                "• Orchestrating specialist models → optimal efficiency\n"
                "• Managing token budgets → solving context limitations\n\n"
                "Try the sample queries to see systematic decomposition →"
            ),
            key="user_input_area",
        )

        btn_col, reset_col = st.columns([2, 1])
        with btn_col:
            generate_clicked = st.button("Generate SPL", type="primary", use_container_width=True)
        with reset_col:
            if st.button("Reset", use_container_width=True):
                reset_pipeline_state()
                st.rerun()

    with col_samples_core:
        st.caption("**🎯 Core Examples**:")
        # Display first 4 samples (core examples)
        for label, query in _SAMPLE_QUERIES[:4]:
            if st.button(label, key=f"sample_{label}", use_container_width=True):
                st.session_state["_sample_pending"] = query
                st.rerun()

    with col_samples_advanced:
        st.caption("**🚀 Multi-Model Examples**:")
        # Display next 4 samples (advanced multi-model examples)
        for label, query in _SAMPLE_QUERIES[4:8]:
            if st.button(label, key=f"sample_{label}", use_container_width=True):
                st.session_state["_sample_pending"] = query
                st.rerun()

    with col_samples_showcase:
        st.caption("**⚡ SPL-Flow Showcase**:")
        # Display last 4 samples (architecture showcase examples)
        for label, query in _SAMPLE_QUERIES[8:12]:
            if st.button(label, key=f"sample_{label}", use_container_width=True):
                st.session_state["_sample_pending"] = query
                st.rerun()

    if generate_clicked:
        if not user_input.strip():
            st.warning("Please enter a query before generating SPL.")
        else:
            with st.spinner("Translating to SPL (Text2SPL + RAG retrieval)..."):
                result = api.generate(
                    user_input,
                    context_text=context_text,
                    adapter=adapter,
                    selected_model_id=selected_model_id,
                    selected_provider=selected_provider
                )
            if result["error"]:
                st.error(f"SPL generation failed: {result['error']}")
            elif result["spl_query"]:
                st.session_state.spl_query = result["spl_query"]
                # Force both panels to show the newly generated SPL.
                # st.text_area ignores value= once its key exists in session_state,
                # so we overwrite both keys directly before the widgets render.
                st.session_state.spl_editor = result["spl_query"]
                st.session_state.spl_view   = result["spl_query"]
                st.session_state.spl_generated = True
                st.session_state.flow_state = result
                st.session_state.executed = False
                st.session_state.execution_results = []
                st.session_state.user_input_saved = user_input
                if result["retry_count"] > 1:
                    st.info(f"Generated after {result['retry_count']} attempt(s).")
                # Force all fragments to re-render with the new SPL
                st.rerun()
            else:
                st.warning("No SPL was generated — try rephrasing your query.")

# ── STEP 1: Query Input (Fragment) ────────────────────────────────────────────
step_1_query_input()

@st.fragment  # Commented out for troubleshooting
def step_2_spl_review():
    """Step 2: SPL preview & edit with execution (fragment)"""
    # Always render the section, but show conditional content
    if not (st.session_state.get("spl_generated", False) and st.session_state.get("spl_query", "")):
        return

    # st.divider()
    st.subheader("Step 2 — Review & edit SPL")

    for w in st.session_state.flow_state.get("spl_warnings", []):
        st.warning(f"Warning: {w}")

    original_spl = st.session_state.spl_query or ""

    col_edit, _, col_tools = st.columns([4, 0.1, 2])

    with col_edit:
        # st.caption("Edit SPL — run your version (edits apply immediately on Execute)")
        edited_spl = st.text_area(
            "Edit SPL",
            height=280,
            label_visibility="collapsed",
            key="spl_editor",
        )

        # Four buttons in a row under the text area
        btn1, btn2, btn3, btn4 = st.columns(4)
        with btn1:
            exec_edited = st.button(
                "▶ Execute", key="exec_edited",
                type="primary", use_container_width=True,
            )
        with btn2:
            clear_result = st.button(
                "🗑️ Clear Result", key="clear_result",
                use_container_width=True,
                help="Clear the current Step 3 results"
            )
        with btn3:
            # Sanitize adapter and model names for filename
            _safe_adapter = adapter.replace("/", "-").replace(":", "-").replace(" ", "-")
            _safe_model = selected_model_id.replace("/", "-").replace(":", "-").replace(" ", "-") if selected_model_id else "auto"
            _ts = datetime.now().strftime('%Y%m%d-%H%M%S')
            _spl_filename = f"spl-{_safe_adapter}-{_safe_model}-{_ts}.spl"
            st.download_button(
                "⬇ Download SPL",
                data=edited_spl or original_spl,
                file_name=_spl_filename,
                mime="text/plain",
                use_container_width=True,
            )
        with btn4:
            if st.button("📌 Save to Benchmark", key="save_to_bench", use_container_width=True,
                         help="Pin this SPL so you can load it on the Benchmark page"):
                _entry = {
                    "label": st.session_state.get("user_input_saved", "")[:80] or "SPL script",
                    "query": st.session_state.get("user_input_saved", ""),
                    "spl":   edited_spl or original_spl,
                    "ts":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                if "saved_spls" not in st.session_state:
                    st.session_state.saved_spls = []
                # avoid exact duplicates
                if not any(e["spl"] == (edited_spl or original_spl) for e in st.session_state.saved_spls):
                    st.session_state.saved_spls.append(_entry)
                st.toast("SPL pinned to Benchmark session ✓", icon="📌")

        # Handle Clear Result button
        if clear_result:
            st.session_state.executed = False
            st.session_state.execution_results = []
            st.session_state.flow_state = {}
            st.toast("Results cleared ✓", icon="🗑️")
            st.rerun()

    with col_tools:
        # Execution Plan in the right column
        if SPL_AVAILABLE and spl_explain is not None:
            with st.expander("Execution Plan — EXPLAIN", expanded=True):
                try:
                    plan_text = spl_explain(edited_spl or original_spl)
                    st.text(plan_text)
                except Exception as ex:
                    st.caption(f"Could not generate EXPLAIN plan: {ex}")

        # # Execute original button
        # st.write("")  # Small gap
        # exec_original = st.button(
        #     "▶ Execute original", key="exec_original",
        #     use_container_width=True, help="Run the original generated SPL"
        # )

    # Determine which SPL to run and whether a button was clicked
    spl_to_run: str | None = None
    run_label = ""
    # if exec_original:
    #     spl_to_run = original_spl
    #     run_label  = "original"
    if exec_edited:
        spl_to_run = edited_spl or original_spl
        run_label  = "edited"

    execute_clicked = spl_to_run is not None

    if execute_clicked:
        with st.spinner(f"Executing {run_label} SPL (may call multiple LLMs in parallel)..."):
            exec_result = api.exec_spl(
                spl_to_run or "",
                adapter=adapter,
                spl_params=spl_params,
                cache_enabled=cache_enabled,
                provider=selected_provider,
            )
        st.session_state.flow_state = exec_result
        st.session_state.execution_results = exec_result.get("execution_results", [])
        st.session_state.executed = True
        if exec_result.get("error"):
            st.error(f"Execution error: {exec_result['error']}")
            st.rerun()  # Force UI update to show error
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
            # Force UI update to show Step 3 results immediately
            st.rerun()

# ── STEP 2: SPL Preview & Edit (Fragment) ─────────────────────────────────────
step_2_spl_review()

@st.fragment  # Commented out for troubleshooting
def step_3_result_display():
    """Step 3: Result display (fragment)"""
    if not st.session_state.get("executed", False):
        return

    # st.divider()
    st.subheader("Step 3 — Result")

    flow_state = st.session_state.flow_state
    results    = st.session_state.execution_results
    error      = flow_state.get("error", "")

    if error:
        st.error(error)
    else:
        primary = flow_state.get("primary_result", "")
        final   = results[-1] if results else {}

        col_result, _, col_metrics = st.columns([15, 0.5, 3])

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
                            preview = preview[:600] + "..."
                        st.text(preview)
                        c1, c2, c3 = st.columns(3)
                        c1.caption(f"Tokens: {r.get('total_tokens', 0):,}")
                        c2.caption(f"Latency: {r.get('latency_ms', 0) / 1000:.1f}s")
                        _rc = r.get("cost_usd")
                        c3.caption(f"Cost: ${_rc:.5f}" if _rc is not None else "Cost: —")
                        # st.divider()

        with col_metrics:
            if final:
                _cost = final.get("cost_usd")
                st.metric("Adapter", adapter.title())
                st.metric("Model",   final.get("model", "—"))
                st.metric("Tokens",  f"{final.get('total_tokens', 0):,}")
                st.metric("Latency", f"{final.get('latency_ms', 0) / 1000:.1f}s")
                st.metric("Cost",    f"${_cost:.5f}" if _cost is not None else "—")

            if primary:
                st.write("")  # small gap between metrics and download button
                # Sanitize adapter and model names for filename
                _safe_adapter = adapter.replace("/", "-").replace(":", "-").replace(" ", "-")
                _actual_model = final.get("model", selected_model_id or "auto")
                _safe_model = _actual_model.replace("/", "-").replace(":", "-").replace(" ", "-")
                _ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                _result_filename = f"splflow-{_safe_adapter}-{_safe_model}-{_ts}.md"
                _cost_str = f"${_cost:.5f}" if (_cost := final.get("cost_usd")) is not None else "—"
                _dl_content = (
                    f"# SPL-Flow Result\n\n"
                    f"**Query:** {st.session_state.get('user_input_saved', '')}\n\n"
                    f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"**Adapter:** {adapter}\n\n"
                    f"**Provider:** {selected_provider or 'auto'}\n\n"
                    f"---\n\n"
                    f"## Metrics\n\n"
                    f"| Metric | Value |\n"
                    f"|--------|-------|\n"
                    f"| Adapter | {adapter} |\n"
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

# ── STEP 3: Result Display (Fragment) ─────────────────────────────────────────
step_3_result_display()

render_footer()
