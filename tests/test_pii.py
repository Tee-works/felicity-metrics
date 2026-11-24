from felicity import pii


def test_redact_removes_all_patterns():
    s = "I'm Sarah, call 07700 900123 or +44 7700 900456 or 07700900789, sarah.j@example.com, CB1 2AB"
    out = pii.redact(s)
    assert pii.find_pii(out) == {}
    assert out.count("[PHONE]") == 3 and "[EMAIL]" in out and "[POSTCODE]" in out


def test_sql_redaction_matches_python_redaction(con):
    rows = con.execute("""SELECT r.body, s.body_redacted FROM raw.messages r
                          JOIN staging.messages s USING (message_id) LIMIT 3000""").fetchall()
    assert rows
    for raw_body, staged in rows:
        assert staged == pii.redact(raw_body)


def test_no_contact_columns_in_staging(con):
    cols = {r[0] for r in con.execute("""SELECT column_name FROM information_schema.columns
                                         WHERE table_schema = 'staging'""").fetchall()}
    assert not cols & {"contact_email", "contact_phone", "body", "notes"}
