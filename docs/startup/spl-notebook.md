# SPL-Notebook — Product Vision

*February 2026 | Digital-Duck LLC*
*Captured via human×AI strategy session*

---

## The Real Pain Point (Relatable, Not Technical)

Every power AI user today lives this problem:

```
Monday:   Great conversation with Claude about my research paper
Tuesday:  Continued with ChatGPT — it had better context on X
Thursday: Used Gemini for the long document — 1M context window
Friday:   Can't find any of it. Which AI said what? Where is it?
```

**The fragmentation problem:**

| Where | What happens to your data |
|-------|--------------------------|
| Claude.ai | Anthropic's servers. They own it. You can't export easily. |
| ChatGPT | OpenAI's servers. They own it. May train on it. |
| Gemini | Google's servers. They own it. |
| Local Ollama | Your machine. You own it. But no sync, no search, no history. |

Result: your AI knowledge is **scattered, unowned, unsearchable, and fragile**.
Every conversation is a silo. Every provider is a walled garden.

**The subscription problem:**

| Subscription | Cost/month |
|-------------|-----------|
| Claude Pro (Anthropic) | $20 |
| ChatGPT Plus (OpenAI) | $20 |
| Gemini Advanced (Google) | $20 |
| Perplexity Pro | $20 |
| **Total** | **$80+/month** |

Four separate accounts. Four billing relationships. Four sets of API keys.
No single view of what you've done, what it cost, what worked best.

**SPL-Flow solves both problems with one platform.**

---

## The Vision: One Encrypted Vault for All Your AI

```
Before SPL-Flow:                    After SPL-Flow:

Claude.ai  ──┐                      ┌─────────────────────────────┐
ChatGPT    ──┤  (scattered,         │  SPL-Notebook               │
Gemini     ──┤   unowned,           │  ├── All AI sessions         │
Perplexity ──┘   fragile)           │  ├── Cross-model search      │
                                    │  ├── Your data, encrypted     │
                                    │  ├── One subscription         │
                                    │  └── One interface            │
                                    └─────────────────────────────┘
                                          │         │         │
                                        Claude    GPT-4    Gemini
                                        Ollama  Mistral   Qwen2.5
```

**The positioning statement:**

> "All your AI conversations — one encrypted vault.
>  All the models — one subscription.
>  Your data, your control."

This is not a technical pitch. It is a user rights pitch.

---

## SPL-Notebook: The Jupyter for AI Orchestration

### The Jupyter analogy

| Jupyter Notebook | SPL-Notebook |
|-----------------|--------------|
| Python kernel (computation engine) | SPL Engine (MoM orchestration) |
| Code cells | SPL script cells |
| Markdown cells | Markdown cells |
| Output cells | AI-generated output (table, audio, image) |
| Kernel state | RAG context (persistent memory) |
| `.ipynb` file format | `.splnb` file format |
| nbviewer (static share) | SPL-Notebook share link |
| Binder (live, runnable) | SPL-Notebook live run |
| JupyterHub (hosted) | Digital-Duck platform (hosted) |

### The `.splnb` file format

A `.splnb` file is human-readable JSON — version-controlled, portable, shareable:

```json
{
  "version": "0.1",
  "metadata": {
    "title": "日-Family Chinese Characters — Multilingual Study",
    "author": "wen.gong@digital-duck.io",
    "created": "2026-02-14",
    "tags": ["zinets", "chinese", "日-radical", "multilingual"]
  },
  "context": {
    "rag_collection": "zinets-radicals",
    "params": {"radical": "日"},
    "adapter": "openrouter"
  },
  "cells": [
    {
      "type": "markdown",
      "source": "# 日-Family Exploration\nStudying characters built on the sun radical."
    },
    {
      "type": "spl",
      "source": "PROMPT table USING MODEL auto\nWITH chars AS (...)\nWITH german AS (...)\nWITH insights AS (...)\nSELECT compose_table(...)\nWITH OUTPUT FORMAT markdown;"
    },
    {
      "type": "output",
      "format": "markdown",
      "model": "claude-sonnet-4-5",
      "tokens": 775,
      "cost_usd": 0.002,
      "content": "| Character | Formula | Pinyin | English | German | Insight |\n..."
    }
  ]
}
```

### What you can do with a `.splnb`

