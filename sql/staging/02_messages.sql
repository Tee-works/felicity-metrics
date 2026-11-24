-- staging.messages: deduplicated on message_id, orphans dropped, body redacted.
-- The raw body never leaves the raw layer. Patterns mirror felicity/pii.py.

DROP TABLE IF EXISTS staging.messages;
CREATE TABLE staging.messages AS
WITH dedup AS (
    SELECT m.*,
           ROW_NUMBER() OVER (PARTITION BY message_id ORDER BY ingested_at) AS rn
    FROM raw.messages m
)
SELECT d.message_id,
       d.conversation_id,
       d.turn_index,
       d.sender,
       d.sent_at,
       regexp_replace(
         regexp_replace(
           regexp_replace(d.body,
             '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', '[EMAIL]', 'g'),
           '(\+44 ?7[0-9]{3}|07[0-9]{3}) ?[0-9]{3} ?[0-9]{3}', '[PHONE]', 'g'),
         '[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}', '[POSTCODE]', 'g') AS body_redacted
FROM dedup d
JOIN staging.conversations c ON c.conversation_id = d.conversation_id   -- drops orphans
WHERE d.rn = 1;

DROP TABLE IF EXISTS staging.outcomes;
CREATE TABLE staging.outcomes AS
SELECT DISTINCT o.outcome_id, o.conversation_id, o.outcome_type, o.outcome_at
FROM raw.outcomes o
JOIN staging.conversations c ON c.conversation_id = o.conversation_id;  -- drops orphans
