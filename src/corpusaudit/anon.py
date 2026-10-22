"""Redact third-party personal data from anything we release or show.

The corpus is public web text and FineWeb2 already replaces most email addresses
with placeholders (``email@example.com``, ``firstname.lastname@example.org``); a
small residue survives, 0.009% of documents in our sample. Those are real
addresses belonging to people who are not part of this study, so they are redacted
wherever we log, release or print a document: the audit never needs them, and no
finding depends on one.

The placeholders themselves are deliberately kept. They are not personal data, and
one candidate finding is precisely that the corpus substitutes them silently, so
erasing them would erase the evidence.

``redact_pii`` is idempotent, which is what lets the trajectory replay compare a
freshly fetched result against an already-redacted log.
"""

from __future__ import annotations

import re

# Conservative: a local part, an @, a dotted host with a plausible TLD.
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}")

# FineWeb2's own anonymisation placeholders, which must survive redaction.
_PLACEHOLDERS = ("@example.com", "@example.org")

REDACTED = "[email]"


def _keep(match: str) -> bool:
    return any(match.lower().endswith(p) for p in _PLACEHOLDERS)


def redact_pii(text: str) -> str:
    """Replace real email addresses with a marker; keep corpus placeholders."""
    if not text or "@" not in text:
        return text
    return _EMAIL.sub(lambda m: m.group(0) if _keep(m.group(0)) else REDACTED, text)


def redact_obj(obj):
    """Apply :func:`redact_pii` to every string inside a JSON-shaped value."""
    if isinstance(obj, str):
        return redact_pii(obj)
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    return obj


def has_real_email(text: str) -> bool:
    """True if a string still contains an address that is not a placeholder."""
    return any(not _keep(m) for m in _EMAIL.findall(text or ""))
