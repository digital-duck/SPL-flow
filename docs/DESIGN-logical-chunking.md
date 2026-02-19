# Logical Chunking in SPL-Flow

**Status:** Implemented (2026-02-19)
**Related paper section:** §9.5 — Logical Chunking: Declarative Map-Reduce for Long Contexts

---

## Motivation

LLM context windows are finite. The smallest denominator among widely-deployed
models is **4,096 tokens** (Llama 2, original GPT-3.5-turbo). A document that
exceeds safe usable context (~3,000 tokens after reserving overhead for system
role, question, and output) cannot be processed in a single PROMPT.

SPL's CTE architecture provides a structurally superior alternative to crude
truncation: **logical chunking** — split the document into k semantically
coherent segments, process each independently in a CTE (Map phase), then
synthesize the results in the outer GENERATE (Reduce phase).

The efficiency argument is formal: transformer attention scales O(N²). Processing
N tokens as k chunks of N/k tokens costs O(k·(N/k)²) = O(N²/k) — a factor-of-k
reduction in attention compute.

---

## Open-Source Chunking Landscape

| Package | Approach | Verdict |
|---|---|---|
| **`chonkie`** | Token / sentence / semantic chunking; lightweight, fast, LLM-pipeline-native | **Chosen** |
| `langchain-text-splitters` | `RecursiveCharacterTextSplitter`, `SemanticChunker` | Heavy LangChain dep |
| `llama-index` | `SentenceSplitter`, `SemanticSplitterNodeParser` | Even heavier dep |
| `nltk` / `spacy` | Grammar-based sentence tokenization | Not semantic |
| `semantic-text-splitter` | Rust-based, tiktoken-native | Less Pythonic |

### Why chonkie

- Purpose-built for LLM pre-processing pipelines
- Zero heavy dependencies for core token/sentence chunking
- Optional `[semantic]` extra adds sentence-transformer embeddings
- Actively maintained; tiktoken-native token counting
- Semantic chunking respects meaning boundaries, not arbitrary character counts

---

## Design Decisions

### 1. Chunk trigger threshold — 3,000 tokens

The smallest popular model context window is 4,096 tokens (Llama 2, GPT-3.5
original). Deducting overhead:

```
4,096 total
 - 200  system role
 - 200  user question / intent
 - 1,500 output budget
─────────────────────
 2,196  usable document context
```

**Threshold = 3,000 tokens** — documents exceeding this are chunked. This
is conservative (slightly above the true floor) to ensure compatibility even
with the most constrained 4K models while avoiding over-chunking short docs.

### 2. Chunk strategy — semantic (chonkie SemanticChunker)

Semantic chunking uses sentence embeddings to find natural meaning boundaries
rather than splitting at arbitrary character or token counts. This produces
coherent chunks that each stand alone as a processable unit.

Default embedding model: `minishlab/potion-base-8M` — a lightweight 8M-param
model (~30 MB), runs offline, no API key required.

**Fallback:** `chonkie.TokenChunker` — used when the `[semantic]` extra is
not installed. Splits at token boundaries, no embedding required.

### 3. k — dynamic, capped at MAX_CHUNKS = 16

```python
k = ceil(document_tokens / CHUNK_SIZE_TOKENS)
k = min(k, MAX_CHUNKS)   # prevent abuse / runaway costs
```

`CHUNK_SIZE_TOKENS = 2,800` — each chunk fits comfortably in a 4K context
with overhead. The cap of 16 limits processing of adversarially large inputs
without user confirmation.

### 4. Specialist model per CTE — adapter's "general" model

Each CTE chunk uses the adapter's general-purpose model (fast, cheap, reliable).
No domain-specialist routing needed at the chunk level — the content is
homogeneous within a split document. `USING MODEL auto` is reserved for
heterogeneous multi-domain scripts.

### 5. Reduce (synthesis) model — same as specialist

The synthesis step uses the same model as the chunk CTEs. This keeps costs
predictable and avoids unexpected model-mixing. Users who want a stronger
synthesis model can override via `synthesis_model` parameter.

### 6. Internal language — English pivot

All NL input is translated to English before Text2SPL processing so that:
- The chunker operates on a single well-supported language
- The SPL system_role / GENERATE instruction is always English
- The LLM responses (per chunk) are in English, making synthesis reliable

Language detection uses `langdetect`. Translation uses the active LLM adapter
(fast, cheap call with haiku-class model).

---

## Architecture

