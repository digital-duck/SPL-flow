"""Few-shot examples and prompt templates for Text2SPL translation."""

# ── Per-adapter routing tables ────────────────────────────────────────────────
# ── Dynamic routing tables from MODEL_CATALOG ────────────────────────────────

from src.utils.model_catalog import MODEL_CATALOG, get_models

def _build_routing_table(adapter: str) -> str:
    """Build routing table dynamically from MODEL_CATALOG for given adapter."""
    models = get_models(adapter, active_only=True)

    # Task type mapping to find best models
    task_models = {}

    for model_id, info in models.items():
        strengths = info.get("strengths", [])
        for strength in strengths:
            if strength not in task_models:
                task_models[strength] = []
            task_models[strength].append(model_id)

    # If no dedicated synthesis model exists, fall back to general so the LLM
    # always has explicit guidance for the outer/final PROMPT — without this,
    # models hallucinate adapter-incorrect names like "claude-sonnet-4-5".
    if "synthesis" not in task_models and "general" in task_models:
        task_models["synthesis"] = task_models["general"]

    # Build the routing table string
    rows = []
    task_labels = {
        "cjk": "CJK (Chinese/Japanese/Korean) text",
        "eu_lang": "European languages (German, French, Spanish)",
        "code": "Code review / generation",
        "math": "Math / complex reasoning",
        "reasoning": "Reasoning / analysis",
        "synthesis": "Final synthesis / composition",
        "general": "Simple factual / general",
    }

    for task, label in task_labels.items():
        if task in task_models and task_models[task]:
            # Use first model for this task type
            model = task_models[task][0]
            rows.append(f'| {label} | "{model}" |')

    if not rows:
        # Fallback if no models found
        if adapter == "claude_cli":
            rows.append('| General / synthesis | "claude-sonnet-4-5" |')
        else:
            rows.append('| General | "qwen3:latest" |')

    header = "| Task Type | Use Model |\n|-----------|-----------|"
    return header + "\n" + "\n".join(rows)

def _get_example_models(adapter: str) -> dict[str, str]:
    """Get example model names for each task type from MODEL_CATALOG."""
    models = get_models(adapter, active_only=True)

    # Find best model for each task type
    task_models = {}
    for model_id, info in models.items():
        strengths = info.get("strengths", [])
        for strength in strengths:
            if strength not in task_models:
                task_models[strength] = model_id

    # Ensure we have fallbacks
    fallback = list(models.keys())[0] if models else "claude-sonnet-4-5"

    return {
        "general": task_models.get("general", fallback),
        "cjk": task_models.get("cjk", fallback),
        "eu_lang": task_models.get("eu_lang", fallback),
        "code": task_models.get("code", fallback),
    }

# ── Static prompt body (routing table + examples are injected dynamically) ────

_PROMPT_HEADER = """\
You are an expert SPL (Structured Prompt Language) code generator.

SPL is a SQL-inspired declarative language for orchestrating LLM prompts.

## SPL Syntax Reference

```
PROMPT <name>
WITH BUDGET <n> tokens
USING MODEL "<model_name>"

[WITH <cte_name> AS (
    PROMPT <inner_name>
    WITH BUDGET <n> tokens
    USING MODEL "<model_name>"

    SELECT
        system_role("system prompt text"),
        context.<param> AS <alias> LIMIT <n> tokens

    GENERATE
        <function>(arg, "instruction string with {param} placeholders")
    WITH OUTPUT BUDGET <n> tokens, TEMPERATURE <f>, FORMAT <json|markdown|text>
),
<cte_name2> AS (
    ...
)]

SELECT
    system_role("system prompt text"),
    context.<param> AS <alias> LIMIT <n> tokens

GENERATE
    <function>(arg1, arg2, "instruction string with {arg1} placeholders")
WITH OUTPUT BUDGET <n> tokens, TEMPERATURE <f>, FORMAT <markdown|json|text>;
```

## Model Routing Guidelines

{routing_table}

## When to Use CTEs

Use multi-model CTEs when the task has **distinct sub-tasks that benefit from specialist models**:
- CJK content + European language translation → use CJK specialist CTE + EU language CTE
- Code analysis + documentation → two CTEs with specialist models
- Data extraction + synthesis → extraction CTE + synthesis PROMPT

Use a SINGLE PROMPT when one model handles the task well.

## Critical Syntax Rules

1. Model names MUST be in double quotes: `USING MODEL "model-name"` (NOT `USING MODEL model-name`)
2. WITH BUDGET must come BEFORE USING MODEL
3. CTEs come AFTER USING MODEL, BEFORE SELECT
4. GENERATE instruction must be a SINGLE quoted string literal (no line continuation)
5. `{{param}}` placeholders in the instruction string reference SELECT aliases
6. Statement ends with semicolon

## Output Budget Sizing Guide

Set OUTPUT BUDGET large enough so the model is never truncated mid-response:

| Output type                          | Minimum OUTPUT BUDGET |
|--------------------------------------|-----------------------|
| Short answer / single fact           | 200–400 tokens        |
| Paragraph summary (3–5 sentences)    | 400–600 tokens        |
| List of 5 items (JSON or markdown)   | 800–1000 tokens       |
| List of 10 items (JSON or markdown)  | 1500–2000 tokens      |
| Full table (10+ rows, 4+ columns)    | 2000–3000 tokens      |
| Long-form synthesis / composition    | 2000–4000 tokens      |
| Complete script / code file          | 2000–4000 tokens      |

**Rule of thumb**: when the user asks for N items, set OUTPUT BUDGET ≥ N × 150 tokens for JSON,
N × 100 tokens for markdown. Always err on the side of MORE — unused budget costs nothing.\
"""

