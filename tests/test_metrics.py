def q(con, sql):
    return con.execute(sql).fetchall()


def test_client_report_traces_to_lineage(con):
    mismatches = q(con, """
        WITH lin AS (
            SELECT agency_id, report_month, metric,
                   SUM(CASE WHEN role = 'numerator' THEN 1 ELSE 0 END) AS num,
                   SUM(CASE WHEN role IN ('denominator', 'population') THEN 1 ELSE 0 END) AS den
            FROM marts.client_report_lineage GROUP BY 1, 2, 3)
        SELECT r.* FROM marts.client_report r JOIN lin l USING (agency_id, report_month, metric)
        WHERE r.denominator <> l.den
           OR (r.metric NOT IN ('conversations_handled', 'median_first_response_seconds') AND r.numerator <> l.num)""")
    assert mismatches == []


def test_lineage_ids_exist_in_raw_source(con):
    missing = q(con, """SELECT COUNT(*) FROM marts.client_report_lineage l
                        WHERE NOT EXISTS (SELECT 1 FROM raw.conversations c WHERE c.conversation_id = l.conversation_id)""")
    assert missing[0][0] == 0


def test_every_report_row_has_lineage(con):
    n = q(con, """SELECT COUNT(*) FROM marts.client_report r
                  WHERE NOT EXISTS (SELECT 1 FROM marts.client_report_lineage l
                                    WHERE l.agency_id = r.agency_id AND l.report_month = r.report_month AND l.metric = r.metric)""")
    assert n[0][0] == 0


def test_rates_are_rates(con):
    for table, col in [("metric_out_of_hours_share", "out_of_hours_share"), ("metric_leads_captured", "crm_sync_rate"),
                       ("metric_enquiry_to_viewing", "viewing_booked_rate"), ("metric_handoff_rate", "handoff_rate")]:
        lo, hi = q(con, f"SELECT MIN({col}), MAX({col}) FROM marts.{table}")[0]
        assert 0 <= lo <= hi <= 1, table


def test_percentiles_ordered_and_unanswered_excluded(con):
    assert q(con, "SELECT COUNT(*) FROM marts.metric_first_response WHERE median_seconds > p90_seconds")[0][0] == 0
    assert q(con, "SELECT COUNT(*) FROM marts.fct_conversations WHERE has_response = 0 AND first_response_seconds IS NOT NULL")[0][0] == 0
    assert q(con, "SELECT COUNT(*) FROM marts.fct_conversations WHERE first_response_seconds < 0")[0][0] == 0


def test_one_row_per_conversation(con):
    a, b = q(con, "SELECT COUNT(*), COUNT(DISTINCT conversation_id) FROM marts.fct_conversations")[0]
    assert a == b
    assert a == q(con, "SELECT COUNT(*) FROM staging.conversations")[0][0]


def test_leads_captured_never_exceeds_qualified(con):
    assert q(con, "SELECT COUNT(*) FROM marts.metric_leads_captured WHERE leads_captured > leads_qualified")[0][0] == 0


def test_bank_holiday_is_out_of_hours(con):
    # 31 Aug 2026 is a Monday bank holiday: every conversation that day is out of hours
    n_in = q(con, """SELECT COUNT(*) FROM staging.conversations
                     WHERE CAST(started_at_local AS DATE) = DATE '2026-08-31' AND NOT is_out_of_hours""")[0][0]
    assert n_in == 0
