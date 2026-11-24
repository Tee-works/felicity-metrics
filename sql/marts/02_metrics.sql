-- Metric tables. Definitions (purpose, grain, inclusion, edge cases) live in
-- docs/metrics.md. Each block below names the definition it implements.
-- ROUND(CAST(x AS NUMERIC), n) is used because Postgres has no ROUND(double, int).

-- M1. First-response time, by channel and by inside/outside branch hours.
DROP TABLE IF EXISTS marts.metric_first_response;
CREATE TABLE marts.metric_first_response AS
WITH base AS (
    SELECT channel,
           CASE WHEN is_out_of_hours THEN 'out_of_hours' ELSE 'in_hours' END AS period,
           has_response, first_response_seconds
    FROM marts.fct_conversations
    UNION ALL
    SELECT 'all', CASE WHEN is_out_of_hours THEN 'out_of_hours' ELSE 'in_hours' END,
           has_response, first_response_seconds
    FROM marts.fct_conversations
)
SELECT channel,
       period,
       COUNT(*)                         AS conversations,
       SUM(has_response)                AS responded,
       COUNT(*) - SUM(has_response)     AS unanswered,
       ROUND(CAST(percentile_cont(0.5) WITHIN GROUP (ORDER BY first_response_seconds) AS NUMERIC), 1) AS median_seconds,
       ROUND(CAST(percentile_cont(0.9) WITHIN GROUP (ORDER BY first_response_seconds) AS NUMERIC), 1) AS p90_seconds
FROM base
GROUP BY channel, period;

-- M2. Out-of-hours share, by agency.
DROP TABLE IF EXISTS marts.metric_out_of_hours_share;
CREATE TABLE marts.metric_out_of_hours_share AS
SELECT COALESCE(agency_id, 'ALL') AS agency_id,
       COUNT(*) AS conversations,
       SUM(CASE WHEN is_out_of_hours THEN 1 ELSE 0 END) AS out_of_hours,
       ROUND(CAST(SUM(CASE WHEN is_out_of_hours THEN 1 ELSE 0 END) AS NUMERIC) / COUNT(*), 4) AS out_of_hours_share
FROM marts.fct_conversations
GROUP BY ROLLUP (agency_id);

-- M3. Leads captured: qualified by Felicity AND present in the agency CRM.
DROP TABLE IF EXISTS marts.metric_leads_captured;
CREATE TABLE marts.metric_leads_captured AS
SELECT COALESCE(f.agency_id, 'ALL') AS agency_id,
       SUM(f.is_lead_qualified) AS leads_qualified,
       SUM(CASE WHEN f.is_lead_qualified = 1 AND f.is_in_crm = 1 THEN 1 ELSE 0 END) AS leads_captured,
       SUM(CASE WHEN f.is_lead_qualified = 1 AND f.is_in_crm = 0 THEN 1 ELSE 0 END) AS qualified_not_in_crm,
       ROUND(CAST(SUM(CASE WHEN f.is_lead_qualified = 1 AND f.is_in_crm = 1 THEN 1 ELSE 0 END) AS NUMERIC)
             / NULLIF(SUM(f.is_lead_qualified), 0), 4) AS crm_sync_rate
FROM marts.fct_conversations f
GROUP BY ROLLUP (f.agency_id);

-- M4. Enquiry-to-viewing conversion (lettings and sales enquiries only).
DROP TABLE IF EXISTS marts.metric_enquiry_to_viewing;
CREATE TABLE marts.metric_enquiry_to_viewing AS
SELECT COALESCE(channel, 'all') AS channel,
       COUNT(*) AS enquiries,
       SUM(is_viewing_booked) AS viewings_booked,
       ROUND(CAST(SUM(is_viewing_booked) AS NUMERIC) / COUNT(*), 4) AS viewing_booked_rate,
       SUM(is_viewing_attended) AS viewings_attended_crm,
       ROUND(CAST(SUM(is_viewing_attended) AS NUMERIC) / NULLIF(SUM(is_viewing_booked), 0), 4) AS attended_per_booked
FROM marts.fct_conversations
WHERE enquiry_type IN ('lettings', 'sales')
GROUP BY ROLLUP (channel);

-- M5. Human-handoff rate, by channel.
DROP TABLE IF EXISTS marts.metric_handoff_rate;
CREATE TABLE marts.metric_handoff_rate AS
SELECT COALESCE(channel, 'all') AS channel,
       COUNT(*) AS conversations,
       SUM(is_handed_to_human) AS handed_to_human,
       ROUND(CAST(SUM(is_handed_to_human) AS NUMERIC) / COUNT(*), 4) AS handoff_rate
FROM marts.fct_conversations
GROUP BY ROLLUP (channel);

-- M6. Human pickup time after a handoff, inside vs outside branch hours.
DROP TABLE IF EXISTS marts.metric_human_pickup;
CREATE TABLE marts.metric_human_pickup AS
SELECT CASE WHEN is_out_of_hours THEN 'out_of_hours' ELSE 'in_hours' END AS period,
       enquiry_type = 'maintenance' AS is_maintenance,
       COUNT(*) AS handoffs,
       ROUND(CAST(percentile_cont(0.5) WITHIN GROUP (ORDER BY human_pickup_seconds) / 60 AS NUMERIC), 1) AS median_minutes,
       ROUND(CAST(percentile_cont(0.9) WITHIN GROUP (ORDER BY human_pickup_seconds) / 60 AS NUMERIC), 1) AS p90_minutes
FROM marts.fct_conversations
WHERE is_handed_to_human = 1
GROUP BY 1, 2;