_PROMPT_FOOTER = """\
---

Now generate SPL for the following user request. Output ONLY valid SPL code, no explanation, no markdown fences.\
"""


def _build_examples(models: dict[str, str]) -> str:
    """Return the three few-shot examples with adapter-correct model IDs."""
    g = models["general"]
    cjk = models["cjk"]
    eu = models["eu_lang"]
    code = models["code"]

    return f"""\
---

## EXAMPLE 1: Simple Single-Model Query

**User asks:** "Summarize this article in 3 bullet points"

```sql
PROMPT summarize_article
WITH BUDGET 4000 tokens
USING MODEL "{g}"

SELECT
    system_role("You are a concise technical writer who creates clear, actionable summaries."),
    context.document AS article LIMIT 2500 tokens

GENERATE
    summarize(article, "Summarize the following content in exactly 3 clear bullet points. Each bullet should capture a key insight. Be specific and avoid vague language.")
WITH OUTPUT BUDGET 500 tokens, TEMPERATURE 0.3, FORMAT markdown;
```

---

## EXAMPLE 2: Multi-Language CTE Query

**User asks:** "Generate a table of 10 Japanese water radical kanji with meanings, formulas, and German translations"

```sql
PROMPT water_kanji_table
WITH BUDGET 8000 tokens
USING MODEL "{g}"

WITH cjk_analysis AS (
    PROMPT kanji_data
    WITH BUDGET 2000 tokens
    USING MODEL "{cjk}"

    SELECT
        system_role("You are a Japanese and Chinese linguistics expert specializing in kanji etymology and composition."),
        context.topic AS topic LIMIT 50 tokens

    GENERATE
        kanji_list(topic, "List exactly 10 Japanese kanji containing the water radical. For each: kanji character, compositional formula (e.g. water+eye=tears), on-reading, kun-reading, and English meaning. Output as JSON array with keys: kanji, formula, on_reading, kun_reading, english_meaning.")
    WITH OUTPUT BUDGET 1500 tokens, TEMPERATURE 0.1, FORMAT json
),

german_translations AS (
    PROMPT german_data
    WITH BUDGET 2000 tokens
    USING MODEL "{eu}"

    SELECT
        system_role("You are a professional German linguist specializing in translating East Asian concepts."),
        context.topic AS topic LIMIT 50 tokens

    GENERATE
        translate_german(topic, "For 10 common Japanese kanji containing the water radical (sea, river, lake, rain, snow, ice, swim, wash, pour, flow), provide accurate German translations. Output as JSON array with keys: kanji, german_word, german_example.")
    WITH OUTPUT BUDGET 1500 tokens, TEMPERATURE 0.1, FORMAT json
)

SELECT
    system_role("You are an expert at composing multilingual scholarly tables from structured JSON data."),
    context.cjk_analysis AS kanji_data LIMIT 1500 tokens,
    context.german_translations AS german_data LIMIT 1500 tokens

GENERATE
    compose_table(kanji_data, german_data, "Merge the two JSON datasets into one markdown table with columns: | Kanji | Formula | On-Reading | Kun-Reading | English Meaning | German Translation |. Align rows by kanji character. Output only the markdown table.")
WITH OUTPUT BUDGET 2000 tokens, TEMPERATURE 0.1, FORMAT markdown;
```

---

## EXAMPLE 3: Code Generation Query

**User asks:** "Write a Python script using Click to list files in a directory"

```sql
PROMPT list_files_cli
WITH BUDGET 6000 tokens
USING MODEL "{code}"

SELECT
    system_role("You are a senior Python developer specializing in CLI applications.")

GENERATE
    generate_code("Write a complete Python script using the Click library to list files in a given directory. Include: Click decorators for argument/option parsing, error handling for missing or invalid paths, colored output, a --recursive flag, and a main guard. Add docstrings and PEP 8 compliant style.")
WITH OUTPUT BUDGET 3000 tokens, TEMPERATURE 0.1, FORMAT text;
```"""


