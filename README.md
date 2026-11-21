# KRONOS — Connecting Evidence. Reconstructing Truth.

**AI-assisted digital investigation platform** · Smart India Hackathon — Problem Statement 5 · Team Nexora

KRONOS brings FIRs, call records, location data, financial transactions, social-media messages and criminal history into one
time-ordered evidence base. It analyses them with explainable engines and answers investigators' questions with a
**local** AI (Llama 3.1 8B), so no investigation data leaves the machine. Every statement it makes cites the evidence it rests on.

![KRONOS home](backend/docs/screenshots/after/premium_home_3d.png)

## What it does

| Problem Statement 5 asks for | In KRONOS |
|---|---|
| Natural-language querying, conversational assistant | Local Llama 3.1 assistant: retrieval over the evidence, citations on every point, removal of invented IDs, a grounding check. Facts mode and Detective mode. Answers in English, Hindi, Gujarati and Punjabi |
| Context-aware evidence search | Plain-language search that turns a question into explainable filters, plus full-text and vector search |
| Case summarisation, draft reports, case diary | Case summary, a 10-section draft report and a BNSS-style case diary, printable and multilingual |
| Suspicious patterns | Financial anomalies (Isolation Forest, IQR, pass-through, structuring, fan-in), impossible travel, contact bursts, co-location, cross-case links |
| Investigative leads | Hypotheses with supporting **and** contradicting evidence, investigative priority (never a guilt score), next-best-evidence recommendations |

**The five novelties:**
- **Impossible travel:** Haversine distance against time, adjusted for location accuracy.
- **Fuzzy identity matching:** combines identifiers and behaviour, and never merges records automatically.
- **Next best evidence:** recommendations ranked by a value score.
- **Federated learning + evidence ledger:** 4 agencies; SHA-256 hash chain with Merkle proofs and Ed25519 signatures.
- **Criminal-history linkage:** prior records are shown as context only.

**Also included:**
- A **Temporal Engine** on the home page: replay anyone's recorded activity and check the feasibility of every move.
- A **3D network graph** with a GNN (GraphSAGE).
- **40 real High Court cases** (pseudonymised).
- A locally **fine-tuned** model (an experiment; results below).

| Temporal engine | Case workspace | 3D network graph |
|---|---|---|
| ![temporal](backend/docs/screenshots/after/home_temporal_impossible_travel.png) | ![case](backend/docs/screenshots/after/premium_case.png) | ![graph](backend/docs/screenshots/after/premium_graph.png) |

## Run it

**Hardware:** 16 GB RAM is recommended for the AI, plus about 10 GB of free disk. Tested on macOS (Apple Silicon). Linux should work; on Windows, use WSL2 (Ubuntu).

**Prerequisites:**
- Python 3.11+
- PostgreSQL with pgvector
- Node.js 18+
- [Ollama](https://ollama.com) (optional; without it everything works except the AI assistant)

```bash
# macOS (Homebrew):  brew install python@3.12 postgresql@16 pgvector node ollama && brew services start postgresql@16
# Ubuntu:            sudo apt install python3.12-venv postgresql postgresql-16-pgvector nodejs npm && sudo -u postgres createuser -s $USER
git clone https://github.com/chintansood/KRONOS.git && cd KRONOS
./setup.sh      # creates the environment and database, downloads the AI models (~5 GB), generates the data, builds the site (~10 min)
./run.sh        # → http://localhost:8000
```

`setup.sh` produces a reproducible synthetic investigation world (seed 42: 40 cases, about 28,000 records across 5
sources, plus criminal history). It runs every engine, loads the real court cases and builds the website. The tests run
with `cd backend && .venv/bin/python -m pytest tests` (28 tests).

## Data and privacy

- **Synthetic investigation data.** People, calls, locations, payments and messages are generated, including deliberate traps (namesakes, households sharing a phone, aliases, flights, legitimate large payments). Detectors can therefore be scored against ground truth.
- **40 real criminal cases** from Punjab & Haryana High Court orders (open dataset, CC-BY-4.0, Dattam Labs / eCourts):
  - The real FIR particulars are kept: number, date, police station, sections, outcome.
  - **Every person is pseudonymised** ([Accused A1], [Complainant C1]); phones, vehicle numbers and addresses are masked.
  - Sexual-offence, POCSO, juvenile, kidnapping, matrimonial and SC/ST cases are excluded.
  - The real people are never matched against other records.
  - The original documents and the extracted text are **not** in this repository; only the pseudonymised records are.
  - See `backend/docs/PUBLIC_RECORDS.md`.
- **Local AI only.** Answers come from Llama 3.1 running on the machine via Ollama, and nothing is sent to an external AI service.

## Results (honest)

On the synthetic ground truth, which shows the methods work as designed rather than predicting real-world accuracy:

| Check | Result |
|---|---|
| Identity matching | Precision and recall 1.0, including 4 identity switches that share no identifier; held-out worlds 0.92 |
| Impossible travel | 9 of 9 |
| Criminal-history links | Precision 1.0, no false links to same-name strangers |
| Financial anomalies | Precision 0.80, recall 0.78 |
| Evidence ledger | Verifies; tampering is detected |

For the AI assistant on 39 unseen questions:

| | Base model | Fine-tuned (QLoRA) |
|---|---|---|
| Overall pass rate | 56% | 67% |
| Abstains correctly | 50% | 100% |
| Cites the key evidence | 88% | 44% |

The base model stays the default; see `backend/docs/FINETUNING.md`.

**Not built:**
- vision and audio (ASR) pipelines;
- surveillance reports;
- Neo4j (the graph uses NetworkX);
- full sequence mining.

## Repository layout

```
frontend/   the KRONOS website (single-page app; kronos-live.js connects it to the API; premium + temporal layers)
backend/    FastAPI + PostgreSQL/pgvector + engines (ingestion, temporal, graph/GNN, identity, intelligence, LLM, ledger,
            federated, real-records pipeline, fine-tuning)  ·  docs/ has the details and screenshots
setup.sh    one-command setup        run.sh    start on http://localhost:8000
```

Every analytical output is an **investigative aid with evidence references, not a finding of guilt**.
