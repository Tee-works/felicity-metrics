-- staging.crm_leads: one lead per (crm_system, conversation). Duplicate webhook
-- deliveries collapse to the earliest lead. Contact details are replaced by a
-- hashed key (enough to join and count people, not enough to contact them) and
-- free-text notes are redacted.

DROP TABLE IF EXISTS staging.crm_leads;
CREATE TABLE staging.crm_leads AS
WITH ranked AS (
    SELECT l.*,
           ROW_NUMBER() OVER (
               PARTITION BY l.crm_system, COALESCE(l.conversation_id, l.crm_lead_id)
               ORDER BY l.created_at, l.crm_lead_id) AS rn
    FROM raw.crm_leads l
)
SELECT r.crm_lead_id,
       r.crm_system,
       r.agency_id,
       r.conversation_id,
       md5(lower(trim(r.contact_email))) AS contact_key,
       r.created_at,
       r.status,
       regexp_replace(
         regexp_replace(r.notes,
           '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', '[EMAIL]', 'g'),
         '(\+44 ?7[0-9]{3}|07[0-9]{3}) ?[0-9]{3} ?[0-9]{3}', '[PHONE]', 'g') AS notes_redacted,
       r.ingested_at
FROM ranked r
WHERE r.rn = 1
  AND (r.conversation_id IS NULL
       OR r.conversation_id IN (SELECT conversation_id FROM staging.conversations));

-- Duplicate lead ids map to the surviving lead, so CRM events on a duplicate still count.
DROP TABLE IF EXISTS staging.crm_lead_aliases;
CREATE TABLE staging.crm_lead_aliases AS
SELECT d.crm_lead_id AS alias_lead_id, s.crm_lead_id AS canonical_lead_id
FROM raw.crm_leads d
JOIN staging.crm_leads s
  ON s.crm_system = d.crm_system AND s.conversation_id = d.conversation_id;

DROP TABLE IF EXISTS staging.crm_events;
CREATE TABLE staging.crm_events AS
SELECT DISTINCT e.crm_event_id, a.canonical_lead_id AS crm_lead_id, e.crm_system, e.event_type, e.event_at, e.ingested_at
FROM raw.crm_events e
JOIN staging.crm_lead_aliases a ON a.alias_lead_id = e.crm_lead_id;