def _build_system_prompt(adapter: str, selected_model_id: str = "", selected_provider: str = "") -> str:
    # If specific model is selected, create a custom routing table
    if selected_model_id:
        # Build custom routing table with the selected model
        routing = f"""| Task Type | Use Model |
|-----------|-----------|
| All tasks | "{selected_model_id}" |"""

        # Create custom example models dictionary
        example_models = {
            "general": selected_model_id,
            "cjk": selected_model_id,
            "eu_lang": selected_model_id,
            "code": selected_model_id,
        }
    else:
        # Use dynamic routing as before
        routing = _build_routing_table(adapter)
        example_models = _get_example_models(adapter)

    header = _PROMPT_HEADER.replace("{routing_table}", routing)
    examples = _build_examples(example_models)
    return f"{header}\n\n{examples}\n\n{_PROMPT_FOOTER}"


def get_text2spl_prompt(
    user_input: str,
    context_text: str = "",
    error: str = "",
    retrieved_examples: list[dict] | None = None,
    adapter: str = "openrouter",
    selected_model_id: str = "",
    selected_provider: str = "",
) -> str:
    """Format the complete prompt for Text2SPL translation.

    Args:
        user_input:          The user's natural language query.
        context_text:        Optional reference document pasted by the user.
        error:               Previous parse error (populated on retry).
        retrieved_examples:  RAG-retrieved (nl_query, spl_query) dicts, ordered
                             by semantic similarity.  When provided they are
                             injected between the static examples and the user
                             request so the LLM sees task-relevant prior art
                             before generating new SPL.
        adapter:             Execution adapter ("openrouter", "ollama",
                             "claude_cli").  Controls which model IDs appear
                             in the routing table and few-shot examples.

    Returns:
        Complete formatted prompt string for the LLM.
    """
    parts = [_build_system_prompt(adapter, selected_model_id, selected_provider)]

    # ── Dynamic few-shot examples from RAG store ──────────────────────────────
    if retrieved_examples:
        examples_text = "\n\n---\n\n".join(
            f"**Similar query:** {ex['nl_query']}\n\n```sql\n{ex['spl_query']}\n```"
            for ex in retrieved_examples[:5]
        )
        parts.append(
            "## Retrieved Examples (from your query history — highest relevance first)\n\n"
            "These are real (query, SPL) pairs from previous sessions that are "
            "semantically similar to the current request. Use them as additional "
            "style and structure guidance:\n\n"
            + examples_text
        )

    if error:
        parts.append(
            f"## IMPORTANT: Previous Attempt Failed\n"
            f"Your previous SPL output produced this parse error:\n"
            f"```\n{error}\n```\n"
            f"Fix the error in your new output. Common fixes:\n"
            f"- Ensure model names are in double quotes: USING MODEL \"model-name\"\n"
            f"- Ensure WITH BUDGET comes before USING MODEL\n"
            f"- Ensure CTEs come after USING MODEL and before SELECT\n"
            f"- Ensure GENERATE instruction is a single string literal (no string concatenation)\n"
            f"- Ensure the statement ends with a semicolon\n"
            f"- Ensure context references use format: context.<param> AS <alias>\n"
        )

    if context_text.strip():
        parts.append(
            f"## Reference Document Provided by User\n"
            f"The user has pasted the following document. Generate SPL that references it "
            f"via `context.document` in the SELECT clause with appropriate LIMIT tokens.\n\n"
            f"(Document preview — first 500 chars):\n"
            f"{context_text[:500]}"
        )

    parts.append(f"## User Request\n{user_input}")
    parts.append("## Your SPL Output")

    return "\n\n".join(parts)