- **Run it**: `spl-flow run my_notebook.splnb --param radical=水`
- **Version it**: git-diffable JSON, branch per experiment
- **Share it**: publish to SPL-Notebook community (static view or live-runnable)
- **Fork it**: take someone's public notebook, adapt to your domain
- **Schedule it**: run every Monday, get results in your inbox
- **Embed it**: drop a live SPL-Notebook into a Notion page or web app

---

## RAG Vault: Your Encrypted AI Memory

### The three-model reference stack

| Reference | What they do well | What we borrow |
|-----------|------------------|----------------|
| **Gmail** | Hosts your email archive, great search, great UI | Host the storage, monetize the service |
| **ProtonMail** | Zero-knowledge encryption — can't read your mail even if asked | Privacy-first trust contract, E2EE |
| **Notion** | Beautiful blocks-based UI, templates, sharing | Content management + community marketplace |
| **Jupyter** | Interactive cells, shareable notebooks, cloud hosting | Notebook format + live-runnable sharing |

### The encryption architecture

```
Your RAG Vault:
  ├── Documents encrypted at rest (AES-256)
  ├── In transit: TLS 1.3
  ├── Zero-knowledge option: client-side encryption before upload
  │     └── Digital-Duck sees only ciphertext — legally and technically
  └── Key management:
        ├── Managed key  (convenient, standard)  ← most users
        └── Self-managed key (fully private, user's responsibility) ← power users

Sharing model:
  ├── Private     — only you (default)
  ├── Link share  — decryption key in URL (like Notion share links)
  ├── Team        — org-level shared key
  └── Public      — user explicitly removes encryption for community sharing
```

### The digital twin

Your RAG Vault is not static storage. It grows into a model of you:

**For ZiNets learners:**
- Session 1: knows nothing → teaches 日
- Session 50: knows your tonal error patterns, native language interference, preferred examples
- Session 200: knows your vocabulary level, your learning pace, your cultural references
- The tutor that emerges from session 200 is qualitatively different from session 1
  — not because the model changed, but because the context grew

**For developers:**
- Accumulates preferred model choices, domain documents, reusable CTE patterns
- SPL scripts get smarter with each run as context injection gets richer
- Cross-project knowledge (what worked in project A helps project B)

The digital twin is not a feature — it is the moat.
Once a user has 6 months of AI interaction history in Digital-Duck's vault,
they will not leave.

---

## Subscription Consolidation: One Key to All Models

### The problem today

Users who work with multiple LLMs manage:
- 3-4 separate provider accounts and billing relationships
- Multiple API keys (Anthropic, OpenAI, OpenRouter, Gemini)
- Rate limits across different dashboards
- No unified cost visibility

### What Digital-Duck provides

```
User pays: Digital-Duck subscription
                  │
                  ▼
Digital-Duck manages:
  ├── Anthropic API key  ──► Claude models
  ├── OpenAI API key     ──► GPT-4o, o3
  ├── OpenRouter key     ──► 100+ models
  └── Local Ollama       ──► on-device models (free tier)

User sees:
  ├── One login
  ├── One billing statement
  ├── One cost dashboard (per-model, per-notebook, per-month)
  └── All models via one SPL interface
```

**BYOK option (Bring Your Own Key):**
Power users who want direct cost control keep their own API keys.
Digital-Duck stores them encrypted; never sees plaintext.
Users pay providers directly, pay Digital-Duck for platform only.

### Tier design

| Tier | Storage | Models | Sync | Price |
|------|---------|--------|------|-------|
| **Self-hosted** | Local file | All (your keys) | None | Free (open source) |
| **Free cloud** | 100MB encrypted vault | Managed tier | Cross-device | $0 |
| **Pro** | 10GB vault + history | All managed | Cross-device + backup | $29/mo |
| **Team** | 100GB shared vault | All + priority | Team sync + admin | $99/mo |
| **Enterprise** | Unlimited + private deploy | Custom fleet | On-prem option | Custom |

The self-hosted tier is the open-source SPL engine.
It is the community acquisition channel — developers love it, then upgrade.

---

## Sharing & Community: The Notion + GitHub Layer

### What users share

