from felicity import dq


def by(results, check, layer, target_prefix=""):
    return [r for r in results if r.check == check and r.layer == layer and r.target.startswith(target_prefix)]


def test_raw_layer_catches_every_planted_defect(con):
    res = dq.run_all(con)
    assert by(res, "uniqueness", "raw", "crm_leads")[0].failing_rows > 0      # duplicate CRM leads
    assert by(res, "uniqueness", "raw", "messages")[0].failing_rows > 0       # ingest retries
    assert by(res, "referential_integrity", "raw", "messages")[0].failing_rows > 0  # orphan messages
    tz = by(res, "timezone_sanity", "raw")[0]
    assert tz.failing_rows > 0
    assert tz.extra["mismatches_inside_bst"] == tz.failing_rows               # only during BST
    assert all(s["source_system"] == "sms_gateway_v1" and s["offset_hours"] == 1 for s in tz.extra["by_source"])
    stale = {r.target: r.status for r in by(res, "freshness", "raw")}
    assert stale["crm_street"] == "warn"
    assert all(v == "pass" for k, v in stale.items() if k != "crm_street")
    assert by(res, "pii_scan", "raw", "messages")[0].failing_rows > 0


def test_staging_layer_is_clean(con):
    res = dq.run_all(con)
    failures = [r for r in res if r.layer == "staging" and r.status != "pass"]
    assert failures == []


def test_timezone_fix_changes_some_out_of_hours_flags(con):
    tz = [r for r in dq.timezone_sanity(con) if r.layer == "staging"][0]
    assert tz.extra["corrected"] > 0
    assert 0 < tz.extra["ooh_flag_flips_prevented"] < tz.extra["corrected"]
