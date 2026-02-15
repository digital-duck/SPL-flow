# Liquid AI Partnership — Digital-Duck LLC

*February 2026 | Confidential — Internal Strategy Document*

---

## TL;DR

Digital-Duck has two concrete use cases that showcase Liquid AI's LFM family in ways no
chat product can. LFM is open-source — we can build both without a formal partnership.
But a partnership is win-win:

| Party | What they get |
|-------|--------------|
| **Liquid AI** | Two production reference apps demonstrating LFM beyond chat: structured translation (developer tooling) + on-device multimodal tutoring (consumer EdTech) |
| **Digital-Duck** | Fine-tuning support, early model access, co-marketing, possible inclusion in Liquid AI's showcase portfolio |

---

## Relationship

**Ramin Hasani (CEO, Co-founder)**
- Former colleague — warm relationship, not a cold pitch.
- Left to co-found Liquid AI with the Liquid Neural Network research from MIT.
- Approach: after SPL-Flow MVP demonstrates the Chinese Learning use case end-to-end
  with multi-modal output (table + audio + image). That demo makes the pitch self-evident.

**Alexander Amini (Chief Scientist, Co-founder)**
- Met at MIT Sloan Tech Summit, February 2026.
- Technical co-founder — can evaluate and champion the use cases internally.
- Second entry point if Ramin is hard to reach.

**Strategy**: Build first, pitch with a working demo. The code speaks louder than a deck.

---

## Why LFM Being Open-Source Changes the Dynamic

LFM models (LFM2.5 family: Text / Audio / Vision) are open-sourced by Liquid AI.
This means:

- Digital-Duck can start development **today**, without permission or partnership.
- We can fine-tune LFM 1.3B for Text2SPL on our own infrastructure.
- We can integrate LFM Audio/Vision into ZiNets without a commercial agreement.

A partnership is not a prerequisite — it is an accelerant.

What a formal partnership adds:
- Liquid AI's fine-tuning infrastructure and guidance
- Early access to unreleased LFM variants
- Co-branding: "Powered by Liquid AI LFM"
- Potential inclusion in Liquid AI's developer showcase
- Joint press release / conference presence

---

## Use Case 1 — Text2SPL: NL-to-SPL Structured Translator

### What it is

A tiny (1.3B parameter) specialized model that translates natural language queries
into valid SPL (Structured Prompt Language) scripts. Runs locally, on-device,
with no cloud dependency for the translation step.

```
User types: "List 10 Chinese characters with water radical,
             meanings, German translations, cultural insights"
         │
         ▼  80ms · local · private
Text2SPL LFM 1.3B
  └── Grammar-constrained beam search (output always valid SPL)
         │
         ▼
PROMPT table USING MODEL auto
WITH chars    AS (PROMPT ... USING MODEL "qwen2.5")      -- CJK specialist
WITH german   AS (PROMPT ... USING MODEL "mistral")      -- EU language specialist
WITH insights AS (PROMPT ... USING MODEL "llama3.1")     -- cultural reasoning

SELECT compose_table(chars, german, insights, ...)
WITH OUTPUT FORMAT markdown;
```

### Why LFM is the right foundation

| Property | Why it matters |
|----------|---------------|
| LFM 1.3B compact size | Runs on CPU, in browser (WASM), on mobile |
| Liquid Neural Network architecture | Efficient for structured sequence translation |
| Fast inference | ~80ms NL→SPL vs 2-3s for GPT-4 |
| On-device / privacy-first | No query data leaves the user's machine |
| Fine-tunable | Supports domain-specific sequence-to-sequence training |

### Training strategy

```
Phase 1 — Synthetic Bootstrap (automated)
  Generate 10,000+ (NL query, SPL script) pairs via Claude/GPT-4
  Validate every SPL with `spl validate` — discard invalid
  Diversity: single-model, multi-CTE, various domains and adapters

Phase 2 — Fine-tune LFM 1.3B
  Task: sequence-to-sequence (NL → SPL)
  Grammar-constrained decoding (beam search within SPL grammar)
  Metric: parse success rate + semantic intent alignment
  Target: >95% valid SPL on held-out test set

Phase 3 — RLHF / DPO Alignment
  Human preference: (query, SPL_A, SPL_B) → preferred
  Aligns "valid SPL" with "correct SPL for this task"

Phase 4 — Integration
  Packaged as spl-flow-translator (optional pip install)
  Falls back to GPT-4/Claude if LFM not available
  Runs fully locally when LFM is present
```

### Market framing

NL→SQL has a $1B+ tooling market (text-to-query is a proven category).
NL→SPL is a new category: **NL-to-LLM-orchestration-script**.
Every data engineer who knows SQL and wants to work with LLMs is a potential user.
The Text2SPL LFM is the on-device, privacy-first entry point.

---

## Use Case 2 — ZiNets Chinese Learning App

### What it is

An AI-powered Chinese language learning platform that routes each pedagogical sub-task
to the world's best specialist model — coordinated by a declarative SPL script.