| Object | Share format | Analogy |
|--------|-------------|---------|
| SPL script | Syntax-highlighted, runnable | GitHub Gist |
| RAG context (curated subset) | Public knowledge base | Notion page |
| Full `.splnb` notebook | Static view or live-runnable | nbviewer + Binder |
| AI output | Rendered markdown/table/image | Notion published page |
| Full experience | Notebook + context + output bundled | Notion template |

### The community flywheel

```
Power user creates:
  "Complete 水-family lesson with audio + visual mnemonics"
  (SPL script + curated RAG context + sample output)
        │
        ▼ publishes to SPL-Notebook Community
        │
        ▼
Beginner finds it, runs it with their own RAG profile merged in
Lesson adapts to their level → they learn faster → they stay
        │
        ▼
They create their own notebook, publish it
        │
        ▼
Community catalogue grows → more users discover Digital-Duck
        │
        ▼ (flywheel)
```

This is the Notion template marketplace + Figma community model.
User-generated content creates the catalogue.
The catalogue attracts the users.
The users create the content.

---

## Technical Challenges

### Hard problems (require real R&D)

**1. Searchable encryption**
Zero-knowledge means the server can't see plaintext — but you still need to
search across thousands of encrypted documents. Approaches:
- Client-side search: decrypt locally, search locally. Works; slow at scale.
- Searchable Symmetric Encryption (SSE): cryptographic primitive allowing limited
  search on ciphertext. Research-grade, not production-ready at scale yet.
- Practical compromise: encrypt content, store embeddings separately with
  a clearly communicated privacy tradeoff. Users choose their level.

**2. Vector store sync**
FAISS has no built-in replication. Need to build:
- Delta sync protocol (only new vectors since last sync)
- Conflict resolution (offline edits on two devices)
- Versioned snapshots for rollback
- This is a non-trivial distributed systems problem.

**3. Multi-modal RAG**
Text embeddings are solved. Audio and image retrieval are harder:
- Audio: transcribe first (Whisper), then embed text? Or embed audio directly?
- Image: CLIP embeddings for cross-modal retrieval? Or describe first, then embed?
- Cross-modal retrieval ("find the image that goes with this text") is still
  an active research problem.

**4. Browser-native SPL engine**
Running SPL engine in WASM requires:
- Python → WASM (Pyodide works but is heavy ~50MB)
- Or: rewrite SPL engine in Rust/Go for lean WASM target
- LFM 1.3B in WASM (Liquid AI is working on this; not production-ready yet)
- Browser sandbox limits raw TCP connections — Ollama calls need a local bridge.

**5. Right to deletion (GDPR)**
"Forget me" in a vector store is non-trivial:
- Can't just delete the source document — the embedding is baked into the index
- True deletion requires re-indexing the entire collection without that document
- At scale (millions of users, large vaults): computationally expensive
- Need an architectural solution upfront, not a retrofit.

### Medium problems (solved with engineering effort)

**6. SPL-Notebook format stability**
`.splnb` format must be defined carefully:
- Backwards-compatible versioning from day 1
- Output cells: how to store multi-modal outputs (audio bytes? image URLs? inline base64?)
- RAG references: how to refer to a collection that might not exist on another machine

**7. Cold start**
RAG Vault is empty for new users. Value accumulates over time.
Need to provide immediate value before the digital twin effect kicks in.
Solution: community-curated starter RAG packs (e.g., "ZiNets 400-character foundation").

**8. Context relevance degradation**
As the vault grows to thousands of documents, retrieval quality can degrade.
Need: hierarchical indexing, active pruning of stale context, user-controlled curation.

---

## Business Challenges

### Hard problems (require time and trust-building)

**1. The trust gap**
"We can't read your data" is a claim, not a proof.
Building cryptographic trust requires:
- Open-sourcing the encryption layer (auditability)
- Third-party security audits (SOC 2, ISO 27001 for enterprise)
- Bug bounty program
- Time and track record — trust is earned slowly, lost instantly.

**2. Network effects take time**
The community notebook marketplace is empty on day 1.
A marketplace with no content has no value.
Need a seeding strategy: curate the first 50 high-quality notebooks in-house.
Build the community before launching the feature.

**3. Open source tension**
SPL engine is Apache 2.0. If Digital-Duck's RAG service is too good,
the community might build a self-hosted alternative (Supabase vs Firebase dynamic).
Mitigations:
- Keep the sync protocol proprietary (the hosted service has moat)
- Compete on UX, not on features the community can replicate
- Embrace self-hosted: it's the acquisition channel, not the threat.

