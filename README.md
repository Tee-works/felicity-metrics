# felicity-metrics

A small metrics layer for an AI front desk that answers calls, emails and messages for UK letting and estate
agents: conversations, outcomes and CRM records in, checked numbers out. Built by Iyanujesu Akinyefa as a
worked example for a Data Engineer role.

**All data here is synthetic.** Six invented agencies, 14 branches, 3 Aug to 15 Nov 2026. Phone numbers are
from the Ofcom drama range and emails use example.com. No real LightWork data or figures are used or implied.

```
pip install -r requirements.txt
make run       # or: python run.py   (generate, load, check, model, report)
make test      # 22 pytest tests
```

## The problem

Conversations arrive on five channels at all hours, outcomes are logged by the bot, and the result a client
cares about (a lead in their CRM, a viewing attended) lands days later in a different system. Each source
has its own clock, its own IDs and its own failure modes. Before building a number I want to know what it is
for, so every metric in `docs/metrics.md` starts with that, then its grain, what is in and out, and the edge
cases.

| Metric | What it is for | Result (synthetic data) |
|---|---|---|
| First-response time, median and p90 by channel, in and out of hours | Nobody waits; p90 catches a lagging channel | Median 13s in and out of hours. Portal p90 is about 17 minutes |
| Out-of-hours share | How much demand arrives while the branch is closed | 56.9% |
| Leads captured | Qualified by the bot and present in the agency CRM | 9,157 of 9,541 (96.0%) |
| Enquiry-to-viewing | Did the conversation turn into a booked viewing | 27.6%, of which 68.5% later attended |
| Human-handoff rate | Read with the escalation quality score, never alone | 11.2% |
| Client report | Monthly figures per agency, each traceable to conversation ids | 144 rows, every figure tested against its lineage |

The handoff numbers held the most useful finding: the bot answers at 2am as fast as at 2pm, but a non-urgent
handoff out of hours waits a median of 9 hours for a person, against 21 minutes in hours.

## What the data quality checks caught

Checks run on raw (to count problems) and staging (to prove the fixes held); every staging check passes.
From the seeded run (`reports/run_report.md`):

- **Duplicate CRM leads:** 374 extra rows from a webhook firing twice. Staging keeps the earliest and maps
  the duplicate ids, so CRM events filed against a duplicate still count.
- **Timezone:** 828 SMS conversations started exactly one hour late, all from one gateway and all inside
  BST. It writes UK local time and labels it UTC. Staging corrects that exact pattern and flags the rows. 68
  of them would otherwise have been put on the wrong side of the out-of-hours line.
- **Orphans:** 336 messages and 88 outcomes whose conversation row never arrived. Dropped from staging and
  counted.
- **Ingest retries:** 191 duplicate message rows.
- **Freshness:** the Street CRM feed last loaded 89 hours before the as-of time (SLA 26). That agency's
  CRM sync rate reads 94.4% against about 96% elsewhere. That gap is the feed, not the bot, and a client
  report should say so.
- **PII (GDPR):** 12,428 message bodies and 3,196 CRM notes contained emails, UK phone numbers or postcodes.
  After redaction in SQL, zero. Contact columns become a hashed key. Names need an NER pass; regex cannot
  catch them.

## Conversation quality and testing

`quality/labelled_sample.jsonl` holds 60 redacted conversations scored on three binary rubric items. The
judge interface in `felicity/judge.py` takes any model call and falls back to keyword rules when there is no
API key. The keyword judge agreed on 37 of 40 "details captured" labels. Run across every conversation, it
also passed 437 conversations under greeting B that never offered a viewing, because greeting B mentions
viewings. A judge used to read an A/B test needs checking within each arm.

`reports/ab_readout.md` reads a greeting test: viewing-booked rate 26.1% (A) against 29.0% (B), +2.8 points,
95% CI +0.9 to +4.8, p = 0.004, with a handoff-rate guardrail and a sample ratio check.

## Mapping to Alto, MRI, Street and Loop

All four hold what this model needs under different names: people (applicants, landlords, tenants),
properties, and appointments with a progression status. `raw.crm_leads` takes the person record created from
a conversation; `raw.crm_events` takes viewings and status changes, with a per-CRM status map turning each
vendor's vocabulary into one set of event types. The key question per integration is how a CRM record links
back to a conversation. If the bot writes its conversation id onto the record, the join is exact. If not,
match on hashed email or phone within a time window and report the match rate beside every figure that
depends on it. Field names need confirming against each vendor's API.

## First 30 days

1. **Week 1.** List every source, its owner and its refresh pattern. Ask the Product Lead which five numbers
   drive decisions and what each decision is. Run these checks against the real tables and share the output.
2. **Week 2.** Ship one production pipeline change: likely freshness alerts per CRM feed and UTC
   normalisation at ingest, since both skew every downstream number without raising an error.
3. **Week 3.** Agree the metric definitions in writing, build the fact table and client-report lineage in
   Postgres, and send the first weekly numbers.
4. **Week 4.** Label 200 conversations with two people, measure their agreement, then the judge's agreement
   per channel and per arm. Set up the next A/B test with its metric, guardrail and sample size fixed before
   it starts.

Postgres compatibility is checked by `scripts/postgres_check.sh`, which gives the same results as DuckDB.
See `docs/dialect_notes.md`.
