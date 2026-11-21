# KRONOS Backend — Criminal Network Intelligence & Digital Investigation API

Backend for the KRONOS investigator interface (`../kronos-app/index.html`). It is built from scratch and runs fully locally: PostgreSQL with pgvector for storage, and Ollama (Llama 3.1 8B plus nomic-embed-text) for the LLM. No case data leaves the machine.

> Every analytical output here (flags, rankings, hypotheses, identity and prior-record links) is an **investigative aid with evidence references, not a finding of guilt**. The investigation world is synthetic. 40 real court cases are included in pseudonymised form.

## Quick start

```bash
# prerequisites: PostgreSQL 15+ with pgvector, Ollama with llama3.1:8b and nomic-embed-text
createdb kronos
python3 -m venv --system-site-packages .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                      # optional; defaults work for a local setup

.venv/bin/python scripts/build_all.py --generate   # generate → ingest → analyse → index (~2 min)
.venv/bin/python scripts/evaluate.py               # ground-truth evaluation (synthetic data only)
.venv/bin/python -m uvicorn kronos.api.main:app --port 8000

cd ../kronos-app && npm run dev           # http://localhost:5173 — Vite proxies /api → :8000
.venv/bin/python -m pytest tests          # 28 tests
```

If the API is not reachable, the website automatically falls back to its original offline demonstration data, so static deploys keep working.

## Problem Statement 5 coverage

| PS5 requirement | Implementation | Where |
|---|---|---|
| Natural-language querying of forensic evidence | Intent routing to the engines, hybrid retrieval and local Llama 3.1, with citation filtering and a line-level grounding check | All chats; `POST /api/assistant/query` |
| Context-aware evidence search / **evidence retrieval engine** | Natural-language queries are parsed into inspectable filters (type, amount range, dates, time of day, persons, places, phones/accounts/devices, flagged only), combined with full-text and vector matching. The open case/person and earlier conversation boost ranking, and every result says why it matched. Hindi/Gujarati/Punjabi queries are accepted. | Case tab 3 search box; the assistant; `GET /api/search/evidence` |
| Automated case summarization | `generate_case_summary()` produces JSON and TXT, an optional LLM narrative, and data-hash staleness checking | Case tab 1; `GET /api/cases/{id}/summary(.txt)` |
| Suspicious patterns and anomalies | Financial (5 detectors), impossible travel, bursts, co-location, identity switches, cross-case links, hidden links | Timeline flags, case tabs, alerts |
| Recommendation of investigative leads / **investigative recommendation module** | Next-best-evidence with value scores, investigative priority, and two-sided hypotheses | Case tab 2, dossier, Detective mode |
| Generation of draft case reports | 10-section printable draft (brief facts, persons, chronology, exhibits with SHA-256 and ledger blocks, findings, hypotheses, pending steps, prior records as context, uncertainties, integrity) | Case tab 5; `GET /api/cases/{id}/report.html` |
| **Conversational forensic assistant** | Multi-turn: follow-ups are rewritten into standalone questions ("what about **him**?" becomes the person), and entities carry over only on genuine follow-ups | Dossier, home and Copilot chats |
| **Automated case diary generator** | Draft day-by-day diary in BNSS s.192 structure, built only from recorded events, KRONOS activity on the ledger and IO entries (which are themselves ledger-recorded) | Case tab 5; `GET /api/cases/{id}/diary(.html)`, `POST …/diary/entries` |
| **Multilingual interface** | English, Hindi, Gujarati and Punjabi. Questions in any of them are understood; answers and documents come back in the question's or the selected language. Identifiers, amounts and dates are masked during translation, and any line that loses one or gains an invented number is rejected and shown in English. The verified English text is always attached. | Language setting (now with Punjabi); all chats; documents (`?lang=`) |

Multilingual quality: Hindi is good (5 of 5 test lines accepted). Gujarati is limited (accepted lines keep every identifier, but wording can be imprecise). Punjabi is limited (about 3 of 5 lines; the rest stay in English). A dedicated Indic translation model (e.g. AI4Bharat IndicTrans2, offline) would raise Gujarati/Punjabi quality. Answers in another language take about 1 minute on this 16 GB laptop.

