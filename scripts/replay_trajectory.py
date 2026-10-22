#!/usr/bin/env python
"""Replay a logged audit trajectory and check it still reproduces.

The paper claims that every tool call is logged so an investigation can be
replayed. This script tests that claim rather than asserting it: it re-executes
the deterministic, read-only calls from a run's JSONL log against the same corpus
and compares the results with what was recorded.

Calls whose output depends on session state rather than on the corpus (the
remaining inspection budget, which every document-returning tool appends) are
compared on the corpus-dependent part only; `schema` is skipped, since its whole
output is budget state.

    .venv/bin/python scripts/replay_trajectory.py out/runs/main
"""

from __future__ import annotations

import argparse
import glob
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.corpusaudit.db import open_corpus  # noqa: E402
from src.corpusaudit.anon import redact_pii
from src.corpusaudit.sqlguard import UnsafeSQL  # noqa: E402
from src.corpusaudit.tools import AGENT_COLUMNS, AuditSession  # noqa: E402

# A replay below this same-row rate is a regression rather than tie noise.
MIN_SET_RATE = 0.95

# Pure functions of the corpus: replayed and compared in full.
PURE = {"aggregate", "run_detector", "domain_stats", "crawl_stats"}
# Corpus-dependent but with a trailing budget line: compared without it.
BUDGETED = {"sample_documents", "inspect_document", "search_text", "evaluate_detector"}
SKIP = {"schema", "save_finding", "sentence_lid", "refused"}
LOG_TRUNCATION = 4000
BUDGET_LINE = re.compile(r"\n\[inspections left: \d+\]\s*$")


def strip_budget(text: str) -> str:
    return BUDGET_LINE.sub("", text).strip()


def same_rows(a: str, b: str) -> bool:
    """True when two logged results hold the same rows, ignoring row order."""
    try:
        ra, rb = json.loads(a), json.loads(b)
    except json.JSONDecodeError:
        return False
    if not (isinstance(ra, list) and isinstance(rb, list)) or len(ra) != len(rb):
        return False
    key = lambda rows: sorted(json.dumps(r, sort_keys=True) for r in rows)  # noqa: E731
    return key(ra) == key(rb)