```
SPL script (generated from plain English via Text2SPL LFM):

PROMPT lesson USING MODEL "claude-sonnet"
WITH characters AS (PROMPT extract_chars USING MODEL "qwen2.5")        -- CJK specialist
WITH audio      AS (PROMPT pronounce     USING MODEL "lfm2.5-audio")   -- LFM Audio
WITH image      AS (PROMPT visual_mnem   USING MODEL "sdxl")           -- image generation
WITH strokes    AS (PROMPT stroke_order  USING MODEL "cjk-animator")   -- stroke specialist

SELECT compose_lesson(characters, audio, image, strokes, ...)
WITH OUTPUT FORMAT rich;
```

One declarative script. Four specialist models in parallel. One composed lesson.

### LFM's role in ZiNets

| LFM Model | ZiNets Application |
|-----------|-------------------|
| LFM2.5 Audio 1.5B | Pronunciation correction: learner speaks, LFM detects tonal errors in real time |
| LFM2.5 Vision | Character recognition: learner writes on screen, LFM grades stroke order |
| LFM2.5 Text (fine-tuned) | Conversational tutoring: context-aware dialogue adapted to learner's level |

### Why this is unique and unreplicable

- Every competitor uses one model for everything (monolithic architecture).
- SPL-Flow routes each sub-task to the best specialist — transparent, auditable, updatable.
- The orchestration is invisible to the learner; they see one beautiful composed result.
- As better models appear, the YAML model registry updates — the platform gets smarter automatically.
- Text2SPL LFM makes the orchestration accessible to educators without engineering skills.

### Foundation already built (Feb 14 2026)

- 400-character semantic radical database (ZiNets research, published arXiv).
- SPL engine proven: 3 specialist models, parallel CTE dispatch,
  Claude synthesizes a 6-column multilingual scholarly table in one pipeline run.
- Validated on Ollama (local/free), OpenRouter (cloud/$0.002/run), and Claude CLI.
- Radical family table: Character + Formula + Pinyin + English + German + NaturalInsight
  — all 6 columns populated from 3 parallel specialist models.

---

## The Two-Use-Case Pitch — Stronger Together

| Use Case | LFM Role | Market |
|----------|----------|--------|
| Text2SPL Translator | LFM 1.3B fine-tuned: NL→SPL structured translation | B2B Developer Tooling |
| ZiNets Chinese Learning | LFM Audio/Vision: on-device pronunciation + conversational tutoring | Consumer EdTech |

Together: **LFM as the edge inference layer for the entire SPL-Flow platform** —
structured translation at the front (Text2SPL), multimodal tutoring at the consumer
surface (ZiNets). Both are non-chat: specialized, structured, on-device, privacy-first.

This is the angle Liquid AI needs most: demonstrations that LFM capabilities go beyond chat.

---

## What We Are Building Regardless

Since LFM is open-source, development proceeds on our timeline:

- [x] SPL engine with parallel CTE dispatch (`spl-llm` package, 58/58 tests, Apache 2.0)
- [x] SPL-Flow MVP: Text2SPL + PocketFlow orchestration + Streamlit UI (Feb 2026)
- [x] Chinese radical table demo: 3 models in parallel, Claude synthesizes
- [ ] Multi-modal CTEs: audio + image columns in radical family table
- [ ] Text2SPL fine-tuning dataset: 10,000+ (NL, SPL) pairs via synthetic bootstrap
- [ ] LFM 1.3B fine-tune: Text2SPL translator prototype
- [ ] ZiNets LFM Audio integration: pronunciation correction prototype

A working demo will exist before any partnership conversation.

---

## Partnership Ask (When the Time is Right)

The pitch is not "fund us." The pitch is "co-develop and co-showcase."

**What Digital-Duck brings:**
- Working SPL engine (open-source, Apache 2.0, pip-installable as `spl-llm`)
- Working SPL-Flow MVP with Text2SPL layer and PocketFlow orchestration
- ZiNets semantic radical database (400 characters, multilingual)
- arXiv / TMLR / ICML publications establishing the research credibility
- Warm relationships with both founders

**What we ask from Liquid AI:**
- Fine-tuning compute or infrastructure support for LFM 1.3B Text2SPL training
- Early access to LFM Audio/Vision for ZiNets prototype
- Co-branding on release: "Text2SPL powered by Liquid AI LFM"
- Optional: blog post or conference showcase of both use cases

---

## Contact Plan

1. **Now**: Continue building. Document progress in demo-ready form.
2. **Demo milestone**: ZiNets lesson running end-to-end with characters + audio from LFM2.5 Audio.
3. **First contact — Alexander Amini** (met MIT Sloan Tech Summit, Feb 2026).
   Share the demo link, ask for technical feedback. Lower-pressure entry than going straight to CEO.
4. **Ramin Hasani follow-up**: Leverage the warm relationship.
   Brief summary email + demo link. Let the demo do the talking.
5. **If partnership materializes**: formalize with a co-development or joint showcase agreement.
   If not: continue independently. LFM is open-source — we lose nothing either way.

---

*Last updated: February 14, 2026*
*Document owner: Digital-Duck LLC*
*Related: `docs/startup/architecture.md` — Section 8: Three Core Innovations*
