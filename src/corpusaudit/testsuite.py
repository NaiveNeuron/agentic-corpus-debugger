"""Run a corpus regression-test suite: pytest for web corpora.

A test is a YAML file with a ``selector`` (a SQL condition over the corpus
schema) and an ``assertion`` (a boolean expression over ``prevalence`` and
``n_matched``).  Running the suite requires no GPU and no LLM calls: it is a
handful of scans over the corpus metadata.

    python -m src.corpusaudit.testsuite tests/slk_Latn --derived data/derived
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time

import yaml

from .db import open_corpus
from .selectors import needs_text
from .tools import wilson

ASSERT_OK = re.compile(r"^[0-9a-z_\s.<>=!+*/()-]+$")


def evaluate(con, selector: str, n_total: int, n_sample: int) -> dict:
    """Measure a selector; exact on the full corpus if it needs no text."""
    uses_text = needs_text(selector)
    rel, n = ("docs", n_sample) if uses_text else ("meta", n_total)
    t0 = time.perf_counter()
    k = con.execute(f"select count(*) from {rel} where ({selector})").fetchone()[0]
    dt = time.perf_counter() - t0
    lo, hi = wilson(k, n)
    return {
        "n_matched": k,
        "n_evaluated": n,
        "prevalence": k / n if n else 0.0,
        "prevalence_ci95": [lo, hi],
        "exact_on_full_corpus": not uses_text,
        "seconds": round(dt, 3),
    }


# Derived columns and the shipped column each one is computed from.  A release
# that does not ship the source cannot measure a selector that reads the
# derivative: such a test must say so rather than match nothing and pass.
DERIVED_FROM = {
    "fasttext": "fasttext",
    "langdetect": "langdetect",
    "top_langs": "top_langs",
    "glotlid_ces": "top_langs",
    "glotlid_slk": "top_langs",
    "lid_second": "top_langs",
    "lid_second_score": "top_langs",
    "lingua": "lingua",
    "lingua_top": "lingua",
    "lingua_top_p": "lingua",
    "lingua_sk_p": "lingua",
    "lingua_cs_p": "lingua",
    "n_bad_words": "bad_words",
}


def unavailable_columns(corpus) -> set[str]:
    """Shipped columns this release lacks, detected as wholly NULL."""
    probes = {"fasttext", "langdetect", "top_langs", "lingua", "n_bad_words"}
    have = {r[0] for r in corpus.con.execute("describe select * from meta").fetchall()}
    missing = set()
    for col in sorted(probes & have):
        if corpus.con.execute(f"select count({col}) from meta").fetchone()[0] == 0:
            missing.add("bad_words" if col == "n_bad_words" else col)
    return missing


def unmeasurable_with(selector: str, missing: set[str]) -> set[str]:
    """Which absent source columns this selector depends on."""
    return {
        src
        for col, src in DERIVED_FROM.items()
        if src in missing and re.search(rf"\b{col}\b", selector)
    }


def corpus_scope(corpus) -> str:
    """The corpus's own label for what it contains, e.g. ``slk_Latn``.

    Taken from the pipeline's ``language`` column, joined with
    ``language_script`` when the release ships it; a corpus with no dominant
    label is unscoped.
    """
    have = {r[0] for r in corpus.con.execute("describe select * from meta").fetchall()}
    script = "language_script" if "language_script" in have else "null"
    row = corpus.con.execute(
        f"select language, {script}, count(*) c from meta "
        "group by 1, 2 order by c desc limit 1"
    ).fetchone()
    if not row or not row[0]:
        return "any"
    if row[1]:
        return f"{row[0]}_{row[1]}"
    return {"sk": "slk_Latn", "slk": "slk_Latn"}.get(row[0], row[0])


def in_scope(test_scope: str, corpus: str) -> bool:
    """A test runs when it is language-neutral or its scope matches the corpus."""
    if test_scope in ("any", "*", "", None):
        return True
    if "_" in test_scope and "_" in corpus:
        return test_scope == corpus
    return test_scope.split("_")[0] == corpus.split("_")[0]


REQUIRED_FIELDS = {"id", "scope", "description", "selector", "assertion"}
OPTIONAL_FIELDS = {"status", "discovered_by", "found_in_runs", "evidence", "kind"}


def validate_test(test: object, path: str) -> list[str]:
    """Problems that make a test file meaningless, as human-readable strings.

    A test framework whose broken tests count as passing is worse than no
    framework: a misspelled ``assertions:`` key used to be reported ``no-assert``
    and excluded from the failure count, so a suite of typos exited 0. Unknown
    keys are errors precisely because that is what a misspelling looks like.
    """
    if not isinstance(test, dict):
        return [f"{path}: not a YAML mapping"]
    problems = []
    missing = sorted(REQUIRED_FIELDS - set(test))
    if missing:
        problems.append(f"{path}: missing {', '.join(missing)}")
    unknown = sorted(set(test) - REQUIRED_FIELDS - OPTIONAL_FIELDS)
    if unknown:
        problems.append(f"{path}: unknown field(s) {', '.join(unknown)} "
                        f"(a misspelling of {', '.join(sorted(REQUIRED_FIELDS))}?)")
    assertion = str(test.get("assertion", "")).strip()
    if assertion:
        if not ASSERT_OK.match(assertion):
            problems.append(
                f"{path}: assertion {assertion!r} is not of the permitted form")
        else:
            # The grammar admits `prevalence = 0.01`, which is a statement, not a
            # comparison: catch it here rather than at evaluation time.
            try:
                compile(assertion, "<assertion>", "eval")
            except SyntaxError:
                problems.append(f"{path}: assertion {assertion!r} is not an expression "
                                f"(did you mean == or <=?)")
    return problems


def run(suites: str | list[str], derived: str, report: str | None = None) -> int:
    corpus = open_corpus(derived)
    scope = corpus_scope(corpus)
    if isinstance(suites, str):
        suites = [suites]
    paths = [p for suite in suites for p in sorted(glob.glob(os.path.join(suite, "*.yaml")))]
    if not paths:
        print(f"no tests found in {', '.join(suites)}", file=sys.stderr)
        return 2
    rows, failed, skipped, unmeasurable = [], 0, [], []
    malformed: list[str] = []
    missing = unavailable_columns(corpus)
    t0 = time.perf_counter()
    for path in paths:
        test = yaml.safe_load(open(path))
        problems = validate_test(test, path)
        if problems:
            malformed.extend(problems)
            name = (test or {}).get("id", os.path.basename(path)) if isinstance(test, dict) \
                else os.path.basename(path)
            print(f"{'MALFORMED':>10}  {name:<44} {problems[0].split(': ', 1)[1]}")
            continue
        if not in_scope(str(test.get("scope", "any")), scope):
            skipped.append(test["id"])
            print(f"{'skip':>10}  {test['id']:<44} scope {test['scope']} != corpus {scope}")
            continue
        needs = unmeasurable_with(test["selector"], missing)
        if needs:
            unmeasurable.append({"id": test["id"], "needs": sorted(needs)})
            print(f"{'unmeasured':>10}  {test['id']:<44} "
                  f"release ships no {', '.join(sorted(needs))}")
            continue
        try:
            stats = evaluate(corpus.con, test["selector"], corpus.n_total, corpus.n_sample)
        except Exception as exc:
            # An unparseable selector is a broken test, not a crashed harness: say
            # which file and carry on, so one bad contribution cannot hide the rest.
            first = str(exc).strip().splitlines()[0]
            malformed.append(f"{path}: selector failed: {first}")
            print(f"{'MALFORMED':>10}  {test['id']:<44} selector failed: {first}")
            continue
        # Validation above guarantees a permitted assertion, so the only way to
        # land outside PASS/FAIL is an evaluation error -- which is a broken test,
        # never a passing one.
        assertion = str(test["assertion"]).strip()
        env = {"prevalence": stats["prevalence"], "n_matched": stats["n_matched"]}
        try:
            status = "PASS" if eval(assertion, {"__builtins__": {}}, env) else "FAIL"
        except Exception as exc:
            status = "bad-assert"
            malformed.append(f"{path}: assertion raised {exc!r}")
        failed += status != "PASS"
        rows.append({"id": test["id"], "status": status, "assertion": assertion,
                     "kind": test.get("kind", "prevalence_guard"), **stats})
        flag = "exact" if stats["exact_on_full_corpus"] else "sampled"
        print(
            f"{status:>10}  {test['id']:<44} {stats['prevalence']:>9.5%} "
            f"({stats['n_matched']:>9,d} docs, {flag}, {stats['seconds']:>5.2f}s)"
        )
    total = time.perf_counter() - t0
    print(f"\n{len(rows)} tests over {corpus.n_total:,} documents ({scope}) in {total:.1f}s; "
          f"{failed} failing"
          + (f"; {len(skipped)} out of scope" if skipped else "")
          + (f"; {len(unmeasurable)} unmeasurable on this release" if unmeasurable else "")
          + (f"; {len(malformed)} MALFORMED" if malformed else ""))
    if failed:
        print("a failing test is a live defect, not a broken harness")
    if malformed:
        print("\na malformed test measures nothing; fix these before trusting the suite:")
        for m in malformed:
            print(f"  - {m}")
    if report:
        json.dump({"tests": rows, "seconds": round(total, 2), "scope": scope,
                   "skipped_out_of_scope": skipped, "unmeasurable": unmeasurable,
                   "malformed": malformed,
                   "n_total": corpus.n_total, "n_sample": corpus.n_sample},
                  open(report, "w"), indent=2)
    if malformed:
        return 2
    return 1 if failed else 0


def default_suites() -> list[str]:
    """Every directory under ``tests/`` that holds test files.

    Hardcoding ``tests/slk_Latn`` would mean a second language community's tests
    are silently absent from the default run rather than reported out of scope,
    which is the difference between a suite that ports and one that looks like it
    does. Scope filtering already decides what actually executes.
    """
    found = sorted(d for d in glob.glob(os.path.join("tests", "*"))
                   if glob.glob(os.path.join(d, "*.yaml")))
    return found or ["tests/slk_Latn", "tests/metadata"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("suite", nargs="*", default=default_suites())
    ap.add_argument("--derived", default="data/derived")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()
    return run(args.suite, args.derived, args.report)


if __name__ == "__main__":
    sys.exit(main())
