"""Line-level language identification, used by the ``sentence_lid`` tool.

Deliberately generic: the detector is built over every language Lingua
supports (75, in many scripts) rather than a hand-picked pair, so that using
this tool does not presuppose which confusion the auditor is looking for, and
it works on a FineWeb2 language in any of those scripts.
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache

MIN_CHARS = 25

# FineWeb2 labels some languages with an individual-language code where Lingua
# uses the macrolanguage (Standard Latvian ``lvs`` for Latvian ``lav``, ...).
FINEWEB2_TO_LINGUA = {
    "lvs": "lav", "ekk": "est", "zsm": "msa", "arb": "ara", "cmn": "zho",
    "swh": "swa", "khk": "mon", "azj": "aze",
    "als": "sqi", "fil": "tgl",
}


def knows(scope: str) -> bool:
    """Whether the detector covers a corpus language such as ``hun_Latn``.

    An unscoped corpus (``any``) counts as known: there is nothing to warn about.
    """
    if scope in ("any", "*", ""):
        return True
    from lingua import Language

    code = scope.split("_")[0].lower()
    code = FINEWEB2_TO_LINGUA.get(code, code)
    return code in {lang.iso_code_639_3.name.lower() for lang in Language.all()}


@lru_cache(maxsize=1)
def _detector():
    from lingua import LanguageDetectorBuilder

    return (
        LanguageDetectorBuilder.from_all_languages()
        .with_preloaded_language_models()
        .build()
    )


def line_lid(text: str, max_lines: int = 60) -> dict:
    """Identify the language of each sufficiently long line of ``text``."""
    det = _detector()
    lines = [ln.strip() for ln in text.split("\n")]
    out = []
    counts: Counter[str] = Counter()
    chars: Counter[str] = Counter()
    for ln in lines:
        if len(ln) < MIN_CHARS:
            continue
        if len(out) >= max_lines:
            break
        vals = det.compute_language_confidence_values(ln)
        best = vals[0] if vals else None
        lang = best.language.iso_code_639_1.name.lower() if best else "unknown"
        conf = round(best.value, 3) if best else 0.0
        counts[lang] += 1
        chars[lang] += len(ln)
        out.append({"line": ln[:160], "lang": lang, "confidence": conf})
    total_chars = sum(chars.values()) or 1
    return {
        "lines": out,
        "lines_by_language": dict(counts.most_common()),
        "char_share_by_language": {k: round(v / total_chars, 3) for k, v in chars.most_common()},
    }
