# SPL-Flow — Startup Vision

**The declarative orchestration platform for the LLM economy**

*First captured: February 14, 2026*
*Author: Wen Gong | Co-developed with Claude (Anthropic)*

---

## The One-Line Pitch

SPL-Flow is to LLM engineering what dbt is to data engineering:
an open-source declarative language (SPL) backed by a commercial orchestration platform,
targeting the millions of SQL practitioners who are now — or soon will be — LLM engineers.

---

## The Problem

OpenRouter offers 100+ LLM models. Nobody knows how to choose.

Every LLM engineer faces the same three unsolved problems daily:

1. **Which model for which task?**
   No declarative way to route sub-tasks to the best model. Everyone defaults to
   the most expensive frontier model for everything — costly and often unnecessary.

2. **How to compose complex multi-step prompts?**
   Current tools (LangChain, n8n, Zapier) require imperative Python or GUI drag-and-drop.
   Neither scales. Neither is readable, versionable, or optimizable.

3. **How to know the cost before running?**
   No tool shows token allocation and cost estimates before execution.
   Developers discover cost after the bill arrives.

SPL-Flow solves all three declaratively, with SQL grammar that 10 million data engineers already know.

---

## The Origin Story

The idea surfaced on a Thursday morning in February 2026, during meditation.

> "The LLM context window is a constrained resource — exactly like disk I/O was for databases.
>  SQL solved the database resource management problem in 1970. Where is the SQL for LLMs?"

20+ years of Oracle and SQL engineering, meeting 4 years of LLM engineering, producing a single
insight. Within hours, a working prototype (SPL engine) was implemented via human×AI collaboration.
By Thursday evening, the arXiv paper draft was complete.

The startup was born from the same insight: if this is a real engineering problem
(and it is), there is a platform business in solving it declaratively.

---

## The Vision: LLM Economy Infrastructure

The "LLM economy" is emerging: hundreds of models, dozens of providers, millions of tasks,
wildly varying costs and capabilities. What the LLM economy needs is the same thing
the database economy needed in 1970: **a standard declarative layer**.

SPL-Flow is that layer.

```
┌─────────────────────────────────────────────────────────┐
│                  Human Interface                        │
│         Claude Code · OpenCode · SPL CLI                │
└───────────────────────┬─────────────────────────────────┘
                        │  SPL queries (.spl files)
┌───────────────────────▼─────────────────────────────────┐
│              SPL-Flow Engine (open source)              │
│  Lexer → Parser → Analyzer → Optimizer → Executor       │
│                                                         │
│  • Token budget optimization (EXPLAIN before running)   │
│  • CTE dependency graph (parallel async dispatch)       │
│  • Model routing (leaderboard → routing logic)          │
│  • Memory (SQLite persistent context)                   │
│  • RAG (FAISS / ChromaDB)                               │
└──────┬────────────────┬──────────────────┬──────────────┘
       │                │                  │
┌──────▼──────┐  ┌──────▼──────┐  ┌───────▼──────┐
│  OpenRouter │  │  Direct APIs│  │  Local Ollama│
│  100+ models│  │  Claude     │  │  llama3.2    │
│  (model zoo)│  │  GPT-4o     │  │  qwen2.5     │
│             │  │  Gemini     │  │  mistral     │
└─────────────┘  └─────────────┘  └──────────────┘
```

---

## The Technical Core: SPL as MapReduce for LLMs

The structural analogy to MapReduce (Google, 2004) is precise:

| MapReduce (2004) | SPL-Flow (2026) |
|-----------------|-----------------|
| Commodity hardware cluster | 100+ models via OpenRouter |
| Declarative (Hive/Pig SQL) | Declarative SPL syntax |
| Map: parallel data shards | CTEs: parallel specialist LLM calls |
| Reduce: aggregate results | Final PROMPT: compose CTE responses |
| Cost: cheap vs. mainframe | Cost: 5-10x cheaper via routing |
| Breakthrough: declarative over distributed | Breakthrough: declarative over model zoo |

MapReduce showed that **distributed commodity hardware**, coordinated declaratively,
could outperform a single expensive mainframe.

SPL-Flow shows that **distributed specialist LLMs**, coordinated declaratively,
can outperform a single expensive frontier model — at lower cost and equal or better quality.