## The five novelties (Technical Approach slide)

| Novelty | What is implemented | Where it shows in the UI | Result on synthetic ground truth |
|---|---|---|---|
| **Impossible travel** (location-time anomalies, travel feasibility) | Haversine distance between consecutive geolocated records, minus both records' accuracy radii, divided by elapsed time. Verdicts are `IMPOSSIBLE`, `REQUIRES_AIR_TRAVEL` or `SIMULTANEOUS`, against configurable thresholds (150 km/h road, 950 km/h air). Feasibility is reported for **every** pair checked, not just flags. | Dossier "Travel feasibility" line; ⚠ timeline events; alerts; case observations | Main data: 9 of 9 injected cases found; the only other flags are 3 genuine flights, labelled "requires air travel". Held-out seeds: 10 of 10 and 10 of 10. Cell-tower handovers are not flagged. |
| **Fuzzy identity matching** (behavioural patterns, cross-source mapping) | Multimodal evidence: names and nicknames, FIR aliases, father's name and stated address from FIR "S/o … R/o …", shared phone, handset, SIM and account. **Behavioural** evidence: rarity-weighted social circle, routine places, night-time area, daily rhythm and activity hand-off. Graph neighbourhood overlap. Contradictions: the two records contacting each other, being active far apart at the same moment, or different father's names. Behaviour alone can reach at most `MEDIUM`, and records are **never** merged automatically; Confirm / Reject / Defer are audited. | Dossier "Possible same person" box (band, basis, reasons, contradictions, review buttons) | Main data: 12 of 12 true pairs found at precision 1.0, including **4 identity switches sharing no identifier**. Namesakes and households that share a handset and home are all `INSUFFICIENT_EVIDENCE`. Held-out seeds: precision 0.92 and 1.0, recall 0.92 and 0.92 (one switch per seed reaches only `LOW`). |
| **Next best evidence** (prioritised list, actions based on confidence scoring) | Recommendations typed as AVAILABLE / AVAILABLE_NOT_RETRIEVED / TO_BE_OBTAINED / CANNOT_VERIFY. Each has an explainable **value score**: 0.30 × uncertainty reduction (how unresolved the related hypothesis is) + 0.30 × finding strength + 0.20 × subject priority + 0.20 × obtainability, plus 0.15 if it could clear someone. CCTV retention is accounted for. Hypotheses carry an **evidential balance** (weighted support vs contradiction) and completeness, explicitly *not* a probability of guilt. | Case workspace, tab 2 (score breakdown per item, editable status); dossier panel | Falsely accused case: hypothesis "leans contradicting / unresolved"; alibi verification ranks first. Burner case: identity-switch verification ranked `HIGH`. |
| **Federated learning + blockchain** (train across state units without sharing raw data; hash evidence on chain for chain of custody) | **FL:** 4 state-agency nodes (CHD, PB, HR, DL) train locally; only HMAC-signed weight updates leave a node; FedAvg or median aggregation; versioned global model; a poisoning test. **Ledger:** SHA-256 hash chain recording ingest, access, verify, case edits and reviews; a **Merkle tree per ingested file** with its root signed by the 4 agency nodes (Ed25519, 3-of-4 quorum); per-record inclusion proofs; custody history. | Case tab 4 live panel (FL results, "run" button, anchors and quorum); evidence drawer (verify, Merkle proof, chain of custody) | FL: global model AUC 0.989 / AP 0.831, matching centralised training (0.990 / 0.831) without pooling data. Ledger: chain valid; 6 of 6 anchors with quorum; altering one stored field makes the proof fail, and restoring it makes it pass again. |
| **Case intake** (register a new case: form, Copilot conversation, home page) | A 10-step intake covers the FIR particulars: station, district, state unit, FIR number (next in the station's sequence), registration time, type of information; offence category with usual Acts & Sections; occurrence time and place (known places add coordinates) and delay reason; complainant; accused (known or unknown, alias, father's name, address, phone); victims and witnesses; property, accounts, vehicles, devices; the statement (a draft can be composed from the particulars); officer. Before saving, `/api/intake/check` shows people already on record (same phone, account or name) and identifiers already seen in other cases. **A person is linked to an existing record only if the investigator chooses it.** Registration runs the same pipeline as bulk ingestion: FIR loader, SHA-256 hash, ledger block and Merkle anchor, recorded roles, NER, identity candidates for the new people (never merged), prior-record linkage, case summary and retrieval index (~10 s). Withdrawing a case keeps the original ledger blocks and records the withdrawal; withdrawn case and FIR numbers are never reissued. Protected categories (sexual offences, POCSO, juvenile, kidnapping, matrimonial cruelty, SC/ST atrocities) are refused. Submissions are saved in `data/intake/` and replayed by `build_all.py`. | Home section 05, dashboard **+ New case**, Copilot or home chat ("add a new case"), `POST /api/cases`, `DELETE /api/cases/{id}` | Cyber-fraud complaint naming an accused whose phone and account are already on record: matched to P00023 (and the alias record P00024); phone and account found in CASE002, CASE019 and CASE022. |
| **Alternate hypotheses** (why a person may *not* have been involved) | Each line of inquiry ("P may have been involved") is tested against 8 alternate hypotheses built from the same records: A1 alibi (recorded elsewhere; only a partial alibi if the scene was reachable by road in time), A2 routine presence near the scene, A3 another user of the handset, A4 a legitimate purpose for the money or a co-holder, A5 a contact that predates the incident, A6 named or given a role in error, A7 mistaken identity (namesakes), A8 unreliable location records (impossible travel, low accuracy). Each alternate has a strength (1 − e^(−1.6·Σw), diminishing returns), cited evidence and *the test that would settle it*. Each supporting item lists the alternates that could explain it away. Items no alternate explains are the diagnostic ones. A verdict compares the two sides (line of inquiry / alternate / open), starting from the presumption of innocence; no strength is a probability. | Case tab 2 (side by side), dossier card, case report §6, the assistant ("why may P00371 not be guilty?") | CASE006 P00371: alibi **Strong** (recorded 278.5 km away, scene unreachable by road), so the verdict favours the alternate. CASE013 P00013: shared handset with P00014. CASE019 P00024: location records unreliable. |
| **Criminal history linkage** (linking criminal profiles, network relationships, associated cases) | A 6th data source, `CRIMINAL_HISTORY.csv` (prior arrests, charge-sheets and court records with no KRONOS IDs). Linked through name, alias, father's name, phone and address. A different father's name is a contradiction, and a different first name is capped at `LOW` because a sibling looks the same otherwise. Prior records are also reached through possible identities, and network-associated cases are found via associates and shared identifiers. Prior records are **context only**: excluded from priority and hypothesis scores, with dispositions (e.g. acquitted) always shown. | Dossier "Criminal history linkage" box (Confirm / Reject link); hypotheses as unscored context; the assistant | Main data: precision 1.0, recall 0.78. **0 wrong links** for 13 same-name strangers and 6 namesake traps. Held-out seeds: precision 1.0, recall 0.71 / 0.65; unlinked true records are name-and-city-only matches, correctly left at `LOW`. |

