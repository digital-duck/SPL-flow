"""Few-shot examples and prompt templates for Text2SPL translation."""

TEXT2SPL_SYSTEM_PROMPT = """
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

| Task Type | Use Model |
|-----------|-----------|
| CJK (Chinese/Japanese/Korean) text | "qwen2.5" |
| European languages (German, French, Spanish) | "mistral" |
| Code review / generation | "deepseek-coder" |
| Encyclopedic knowledge / cultural facts | "meta-llama/llama-3.1-8b-instruct" |
| Final synthesis / composition | "anthropic/claude-sonnet-4-5" |
| Simple factual / general | "anthropic/claude-sonnet-4-5" |

## When to Use CTEs

Use multi-model CTEs when the task has **distinct sub-tasks that benefit from specialist models**:
- CJK content + European language translation → use qwen2.5 CTE + mistral CTE
- Code analysis + documentation → two CTEs with specialist models
- Data extraction + synthesis → extraction CTE + synthesis PROMPT

Use a SINGLE PROMPT when one model handles the task well.

## Critical Syntax Rules

1. Model names MUST be in double quotes: `USING MODEL "qwen2.5"` (NOT `USING MODEL qwen2.5`)
2. WITH BUDGET must come BEFORE USING MODEL
3. CTEs come AFTER USING MODEL, BEFORE SELECT
4. GENERATE instruction must be a SINGLE quoted string literal (no line continuation)
5. `{param}` placeholders in the instruction string reference SELECT aliases
6. Statement ends with semicolon

---

## EXAMPLE 1: Simple Single-Model Query

**User asks:** "Summarize this article in 3 bullet points"

```sql
PROMPT summarize_article
WITH BUDGET 4000 tokens
USING MODEL "anthropic/claude-sonnet-4-5"

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
USING MODEL "anthropic/claude-sonnet-4-5"

WITH cjk_analysis AS (
    PROMPT kanji_data
    WITH BUDGET 2000 tokens
    USING MODEL "qwen2.5"

    SELECT
        system_role("You are a Japanese and Chinese linguistics expert specializing in kanji etymology and composition."),
        context.topic AS topic LIMIT 50 tokens

    GENERATE
        kanji_list(topic, "List exactly 10 Japanese kanji containing the water radical. For each: kanji character, compositional formula (e.g. water+eye=tears), on-reading, kun-reading, and English meaning. Output as JSON array with keys: kanji, formula, on_reading, kun_reading, english_meaning.")
    WITH OUTPUT BUDGET 600 tokens, TEMPERATURE 0.1, FORMAT json
),

german_translations AS (
    PROMPT german_data
    WITH BUDGET 2000 tokens
    USING MODEL "mistral"

    SELECT
        system_role("You are a professional German linguist specializing in translating East Asian concepts."),
        context.topic AS topic LIMIT 50 tokens

    GENERATE
        translate_german(topic, "For 10 common Japanese kanji containing the water radical (sea, river, lake, rain, snow, ice, swim, wash, pour, flow), provide accurate German translations. Output as JSON array with keys: kanji, german_word, german_example.")
    WITH OUTPUT BUDGET 600 tokens, TEMPERATURE 0.1, FORMAT json
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

## EXAMPLE 3: Code Analysis Query

**User asks:** "Review this Python function for bugs, performance issues, and style"

```sql
PROMPT code_review
WITH BUDGET 6000 tokens
USING MODEL "anthropic/claude-sonnet-4-5"

SELECT
    system_role("You are a senior Python engineer specializing in code review. Focus on correctness, performance, and Pythonic style."),
    context.document AS code LIMIT 4000 tokens

GENERATE
    review_code(code, "Review the following Python code. Identify: (1) any bugs or logical errors, (2) performance issues or inefficiencies, (3) style violations (PEP 8, naming, readability). For each issue, provide the line reference, problem description, and suggested fix. Format as a structured markdown report.")
WITH OUTPUT BUDGET 1500 tokens, TEMPERATURE 0.2, FORMAT markdown;
```

---

Now generate SPL for the following user request. Output ONLY valid SPL code, no explanation, no markdown fences.
"""


def get_text2spl_prompt(
    user_input: str,
    context_text: str = "",
    error: str = "",
    retrieved_examples: list[dict] | None = None,
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

    Returns:
        Complete formatted prompt string for the LLM.
    """
    parts = [TEXT2SPL_SYSTEM_PROMPT]

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
