# SPL-Flow Evaluation Dataset

A curated question set for measuring the accuracy of SPL-Flow's
**Text2SPL → Execute** pipeline end-to-end, using `claude_cli` as the
execution adapter.

Each question is run through the full pipeline:

```
Natural language question
        │
        ▼  api.generate()   [Text2SPL + RAG retrieval]
    SPL script              saved to data/eval/spl/<id>_<domain>.spl
        │
        ▼  api.exec_spl()   [parse → analyze → optimize → execute]
      Answer                saved to data/eval/results.csv
        │
        ▼
  Human review              fill in  correct (Y / N / ?)  and  notes
```

---

## Dataset Overview

| Domain | Questions | Topics covered |
|--------|-----------|---------------|
| `physics` | 20 | Schrödinger equation, Maxwell's equations, thermodynamics, quantum mechanics, cosmology |
| `math` | 20 | Group theory, Fourier analysis, topology, Gödel, Riemann hypothesis, calculus |
| `cs` | 20 | P vs NP, Turing machines, algorithms, OS, databases, networking |
| `chinese_language` | 20 | Grammar, characters, tones, classical vs modern, dialects, morphology |
| `python3` | 20 | GIL, decorators, MRO, memory management, data structures, dunder methods |
| `sql` | 20 | Joins, window functions, normalisation, indexes, transactions, OLAP vs OLTP |
| `data_engineering` | 20 | Kafka, Spark, medallion architecture, CDC, dbt, Lambda architecture |
| `classical_music` | 20 | Sonata form, fugue, Baroque/Classical/Romantic, Wagner, equal temperament |
| `oracle_bone_script` | 20 | 甲骨文 discovery, Shang Dynasty, 六书, decipherment, Yinxu, divination ritual |
| `movie` | 10 | Cinematography, narrative theory, film movements, Bechdel test, screen-writing |
| **Total** | **190** | |

Questions are intentionally non-trivial — they require specific factual
knowledge and are chosen so that a domain expert can clearly mark them
correct or incorrect.

---

## File Structure

```
dataset/eval/               ← version-controlled (this repo)
├── README.md               ← this file
├── questions.csv           ← 190 questions (id, domain, question)
└── run_eval.py             ← evaluation runner (Click CLI)

data/eval/                  ← gitignored (runtime outputs, can be large)
├── results.csv             ← answers + your Y/N/? marks
└── spl/
    ├── 001_physics.spl
    ├── 002_physics.spl
    └── ...                 ← one .spl file per question
```

`data/` is excluded from git (see `.gitignore`) because `results.csv`
grows with LLM responses and the `spl/` directory can hold hundreds of
generated files.

---

## Running the Evaluation

### Prerequisites

```bash
conda activate spl


# From the SPL-Flow project root
pip install -r requirements.txt

# Claude CLI must be authenticated
claude auth
```

### Quick smoke-test — one domain

```bash
python3 dataset/eval/run_eval.py --domain movie
```

### Run a specific set of domains

```bash
python3 dataset/eval/run_eval.py --domain movie
```

### Run everything except already-completed domains

```bash
# After finishing the movie smoke-test, continue with the rest
python3 dataset/eval/run_eval.py --exclude movie

# Skip multiple domains
python3 dataset/eval/run_eval.py --exclude movie,physics,math
```

### Restrict to a question-ID range

```bash
python3 dataset/eval/run_eval.py --start 1 --end 20
```

### Dry run — preview without calling the API

```bash
python3 dataset/eval/run_eval.py --domain movie --dry-run
```

### Full help

```bash
python3 dataset/eval/run_eval.py --help
```

---

## Incremental Execution

The script is **safe to interrupt and resume**.  On every run it reads
`data/eval/results.csv` and skips any question that already has an
answer.  This means:

- `Ctrl+C` mid-run → rerun the same command to continue from where it left off
- A question with an error (empty `answer`) will be **retried** on the next run
- Running the same domain twice will do nothing if all rows are already answered

---

## Reviewing Results

Open `data/eval/results.csv` in any spreadsheet application and fill in
two columns for each row:

| Column | Values | Meaning |
|--------|--------|---------|
| `correct` | `Y` | Answer is factually correct and complete |
| | `N` | Answer is wrong, missing key facts, or hallucinated |
| | `?` | Partially correct or impossible to verify without research |
| `notes` | free text | Specific errors, missing information, or observations |

### CSV schema

| Column | Description |
|--------|-------------|
| `id` | Question ID (1–190) |
| `domain` | Domain name |
| `question` | Original natural language question |
| `spl_generated` | `Y` if Text2SPL produced a valid SPL script |
| `spl_file` | Path to the generated `.spl` file |
| `answer` | LLM response (primary result from SPL execution) |
| `latency_s` | Wall-clock seconds for the execute step |
| `total_tokens` | Total tokens consumed |
| `error` | Non-empty if the run failed |
| `correct` | **Manual** — Y / N / ? |
| `notes` | **Manual** — free-form observations |

---

## Interpreting Accuracy

After marking all rows, compute per-domain accuracy:

```python3
import csv
from collections import defaultdict

rows = list(csv.DictReader(open("data/eval/results.csv")))
by_domain = defaultdict(lambda: {"Y": 0, "N": 0, "?": 0, "total": 0})

for r in rows:
    d = r["domain"]
    c = r["correct"].strip().upper() or "?"
    by_domain[d][c] += 1
    by_domain[d]["total"] += 1

for domain, counts in sorted(by_domain.items()):
    y = counts["Y"]
    n = counts["N"]
    t = counts["total"]
    pct = 100 * y / t if t else 0
    print(f"{domain:25s}  {y}/{t}  ({pct:.0f}%)  N={n}  ?={counts['?']}")
```

---

## Design Decisions

- **`claude_cli` adapter only** — consistent baseline; avoids cross-adapter
  variance in this first evaluation pass.
- **Text2SPL generates the SPL** — tests the full pipeline, not just the LLM's
  raw knowledge; accuracy reflects both routing quality and model capability.
- **Human verification** — LLM-as-judge is deliberately avoided here; the goal
  is a gold-standard labelled dataset built from domain-expert review.
- **SPL files preserved** — every generated `.spl` file is kept so you can
  inspect exactly what prompt was sent to the model and reproduce any run with
  `api.exec_spl(open("spl/001_physics.spl").read(), adapter="claude_cli")`.