**4. LLM provider dependency**
If Anthropic raises API prices, or OpenRouter changes terms,
or OpenAI deprecates a model — the core product is affected.
Mitigations: adapter pattern (swap providers without user impact),
multi-provider redundancy, Ollama as always-available local fallback.

### Medium problems (solvable with execution)

**5. Two markets simultaneously**
Developers (SPL-Notebook as power tool) and consumers (ZiNets learners)
require different UX, different go-to-market, different support.
Recommendation: pick one to lead with. Developers first (open source acquisition),
consumers second (once platform is stable).

**6. Pricing the vector storage**
Vector storage costs more than blob storage:
- S3/GCS: ~$0.023/GB/month
- Managed vector stores: ~$0.10/1M vectors/month
- Need unit economics per user before setting Pro tier price.
- Risk: underpricing storage at scale.

**7. Regulatory complexity**
GDPR: right to erasure (vector re-indexing problem — see Technical #5)
CCPA: California data residency
Enterprise: data sovereignty requirements (EU customers may need EU-only storage)
These are solvable but require legal + infrastructure investment upfront.

**8. Execution bandwidth**
The full vision:
SPL engine + SPL-Flow + SPL-Notebook + RAG Vault + Community Hub + ZiNets + Text2SPL LFM
— is enormous for a small team.
Ruthless prioritization is existential. Ship the SPL-Notebook format and local RAG first.
Cloud sync and community hub come later, when there are users who need them.

---

## The Phased Build Path

### Phase 1 — Local + Import-First (MVP, now)

**The killer Day 1 feature: import your existing AI chat history.**

Every power AI user has years of valuable conversations scattered across providers.
They cannot search across them. This is the immediate, relatable pain point.

```
Import parsers (boring engineering, high impact):
  ChatGPT  → Settings → Export data → conversations.json  (documented format)
  Claude   → Settings → Export data                        (documented format)
  Gemini   → Google Takeout → JSON/HTML                   (documented format)

All sessions → local FAISS index (~/.spl/vault/)

Search UI:
  "where did I discuss manifold learning?"
  → Claude session, Jan 15  |  ChatGPT session, Feb 3
  filter: by date / by model / by topic
```

**Why personal search is technically simple (key insight):**
The search is on the user's OWN data, not global search across all users.
When the user is authenticated, their decryption key is available.
Search runs against their decrypted personal vectors.
No cryptographic gymnastics (SSE, homomorphic encryption) required.
Same model as Gmail: encrypted at rest, searchable when you're logged in.

```
Full Phase 1 scope:
  ✓ SPL engine + SPL-Flow MVP (done, Feb 2026)
  ○ .splnb file format spec
  ○ Local RAG vault: ~/.spl/vault/ (FAISS, no sync needed)
  ○ Import parsers: ChatGPT / Claude / Gemini
  ○ Semantic search UI over personal vault
  ○ Every new SPL-Flow session auto-saved to vault

Value delivered before any cloud infrastructure:
  unified search across ALL your AI conversations, locally, privately.
```

### Phase 2 — Cloud Sync (3-6 months)

```
  Digital-Duck account + encrypted vault
  Cross-device sync (delta sync protocol)
  Backup and version history
  Value: one place for all AI history, accessible anywhere
```

### Phase 3 — Community (6-12 months)

```
  Public notebook sharing
  Starter RAG packs (curated in-house, then community-seeded)
  Fork + remix workflows
  Value: network effects begin — catalogue attracts users
```

### Phase 4 — Subscription Consolidation (12+ months)

```
  Digital-Duck manages API keys to LLM providers
  One billing relationship replaces 3-4 subscriptions
  Unified cost dashboard across all models
  Value: subscription simplification, broader audience
```

---

## Revised Positioning (Two-Line Pitch)

**Technical audience:**
> "SPL-Flow is declarative LLM orchestration — SQL for the model zoo."

**Everyone else:**
> "All your AI conversations, one encrypted vault. All the models, one subscription.
>  Your data. Your control."

Both are true. Lead with the second one.

---

*Document owner: Digital-Duck LLC*
*Related: `docs/startup/architecture.md`, `docs/startup/vision.md`*
*Related: `biz-dev/liquid_ai/readme.md`*
*Last updated: February 2026*