```
run_chunking_flow(user_input, context_text, ...)
        │
        ├─ [1] Detect language of user_input + context_text
        │
        ├─ [2] Translate to English (LLM call if non-English)
        │
        ├─ [3] Count tokens in context_text
        │        < CHUNK_THRESHOLD (3000) ─────────────────► run_spl_flow() (existing path)
        │        ≥ CHUNK_THRESHOLD
        │
        ├─ [4] SemanticChunker → k chunks (k ≤ MAX_CHUNKS=16)
        │
        ├─ [5] chunk_spl_builder → multi-CTE SPL + params dict
        │         SPL structure:
        │           WITH chunk_1_summary AS (PROMPT analyze_chunk_1 ... )
        │           WITH chunk_2_summary AS (PROMPT analyze_chunk_2 ... )
        │           ...
        │           SELECT chunk_1_summary, ..., chunk_k_summary
        │           GENERATE comprehensive_synthesis(...)
        │
        └─ [6] ValidateSPLNode → ExecuteSPLNode → DeliverNode
                 (existing SPL-Flow pipeline, SPL pre-built — no Text2SPL LLM call)
```

**Map phase:** each CTE processes one chunk independently. In the executor,
CTEs with nested PromptStatements are dispatched; with cloud adapters these
run in parallel via `asyncio.gather`.

**Reduce phase:** the outer GENERATE receives all k chunk summaries and
synthesizes a coherent final response.

---

## Token Budget Formula

```python
CHUNK_THRESHOLD_TOKENS  = 3_000   # trigger threshold (4K model floor)
CHUNK_SIZE_TOKENS       = 2_800   # content per chunk (fits 4K with overhead)
MAX_CHUNKS              = 16      # DoS cap

BUDGET_PER_CHUNK        = 4_000   # 2800 content + 800 output + 400 overhead
OUTPUT_PER_CHUNK        = 800     # per-CTE output
FINAL_OUTPUT_BUDGET     = 2_000   # synthesis output
FINAL_BUDGET            = max(8_000, k * OUTPUT_PER_CHUNK + FINAL_OUTPUT_BUDGET + 1_000)
```

---

## Generated SPL Example (k=3)

```sql
PROMPT synthesize_document
WITH BUDGET 5400 tokens
USING MODEL "claude-sonnet-4-5"

WITH chunk_1_summary AS (
    PROMPT analyze_chunk_1
    WITH BUDGET 4000 tokens
    USING MODEL "claude-sonnet-4-5"

    SELECT
        system_role("Expert analyst. Process this section for: summarize the key findings"),
        context.chunk_1 AS text LIMIT 2800 tokens

    GENERATE section_summary(text)
    WITH OUTPUT BUDGET 800 tokens
),
chunk_2_summary AS (
    PROMPT analyze_chunk_2
    WITH BUDGET 4000 tokens
    USING MODEL "claude-sonnet-4-5"

    SELECT
        system_role("Expert analyst. Process this section for: summarize the key findings"),
        context.chunk_2 AS text LIMIT 2800 tokens

    GENERATE section_summary(text)
    WITH OUTPUT BUDGET 800 tokens
),
chunk_3_summary AS (
    PROMPT analyze_chunk_3
    WITH BUDGET 4000 tokens
    USING MODEL "claude-sonnet-4-5"

    SELECT
        system_role("Expert analyst. Process this section for: summarize the key findings"),
        context.chunk_3 AS text LIMIT 2800 tokens

    GENERATE section_summary(text)
    WITH OUTPUT BUDGET 800 tokens
)

SELECT
    system_role("Synthesize all section analyses into a comprehensive response for: summarize the key findings"),
    chunk_1_summary AS summary_1,
    chunk_2_summary AS summary_2,
    chunk_3_summary AS summary_3

GENERATE comprehensive_synthesis(summary_1, summary_2, summary_3)
WITH OUTPUT BUDGET 2000 tokens, FORMAT markdown

STORE RESULT IN memory.chunked_result;
```

---

## Stress-Test Potential

With logical chunking + MoM routing, SPL-Flow can now benchmark against
top-tier models on long-document tasks:

| Scenario | Config |
|---|---|
| Long research paper (16K tokens, k=6) | `chonkie` semantic split → 6 CTEs → synthesis |
| Multilingual document | Translate to English → chunk → execute → deliver |
| Cost comparison | Same chunked query across Haiku / Sonnet / GPT-4o / Llama3 |
| Parallel vs sequential | Cloud asyncio.gather vs Ollama sequential overnight |

---

## Files

| File | Role |
|---|---|
| `src/utils/chunker.py` | Language detection, English translation, semantic chunking |
| `src/utils/chunk_spl_builder.py` | Builds multi-CTE SPL string + params dict directly (no LLM) |
| `src/flows/chunking_flow.py` | `run_chunking_flow()` entry point |
| `src/flows/spl_flow.py` | Existing flow; `run_chunking_flow` delegates here for short docs |