### Example: Multi-Model CTE Execution

```sql
-- Three specialist models run IN PARALLEL
WITH characters AS (          -- qwen2.5: best CJK model
    PROMPT list_characters USING MODEL qwen2.5 ...
),
german AS (                   -- mistral: best EU languages
    PROMPT translate USING MODEL mistral ...
),
insights AS (                 -- llama3.1: encyclopedic
    PROMPT explain USING MODEL llama3.1:8b ...
)
-- Frontier model only for final synthesis
PROMPT compose_table USING MODEL anthropic/claude-sonnet-4-5
SELECT context.characters, context.german, context.insights
GENERATE merged_table(...)
WITH OUTPUT BUDGET 2000 tokens, FORMAT markdown;
```

EXPLAIN shows the full cost breakdown before a single API call is made:
```
CTE characters    qwen2.5          ~$0.001
CTE german        mistral          ~$0.0008
CTE insights      llama3.1:8b      ~$0.0005  (local: $0.00)
Final compose     claude-sonnet    ~$0.012
─────────────────────────────────────────
Total                              ~$0.014   (vs $0.04 single-model)
```

---

## Model Routing: Codifying the Leaderboard

The model selection problem is solvable. Leaderboard data (LMSYS Chatbot Arena, MMLU,
HumanEval, BEIR, multilingual benchmarks) already encodes which models win at which tasks.

SPL-Flow codifies this into routing rules:

```sql
-- v0.3 target syntax
USING MODEL AUTO FOR translation     -- routes to mistral / qwen2.5 based on language
USING MODEL AUTO FOR code            -- routes to deepseek-coder / codellama
USING MODEL AUTO FOR reasoning       -- routes to claude / gpt-4o
USING MODEL AUTO FOR synthesis       -- routes to frontier model
USING MODEL AUTO BUDGET $0.01        -- finds best model under cost cap
```

The routing layer:
1. Maintains a model capability registry (cost/token, benchmark scores, specializations)
2. Learns from execution history (which models performed well for which prompt types)
3. Exposes routing decisions transparently via EXPLAIN

---

## The Platform Business: Beyond the Engine

The open-source SPL engine (spl-llm on PyPI) is the language.
SPL-Flow is the **platform** — the commercial layer that makes the language useful at scale.

### Platform Services

| Service | Description | Analogy |
|---------|-------------|---------|
| **Async execution** | Submit SPL query, receive result when done | SQL batch job |
| **Scheduled prompts** | Run SPL query daily/weekly/on-event | cron + SQL |
| **Result delivery** | Email, webhook, Slack notification | BI report delivery |
| **Document generation** | SPL result → PDF, DOCX, HTML | Crystal Reports for LLMs |
| **App deployment** | SPL result → deployed Streamlit/FastAPI app | Low-code app builder |
| **Model registry** | Curated routing rules, updated from leaderboards | Package registry |
| **Team workspace** | Shared SPL files, execution history, cost tracking | dbt Cloud workspace |

### The Async Vision

Today: user writes SPL, waits at keyboard, gets result.

SPL-Flow: user submits SPL at 9am, receives PDF report in inbox at 10am.
No babysitting. No waiting. The platform runs the multi-model CTE pipeline,
composes the result, renders the document, and delivers it.

```bash
spl-flow submit research_report.spl \
    --param topic="quantum computing" \
    --notify wen.gong.research@gmail.com \
    --format pdf \
    --schedule "every Monday 8am"
```

This is the moment the user is no longer constrained by sitting in front of a computer.
Complex LLM workflows become scheduled, persistent, automated — like database jobs.

---

## Business Model

### Open Source + Commercial Platform (the dbt model)

| Layer | Product | License | Revenue |
|-------|---------|---------|---------|
| Language | SPL engine (spl-llm) | Apache 2.0 | None — build ecosystem |
| Platform | SPL-Flow Cloud | Commercial | Subscription + usage |

**dbt precedent:**
- dbt Core: open source, 30,000+ GitHub stars, massive community
- dbt Cloud: $50/seat/month, $222M raised, $4.2B valuation (2022)
- The community built on dbt Core is dbt Cloud's acquisition channel

