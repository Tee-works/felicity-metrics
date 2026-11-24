# A/B readout: greeting variant and viewing bookings

SYNTHETIC DATA. The effect below was planted by the generator; the point is the shape of the readout.

**Question.** Does greeting B ("I can book viewings and answer questions any time, day or night") book more
viewings than greeting A ("How can I help?")?

**Population.** Lettings and sales enquiries in the reporting window. Unit: conversation, randomised 50/50 at the
first reply. Pre-registered decision rule: ship B if the primary metric improves at p < 0.05, the guardrail
holds, and there is no sample ratio mismatch.

| | A | B |
|---|---|---|
| Conversations | 4155 | 4156 |
| Viewings booked | 1086 | 1204 |
| Viewing-booked rate (primary) | 26.1% | 29.0% |
| Human-handoff rate (guardrail) | 6.7% | 7.0% |
| Median first response (s) | 13.0 | 13.0 |

**Primary.** B minus A = +2.8 pp (95% CI +0.9 pp to +4.8 pp), z = 2.89, p = 0.0038.

**Guardrail.** Handoff rate B minus A = +0.3 pp (95% CI -0.8 pp to +1.4 pp).
Rule: the upper bound must stay below +2.0 pp. Holds.

**Sample ratio check.** p = 0.991 against a 50/50 split. No mismatch.

**Power note.** Detecting a 3 pp lift from a 26.1% base needs about 3488 conversations per arm
(5% two-sided, 80% power). Size the test before starting it, not after.

**Decision.** Ship B.

**Caveats I'd raise before acting on a real version of this.**
- Randomisation is per conversation, so a returning customer can see both greetings. Per contact is cleaner.
- "Viewing booked" is not "viewing attended". Re-read the result once CRM attendance data has landed (lag about 10 days).
- Agencies with very different volumes can dominate the pooled rate. Check the sign of the effect per agency.
