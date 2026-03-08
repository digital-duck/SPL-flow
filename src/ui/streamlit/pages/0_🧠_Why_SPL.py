"""SPL-Flow — Why SPL? page.

Demonstrates why SPL-Flow is needed by showcasing a challenging benchmark query
that defeated 7 out of 9 top-tier LLM providers.
"""
import sys
from pathlib import Path
sys.path.insert(0, Path.home() / "projects/digital-duck/SPL")
sys.path.insert(0, Path.home() / "projects/digital-duck/SPL-flow")

import streamlit as st

st.set_page_config(
    page_title="SPL-Flow · Why SPL?",
    page_icon="🧠",
    layout="wide",
)

from src.utils.page_helpers import render_footer, render_sidebar

# ── Page Setup ────────────────────────────────────────────────────────────────
render_sidebar()

st.title("🧠 Why SPL?")
st.caption("See why declarative approaches outperform traditional LLM prompting")
st.divider()

# ── The Challenge ─────────────────────────────────────────────────────────────
st.subheader("🎯 The Challenge That Broke 7 LLMs")

st.markdown("""
We tested **9 top-tier LLM providers** with a complex, multi-constraint query that requires:
- **Factual knowledge** across 3 different academic fields
- **Temporal reasoning** with specific constraints
- **Structured output** with hierarchical organization
- **Research currency** tracking recent publications

**Result**: Only **2 out of 9 providers (22%)** successfully completed the task.
""")

# ── The Benchmark Query ───────────────────────────────────────────────────────
st.subheader("📋 The Benchmark Query")

col_query, col_try = st.columns([3, 1])

with col_query:
    benchmark_query = """List most recent 2 papers published by each nobel prize winner in physics, field medal winner in math, and turing prize winner in computer science in past 5 years"""

    st.code(benchmark_query, language="text")

    st.markdown("""
    **Why this query is difficult:**
    1. **Multi-constraint complexity**: Multiple award types + time constraints + paper counts
    2. **Cross-domain knowledge**: Physics, Mathematics, Computer Science expertise
    3. **Temporal precision**: "Past 5 years" requires current date awareness
    4. **Structured aggregation**: 3-level hierarchy (field → winner → papers)
    5. **Research tracking**: Recent academic publications not always in training data
    """)

with col_try:
    st.markdown("**Try it yourself:**")
    if st.button("🧪 Test with SPL-Flow", type="primary", use_container_width=True):
        # Store the benchmark query and redirect to Chat page
        st.session_state["_sample_pending"] = benchmark_query
        st.switch_page("pages/1_Chat.py")

    st.caption("See how SPL-Flow handles this complex query!")

# ── Results Breakdown ─────────────────────────────────────────────────────────
st.divider()
st.subheader("📊 LLM Provider Results")

# Create tabs for different result views
tab_summary, tab_details, tab_analysis = st.tabs(["📈 Summary", "📋 Details", "🔍 Analysis"])

with tab_summary:
    col_metrics, col_chart = st.columns([1, 2])

    with col_metrics:
        st.metric("Total Providers Tested", "9")
        st.metric("Successful", "2", delta="22%")
        st.metric("Failed", "7", delta="-78%", delta_color="inverse")
        st.metric("Gave Up Without Trying", "1", delta="Perplexity")

    with col_chart:
        # Results data
        results_data = {
            "Provider": ["Claude Opus 4.6", "GLM 5", "ChatGPT", "Gemini", "Grok X", "Qwen", "DeepSeek", "Kimi", "Perplexity"],
            "Status": ["✅ Passed", "✅ Passed", "❌ Failed", "❌ Failed", "❌ Failed", "❌ Failed", "❌ Failed", "❌ Failed", "❌ Gave Up"],
            "Score": [100, 100, 30, 25, 20, 35, 20, 25, 0]
        }

        st.markdown("**Performance Comparison:**")
        for i, provider in enumerate(results_data["Provider"]):
            status = results_data["Status"][i]
            score = results_data["Score"][i]

            if "Passed" in status:
                st.success(f"**{provider}**: {status}")
            elif "Gave Up" in status:
                st.error(f"**{provider}**: {status} (Explicitly admitted defeat)")
            else:
                st.error(f"**{provider}**: {status} (Incomplete/inaccurate)")

