-- Client report: one row per agency, month and metric.
--
-- Built in two steps so every figure traces to source:
--   1. client_report_lineage lists, for each figure, the conversation_ids in its
--      numerator and denominator.
--   2. client_report is computed only from the lineage table.
-- If an agency asks "which 212 viewings?", the answer is a WHERE clause on step 1.

DROP TABLE IF EXISTS marts.client_report_lineage;
CREATE TABLE marts.client_report_lineage AS
SELECT agency_id, report_month, 'conversations_handled' AS metric, 'denominator' AS role, conversation_id
FROM marts.fct_conversations
UNION ALL
SELECT agency_id, report_month, 'out_of_hours_share', 'numerator', conversation_id
FROM marts.fct_conversations WHERE is_out_of_hours
UNION ALL
SELECT agency_id, report_month, 'out_of_hours_share', 'denominator', conversation_id
FROM marts.fct_conversations
UNION ALL
SELECT agency_id, report_month, 'leads_captured', 'numerator', conversation_id
FROM marts.fct_conversations WHERE is_lead_qualified = 1 AND is_in_crm = 1
UNION ALL
SELECT agency_id, report_month, 'leads_captured', 'denominator', conversation_id
FROM marts.fct_conversations WHERE is_lead_qualified = 1
UNION ALL
SELECT agency_id, report_month, 'enquiry_to_viewing', 'numerator', conversation_id
FROM marts.fct_conversations WHERE enquiry_type IN ('lettings', 'sales') AND is_viewing_booked = 1
UNION ALL
SELECT agency_id, report_month, 'enquiry_to_viewing', 'denominator', conversation_id
FROM marts.fct_conversations WHERE enquiry_type IN ('lettings', 'sales')
UNION ALL
SELECT agency_id, report_month, 'handoff_rate', 'numerator', conversation_id
FROM marts.fct_conversations WHERE is_handed_to_human = 1
UNION ALL
SELECT agency_id, report_month, 'handoff_rate', 'denominator', conversation_id
FROM marts.fct_conversations
UNION ALL
SELECT agency_id, report_month, 'median_first_response_seconds', 'population', conversation_id
FROM marts.fct_conversations WHERE has_response = 1;

DROP TABLE IF EXISTS marts.client_report;
CREATE TABLE marts.client_report AS
WITH counts AS (
    SELECT agency_id, report_month, metric,
           SUM(CASE WHEN role = 'numerator'   THEN 1 ELSE 0 END) AS numerator,
           SUM(CASE WHEN role = 'denominator' THEN 1 ELSE 0 END) AS denominator
    FROM marts.client_report_lineage
    WHERE role IN ('numerator', 'denominator')
    GROUP BY agency_id, report_month, metric
),
medians AS (
    SELECT l.agency_id, l.report_month, l.metric,
           COUNT(*) AS population,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY f.first_response_seconds) AS median_seconds
    FROM marts.client_report_lineage l
    JOIN marts.fct_conversations f ON f.conversation_id = l.conversation_id
    WHERE l.role = 'population'
    GROUP BY l.agency_id, l.report_month, l.metric
),
w AS (
    SELECT CAST(window_start_local AS DATE) AS ws, CAST(window_end_local AS DATE) AS we FROM ref.reporting_window
)
SELECT r.agency_id, a.agency_name, r.report_month, r.metric, r.numerator, r.denominator, r.value,
       CASE WHEN r.report_month < w.ws OR r.report_month + INTERVAL '1 month' > w.we THEN TRUE ELSE FALSE END AS is_partial_month
FROM (
    SELECT agency_id, report_month, metric,
           CASE WHEN metric = 'conversations_handled' THEN denominator ELSE numerator END AS numerator,
           denominator,
           CASE WHEN metric = 'conversations_handled' THEN CAST(denominator AS NUMERIC)
                ELSE ROUND(CAST(numerator AS NUMERIC) / NULLIF(denominator, 0), 4) END AS value
    FROM counts
    UNION ALL
    SELECT agency_id, report_month, metric, NULL, population, ROUND(CAST(median_seconds AS NUMERIC), 1)
    FROM medians
) r
JOIN raw.agencies a ON a.agency_id = r.agency_id
CROSS JOIN w;
