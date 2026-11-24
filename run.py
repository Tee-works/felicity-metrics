#!/usr/bin/env python3
"""One command: generate synthetic data, build the warehouse, run DQ checks,
compute metrics, score the quality sample, write the A/B readout.

    python run.py

Outputs land in reports/ and quality/. Exits non-zero if any staging-layer check fails.
"""
import csv
import json
import random
import sys

from felicity import abtest, config, dq, generate, judge, warehouse
from felicity.warehouse import rows


def md_table(data: list[dict], cols: list[str] | None = None) -> str:
    if not data:
        return "_no rows_\n"
    cols = cols or list(data[0].keys())
    fmt = lambda v: "" if v is None else (f"{v:.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v))
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(fmt(r[c]) for c in cols) + " |" for r in data]
    return "\n".join(lines) + "\n"


def to_float(rs):
    return [{k: (float(v) if hasattr(v, "as_integer_ratio") and not isinstance(v, (int, bool)) else v) for k, v in r.items()} for r in rs]


def quality_sample(con, n_per_stratum: int = 20, seed: int = config.SEED):
    with open(config.TRUTH_DIR / "quality_truth.csv") as f:
        truth = list(csv.DictReader(f))
    in_staging = {r["conversation_id"] for r in rows(con, "SELECT conversation_id FROM staging.conversations")}
    rng = random.Random(seed)
    strata = {
        "lettings": [t for t in truth if t["enquiry_type"] == "lettings"],
        "sales": [t for t in truth if t["enquiry_type"] == "sales"],
        "urgent_maintenance": [t for t in truth if t["enquiry_type"] == "maintenance" and t["urgent"] == "1"],
    }
    picked = []
    for name, pool in strata.items():
        pool = [t for t in pool if t["conversation_id"] in in_staging and (t["details_captured"] or t["safe_escalation"])]
        picked += [(name, t) for t in rng.sample(pool, n_per_stratum)]
    ids = ", ".join(f"'{t['conversation_id']}'" for _, t in picked)
    msgs = rows(con, f"""SELECT conversation_id, sender, body_redacted FROM staging.messages
                         WHERE conversation_id IN ({ids}) ORDER BY conversation_id, turn_index""")
    turns = {}
    for m in msgs:
        turns.setdefault(m["conversation_id"], []).append(judge.Turn(m["sender"], m["body_redacted"]))

    j = judge.LLMJudge()  # no model configured, so the deterministic fallback runs
    gold, scored, records = [], [], []
    as_int = lambda v: None if v == "" else int(v)
    for stratum, t in picked:
        conv = judge.Conversation(t["conversation_id"], t["enquiry_type"], turns[t["conversation_id"]])
        g = {"conversation_id": t["conversation_id"], **{d: as_int(t[d]) for d in judge.RUBRIC}}
        s = j.score(conv)
        gold.append(g)
        scored.append(s)
        records.append({"conversation_id": conv.conversation_id, "stratum": stratum, "enquiry_type": conv.enquiry_type,
                        "transcript_redacted": [{"sender": x.sender, "body": x.body} for x in conv.turns],
                        "label": {d: g[d] for d in judge.RUBRIC}, "label_source": "synthetic ground truth (stands in for a human label)",
                        "judge": s.as_dict()})
    config.QUALITY_DIR.mkdir(exist_ok=True)
    with open(config.QUALITY_DIR / "labelled_sample.jsonl", "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return judge.agreement(gold, scored), j.name, len(records)


def judge_by_variant(con) -> list[dict]:
    """Score every lettings/sales conversation and compare with the synthetic truth, split by greeting.

    You would not have full labels in production. It is here to show why a judge
    should be checked per A/B arm: greeting B mentions viewings, which fools the
    keyword rule for next_step_offered.
    """
    with open(config.TRUTH_DIR / "quality_truth.csv") as f:
        truth = {r["conversation_id"]: r for r in csv.DictReader(f) if r["next_step_offered"] != ""}
    variant = dict(con.execute("SELECT conversation_id, greeting_variant FROM staging.conversations").fetchall())
    turns = {}
    for cid, sender, body in con.execute("""SELECT conversation_id, sender, body_redacted FROM staging.messages
                                            ORDER BY conversation_id, turn_index""").fetchall():
        if cid in truth:
            turns.setdefault(cid, []).append(judge.Turn(sender, body))
    h, stats = judge.HeuristicJudge(), {}
    for cid, t in truth.items():
        if cid not in turns or cid not in variant:
            continue
        s = h.score(judge.Conversation(cid, t["enquiry_type"], turns[cid]))
        st = stats.setdefault(variant[cid], {"greeting": variant[cid], "scored": 0, "agree": 0, "false_pass": 0, "false_fail": 0})
        label = int(t["next_step_offered"])
        st["scored"] += 1
        st["agree"] += int(label == s.next_step_offered)
        st["false_pass"] += int(label == 0 and s.next_step_offered == 1)
        st["false_fail"] += int(label == 1 and s.next_step_offered == 0)
    out = []
    for k in sorted(stats):
        st = stats[k]
        st["agreement"] = round(st["agree"] / st["scored"], 3)
        out.append(st)
    return out


def ab_readout(con) -> tuple[str, dict]:
    arms = {r["greeting_variant"]: r for r in rows(con, """
        SELECT greeting_variant,
               COUNT(*) AS n,
               SUM(is_viewing_booked) AS viewings,
               SUM(is_handed_to_human) AS handoffs,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY first_response_seconds) AS median_frt
        FROM marts.fct_conversations
        WHERE enquiry_type IN ('lettings', 'sales')
        GROUP BY greeting_variant""")}
    a, b = arms["A"], arms["B"]
    primary = abtest.two_proportion_test(int(a["viewings"]), int(a["n"]), int(b["viewings"]), int(b["n"]))
    guard = abtest.two_proportion_test(int(a["handoffs"]), int(a["n"]), int(b["handoffs"]), int(b["n"]))
    srm_p = abtest.srm_check(int(a["n"]), int(b["n"]))
    need = abtest.required_n_per_arm(primary.rate_a, 0.03)
    guard_ok = guard.ci_high < 0.02
    ship = primary.p_value < 0.05 and primary.diff > 0 and guard_ok and srm_p > 0.001
    pct = lambda x: f"{x * 100:.1f}%"
    pp = lambda x: f"{x * 100:+.1f} pp"
    text = f"""# A/B readout: greeting variant and viewing bookings

SYNTHETIC DATA. The effect below was planted by the generator; the point is the shape of the readout.

**Question.** Does greeting B ("I can book viewings and answer questions any time, day or night") book more
viewings than greeting A ("How can I help?")?

**Population.** Lettings and sales enquiries in the reporting window. Unit: conversation, randomised 50/50 at the
first reply. Pre-registered decision rule: ship B if the primary metric improves at p < 0.05, the guardrail
holds, and there is no sample ratio mismatch.

| | A | B |
|---|---|---|
| Conversations | {a['n']} | {b['n']} |
| Viewings booked | {a['viewings']} | {b['viewings']} |
| Viewing-booked rate (primary) | {pct(primary.rate_a)} | {pct(primary.rate_b)} |
| Human-handoff rate (guardrail) | {pct(guard.rate_a)} | {pct(guard.rate_b)} |
| Median first response (s) | {float(a['median_frt']):.1f} | {float(b['median_frt']):.1f} |

**Primary.** B minus A = {pp(primary.diff)} (95% CI {pp(primary.ci_low)} to {pp(primary.ci_high)}), z = {primary.z:.2f}, p = {primary.p_value:.2g}.

**Guardrail.** Handoff rate B minus A = {pp(guard.diff)} (95% CI {pp(guard.ci_low)} to {pp(guard.ci_high)}).
Rule: the upper bound must stay below +2.0 pp. {'Holds.' if guard_ok else 'Breached.'}

**Sample ratio check.** p = {srm_p:.3f} against a 50/50 split. {'No mismatch.' if srm_p > 0.001 else 'Mismatch: stop and debug assignment before reading results.'}

**Power note.** Detecting a 3 pp lift from a {pct(primary.rate_a)} base needs about {need} conversations per arm
(5% two-sided, 80% power). Size the test before starting it, not after.

**Decision.** {'Ship B.' if ship else 'Do not ship B on this evidence.'}

**Caveats I'd raise before acting on a real version of this.**
- Randomisation is per conversation, so a returning customer can see both greetings. Per contact is cleaner.
- "Viewing booked" is not "viewing attended". Re-read the result once CRM attendance data has landed (lag about 10 days).
- Agencies with very different volumes can dominate the pooled rate. Check the sign of the effect per agency.
"""
    summary = {"rate_a": primary.rate_a, "rate_b": primary.rate_b, "diff": primary.diff, "ci": [primary.ci_low, primary.ci_high],
               "p_value": primary.p_value, "guardrail_handoff_diff": guard.diff, "guardrail_ci_high": guard.ci_high,
               "srm_p": srm_p, "decision": "ship B" if ship else "do not ship"}
    return text, summary


def main() -> int:
    counts = generate.generate()
    con = warehouse.build()
    config.REPORTS_DIR.mkdir(exist_ok=True)

    results = dq.run_all(con)
    with open(config.REPORTS_DIR / "dq_results.json", "w") as f:
        json.dump([r.as_dict() for r in results], f, indent=2, default=str)

    m_frt = to_float(rows(con, "SELECT * FROM marts.metric_first_response ORDER BY channel = 'all', channel, period"))
    m_ooh = to_float(rows(con, "SELECT * FROM marts.metric_out_of_hours_share ORDER BY agency_id"))
    m_leads = to_float(rows(con, "SELECT * FROM marts.metric_leads_captured ORDER BY agency_id"))
    m_view = to_float(rows(con, "SELECT * FROM marts.metric_enquiry_to_viewing ORDER BY channel = 'all', channel"))
    m_hand = to_float(rows(con, "SELECT * FROM marts.metric_handoff_rate ORDER BY channel = 'all', channel"))
    m_pick = to_float(rows(con, "SELECT * FROM marts.metric_human_pickup ORDER BY period, is_maintenance"))
    report = to_float(rows(con, "SELECT * FROM marts.client_report ORDER BY agency_id, report_month, metric"))
    with open(config.REPORTS_DIR / "client_report.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(report[0].keys()))
        w.writeheader()
        w.writerows(report)
    trace = rows(con, """SELECT conversation_id FROM marts.client_report_lineage
                         WHERE agency_id = 'AG01' AND report_month = DATE '2026-10-01'
                           AND metric = 'enquiry_to_viewing' AND role = 'numerator'
                         ORDER BY conversation_id LIMIT 5""")

    agree, judge_name, n_labelled = quality_sample(con)
    jv = judge_by_variant(con)
    ab_text, ab = ab_readout(con)
    (config.REPORTS_DIR / "ab_readout.md").write_text(ab_text)

    dq_rows = [{"check": r.check, "layer": r.layer, "target": r.target, "status": r.status,
                "failing_rows": r.failing_rows, "detail": r.detail} for r in results]
    agree_rows = [{"dimension": k, **v} for k, v in agree.items()]
    out = f"""# Run report

SYNTHETIC DATA. Generated with seed {config.SEED}. As-of {config.AS_OF_UTC:%Y-%m-%d %H:%M} UTC.
Window (UK local): {config.WINDOW_START_LOCAL:%Y-%m-%d} to {config.WINDOW_END_LOCAL:%Y-%m-%d} (exclusive).

Generated: {counts['conversations']} conversations, {counts['messages']} messages, {counts['outcomes']} outcomes,
{counts['crm_leads']} CRM leads, {counts['crm_events']} CRM events.

## Data quality

{md_table(dq_rows)}
## First-response time (seconds)

{md_table(m_frt)}
## Out-of-hours share

{md_table(m_ooh)}
## Leads captured

{md_table(m_leads)}
## Enquiry-to-viewing conversion (lettings and sales)

{md_table(m_view)}
## Human-handoff rate

{md_table(m_hand)}
## Human pickup after handoff (minutes)

{md_table(m_pick)}
## Client report

{len(report)} rows in reports/client_report.csv. Every rate's numerator and denominator are counts of rows in
marts.client_report_lineage. Example: the first five conversations behind AG01's October viewings:
{', '.join(t['conversation_id'] for t in trace)}.

## Conversation-quality sample

{n_labelled} conversations in quality/labelled_sample.jsonl, scored by: {judge_name}.

{md_table(agree_rows)}
Same keyword judge, `next_step_offered` only, over every lettings and sales conversation, split by greeting:

{md_table(jv, ["greeting", "scored", "agreement", "false_pass", "false_fail"])}
## A/B

Viewing-booked rate A {ab['rate_a']:.3f}, B {ab['rate_b']:.3f}, p = {ab['p_value']:.2g}. Decision: {ab['decision']}.
Full readout: reports/ab_readout.md.
"""
    (config.REPORTS_DIR / "run_report.md").write_text(out)

    # Console summary
    print(f"Generated {counts['conversations']} conversations, {counts['messages']} messages (synthetic).")
    print("DQ:")
    for r in results:
        print(f"  [{r.status.upper():4}] {r.layer:7} {r.check:22} {r.target:45} {r.detail}")
    allr = {(r['channel'], r['period']): r for r in m_frt}
    print("Headline metrics:")
    print(f"  out-of-hours share: {m_ooh[-1]['out_of_hours_share']:.1%}")
    print(f"  median first response: in-hours {allr[('all', 'in_hours')]['median_seconds']}s, out-of-hours {allr[('all', 'out_of_hours')]['median_seconds']}s")
    print(f"  leads captured: {int(m_leads[-1]['leads_captured'])} of {int(m_leads[-1]['leads_qualified'])} qualified ({m_leads[-1]['crm_sync_rate']:.1%} reached the CRM)")
    print(f"  enquiry-to-viewing: {m_view[-1]['viewing_booked_rate']:.1%}")
    print(f"  handoff rate: {m_hand[-1]['handoff_rate']:.1%}")
    print(f"  A/B: B-A = {ab['diff'] * 100:+.1f} pp, p = {ab['p_value']:.2g} -> {ab['decision']}")
    print(f"  judge agreement: " + ", ".join(f"{k} {v['agreement']}" for k, v in agree.items()))
    print("  judge next_step_offered by greeting: " + ", ".join(f"{v['greeting']} agreement {v['agreement']} ({v['false_pass']} false passes)" for v in jv))
    print("Reports: reports/run_report.md, reports/dq_results.json, reports/ab_readout.md, reports/client_report.csv")

    staging_fail = [r for r in results if r.layer == "staging" and r.status == "fail"]
    if staging_fail:
        print(f"FAILED: {len(staging_fail)} staging checks failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