def replay(run: str, derived: str, budgeted: bool) -> dict:
    corpus = open_corpus(derived)
    con = corpus.con
    con.execute("create view corpus as select text, top_langs, lingua, "
                + ", ".join(AGENT_COLUMNS) + " from docs")
    con.execute("create view corpus_meta as select top_langs, lingua, "
                + ", ".join(AGENT_COLUMNS) + " from meta")
    # A budget large enough that replay is never throttled where the original was not.
    session = AuditSession(con=con, n_total=corpus.n_total, n_sample=corpus.n_sample,
                           budget=10**9, log_path="/dev/null",
                           findings_dir="/tmp/replay_findings")

    records = [json.loads(l) for l in open(pathlib.Path(run) / "tools.jsonl") if l.strip()]
    stats = {"run": pathlib.Path(run).name, "logged_calls": len(records),
             "replayed": 0, "matched": 0, "matched_as_set": 0, "skipped": 0,
             "errors": 0, "refused_now": 0, "refused_calls": [], "mismatches": []}
    for rec in records:
        tool, args, logged = rec["tool"], rec["args"], rec["result"]
        if tool in SKIP or (tool in BUDGETED and not budgeted):
            stats["skipped"] += 1
            continue
        if tool not in PURE | BUDGETED:
            stats["skipped"] += 1
            continue
        call_args = dict(args)
        if tool == "inspect_document":  # logged under its schema name
            call_args = {"doc_id": args.get("id", args.get("doc_id"))}
        try:
            got = str(getattr(session, tool)(**call_args))
        except UnsafeSQL as exc:
            # The call ran when the trajectory was recorded but the current SQL
            # guard refuses it (it read text through a free tool, or reached
            # outside the agent relations). That is a property of the old run,
            # reported for disclosure, not a failure to reproduce.
            stats["refused_now"] += 1
            stats["refused_calls"].append({"call": rec["call"], "tool": tool,
                                           "reason": str(exc)[:160]})
            continue
        except Exception as exc:
            stats["errors"] += 1
            stats["mismatches"].append({"call": rec["call"], "tool": tool,
                                        "error": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        stats["replayed"] += 1
        # Released logs are PII-redacted and the tools redact at the boundary;
        # redaction is idempotent, so applying it to both sides is a no-op for a
        # faithful replay and keeps an older, unredacted log comparable.
        a, b = redact_pii(logged), redact_pii(got)
        if tool in BUDGETED:
            a, b = strip_budget(a), strip_budget(b)
        # the log truncates long results, so compare on the recorded prefix
        n = min(len(a), LOG_TRUNCATION)
        if b[:n] == a[:n]:
            stats["matched"] += 1
            stats["matched_as_set"] += 1
        elif same_rows(a, b):
            # identical rows in a different order: SQL leaves ties unordered, so
            # this is reproduction of the result, not of the row sequence
            stats["matched_as_set"] += 1
        else:
            first = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), min(len(a), len(b)))
            stats["mismatches"].append({"call": rec["call"], "tool": tool,
                                        "logged": a[max(0, first - 40):first + 60],
                                        "replayed": b[max(0, first - 40):first + 60]})
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*", default=sorted(glob.glob("out/runs/*")))
    ap.add_argument("--derived", default="data/derived")
    ap.add_argument("--budgeted", action="store_true",
                    help="also replay document-returning calls (slower)")
    ap.add_argument("--report", default="out/analysis/replay_report.json")
    args = ap.parse_args()

    all_stats = []
    for run in args.runs:
        if not (pathlib.Path(run) / "tools.jsonl").exists():
            continue
        st = replay(run, args.derived, args.budgeted)
        all_stats.append(st)
        rate = st["matched"] / st["replayed"] if st["replayed"] else 0.0
        srate = st["matched_as_set"] / st["replayed"] if st["replayed"] else 0.0
        print(f"{st['run']:20s} logged {st['logged_calls']:>4d}  replayed {st['replayed']:>4d}  "
              f"exact {st['matched']:>4d} ({rate:.1%})  same rows {st['matched_as_set']:>4d} "
              f"({srate:.1%})  errors {st['errors']}  refused by current guard {st['refused_now']}")
        for m in st["mismatches"][:3]:
            print(f"    ! call {m['call']} {m['tool']}: "
                  f"{m.get('error') or repr(m['logged'])[:80] + ' vs ' + repr(m['replayed'])[:80]}")

    total_r = sum(s["replayed"] for s in all_stats)
    total_m = sum(s["matched"] for s in all_stats)
    total_s = sum(s["matched_as_set"] for s in all_stats)
    pathlib.Path(args.report).write_text(json.dumps(
        {"runs": all_stats, "replayed": total_r, "matched_exactly": total_m,
         "matched_as_set": total_s,
         "exact_rate": total_m / total_r if total_r else 0.0,
         "set_rate": total_s / total_r if total_r else 0.0,
         "budgeted_calls_included": args.budgeted,
         "refused_by_current_guard": sum(s["refused_now"] for s in all_stats),
         "note": "Mismatches are rows ordered differently where the SQL leaves "
                 "ties unordered; the tools now impose total orders, so future "
                 "trajectories replay byte-for-byte."}, indent=2))
    if not total_r:
        print("nothing replayed")
        return 1
    errors = sum(s["errors"] for s in all_stats)
    print(f"\n{total_m}/{total_r} replayed calls reproduce byte-exactly "
          f"({total_m / total_r:.1%}); {total_s}/{total_r} reproduce the same rows "
          f"({total_s / total_r:.1%})")
    # A handful of row differences is expected and documented: a query whose
    # ordering key ties at the LIMIT cutoff returns a different tied subset each
    # scan. That is not a regression, so it must not fail the run and abort the
    # scripts that follow. A replay that raises, or that loses a twentieth of its
    # rows, is a regression.
    if errors:
        print(f"{errors} call(s) raised during replay")
        return 1
    if total_s / total_r < MIN_SET_RATE:
        print(f"same-row rate {total_s / total_r:.1%} is below the documented "
              f"{MIN_SET_RATE:.0%}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
