"""Data quality checks.

Each check runs against the raw layer (to count what arrived broken) and, where it
makes sense, the staging layer (to prove the fix held). A check returns a Result;
run_all() returns the list. Status is pass, warn or fail.

  fail  the layer breaks a rule we rely on
  warn  a source problem staging cannot fix (a stale feed); someone has to chase it
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime

from . import config, pii
from .warehouse import rows


@dataclass
class Result:
    check: str
    layer: str
    target: str
    status: str
    failing_rows: int
    detail: str = ""
    extra: dict = field(default_factory=dict)

    def as_dict(self):
        return asdict(self)


def _scalar(con, sql):
    return con.execute(sql).fetchone()[0]


def uniqueness(con) -> list[Result]:
    out = []
    specs = [
        ("conversations", "conversation_id", None),
        ("messages", "message_id", None),
        ("crm_leads", "crm_system, conversation_id", "conversation_id IS NOT NULL"),
    ]
    for table, key, where in specs:
        for layer in ("raw", "staging"):
            w = f"WHERE {where}" if where else ""
            n = _scalar(con, f"""SELECT COALESCE(SUM(c - 1), 0) FROM (
                                   SELECT {key}, COUNT(*) AS c FROM {layer}.{table} {w}
                                   GROUP BY {key} HAVING COUNT(*) > 1) d""")
            out.append(Result("uniqueness", layer, f"{table}({key})", "fail" if n else "pass", int(n),
                              f"{n} extra rows share a key" if n else "keys unique"))
    return out


def freshness(con, as_of: datetime = config.AS_OF_UTC, sla_hours: int = config.FRESHNESS_SLA_HOURS) -> list[Result]:
    out = []
    sources = [("felicity_platform", "SELECT MAX(ingested_at) FROM raw.conversations")]
    for crm in [r["crm_system"] for r in rows(con, "SELECT DISTINCT crm_system FROM raw.agencies ORDER BY 1")]:
        sources.append((f"crm_{crm}", f"SELECT MAX(ingested_at) FROM raw.crm_leads WHERE crm_system = '{crm}'"))
    for name, sql in sources:
        last = _scalar(con, sql)
        lag_h = round((as_of - last).total_seconds() / 3600, 1)
        ok = lag_h <= sla_hours
        out.append(Result("freshness", "raw", name, "pass" if ok else "warn", 0 if ok else 1,
                          f"last load {last:%Y-%m-%d %H:%M} UTC, {lag_h}h before as-of (SLA {sla_hours}h)",
                          {"lag_hours": lag_h}))
    return out


def referential_integrity(con) -> list[Result]:
    specs = [
        ("messages", "conversation_id", "conversations", "conversation_id"),
        ("outcomes", "conversation_id", "conversations", "conversation_id"),
        ("crm_leads", "conversation_id", "conversations", "conversation_id"),
        ("conversations", "branch_id", "branches", "branch_id"),
    ]
    out = []
    for child, ck, parent, pk in specs:
        for layer in ("raw", "staging"):
            # branches has no staging copy, so both layers check against raw.branches
            parent_ref = f"staging.{parent}" if (layer == "staging" and parent == "conversations") else f"raw.{parent}"
            n = _scalar(con, f"""SELECT COUNT(*) FROM {layer}.{child} c
                                  WHERE c.{ck} IS NOT NULL
                                    AND NOT EXISTS (SELECT 1 FROM {parent_ref} p WHERE p.{pk} = c.{ck})""")
            out.append(Result("referential_integrity", layer, f"{child}.{ck} -> {parent}", "fail" if n else "pass",
                              int(n), f"{n} orphan rows" if n else "all rows have a parent"))
    return out


def timezone_sanity(con) -> list[Result]:
    out = []
    # Raw: does started_at match the first customer message?
    r = rows(con, """
        WITH f AS (SELECT conversation_id, MIN(sent_at) AS first_customer_at
                   FROM raw.messages WHERE sender = 'customer' GROUP BY conversation_id)
        SELECT c.source_system,
               EXTRACT(EPOCH FROM (c.started_at - f.first_customer_at)) / 3600 AS offset_hours,
               COUNT(*) AS n
        FROM raw.conversations c JOIN f ON f.conversation_id = c.conversation_id
        WHERE c.started_at <> f.first_customer_at
        GROUP BY 1, 2 ORDER BY 3 DESC""")
    n = sum(x["n"] for x in r)
    detail = "; ".join(f"{x['source_system']}: {x['n']} rows off by {x['offset_hours']:+.0f}h" for x in r) or "start times match first message"
    out.append(Result("timezone_sanity", "raw", "conversations.started_at vs first message", "fail" if n else "pass", int(n), detail,
                      {"by_source": [{k: (float(v) if k == "offset_hours" else v) for k, v in x.items()} for x in r]}))

    # Raw: do the mismatches sit only inside BST? That is the signature of local-time-labelled-as-UTC.
    in_bst = _scalar(con, """
        WITH f AS (SELECT conversation_id, MIN(sent_at) AS t FROM raw.messages WHERE sender = 'customer' GROUP BY conversation_id)
        SELECT COUNT(*) FROM raw.conversations c JOIN f ON f.conversation_id = c.conversation_id
        JOIN ref.uk_clock_changes k ON k.year = EXTRACT(YEAR FROM f.t)
        WHERE c.started_at <> f.t AND f.t >= k.bst_starts_utc AND f.t < k.bst_ends_utc""")
    out[-1].extra["mismatches_inside_bst"] = int(in_bst)

    # Staging: after correction, nothing should be off, and nothing should be in the future.
    s = _scalar(con, """
        WITH f AS (SELECT conversation_id, MIN(sent_at) AS t FROM staging.messages WHERE sender = 'customer' GROUP BY conversation_id)
        SELECT COUNT(*) FROM staging.conversations c JOIN f ON f.conversation_id = c.conversation_id
        WHERE c.started_at_utc <> f.t""")
    fut = _scalar(con, "SELECT COUNT(*) FROM staging.conversations c CROSS JOIN ref.reporting_window w WHERE c.started_at_utc > w.as_of_utc")
    flips = _scalar(con, "SELECT COUNT(*) FROM staging.conversations WHERE tz_corrected AND is_out_of_hours <> is_out_of_hours_uncorrected")
    corrected = _scalar(con, "SELECT COUNT(*) FROM staging.conversations WHERE tz_corrected")
    bad = int(s + fut)
    out.append(Result("timezone_sanity", "staging", "conversations.started_at_utc", "fail" if bad else "pass", bad,
                      f"{corrected} rows corrected by -1h; {flips} of them would have had the wrong in-hours/out-of-hours flag; "
                      f"{s} still mismatched; {fut} in the future",
                      {"corrected": int(corrected), "ooh_flag_flips_prevented": int(flips)}))
    return out


def pii_scan(con) -> list[Result]:
    targets = [("raw", "messages", "message_id", "body"),
               ("raw", "crm_leads", "crm_lead_id", "notes"),
               ("staging", "messages", "message_id", "body_redacted"),
               ("staging", "crm_leads", "crm_lead_id", "notes_redacted")]
    out = []
    for layer, table, key, col in targets:
        counts, rows_hit = {}, 0
        for (text,) in con.execute(f"SELECT {col} FROM {layer}.{table} WHERE {col} IS NOT NULL").fetchall():
            found = pii.find_pii(text)
            if found:
                rows_hit += 1
                for k, v in found.items():
                    counts[k] = counts.get(k, 0) + v
        status = "pass" if rows_hit == 0 else ("warn" if layer == "raw" else "fail")
        detail = ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "no PII patterns found"
        out.append(Result("pii_scan", layer, f"{table}.{col}", status, rows_hit, detail, {"matches": counts}))
    # Structured contact columns should not survive into staging at all.
    cols = {r["column_name"] for r in rows(con, """SELECT column_name FROM information_schema.columns
                                                  WHERE table_schema = 'staging' AND table_name = 'crm_leads'""")}
    leaked = sorted(cols & {"contact_email", "contact_phone"})
    out.append(Result("pii_scan", "staging", "crm_leads contact columns", "fail" if leaked else "pass", len(leaked),
                      f"leaked columns: {leaked}" if leaked else "email and phone replaced by hashed contact_key"))
    return out


def accepted_values(con) -> list[Result]:
    allowed = "('call', 'email', 'sms', 'whatsapp', 'portal')"
    n = _scalar(con, f"SELECT COUNT(*) FROM staging.conversations WHERE channel NOT IN {allowed} OR channel IS NULL")
    return [Result("accepted_values", "staging", "conversations.channel", "fail" if n else "pass", int(n),
                   "channel in call/email/sms/whatsapp/portal" if not n else f"{n} unexpected channels")]


def run_all(con) -> list[Result]:
    return (uniqueness(con) + freshness(con) + referential_integrity(con)
            + timezone_sanity(con) + pii_scan(con) + accepted_values(con))