**SPL-Flow pricing hypothesis:**
- Free tier: 1,000 executions/month, no async delivery
- Pro: $49/month — async execution, email/PDF delivery, 50,000 executions
- Team: $199/month — shared workspace, model registry, cost dashboards
- Enterprise: custom — on-premise, private model fleet, SLA

---

## Competitive Landscape

| Competitor | Strength | SPL-Flow Advantage |
|-----------|----------|-------------------|
| **LangChain/LangGraph** | Large ecosystem, multi-model | SQL grammar (declarative vs. imperative Python) |
| **n8n** | Workflow automation, open source | LLM-native, not bolted-on; SQL not GUI |
| **Zapier** | 7,000+ integrations, SMB market | LLM-first, programmable, EXPLAIN cost visibility |
| **Portkey / Helicone** | LLM gateway, observability | Full orchestration language, not just proxy |
| **Martian** | Model routing | Full query language, not just routing |
| **CrewAI / AutoGen** | Multi-agent orchestration | SQL grammar, cost transparency, simpler |

**The gap nobody fills:** A declarative, SQL-grammar, cost-transparent orchestration
language for LLMs targeting data engineers. That is SPL-Flow's market entry point.

---

## Target Audience

**Primary: Data engineers and analysts transitioning to AI engineering**
- 10M+ SQL practitioners worldwide
- Already know the grammar — zero learning curve for SPL syntax
- Currently using LangChain (imperative Python) — frustrated by complexity
- Cost-aware by profession (database query optimization is their job)

**Secondary: LLM application developers**
- Building production LLM applications, hitting prompt management complexity
- Need multi-model routing but lack a clean abstraction

**Tertiary: Enterprises with LLM cost concerns**
- Paying for frontier models across all tasks
- Need declarative routing to cheaper specialist models for routine sub-tasks

---

## The human×AI Founding Story

SPL-Flow is itself a demonstration of its own thesis.

- **Idea**: surfaced during human meditation (domain expertise × intuition)
- **Prototype**: implemented in hours via human×Claude collaboration
- **Paper**: drafted same day via human×Claude
- **Startup vision**: co-developed via human×Claude strategic thinking
- **AI collaborators**: Claude (Anthropic) for implementation; Gemini (Google) for long-context research

The founding model is human×AI — and this partnership did not start with SPL.

Wen Gong has been collaborating with Claude since the early days of the platform,
choosing it over alternatives after direct comparison. That multi-year partnership
produced the ZiNets research program: semantic embedding geometry, manifold analysis
of multilingual embeddings, geodesic reranking for RAG — two papers now under peer
review at ICML 2026 and TMLR simultaneously. SPL emerged from the same partnership,
compressing years of accumulated intuition into a single Thursday morning insight
and a working prototype by evening.

The startup is not a pivot. It is the natural next stage of a research program
that has been bearing fruit precisely because the human×AI model works at depth,
not just at surface productivity.

The founder is already living the problem being solved: choosing Claude vs. Gemini
for different tasks is manual model routing. SPL-Flow automates and declares it.

---

## Roadmap

### Foundation — Done (Feb 2026)
- SPL engine v0.1.0 (`pip install spl-llm`)
- arXiv paper draft (vision + benchmarks)
- Apache 2.0 open source
- Three LLM adapters: Ollama, OpenRouter, Claude CLI
- FAISS + ChromaDB vector stores, SQLite persistent memory
- 58/58 tests passing

### v0.2 — The MapReduce Moment (3 months)
- CTE dependency graph + topological sort
- Parallel async CTE execution (`asyncio.gather`)
- Per-CTE model dispatch via adapter registry
- EXPLAIN shows per-CTE cost breakdown across models
- `examples/format-cte-join/` as reference implementation

### v0.3 — Model Intelligence (6 months)
- Model capability registry (cost, benchmarks, specializations)
- `USING MODEL AUTO FOR <task_type>` routing syntax
- Execution history → routing improvement feedback loop
- Full OpenRouter model catalog integration

### v0.4 — Platform Alpha (9 months)
- Async execution mode (`spl-flow submit`)
- SQLite-backed job queue
- Email result delivery
- PDF/Markdown document output
- Web dashboard (execution history, cost tracking)
- Waitlist + 10 design-partner customers

### v1.0 — Commercial Launch (12 months)
- Hosted SPL-Flow Cloud
- Team workspaces + shared model registry
- Scheduled executions + webhook/Slack delivery
- Pricing tiers live
- Seed round narrative ready

