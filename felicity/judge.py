"""Conversation-quality scoring: rubric, a keyword judge, and an LLM judge stub.

Interface
---------
Every judge has a `name` and a `score(conversation) -> RubricScore` method.
A rubric dimension is 1 (met), 0 (not met) or None (does not apply).

LLMJudge takes any `complete(prompt: str) -> str` callable, so it is not tied to a
vendor SDK. With no callable (the default, and the case with no API key) it falls
back to HeuristicJudge and says so in the `judge` field. Judges only ever see the
redacted transcript from staging.messages, never raw text.

See docs/conversation_quality_spec.md for the dataset and rubric.
"""
import json
import re
from dataclasses import asdict, dataclass
from typing import Callable, Optional, Protocol

RUBRIC = {
    "details_captured": "Lettings: asked when the person wants to move in. Sales: asked about buying position "
                        "(cash or mortgage). Not applicable to other enquiry types.",
    "next_step_offered": "Lettings and sales: offered or booked a viewing. Not applicable to other enquiry types.",
    "safe_escalation": "Urgent maintenance (gas, flooding, no heating, unsecured door): handed to a person or "
                       "emergency line in the same conversation. Not applicable otherwise.",
}
URGENT_TERMS = re.compile(r"gas|water is coming|no heating|lock is broken|flood", re.I)


@dataclass
class Turn:
    sender: str
    body: str


@dataclass
class Conversation:
    conversation_id: str
    enquiry_type: str
    turns: list[Turn]

    def transcript(self) -> str:
        return "\n".join(f"{t.sender.upper()}: {t.body}" for t in self.turns)


@dataclass
class RubricScore:
    conversation_id: str
    details_captured: Optional[int]
    next_step_offered: Optional[int]
    safe_escalation: Optional[int]
    judge: str
    rationale: str = ""

    def as_dict(self):
        return asdict(self)


class Judge(Protocol):
    name: str

    def score(self, conversation: Conversation) -> RubricScore: ...


class HeuristicJudge:
    """Deterministic keyword rules. Cheap, explainable, and wrong in known ways."""
    name = "heuristic-v1"

    def score(self, c: Conversation) -> RubricScore:
        bot = " ".join(t.body.lower() for t in c.turns if t.sender == "felicity")
        customer_first = next((t.body for t in c.turns if t.sender == "customer"), "")
        has_human = any(t.sender == "human_agent" for t in c.turns)
        notes = []
        details = next_step = escalation = None
        if c.enquiry_type == "lettings":
            details = int("move in" in bot or "moving in" in bot)
            notes.append(f"move-in question {'found' if details else 'not found'}")
        elif c.enquiry_type == "sales":
            details = int("mortgage" in bot or "cash buyer" in bot)
            notes.append(f"buying position {'asked' if details else 'not asked'}")
        if c.enquiry_type in ("lettings", "sales"):
            next_step = int("viewing" in bot)
            notes.append(f"viewing {'offered' if next_step else 'not offered'}")
        if c.enquiry_type == "maintenance" and URGENT_TERMS.search(customer_first):
            escalation = int(has_human or "emergency" in bot)
            notes.append(f"urgent repair {'escalated' if escalation else 'not escalated'}")
        return RubricScore(c.conversation_id, details, next_step, escalation, self.name, "; ".join(notes))


PROMPT = """You are grading one conversation between an AI front desk for a UK letting agent and a customer.
Personal details have been replaced with tokens like [PHONE].

Rubric (score 1 if met, 0 if not, null if the item does not apply):
{rubric}

Enquiry type: {enquiry_type}
Transcript:
{transcript}

Reply with JSON only: {{"details_captured": 0|1|null, "next_step_offered": 0|1|null, "safe_escalation": 0|1|null, "rationale": "<one sentence>"}}"""


class LLMJudge:
    """Model-graded rubric. Pass `complete` to use a real model; otherwise the fallback runs."""

    def __init__(self, complete: Optional[Callable[[str], str]] = None, model_name: str = "llm",
                 fallback: Optional[Judge] = None):
        self.complete = complete
        self.fallback = fallback or HeuristicJudge()
        self.name = model_name if complete else f"{self.fallback.name} (fallback: no model configured)"

    def build_prompt(self, c: Conversation) -> str:
        rubric = "\n".join(f"- {k}: {v}" for k, v in RUBRIC.items())
        return PROMPT.format(rubric=rubric, enquiry_type=c.enquiry_type, transcript=c.transcript())

    def score(self, c: Conversation) -> RubricScore:
        if self.complete is None:
            s = self.fallback.score(c)
            s.judge = self.name
            return s
        raw = self.complete(self.build_prompt(c))
        try:
            data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
            vals = {k: (None if data.get(k) is None else int(data[k])) for k in RUBRIC}
            if any(v not in (None, 0, 1) for v in vals.values()):
                raise ValueError("score out of range")
            return RubricScore(c.conversation_id, **vals, judge=self.name, rationale=str(data.get("rationale", "")))
        except (ValueError, KeyError, TypeError):
            s = self.fallback.score(c)
            s.judge = f"{self.fallback.name} (fallback: unparseable model output)"
            return s


def agreement(gold: list[dict], scored: list[RubricScore]) -> dict:
    """Per-dimension agreement between labels and a judge, over items where the label applies."""
    by_id = {s.conversation_id: s for s in scored}
    out = {}
    for dim in RUBRIC:
        pairs = [(g[dim], getattr(by_id[g["conversation_id"]], dim)) for g in gold
                 if g[dim] is not None and g["conversation_id"] in by_id]
        agree = sum(1 for a, b in pairs if a == b)
        false_fail = sum(1 for a, b in pairs if a == 1 and b == 0)
        false_pass = sum(1 for a, b in pairs if a == 0 and b == 1)
        out[dim] = {"labelled": len(pairs), "agree": agree,
                    "agreement": round(agree / len(pairs), 3) if pairs else None,
                    "judge_says_fail_label_says_pass": false_fail,
                    "judge_says_pass_label_says_fail": false_pass}
    return out