with tab_details:
    st.markdown("### 🏆 The Winners")

    col_claude, col_glm = st.columns(2)

    with col_claude:
        st.markdown("#### ✅ Claude Opus 4.6")
        st.markdown("""
        **What they did right:**
        - Comprehensive structured response
        - Covered all three prize categories
        - Organized by year → winner → papers
        - Provided specific paper titles and venues
        - Handled 2021-2025 timeframe correctly
        """)
        if st.button("📄 View Claude Response", key="claude_response"):
            st.info("See actual response in: `/examples/format-cte-join/use-case-top-papers/llm_responses/response-claude-opus46.md`")

    with col_glm:
        st.markdown("#### ✅ GLM 5")
        st.markdown("""
        **What they did right:**
        - Performed actual web searches
        - Provided verifiable URLs for papers
        - Analyzed the challenge methodology
        - Compared approach with other LLMs
        - Self-aware about research rigor needed
        """)
        if st.button("📄 View GLM Response", key="glm_response"):
            st.info("See actual response in: `/examples/format-cte-join/use-case-top-papers/llm_responses/response-glm.md`")

    st.markdown("### 💥 Notable Failures")

    failure_examples = [
        ("Perplexity", "Explicitly gave up", "Stated: 'This request is too broad to answer accurately within a single response'"),
        ("ChatGPT", "Incomplete coverage", "Only covered some categories, mixed up prize types"),
        ("Gemini", "Inadequate response", "Missing key categories, superficial attempt"),
        ("Grok X", "Poor structure", "Disorganized output, incomplete data"),
    ]

    for provider, failure_type, details in failure_examples:
        with st.expander(f"❌ {provider} - {failure_type}"):
            st.markdown(f"**Issue**: {details}")

with tab_analysis:
    st.markdown("### 🔍 What This Benchmark Reveals")

    st.markdown("""
    #### Failure Patterns in Traditional LLM Prompting:

    **1. Scope Overwhelm**
    - Most LLMs struggled with the multi-dimensional constraints
    - Complex queries often lead to incomplete or superficial responses

    **2. Lack of Structured Approach**
    - No systematic way to break down the problem
    - Missing components often went unnoticed

    **3. Verification Challenges**
    - Difficult to validate accuracy of generated results
    - No built-in fact-checking or source verification

    **4. Research Methodology Gap**
    - Most LLMs don't perform actual research
    - Tend to hallucinate rather than admit knowledge gaps
    """)

    st.markdown("### 🚀 How SPL-Flow Would Handle This")

    st.markdown("""
    SPL-Flow's **declarative approach** breaks this complex query into manageable, structured components:
    """)

    spl_example = """-- Conceptual SPL structure for the benchmark query
WITH recent_physics_winners AS (
  PROMPT get_nobel_physics_winners
  WITH BUDGET 2000 tokens
  USING MODEL "claude-sonnet-4-5"
  SELECT winner_name, award_year
  FROM nobel_physics_winners
  WHERE award_year >= 2020
),

recent_math_winners AS (
  PROMPT get_fields_medal_winners
  WITH BUDGET 2000 tokens
  USING MODEL "claude-sonnet-4-5"
  SELECT winner_name, award_year
  FROM fields_medal_winners
  WHERE award_year >= 2020
),

recent_cs_winners AS (
  PROMPT get_turing_award_winners
  WITH BUDGET 2000 tokens
  USING MODEL "claude-sonnet-4-5"
  SELECT winner_name, award_year
  FROM turing_award_winners
  WHERE award_year >= 2020
),

winner_papers AS (
  PROMPT get_recent_papers
  WITH BUDGET 4000 tokens
  USING MODEL "openrouter/anthropic/claude-3.5-sonnet"
  SELECT
    field,
    winner_name,
    paper_title,
    publication_date,
    journal,
    ROW_NUMBER() OVER (
      PARTITION BY winner_name
      ORDER BY publication_date DESC
    ) as paper_rank
  FROM all_winners
  WHERE paper_rank <= 2
)

SELECT
  field,
  winner_name,
  paper_title,
  publication_date,
  journal
FROM winner_papers
ORDER BY field, winner_name, publication_date DESC;"""

    st.code(spl_example, language="sql")

    st.markdown("""
    **SPL-Flow Advantages:**

    1. **Decomposed Complexity**: Breaks the query into logical CTEs
    2. **Parallel Execution**: Different models handle different aspects simultaneously
    3. **Budget Control**: Explicit token allocation prevents scope creep
    4. **Model Routing**: Route sub-tasks to specialist models
    5. **Structured Output**: Guaranteed consistent formatting
    6. **Debuggable**: Each CTE can be tested independently
    7. **Verifiable**: Clear data flow and transformation steps
    """)

# ── Call to Action ────────────────────────────────────────────────────────────
st.divider()
st.subheader("🧪 Try It Yourself")

col_cta1, col_cta2, col_cta3 = st.columns(3)

with col_cta1:
    if st.button("🧪 Test the Benchmark Query", type="primary", use_container_width=True):
        st.session_state["_sample_pending"] = benchmark_query
        st.switch_page("pages/1_Chat.py")

with col_cta2:
    if st.button("📝 Try Other Complex Queries", use_container_width=True):
        st.switch_page("pages/1_Chat.py")

with col_cta3:
    if st.button("⚡ Benchmark Multiple Models", use_container_width=True):
        st.info("Benchmark page coming soon!")

st.markdown("""
---
**See the difference**: Traditional LLM prompting vs. SPL-Flow's declarative approach.

Complex, multi-constraint queries that break most LLMs become manageable, debuggable, and reliable with SPL-Flow.
""")

render_footer()