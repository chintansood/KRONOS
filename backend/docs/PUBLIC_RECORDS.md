# Real case records (pseudonymised High Court orders)

KRONOS now holds **40 real criminal cases** (CASE901–CASE940) next to the synthetic world. They come from real orders of
the **High Court of Punjab and Haryana** — bail, anticipatory-bail and FIR-quashing petitions decided in 2024–2025 — and
are converted into the same FIR schema as the synthetic data.

## Where the data comes from

| | |
|---|---|
| Source | *Indian High Court Judgments* open dataset on the AWS Registry of Open Data — maintained by Dattam Labs, documents from the eCourts portal |
| Licence | CC-BY-4.0 (attribution kept on every record). Orders of Indian courts are public documents. |
| Access | Anonymous, documented bulk access: metadata read column-wise from the public parquet files, PDFs over HTTPS. No login, no captcha, no scraping of court websites. |
| Politeness | At most 1 request per second; every PDF is cached and never fetched twice; a generic User-Agent (no personal or project details). |
| Selection | `CRM-M` petitions by private parties against the State of Punjab, State of Haryana or UT Chandigarh, in random order. |

Run it again with `.venv/bin/python -I scripts/fetch_public_records.py --target 40`, then load the result with
`scripts/build_all.py --public-records`.

## What is real and what is not

| Field | Status |
|---|---|
| FIR number and year, FIR date, police station, district, sections and acts (including sections "added later") | **Real**, extracted from the order text |
| Offence category | Derived from the sections, by rule |
| Facts narrative | **Real text** as recorded in the order (where the order sets out the facts: 9 of 40). All names are pseudonymised. |
| Court, case number, CNR, decision date, outcome, type of petition | **Real** (dataset metadata) |
| People | **Pseudonymised** role labels such as `[Accused A1]` or `[Complainant C1]`, scoped to one case |
| CDR, location, financial and social-media records | **None exist publicly.** None are fabricated for real cases. |

Facts are **allegations as recorded in a court order, not findings**. The case page says so, links the original PDF, and
shows its SHA-256.

## How the data was filtered

| Step | Orders |
|---|---|
| Downloaded | 250 |
| No usable text layer (would need OCR), skipped rather than guessed | 144 |
| No FIR particulars (complaint cases, writs, garbled two-column layout) | 49 |
| **Excluded to protect victims and sensitive groups** | 17 |
| **Included** | **40** |

Cases are excluded outright if they involve any of the following:
- sexual offences: IPC 354/376/509, BNS 63–79;
- POCSO;
- juvenile matters;
- kidnapping or abduction: IPC 363/366, BNS 87/96/137/139;
- matrimonial or dowry matters: IPC 498-A/304-B, BNS 80/85/86;
- SC/ST Act cases, because those records carry caste.

The 40 included cases cover murder or attempt (9), NDPS narcotics (9), cheating, fraud and forgery (9), theft (4), hurt and rioting (4), robbery (2), cyber fraud (1), extortion (1) and other (1).

## Pseudonymisation (no real person is profiled)

Pseudonymisation runs in four layers:
1. **Case title:** the parties named in the title are replaced first.
2. **Role contexts:** names appearing after words such as "complainant X", "son of Y", "namely Z" or "X @ alias" are replaced.
3. **Name lexicon:** title-case word sequences that contain a known Indian given name or surname are replaced.
4. **Safety net:** any remaining capitalised word that is not an English word, legal vocabulary or a known place is masked with a neutral label such as `[Name W3]`. This over-masks some village names, which is the safe failure.

Police stations and districts are protected so they survive, and digital-signature stamps are removed.

Direct identifiers are masked as well: phone numbers, vehicle registrations, Aadhaar-like and account numbers, addresses, villages and e-mail addresses.

Across the 40 records, the layers replaced 74 name mentions and masked 8 identifiers. The safety net caught a further 45 words.

**Second check, using the local AI** (`kronos/realdata/pii_audit.py`): the local LLM was asked to list any personal names left in each of the 40 narratives. It flagged 5. **1 was a genuine leftover name**: a trial-court judge's first name written after "Ms ." (a PDF spacing artefact). The rules were fixed so an honorific always masks the name after it, and the records were rebuilt. The other 4 were false positives: role words and a police-station name. They were not applied. Details are in `data/public_records/report.json` → `piiAudit`.

**Isolation from the synthetic world:** real-case people carry `origin='PUBLIC_RECORD'` and are excluded from identity resolution, criminal-history fuzzy linking and the NER gazetteer. No real person can be matched to a synthetic record. Antecedents that an order itself lists are linked only to that order's petitioner, with status `STATED_IN_SOURCE`. The 40 included orders listed none.

**Provenance:** every row goes through the normal loader, gets a raw-record SHA-256 and a Merkle anchor. Each original PDF also gets a `SOURCE_DOCUMENT` ledger block recording its URL, CNR, licence, retrieval time and SHA-256 as downloaded. This proves what was fetched and when; it does not prove that the allegations are true.

## How accurate is the extraction?

The extraction was checked by hand: on 20 randomly chosen included orders, the extracted fields were compared with the source sentence printed beside them.

| Field | Correct |
|---|---|
| FIR number | 20 / 20 |
| FIR date | 20 / 20 |
| Police station | 20 / 20 |
| District (or correctly left empty when the order does not state it) | 20 / 20 |
| Sections, exact list | 16 / 20 (sub-clause misses such as `22(C)` → `22` and `27A` → `27`, since fixed) |
| Sections, all main sections present | 19 / 20 |

This is a small audit by the developer, not an independent benchmark. The rules are tuned to Punjab & Haryana phrasing, and other courts (for example Bombay, which writes "C.R. No.") would need their own patterns.

## What the engines do with a real case

All engines run on a real case without errors and stay honest about how little data there is:
- **Investigative priority:** "Insufficient evidence to rank".
- **Hypotheses:** "Unresolved".
- **Next best evidence:** call-detail and location records come first.

The assistant answers from the order's text with citations to the record's evidence ID.

## Limits

- **OCR:** 58% of the downloaded orders have no text layer. Adding OCR (for example Tesseract) would roughly double the yield.
- **Thin narratives:** only 9 of the 40 records set out facts. Quashing-on-compromise orders often do not.
- **Allegations only:** all content is as alleged at the bail or quashing stage. It says nothing about the outcome of the trial.
