-- marts.fct_conversations: one row per conversation inside the reporting window.
-- Every metric below is a count, rate or percentile over rows of this table, so any
-- figure can be traced back to a list of conversation_ids.

DROP TABLE IF EXISTS marts.fct_conversations;
CREATE TABLE marts.fct_conversations AS
WITH first_customer AS (
    SELECT conversation_id, MIN(sent_at) AS first_customer_at
    FROM staging.messages
    WHERE sender = 'customer'
    GROUP BY conversation_id
),
first_reply AS (
    -- first message from Felicity or a person, after the customer's first message
    SELECT m.conversation_id, MIN(m.sent_at) AS first_reply_at
    FROM staging.messages m
    JOIN first_customer f ON f.conversation_id = m.conversation_id
    WHERE m.sender <> 'customer' AND m.sent_at >= f.first_customer_at
    GROUP BY m.conversation_id
),
outcome_flags AS (
    SELECT conversation_id,
           MAX(CASE WHEN outcome_type = 'lead_qualified'      THEN 1 ELSE 0 END) AS is_lead_qualified,
           MAX(CASE WHEN outcome_type = 'viewing_booked'      THEN 1 ELSE 0 END) AS is_viewing_booked,
           MAX(CASE WHEN outcome_type = 'valuation_booked'    THEN 1 ELSE 0 END) AS is_valuation_booked,
           MAX(CASE WHEN outcome_type = 'maintenance_triaged' THEN 1 ELSE 0 END) AS is_maintenance_triaged,
           MAX(CASE WHEN outcome_type = 'handed_to_human'     THEN 1 ELSE 0 END) AS is_handed_to_human
    FROM staging.outcomes
    GROUP BY conversation_id
),
handoff_wait AS (
    -- time from Felicity handing over to the first message from a person
    SELECT o.conversation_id, MIN(m.sent_at) - MIN(o.outcome_at) AS wait
    FROM staging.outcomes o
    JOIN staging.messages m
      ON m.conversation_id = o.conversation_id AND m.sender = 'human_agent' AND m.sent_at >= o.outcome_at
    WHERE o.outcome_type = 'handed_to_human'
    GROUP BY o.conversation_id
),
crm AS (
    SELECT l.conversation_id,
           MIN(l.crm_lead_id) AS crm_lead_id,
           MAX(CASE WHEN e.event_type = 'viewing_attended' THEN 1 ELSE 0 END) AS is_viewing_attended,
           MAX(CASE WHEN e.event_type IN ('let_agreed', 'offer_accepted', 'instruction_won') THEN 1 ELSE 0 END) AS is_converted
    FROM staging.crm_leads l
    LEFT JOIN staging.crm_events e ON e.crm_lead_id = l.crm_lead_id
    WHERE l.conversation_id IS NOT NULL
    GROUP BY l.conversation_id
)
SELECT c.conversation_id,
       c.agency_id,
       c.branch_id,
       c.channel,
       c.enquiry_type,
       c.greeting_variant,
       c.started_at_utc,
       c.started_at_local,
       CAST(date_trunc('month', c.started_at_local) AS DATE) AS report_month,
       c.is_out_of_hours,
       c.tz_corrected,
       EXTRACT(EPOCH FROM (r.first_reply_at - f.first_customer_at)) AS first_response_seconds,
       CASE WHEN r.first_reply_at IS NULL THEN 0 ELSE 1 END AS has_response,
       COALESCE(o.is_lead_qualified, 0)      AS is_lead_qualified,
       COALESCE(o.is_viewing_booked, 0)      AS is_viewing_booked,
       COALESCE(o.is_valuation_booked, 0)    AS is_valuation_booked,
       COALESCE(o.is_maintenance_triaged, 0) AS is_maintenance_triaged,
       COALESCE(o.is_handed_to_human, 0)     AS is_handed_to_human,
       EXTRACT(EPOCH FROM hw.wait)           AS human_pickup_seconds,
       crm.crm_lead_id,
       CASE WHEN crm.crm_lead_id IS NULL THEN 0 ELSE 1 END AS is_in_crm,
       COALESCE(crm.is_viewing_attended, 0)  AS is_viewing_attended,
       COALESCE(crm.is_converted, 0)         AS is_converted
FROM staging.conversations c
CROSS JOIN ref.reporting_window w
LEFT JOIN first_customer f ON f.conversation_id = c.conversation_id
LEFT JOIN first_reply r    ON r.conversation_id = c.conversation_id
LEFT JOIN outcome_flags o  ON o.conversation_id = c.conversation_id
LEFT JOIN handoff_wait hw  ON hw.conversation_id = c.conversation_id
LEFT JOIN crm              ON crm.conversation_id = c.conversation_id
WHERE c.started_at_local >= w.window_start_local
  AND c.started_at_local <  w.window_end_local;
