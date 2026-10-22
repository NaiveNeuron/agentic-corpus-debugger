"""The auditor's system prompt, stated for the language under audit.

``prompts/auditor_system.md`` is written for the Slovak slice. For another
corpus the language name and code are substituted; nothing else changes, so the
prompt still names no defect and no language pair.

    python -m src.corpusaudit.prompt data/fineweb2/hun_Latn/derived [--name Hungarian]
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from .lid import FINEWEB2_TO_LINGUA

PROMPT = pathlib.Path(__file__).resolve().parents[2] / "prompts" / "auditor_system.md"


def language_name(scope: str) -> str:
    """English name of a language code such as ``hun_Latn``, or the code itself."""
    from lingua import Language

    code = scope.split("_")[0].lower()
    code = FINEWEB2_TO_LINGUA.get(code, code)
    for lang in Language.all():
        if lang.iso_code_639_3.name.lower() == code:
            return lang.name.capitalize()
    return scope


def auditor_prompt(scope: str, name: str | None = None) -> str:
    """The system prompt for a corpus labelled ``scope``."""
    text = PROMPT.read_text()
    return text.replace("slk_Latn", scope).replace("Slovak", name or language_name(scope))


def main() -> int:
    from .db import open_corpus
    from .testsuite import corpus_scope

    ap = argparse.ArgumentParser(description="Print the auditor prompt for a corpus.")
    ap.add_argument("derived", help="derived tables of the corpus")
    ap.add_argument("--name", default=None, help="English name of the language")
    args = ap.parse_args()
    scope = corpus_scope(open_corpus(args.derived))
    if args.name is None and language_name(scope) == scope:
        print(f"[prompt] no name known for {scope}; pass --name for a readable prompt",
              file=sys.stderr)
    sys.stdout.write(auditor_prompt(scope, args.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
