# Run report

SYNTHETIC DATA. Generated with seed 20261125. As-of 2026-11-16 06:00 UTC.
Window (UK local): 2026-08-03 to 2026-11-16 (exclusive).

Generated: 13721 conversations, 64180 messages, 16646 outcomes,
10962 CRM leads, 2220 CRM events.

## Data quality

| check | layer | target | status | failing_rows | detail |
|---|---|---|---|---|---|
| uniqueness | raw | conversations(conversation_id) | pass | 0 | keys unique |
| uniqueness | staging | conversations(conversation_id) | pass | 0 | keys unique |
| uniqueness | raw | messages(message_id) | fail | 191 | 191 extra rows share a key |
| uniqueness | staging | messages(message_id) | pass | 0 | keys unique |
| uniqueness | raw | crm_leads(crm_system, conversation_id) | fail | 374 | 374 extra rows share a key |
| uniqueness | staging | crm_leads(crm_system, conversation_id) | pass | 0 | keys unique |
| freshness | raw | felicity_platform | pass | 0 | last load 2026-11-15 23:51 UTC, 6.1h before as-of (SLA 26h) |
| freshness | raw | crm_alto | pass | 0 | last load 2026-11-16 00:30 UTC, 5.5h before as-of (SLA 26h) |
| freshness | raw | crm_loop | pass | 0 | last load 2026-11-16 00:09 UTC, 5.8h before as-of (SLA 26h) |
| freshness | raw | crm_mri | pass | 0 | last load 2026-11-16 03:29 UTC, 2.5h before as-of (SLA 26h) |
| freshness | raw | crm_street | warn | 1 | last load 2026-11-12 12:58 UTC, 89.0h before as-of (SLA 26h) |
| referential_integrity | raw | messages.conversation_id -> conversations | fail | 336 | 336 orphan rows |
| referential_integrity | staging | messages.conversation_id -> conversations | pass | 0 | all rows have a parent |
| referential_integrity | raw | outcomes.conversation_id -> conversations | fail | 88 | 88 orphan rows |
| referential_integrity | staging | outcomes.conversation_id -> conversations | pass | 0 | all rows have a parent |
| referential_integrity | raw | crm_leads.conversation_id -> conversations | pass | 0 | all rows have a parent |
| referential_integrity | staging | crm_leads.conversation_id -> conversations | pass | 0 | all rows have a parent |
| referential_integrity | raw | conversations.branch_id -> branches | pass | 0 | all rows have a parent |
| referential_integrity | staging | conversations.branch_id -> branches | pass | 0 | all rows have a parent |
| timezone_sanity | raw | conversations.started_at vs first message | fail | 828 | sms_gateway_v1: 828 rows off by +1h |
| timezone_sanity | staging | conversations.started_at_utc | pass | 0 | 828 rows corrected by -1h; 68 of them would have had the wrong in-hours/out-of-hours flag; 0 still mismatched; 0 in the future |
| pii_scan | raw | messages.body | warn | 12428 | 6930 email, 11064 uk_phone, 4188 uk_postcode |
| pii_scan | raw | crm_leads.notes | warn | 3196 | 1605 email, 1591 uk_phone |
| pii_scan | staging | messages.body_redacted | pass | 0 | no PII patterns found |
| pii_scan | staging | crm_leads.notes_redacted | pass | 0 | no PII patterns found |
| pii_scan | staging | crm_leads contact columns | pass | 0 | email and phone replaced by hashed contact_key |
| accepted_values | staging | conversations.channel | pass | 0 | channel in call/email/sms/whatsapp/portal |

## First-response time (seconds)

| channel | period | conversations | responded | unanswered | median_seconds | p90_seconds |
|---|---|---|---|---|---|---|
| call | in_hours | 2050 | 2016 | 34 | 3 | 5 |
| call | out_of_hours | 2730 | 2696 | 34 | 3 | 5 |
| email | in_hours | 1300 | 1281 | 19 | 90 | 249 |
| email | out_of_hours | 1689 | 1673 | 16 | 87 | 234 |
| portal | in_hours | 884 | 872 | 12 | 321 | 1040.3 |
| portal | out_of_hours | 1182 | 1170 | 12 | 325 | 1091.2 |
| sms | in_hours | 714 | 701 | 13 | 14 | 30 |
| sms | out_of_hours | 929 | 915 | 14 | 14 | 31 |
| whatsapp | in_hours | 970 | 963 | 7 | 12 | 26 |
| whatsapp | out_of_hours | 1273 | 1260 | 13 | 11 | 25 |
| all | in_hours | 5918 | 5833 | 85 | 13 | 279 |
| all | out_of_hours | 7803 | 7714 | 89 | 13 | 285 |

