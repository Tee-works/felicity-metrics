# Metric definitions

Every metric is computed from `marts.fct_conversations` (one row per conversation) so any figure can be
broken back down into conversation ids. "In hours" means the conversation started inside the branch's
opening hours for that weekday, in UK local time, on a day that is not a bank holiday.

Each definition answers four questions: what the number is for, its grain, what is in and out, and the
edge cases that change it.

## 1. First-response time (`marts.metric_first_response`)

- **What it is for.** The product's promise is that nobody waits. Agencies compare this with how long their
  own staff take, and the team uses p90 to catch a channel that has started to lag (a stuck email poller
  shows up here first).
- **Grain.** Conversation. Reported as median and p90 by channel and by in hours / out of hours.
- **Definition.** Seconds from the first customer message to the first message from Felicity or a person
  that comes after it.
- **In.** Conversations in the window with at least one customer message.
- **Out of the percentiles.** Conversations with no reply. They are counted in `unanswered` instead, because
  a percentile that silently drops non-responses looks better the worse things get.
- **Edge cases.** Calls: the first Felicity turn is the answer, so this is pick-up time. Email and portal
  leads depend on polling intervals, so they will never match chat channels and should be judged against
  their own history. Start times from the legacy SMS gateway are corrected for BST first (see DQ).

## 2. Out-of-hours share (`marts.metric_out_of_hours_share`)

- **What it is for.** The core sales argument: how much demand arrives when the branch is closed. It is
  also the denominator for "leads you would have missed".
- **Grain.** Conversation, by agency.
- **Definition.** Conversations started outside branch hours / all conversations.
- **In.** All conversations in the window, answered or not.
- **Edge cases.** Branch hours come per branch per weekday; Sunday has no row and counts as closed. Bank
  holidays are closed. Each branch uses its own hours, so two branches of one agency can classify the same
  minute differently. Timezone matters: 68 of the 828 mis-stamped SMS conversations in the synthetic data would
  have landed on the wrong side of the line without the fix.

## 3. Leads captured (`marts.metric_leads_captured`)

- **What it is for.** What the agency pays for. A lead only counts if it reached their CRM, because a lead
  that Felicity qualified but the CRM never received is worth nothing to the branch.
- **Grain.** Conversation (one lead per conversation after deduplication).
- **Definition.** Conversations with a `lead_qualified` outcome that have a matching lead in the agency CRM.
  Reported next to `leads_qualified` and the gap (`qualified_not_in_crm`), so sync failures are visible.
- **In.** Lettings, sales and valuation conversations (the only ones that produce `lead_qualified`).
- **Edge cases.** Duplicate CRM leads from double webhook deliveries collapse to the earliest one. CRM
  leads with no conversation id (walk-ins) are excluded because Felicity did not produce them. A stale CRM
  feed lowers this number for reasons unrelated to Felicity, so read it next to the freshness check.

## 4. Enquiry-to-viewing conversion (`marts.metric_enquiry_to_viewing`)

- **What it is for.** The step after "we answered": did the conversation turn into a booked viewing? This is
  the primary metric for conversation-design changes (see the A/B readout).
- **Grain.** Conversation.
- **Definition.** Lettings and sales conversations with a `viewing_booked` outcome / all lettings and sales
  conversations. A second column shows viewings later marked attended in the CRM.
- **In.** Lettings and sales enquiries, including unanswered ones (failing to answer is a product failure,
  so it should count against the rate).
- **Out.** Valuation, maintenance and general enquiries.
- **Edge cases.** Attendance arrives from the CRM days later, so recent weeks always look worse on the
  attended column. Compare cohorts by enquiry week once the lag has passed.

## 5. Human-handoff rate (`marts.metric_handoff_rate`)

- **What it is for.** Two readings that pull in different directions: lower means Felicity resolves more on
  its own, but urgent repairs must be handed over. Read it next to the `safe_escalation` quality score, never
  alone.
- **Grain.** Conversation, by channel.
- **Definition.** Conversations with a `handed_to_human` outcome / all conversations.
- **Edge cases.** A handoff late in the evening may not have a human reply yet at the as-of time; it still
  counts as a handoff. Pickup time after handoff is reported separately in `marts.metric_human_pickup`,
  which is where out-of-hours pain actually shows (in the synthetic data, a median of about 9 hours for non-urgent
  handoffs out of hours, against about 20 minutes in hours).

## 6. Client report (`marts.client_report`, `marts.client_report_lineage`)

- **What it is for.** The monthly figures an agency sees. They have to survive the question "show me".
- **Grain.** Agency x month x metric. Months are UK local calendar months.
- **How it traces.** The lineage table holds one row per (agency, month, metric, role, conversation_id),
  where role is numerator, denominator or population. The report is computed only from the lineage table,
  and a test checks that every figure equals its lineage count and every id exists in `raw.conversations`.
- **Edge cases.** The first and last months of the window are partial and flagged `is_partial_month`.
