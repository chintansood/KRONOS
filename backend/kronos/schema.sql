-- KRONOS PostgreSQL schema. Idempotent: safe to re-run.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ------------------------------------------------------------------
-- Ingestion bookkeeping
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id        TEXT PRIMARY KEY,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    source_dir    TEXT,
    stats         JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS ingestion_issues (
    id            BIGSERIAL PRIMARY KEY,
    run_id        TEXT REFERENCES ingestion_runs(run_id) ON DELETE CASCADE,
    modality      TEXT,
    file_name     TEXT,
    row_number    INT,
    source_record_id TEXT,
    severity      TEXT,          -- ERROR (row quarantined) | WARNING (row kept, field flagged)
    field         TEXT,
    issue         TEXT,
    raw_value     TEXT
);

-- Original source rows, exactly as read (all values as text). Never modified.
CREATE TABLE IF NOT EXISTS raw_records (
    source_record_id TEXT PRIMARY KEY,
    modality      TEXT NOT NULL,
    case_id       TEXT,
    file_name     TEXT NOT NULL,
    row_number    INT NOT NULL,
    raw           JSONB NOT NULL,
    content_sha256 TEXT NOT NULL,
    quarantined   BOOLEAN NOT NULL DEFAULT FALSE,
    run_id        TEXT,
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS raw_records_case ON raw_records(case_id);

-- ------------------------------------------------------------------
-- Unified normalised event representation (one row per valid source row)
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    event_id          TEXT PRIMARY KEY,
    source_record_id  TEXT NOT NULL REFERENCES raw_records(source_record_id),
    evidence_id       TEXT NOT NULL UNIQUE,
    case_id           TEXT NOT NULL,
    agency_id         TEXT,
    modality          TEXT NOT NULL,      -- FIR | CDR | LOCATION | FINANCIAL | SOCIAL
    ts                TIMESTAMP,          -- local (IST) naive timestamp
    ts_quality        TEXT,               -- EXACT | DATE_ONLY | MISSING | INVALID
    person_id         TEXT,               -- primary subject of the record
    entity_id_1       TEXT,
    entity_id_2       TEXT,               -- counterparty person id (if any)
    entity_type       TEXT,
    phone_number      TEXT,
    counterpart_phone TEXT,
    account_number    TEXT,
    counterpart_account TEXT,
    device_id         TEXT,
    sim_id            TEXT,
    latitude          DOUBLE PRECISION,
    longitude         DOUBLE PRECISION,
    accuracy_m        DOUBLE PRECISION,
    location_name     TEXT,
    event_type        TEXT,
    event_description TEXT,
    text_content      TEXT,               -- FIR narrative / message body
    amount            NUMERIC(16,2),
    duration_sec      INT,
    source_reliability TEXT,
    confidence        DOUBLE PRECISION,
    extra             JSONB DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS events_case ON events(case_id);
CREATE INDEX IF NOT EXISTS events_person ON events(person_id);
CREATE INDEX IF NOT EXISTS events_e2 ON events(entity_id_2);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS events_mod ON events(modality);

-- ------------------------------------------------------------------
-- Investigation entities
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cases (
    case_id            TEXT PRIMARY KEY,
    title              TEXT,
    offence_category   TEXT,
    description        TEXT,
    status             TEXT DEFAULT 'ACTIVE',
    priority           TEXT DEFAULT 'MEDIUM',
    fir_number         TEXT,
    police_station     TEXT,
    district           TEXT,
    agency_id          TEXT,
    incident_ts        TIMESTAMP,
    registration_ts    TIMESTAMP,
    incident_location  TEXT,
    incident_lat       DOUBLE PRECISION,
    incident_lon       DOUBLE PRECISION,
    lead_investigator  TEXT,
    is_custom          BOOLEAN DEFAULT FALSE,
    updated_at         TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS persons (
    person_id     TEXT PRIMARY KEY,
    display_name  TEXT,
    names         TEXT[] DEFAULT '{}',
    phones        TEXT[] DEFAULT '{}',
    devices       TEXT[] DEFAULT '{}',
    sims          TEXT[] DEFAULT '{}',
    accounts      TEXT[] DEFAULT '{}',
    first_seen    TIMESTAMP,
    last_seen     TIMESTAMP,
    is_subject    BOOLEAN DEFAULT FALSE   -- has records attributed to them (not only a counterparty)
);

-- Role of a person in a case, as RECORDED in FIR text (not inferred guilt).
CREATE TABLE IF NOT EXISTS person_case_roles (
    id            BIGSERIAL PRIMARY KEY,
    person_id     TEXT NOT NULL,
    case_id       TEXT NOT NULL,
    role          TEXT NOT NULL,   -- COMPLAINANT|VICTIM|WITNESS|ACCUSED|PRINCIPAL_ACCUSED|ASSOCIATE|MENTIONED|RECORD_SUBJECT
    source_record_id TEXT,
    evidence_id   TEXT,
    method        TEXT,            -- FIR_NER | FIR_STRUCTURED | RECORD_SUBJECT
    confidence    DOUBLE PRECISION,
    UNIQUE (person_id, case_id, role, source_record_id)
);
CREATE INDEX IF NOT EXISTS pcr_person ON person_case_roles(person_id);
CREATE INDEX IF NOT EXISTS pcr_case ON person_case_roles(case_id);

-- Entities extracted from free text (FIR narratives, messages)
CREATE TABLE IF NOT EXISTS text_entities (
    id              BIGSERIAL PRIMARY KEY,
    source_record_id TEXT NOT NULL,
    evidence_id     TEXT,
    case_id         TEXT,
    modality        TEXT,
    entity_text     TEXT,
    entity_type     TEXT,   -- PERSON|PHONE|ACCOUNT|AMOUNT|LOCATION|DATETIME|VEHICLE|ORG|ALIAS
    role            TEXT,
    span_start      INT,
    span_end        INT,
    normalized      TEXT,
    linked_person_id TEXT,
    confidence      DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS te_src ON text_entities(source_record_id);
CREATE INDEX IF NOT EXISTS te_case ON text_entities(case_id);

-- ------------------------------------------------------------------
-- Analytical outputs
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analysis_cache (
    cache_key     TEXT PRIMARY KEY,
    data_version  TEXT,
    payload       JSONB,
    computed_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS case_summaries (
    case_id       TEXT PRIMARY KEY,
    data_hash     TEXT NOT NULL,
    summary_json  JSONB NOT NULL,
    summary_txt   TEXT NOT NULL,
    llm_narrative TEXT,
    llm_model     TEXT,
    generated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS identity_candidates (
    candidate_id  TEXT PRIMARY KEY,
    person_a      TEXT NOT NULL,
    person_b      TEXT NOT NULL,
    score         DOUBLE PRECISION,
    band          TEXT,
    features      JSONB,
    supporting    JSONB,
    contradicting JSONB,
    reasons       JSONB,
    status        TEXT DEFAULT 'PENDING',   -- PENDING|CONFIRMED|REJECTED|DEFERRED
    updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS identity_reviews (
    id            BIGSERIAL PRIMARY KEY,
    candidate_id  TEXT REFERENCES identity_candidates(candidate_id) ON DELETE CASCADE,
    decision      TEXT NOT NULL,
    reviewer      TEXT,
    note          TEXT,
    previous_status TEXT,
    reviewed_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence_requests (
    request_id    TEXT PRIMARY KEY,
    case_id       TEXT,
    person_id     TEXT,
    evidence_type TEXT,
    payload       JSONB,
    status        TEXT,
    updated_at    TIMESTAMPTZ DEFAULT now()
);

-- ------------------------------------------------------------------
-- Retrieval index (hybrid: pgvector + full-text)
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS doc_chunks (
    chunk_id      TEXT PRIMARY KEY,
    case_id       TEXT,
    person_ids    TEXT[] DEFAULT '{}',
    doc_type      TEXT,          -- CASE_SUMMARY | FIR | MESSAGE | PERSON_PROFILE | FINDING
    evidence_ids  TEXT[] DEFAULT '{}',
    content       TEXT NOT NULL,
    tsv           tsvector,
    embedding     vector(768)
);
CREATE INDEX IF NOT EXISTS doc_chunks_tsv ON doc_chunks USING GIN(tsv);
CREATE INDEX IF NOT EXISTS doc_chunks_case ON doc_chunks(case_id);

-- ------------------------------------------------------------------
-- Evidence provenance ledger (local permissioned hash chain; no raw evidence on chain)
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ledger_blocks (
    block_index   BIGINT PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type    TEXT NOT NULL,     -- GENESIS|INGEST|ACCESS|VERIFY|MODIFY|CASE_EDIT|IDENTITY_REVIEW
    evidence_id   TEXT,
    content_hash  TEXT,              -- SHA-256 of canonical evidence content
    actor         TEXT,
    metadata      JSONB DEFAULT '{}'::jsonb,
    prev_hash     TEXT NOT NULL,
    block_hash    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ledger_evidence ON ledger_blocks(evidence_id);

CREATE TABLE IF NOT EXISTS assistant_log (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ DEFAULT now(),
    mode          TEXT,
    scope         JSONB,
    query         TEXT,
    answer        TEXT,
    cited        TEXT[],
    removed_citations TEXT[],
    model         TEXT,
    latency_ms    INT
);

-- ------------------------------------------------------------------
-- Criminal history (6th source) and its linkage to current profiles
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS criminal_history (
    history_id       TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL REFERENCES raw_records(source_record_id),
    evidence_id      TEXT NOT NULL UNIQUE,
    record_type      TEXT,
    source_system    TEXT,
    full_name        TEXT,
    alias_names      TEXT[] DEFAULT '{}',
    father_name      TEXT,
    birth_year       INT,
    address          TEXT,
    phone_at_record  TEXT,
    fir_reference    TEXT,
    offence_category TEXT,
    sections         TEXT,
    police_station   TEXT,
    district         TEXT,
    record_date      DATE,
    disposition      TEXT,
    modus_operandi   TEXT,
    source_reliability TEXT
);

CREATE TABLE IF NOT EXISTS history_links (
    link_id       TEXT PRIMARY KEY,
    history_id    TEXT REFERENCES criminal_history(history_id) ON DELETE CASCADE,
    person_id     TEXT NOT NULL,
    score         DOUBLE PRECISION,
    band          TEXT,
    features      JSONB,
    reasons       JSONB,
    contradicting JSONB,
    status        TEXT DEFAULT 'PENDING',
    updated_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS history_links_person ON history_links(person_id);

CREATE TABLE IF NOT EXISTS history_reviews (
    id          BIGSERIAL PRIMARY KEY,
    link_id     TEXT REFERENCES history_links(link_id) ON DELETE CASCADE,
    decision    TEXT NOT NULL,
    reviewer    TEXT,
    note        TEXT,
    previous_status TEXT,
    reviewed_at TIMESTAMPTZ DEFAULT now()
);

-- ------------------------------------------------------------------
-- Evidence retrieval engine: full-text index over every evidence record
-- ------------------------------------------------------------------
ALTER TABLE events ADD COLUMN IF NOT EXISTS tsv tsvector GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(event_description, '') || ' ' || coalesce(text_content, '') || ' ' || coalesce(location_name, ''))
) STORED;
CREATE INDEX IF NOT EXISTS events_tsv ON events USING GIN(tsv);

-- ------------------------------------------------------------------
-- Case diary (investigator entries) and evidence-request status history
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS case_diary_entries (
    id            BIGSERIAL PRIMARY KEY,
    case_id       TEXT NOT NULL,
    entry_ts      TIMESTAMP NOT NULL,
    author        TEXT,
    place         TEXT,
    text          TEXT NOT NULL,
    evidence_ids  TEXT[] DEFAULT '{}',
    created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS diary_case ON case_diary_entries(case_id);

CREATE TABLE IF NOT EXISTS evidence_request_log (
    id          BIGSERIAL PRIMARY KEY,
    request_id  TEXT,
    case_id     TEXT,
    status      TEXT,
    actor       TEXT,
    at          TIMESTAMPTZ DEFAULT now()
);

-- Real public records (pseudonymised court orders) live beside the synthetic world, flagged by origin.
ALTER TABLE cases   ADD COLUMN IF NOT EXISTS origin TEXT DEFAULT 'SYNTHETIC';
ALTER TABLE cases   ADD COLUMN IF NOT EXISTS source JSONB;
ALTER TABLE persons ADD COLUMN IF NOT EXISTS origin TEXT DEFAULT 'SYNTHETIC';