---

## What AI Cannot Substitute

Being honest about the startup path:

1. **First 10 paying customers** — requires direct human conversations, not code
2. **Pricing discovery** — nobody knows the right price until someone pays
3. **Fundraising relationships** — investors back people, not AI
4. **Resilience** — the first startup is emotionally harder than it looks

None of these are blockers. They are known variables to prepare for.

---

## Why Now

- LLM adoption is past the early-adopter phase — mainstream engineering teams are building
- The model zoo (OpenRouter 100+) exists and the routing problem is acute now
- SQL practitioners are the largest untapped LLM engineering audience
- The dbt precedent proves the open-source language + commercial platform model works
- human×AI development velocity means a solo founder can move at team speed
- The window to establish the declarative LLM query language standard is open today

SQL took 16 years from research paper (1970) to ANSI standard (1986).
The LLM equivalent has a shorter window — the ecosystem moves faster.
SPL-Flow aims to be the starting point for that standard.

---

## The Architectural Paradigm: A Return to the Mainframe Model

*Insight captured: February 15, 2026*

Computing has come full circle — but at a much higher level:

```
Mainframe era:   dumb terminal ──────────────────────── IBM mainframe
                 (thin client)                          (all compute)

Client-server:   thick client  ────── app server ────── database
                 (some compute)       (mid-tier)         (data)

Web era:         browser ────────── API server ────────── database
                 (thin)              (mid-tier logic)      (data)

LLM era:         browser/SPL ─────────────────────────── LLM providers
                 (thin client)                            (all compute)
                      │
                      └── mid-tier collapses into the SPL script itself
                          (a portable text file, runs anywhere)
```

The "application server" tier — which in traditional web architecture held
all the business logic — compresses into a `.spl` file. The orchestration
logic that used to require a backend server is now a human-readable,
version-controlled, portable text file. Deploy it anywhere the engine runs.

**The JCL analogy:**

IBM's Job Control Language (1964) was declarative scripts submitted to the
mainframe to describe jobs. SPL is to LLM providers what JCL was to the IBM 360.
The difference: JCL was notoriously cryptic. SPL reads like SQL.
Data engineers already know the grammar. That is the bet.

**The Unix pipe analogy:**

Each LLM is a process. SPL CTEs are pipes. The SPL file is the shell script.
Unix proved that composing many small sharp tools beats one monolithic program.
MoM is the LLM-era rediscovery of the same principle:
specialist models piped together outperform one expensive frontier model.

**The AI symphony:**

The user is the composer (describes intent in plain English).
Text2SPL is the arranger (translates to score).
SPL Engine is the conductor (dispatches to sections in parallel).
Each specialist LLM is an orchestra section.
The synthesis model is the mixing board that produces the final recording.

The composer does not need to know what instruments exist.
They describe the music; the conductor handles the rest.

**The edge inference layer:**

With LFM 1.3B running in WASM in the browser for Text2SPL,
and the SPL engine also compilable to WASM:

```
Browser
  ├── Text2SPL LFM (WASM, local, 80ms)    ← orchestration intelligence, edge
  ├── SPL Engine (WASM or lightweight JS)  ← orchestration execution, edge
  └── API calls out to LLM providers       ← heavy inference, cloud/local
        ├── Ollama (localhost, free)
        └── OpenRouter / Anthropic (cloud, pay-per-token)
```

Zero server infrastructure owned by Digital-Duck for the core execution path.
We own the score and the conductor's notebook. Not the orchestra hall.

**What Digital-Duck owns:**

The LLM providers own the instruments (they charge per token).
Digital-Duck owns:
1. The score format (SPL — open standard, Apache 2.0)
2. The conductor (SPL-Flow engine)
3. The conductor's notebook (RAG Vault — encrypted, personal, persistent)

The notebook is the moat. Every AI interaction a user has through SPL-Flow
enriches their personal RAG vault. That vault cannot be replicated by any
LLM provider — it is the user's own accumulated intelligence.

---

*SPL (open source engine): https://github.com/digital-duck/SPL*
*SPL-Flow (platform): https://github.com/digital-duck/SPL-Flow*
*Contact: wen.gong.research@gmail.com*