## Pipeline

| Stage | Module | What it does |
|---|---|---|
| Synthetic data | `kronos/synth/` | Simulates people moving through 37 real places on daily routines, with case scenarios and counter-examples layered on top. These include aliases, identity switches, namesakes, households, flights, legitimate large payments and same-name prior records. Writes 6 interlinked CSVs plus `ground_truth.json` (used for evaluation only). Configurable and seeded. |
| Ingestion | `kronos/ingestion/` | One loader per source plus timestamp normaliser, normaliser and schema validator. Original rows are kept unmodified in `raw_records`; bad fields are nulled and logged, and bad rows are quarantined, never dropped. |
| Multimodal engine (case) | `engines/multimodal/` | Rule and gazetteer NER (roles, aliases, S/o and R/o particulars), financial anomalies (Isolation Forest, IQR, pass-through, split, structuring, fan-in), communication and location analysis, case synthesis, and `generate_case_summary()`. |
| Temporal engine (person) | `engines/temporal/` | Timelines, daily routine with gaps, bursts, co-location, impossible travel and feasibility. |
| Graph engine | `engines/graph/` | Heterogeneous graph with centrality, Louvain communities, paths, cross-case links, Adamic–Adar candidates and a GraphSAGE link predictor. |
| Identity and history | `engines/identity/` | Identity resolution (above) and criminal-history linkage (above). |
| Intelligence | `engines/intelligence/` | Investigative priority (factor contributions; not a guilt score), the hypothesis engine with evidential balance and alternate hypotheses (`alternates.py`), and next-best-evidence with value scores. |
| LLM layer | `engines/llm/` | Hybrid retrieval (pgvector + full-text, RRF), intent routing to the engines, token-budgeted batching, Assistance and Detective prompts, citation filtering, and a line-level grounding check. |
| Provenance | `engines/provenance/ledger.py` | Hash chain, Merkle anchors, agency signatures, inclusion proofs and custody history. |
| Federated | `engines/federated/fedavg.py` | Multi-agency training simulation. |

