-- staging.conversations: one row per conversation, UTC corrected, local time and branch-hours flag added.
--
-- Timezone fix. A conversation starts when the first customer message arrives, so
-- started_at should equal the first customer message time. sms_gateway_v1 writes UK
-- local time and labels it UTC, which puts started_at exactly one hour late during
-- BST and correct during GMT. We correct only that exact pattern and flag it, rather
-- than overwrite every start time with the message time, so the defect stays visible.

DROP TABLE IF EXISTS staging.conversations;
CREATE TABLE staging.conversations AS
WITH dedup AS (
    SELECT c.*,
           ROW_NUMBER() OVER (PARTITION BY conversation_id ORDER BY ingested_at) AS rn
    FROM raw.conversations c
),
first_customer AS (
    SELECT conversation_id, MIN(sent_at) AS first_customer_at
    FROM raw.messages
    WHERE sender = 'customer'
    GROUP BY conversation_id
),
corrected AS (
    SELECT d.conversation_id, d.branch_id, d.channel, d.enquiry_type, d.greeting_variant,
           d.source_system, d.ingested_at,
           d.started_at AS started_at_raw,
           CASE WHEN d.source_system = 'sms_gateway_v1'
                 AND d.started_at - f.first_customer_at = INTERVAL '1 hour'
                THEN TRUE ELSE FALSE END AS tz_corrected
    FROM dedup d
    LEFT JOIN first_customer f ON f.conversation_id = d.conversation_id
    WHERE d.rn = 1
),
utc AS (
    SELECT c.*,
           CASE WHEN tz_corrected THEN started_at_raw - INTERVAL '1 hour' ELSE started_at_raw END AS started_at_utc
    FROM corrected c
),
localised AS (
    SELECT u.*,
           u.started_at_utc + CASE WHEN u.started_at_utc >= k.bst_starts_utc AND u.started_at_utc < k.bst_ends_utc
                                   THEN INTERVAL '1 hour' ELSE INTERVAL '0 hours' END AS started_at_local,
           -- what the local time would have been without the fix, used to size the defect's impact
           u.started_at_raw + CASE WHEN u.started_at_raw >= k.bst_starts_utc AND u.started_at_raw < k.bst_ends_utc
                                   THEN INTERVAL '1 hour' ELSE INTERVAL '0 hours' END AS started_at_local_uncorrected
    FROM utc u
    JOIN ref.uk_clock_changes k ON k.year = EXTRACT(YEAR FROM u.started_at_utc)
)
SELECT l.conversation_id,
       b.agency_id,
       l.branch_id,
       l.channel,
       l.enquiry_type,
       l.greeting_variant,
       l.source_system,
       l.started_at_utc,
       l.started_at_local,
       l.tz_corrected,
       NOT (h.branch_id IS NOT NULL AND bh.holiday_date IS NULL
            AND CAST(l.started_at_local AS TIME) >= h.opens_local
            AND CAST(l.started_at_local AS TIME) <  h.closes_local) AS is_out_of_hours,
       NOT (h2.branch_id IS NOT NULL AND bh2.holiday_date IS NULL
            AND CAST(l.started_at_local_uncorrected AS TIME) >= h2.opens_local
            AND CAST(l.started_at_local_uncorrected AS TIME) <  h2.closes_local) AS is_out_of_hours_uncorrected,
       l.ingested_at
FROM localised l
JOIN raw.branches b ON b.branch_id = l.branch_id
LEFT JOIN raw.branch_hours h
       ON h.branch_id = l.branch_id AND h.day_of_week = EXTRACT(ISODOW FROM l.started_at_local)
LEFT JOIN ref.bank_holidays bh
       ON bh.holiday_date = CAST(l.started_at_local AS DATE)
LEFT JOIN raw.branch_hours h2
       ON h2.branch_id = l.branch_id AND h2.day_of_week = EXTRACT(ISODOW FROM l.started_at_local_uncorrected)
LEFT JOIN ref.bank_holidays bh2
       ON bh2.holiday_date = CAST(l.started_at_local_uncorrected AS DATE);
