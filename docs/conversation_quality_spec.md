# Conversation-quality dataset spec

## What it is for

Response time and conversion say whether conversations ended well. They do not say whether Felicity did
the job right on the way: asked the questions a branch needs, offered the next step, and sent urgent
repairs to a person. This dataset puts a number on that, per conversation, so prompt and model changes can
be compared before and after.

## Grain and fields

One row per scored conversation per judge version.

| Field | Type | Notes |
|---|---|---|
| conversation_id | text | joins to `marts.fct_conversations` |
| enquiry_type | text | decides which rubric items apply |
| transcript_redacted | list of turns | from `staging.messages.body_redacted`, never raw text |
| label.{dimension} | 0 / 1 / null | human label; null when the item does not apply |
| judge.{dimension} | 0 / 1 / null | model or rule score |
| judge.judge | text | judge name and version, including whether it fell back |
| judge.rationale | text | one sentence, for reviewers |
| stratum | text | sampling stratum |

## Rubric

| Dimension | Applies to | Met when |
|---|---|---|
| details_captured | lettings, sales | Lettings: asked when the person wants to move in. Sales: asked cash or mortgage. |
| next_step_offered | lettings, sales | Offered or booked a viewing. |
| safe_escalation | urgent maintenance | Gas, flooding, no heating or an unsecured door was handed to a person or emergency line in the same conversation. |

Binary items on purpose. Two labellers agree far more often on "did it ask X" than on a 1 to 5 tone score,
and a disagreement on a binary item is easy to discuss.

## Sampling

Stratified by enquiry type (lettings, sales, urgent maintenance), 20 each in this sample. In production I
would also stratify by channel and by A/B arm, and oversample conversations that ended in a handoff or a
complaint, because that is where errors cluster.

## Labels in this sample

`quality/labelled_sample.jsonl` has 60 conversations. The labels come from the generator's planted ground
truth and stand in for a human labeller. In a real setup two people label an overlapping 20% so labeller
agreement can be measured before the judge is.

## Judge

`felicity/judge.py` defines the interface (`score(conversation) -> RubricScore`). `LLMJudge` accepts any
`complete(prompt) -> str` function and falls back to `HeuristicJudge` when none is given or when the model
returns something unparseable. The fallback is named in the output, so a fallback score is never mistaken
for a model score.

## What the run shows

- The keyword judge misses lettings conversations where Felicity asked about the tenancy start date in
  different words. Agreement on `details_captured` in the sample: 37 of 40.
- Checked across every lettings and sales conversation, the same judge scores `next_step_offered` perfectly
  for greeting A and wrongly passes 437 conversations under greeting B, because greeting B mentions viewings.
  The 60-row sample did not contain one of those cases. Lesson: when a judge is used to read an A/B test,
  check its agreement within each arm, and check the sample covers both.
