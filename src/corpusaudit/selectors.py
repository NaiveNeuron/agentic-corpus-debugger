"""One definition of "does this selector need the document text?".

A selector that only touches metadata columns can be evaluated exactly on the
whole corpus; one that reads ``text`` must be evaluated on the text-bearing
subsample and extrapolated.  The test has to use a word boundary: the substring
``text`` also occurs inside the column name ``fasttext``, and treating
``fasttext='cs'`` as text-dependent silently moves an exact measurement onto a
1-in-13 sample.
"""

from __future__ import annotations

import re

_TEXT = re.compile(r"\btext\b")


def needs_text(selector: str) -> bool:
    """True when the SQL condition reads the document text column."""
    return bool(_TEXT.search(selector))


def relation_for(selector: str, text_relation: str = "docs", meta_relation: str = "meta") -> str:
    """Relation a selector must be evaluated against."""
    return text_relation if needs_text(selector) else meta_relation
