"""PII patterns shared by the DQ scan (Python) and the staging redaction (SQL).

The SQL in sql/staging/02_messages.sql repeats these patterns. tests/test_pii.py
checks the two stay in step: after staging, the Python scan must find nothing.

Names are not caught by regex. That needs an NER pass (see README, first 30 days).
"""
import re

# Order matters: emails first, so the phone rule never eats part of an address.
PATTERNS = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "uk_phone": r"(\+44 ?7[0-9]{3}|07[0-9]{3}) ?[0-9]{3} ?[0-9]{3}",
    "uk_postcode": r"[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}",
}
TOKENS = {"email": "[EMAIL]", "uk_phone": "[PHONE]", "uk_postcode": "[POSTCODE]"}

_COMPILED = {k: re.compile(v) for k, v in PATTERNS.items()}


def find_pii(text: str | None) -> dict[str, int]:
    """Count matches per PII type in one string."""
    if not text:
        return {}
    out = {}
    for name, rx in _COMPILED.items():
        n = len(rx.findall(text))
        if n:
            out[name] = n
    return out


def redact(text: str | None) -> str | None:
    if text is None:
        return None
    for name, rx in _COMPILED.items():
        text = rx.sub(TOKENS[name], text)
    return text
