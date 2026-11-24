-- Layers
--   raw      lands source data as delivered. No constraints, on purpose: bad rows must
--            arrive so the DQ checks can see and count them.
--   ref      small reference tables (clock changes, bank holidays, reporting window).
--   staging  one cleaned table per source entity: deduplicated, timezone-corrected,
--            PII-redacted, orphans removed. Keys are unique here.
--   marts    one fact table plus metric and client-report tables.
--
-- All timestamps are stored as TIMESTAMP (without time zone) holding UTC, except
-- columns ending _local, which hold UK wall-clock time. Postgres and DuckDB both
-- accept this file as written. See docs/dialect_notes.md.

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS ref;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;

CREATE TABLE raw.agencies (
    agency_id      TEXT,
    agency_name    TEXT,
    crm_system     TEXT          -- alto | mri | street | loop
);

CREATE TABLE raw.branches (
    branch_id      TEXT,
    agency_id      TEXT,
    branch_name    TEXT,
    postcode_area  TEXT
);

CREATE TABLE raw.branch_hours (
    branch_id      TEXT,
    day_of_week    INTEGER,      -- ISO: 1 = Monday ... 7 = Sunday. No row = closed.
    opens_local    TIME,
    closes_local   TIME
);

CREATE TABLE raw.conversations (
    conversation_id  TEXT,
    branch_id        TEXT,
    channel          TEXT,       -- call | email | sms | whatsapp | portal
    enquiry_type     TEXT,       -- lettings | sales | valuation | maintenance | general
    greeting_variant TEXT,       -- A/B test arm
    source_system    TEXT,
    started_at       TIMESTAMP,  -- claimed UTC; sms_gateway_v1 writes UK local time here
    ingested_at      TIMESTAMP
);

CREATE TABLE raw.messages (
    message_id       TEXT,
    conversation_id  TEXT,
    turn_index       INTEGER,
    sender           TEXT,       -- customer | felicity | human_agent
    sent_at          TIMESTAMP,
    body             TEXT,       -- free text, contains PII
    ingested_at      TIMESTAMP
);

CREATE TABLE raw.outcomes (
    outcome_id       TEXT,
    conversation_id  TEXT,
    outcome_type     TEXT,       -- lead_qualified | viewing_booked | valuation_booked | maintenance_triaged | handed_to_human
    outcome_at       TIMESTAMP
);

CREATE TABLE raw.crm_leads (
    crm_lead_id      TEXT,
    crm_system       TEXT,
    agency_id        TEXT,
    conversation_id  TEXT,       -- null for leads that did not come through Felicity
    contact_email    TEXT,
    contact_phone    TEXT,
    created_at       TIMESTAMP,
    status           TEXT,
    notes            TEXT,       -- free text, can contain PII
    ingested_at      TIMESTAMP
);

CREATE TABLE raw.crm_events (
    crm_event_id     TEXT,
    crm_lead_id      TEXT,
    crm_system       TEXT,
    event_type       TEXT,       -- viewing_attended | let_agreed | offer_accepted | instruction_won
    event_at         TIMESTAMP,
    ingested_at      TIMESTAMP
);

CREATE TABLE ref.uk_clock_changes (
    year             INTEGER,
    bst_starts_utc   TIMESTAMP,
    bst_ends_utc     TIMESTAMP
);

CREATE TABLE ref.bank_holidays (
    holiday_date     DATE,
    region           TEXT
);

CREATE TABLE ref.reporting_window (
    window_start_local TIMESTAMP,
    window_end_local   TIMESTAMP,
    as_of_utc          TIMESTAMP
);
