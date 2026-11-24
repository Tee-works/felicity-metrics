#!/usr/bin/env bash
# Run the same SQL against a real Postgres and print the headline metric tables.
# Usage: PGURL=postgresql://user@127.0.0.1:5432/db scripts/postgres_check.sh
# Needs psql and the CSVs from `python run.py` (data/raw).
set -euo pipefail
cd "$(dirname "$0")/.."
: "${PGURL:?set PGURL to a scratch database}"
export PGOPTIONS="-c client_min_messages=warning"
P=(psql "$PGURL" -v ON_ERROR_STOP=1 -q)

"${P[@]}" -c "DROP SCHEMA IF EXISTS raw, ref, staging, marts CASCADE"
"${P[@]}" -f sql/00_schema.sql
for t in agencies branches branch_hours conversations messages outcomes crm_leads crm_events; do
  "${P[@]}" -c "\copy raw.$t FROM 'data/raw/$t.csv' WITH (FORMAT csv, HEADER true)"
done
for t in uk_clock_changes bank_holidays reporting_window; do
  "${P[@]}" -c "\copy ref.$t FROM 'data/raw/$t.csv' WITH (FORMAT csv, HEADER true)"
done
for f in sql/staging/*.sql sql/marts/*.sql; do "${P[@]}" -f "$f"; done

"${P[@]}" -c "SELECT * FROM marts.metric_first_response WHERE channel = 'all' ORDER BY period"
"${P[@]}" -c "SELECT * FROM marts.metric_out_of_hours_share WHERE agency_id = 'ALL'"
"${P[@]}" -c "SELECT * FROM marts.metric_leads_captured WHERE agency_id = 'ALL'"
"${P[@]}" -c "SELECT * FROM marts.metric_enquiry_to_viewing WHERE channel = 'all'"
"${P[@]}" -c "SELECT * FROM marts.metric_handoff_rate WHERE channel = 'all'"
"${P[@]}" -c "SELECT (SELECT COUNT(*) FROM marts.client_report) AS client_report_rows,
                     (SELECT COUNT(*) FROM staging.conversations WHERE tz_corrected) AS tz_corrected,
                     (SELECT COUNT(*) FROM staging.messages WHERE body_redacted LIKE '%@%') AS emails_left"