## Out-of-hours share

| agency_id | conversations | out_of_hours | out_of_hours_share |
|---|---|---|---|
| AG01 | 3061 | 1732 | 0.5658 |
| AG02 | 1855 | 1097 | 0.5914 |
| AG03 | 2516 | 1379 | 0.5481 |
| AG04 | 2319 | 1310 | 0.5649 |
| AG05 | 2083 | 1206 | 0.579 |
| AG06 | 1887 | 1079 | 0.5718 |
| ALL | 13721 | 7803 | 0.5687 |

## Leads captured

| agency_id | leads_qualified | leads_captured | qualified_not_in_crm | crm_sync_rate |
|---|---|---|---|---|
| AG01 | 2158 | 2067 | 91 | 0.9578 |
| AG02 | 1289 | 1217 | 72 | 0.9441 |
| AG03 | 1759 | 1690 | 69 | 0.9608 |
| AG04 | 1601 | 1545 | 56 | 0.965 |
| AG05 | 1443 | 1393 | 50 | 0.9653 |
| AG06 | 1291 | 1245 | 46 | 0.9644 |
| ALL | 9541 | 9157 | 384 | 0.9598 |

## Enquiry-to-viewing conversion (lettings and sales)

| channel | enquiries | viewings_booked | viewing_booked_rate | viewings_attended_crm | attended_per_booked |
|---|---|---|---|---|---|
| call | 2870 | 783 | 0.2728 | 528 | 0.6743 |
| email | 1832 | 509 | 0.2778 | 350 | 0.6876 |
| portal | 1292 | 362 | 0.2802 | 253 | 0.6989 |
| sms | 973 | 285 | 0.2929 | 199 | 0.6982 |
| whatsapp | 1344 | 351 | 0.2612 | 239 | 0.6809 |
| all | 8311 | 2290 | 0.2755 | 1569 | 0.6852 |

## Human-handoff rate

| channel | conversations | handed_to_human | handoff_rate |
|---|---|---|---|
| call | 4780 | 548 | 0.1146 |
| email | 2989 | 359 | 0.1201 |
| portal | 2066 | 232 | 0.1123 |
| sms | 1643 | 177 | 0.1077 |
| whatsapp | 2243 | 223 | 0.0994 |
| all | 13721 | 1539 | 0.1122 |

## Human pickup after handoff (minutes)

| period | is_maintenance | handoffs | median_minutes | p90_minutes |
|---|---|---|---|---|
| in_hours | False | 312 | 21 | 603.2 |
| in_hours | True | 337 | 17.8 | 28.1 |
| out_of_hours | False | 429 | 541.1 | 773.8 |
| out_of_hours | True | 461 | 18.4 | 498.9 |

## Client report

144 rows in reports/client_report.csv. Every rate's numerator and denominator are counts of rows in
marts.client_report_lineage. Example: the first five conversations behind AG01's October viewings:
CV000646, CV000651, CV000655, CV000656, CV000657.

## Conversation-quality sample

60 conversations in quality/labelled_sample.jsonl, scored by: heuristic-v1 (fallback: no model configured).

| dimension | labelled | agree | agreement | judge_says_fail_label_says_pass | judge_says_pass_label_says_fail |
|---|---|---|---|---|---|
| details_captured | 40 | 37 | 0.925 | 3 | 0 |
| next_step_offered | 40 | 40 | 1 | 0 | 0 |
| safe_escalation | 20 | 20 | 1 | 0 | 0 |

Same keyword judge, `next_step_offered` only, over every lettings and sales conversation, split by greeting:

| greeting | scored | agreement | false_pass | false_fail |
|---|---|---|---|---|
| A | 4096 | 1 | 0 | 0 |
| B | 4105 | 0.894 | 437 | 0 |

## A/B

Viewing-booked rate A 0.261, B 0.290, p = 0.0038. Decision: ship B.
Full readout: reports/ab_readout.md.