## Other evaluation results (`scripts/evaluate.py`, main dataset)

| Capability | Result |
|---|---|
| FIR recorded roles | 158 of 171 FIR-named persons correct; 0 wrong, 0 spurious |
| Financial anomalies (any detector) | Precision 0.80, recall 0.78 (held-out seeds: 0.83 / 0.80 and 0.81 / 0.89) |
| Link prediction | GraphSAGE AUC 0.825 ± 0.009 over 5 training seeds vs Adamic–Adar 0.764 on this dataset. On the previous dataset version it **lost** (0.72 vs 0.75), so the advantage is data-dependent. The report states which one wins on each run. |

These numbers come from synthetic data generated by this project, so they show that the methods behave as designed. They do not predict real-world performance. The thresholds were set on the main seed and then checked on two unseen seeds.

## Fine-tuned model and real court cases
- **Fine-tuned LLM (QLoRA, fully local):** 805 training examples were generated from the production prompts of a separate synthetic world, and Llama 3.1 8B was trained for 220 steps with MLX on the M4.
  - Evaluated on 39 unseen questions: overall 56% → 67%, abstention 50% → 100%, invented IDs down.
  - But citing the key evidence fell from 88% to 44%, so the **base model stays the default**.
  - See `docs/FINETUNING.md`.
- **Real data:** 40 real Punjab & Haryana High Court criminal cases from the CC-BY-4.0 open judgments dataset, converted to the FIR schema.
  - All people are pseudonymised, sensitive offence types are excluded, and the real people are isolated from identity matching.
  - Each original PDF is hashed on the ledger.
  - See `docs/PUBLIC_RECORDS.md`.

## Not implemented from the slide
- **Vision + ASR, surveillance reports.** There is no image, video or audio pipeline and no surveillance-report source.
- **Neo4j.** Graphs use NetworkX in memory. There is no Neo4j export.
- **Sequence detection** (frequent event-sequence mining in the temporal engine) and a **fully agentic tool-planning loop**. The assistant routes questions to engines by intent; it does not plan iteratively.
- **Real CDR, location, financial and social records.** These do not exist publicly. Real cases carry only the court-order facts, and nothing is fabricated for them.

## Known limitations
- **LLM speed:** answers take about 20–60 s on a 16 GB M4. The model can attach the wrong figures to a real evidence ID; the grounding check flags these lines but cannot catch every error.
- **Behavioural identity matching:** can produce false `MEDIUM` candidates when two different people share a social circle and routine. That is why it never reaches `HIGH`, needs verification, and is never applied automatically.
- **Rule-based NER:** tuned to this data's FIR phrasing (no spaCy wheel exists for Python 3.14).
- **Federated learning and ledger:** single-machine simulations. All four agency keys live in `data/keys/`. They do not demonstrate network security, key custody or privacy guarantees. The ledger shows tampering relative to the hash recorded at ingestion; it does not prove the original evidence is authentic or was lawfully collected.

See `docs/INTEGRATION.md` for how the website is connected, and `docs/screenshots/` for before/after views.
