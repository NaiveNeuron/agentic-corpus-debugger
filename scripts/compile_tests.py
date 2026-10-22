#!/usr/bin/env python
"""Compile audited findings into the released corpus regression-test suite.

Reads the agent's findings, the measured statistics from out/analysis/summary.json,
the human labels, and (if present) the human adjudication decisions, and writes
one YAML test per accepted finding to tests/<scope>/.

A test is `accepted` only if a human approved it in
out/adjudication/decisions.csv; without a decision it is written with
`status: candidate` so the suite always reflects the current evidence.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.corpusaudit.adjudication import load_decisions  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", default="out/analysis/summary.json")
    ap.add_argument("--adjudication", default="out/adjudication")
    ap.add_argument("--scope", default="slk_Latn")
    ap.add_argument("--out", default="tests")
    ap.add_argument("--include-baseline", action="store_true",
                    help="also emit tests for baseline-proposed findings")
    args = ap.parse_args()

    summary = json.load(open(args.summary))
    decisions, notes, group_of = load_decisions(args.adjudication)

    out = pathlib.Path(args.out) / args.scope
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.yaml"):
        old.unlink()

    n = 0
    for f in summary["findings"]:
        if "error" in f:
            continue
        if f["source"] != "agent" and not args.include_baseline:
            continue
        dec = decisions.get(f["id"], "")
        if dec == "reject":
            continue
        h = f["human"]
        # A cheap, conservative assertion: a future corpus should not exceed the
        # prevalence we measured here (with a small tolerance for crawl drift).
        threshold = max(f["prevalence"] * 1.2, 1e-6)
        test = {
            "id": f["id"],
            "scope": args.scope,
            "status": "accepted" if dec == "approve" else "candidate",
            "description": " ".join(str(f["description"]).split()),
            "selector": f["selector"],
            "assertion": f"prevalence <= {threshold:.8f}",
            "discovered_by": ("agent" if f["source"] == "agent" else f["source"]),
            "found_in_runs": f.get("runs", []),
            "evidence": {
                "prevalence": f["prevalence"],
                "prevalence_ci95": f["prevalence_ci95"],
                "n_matched": f["n_matched"],
                "n_evaluated": f["n_evaluated"],
                "exact_on_full_corpus": f["exact_on_full_corpus"],
                "human_precision": h["precision"],
                "human_precision_ci95": h["precision_ci95"],
                "n_human_judgments": h["n_judged"],
                "human_language_labels": h["language_labels"],
                "human_quality_labels": h["quality_labels"],
                "agent_expected_precision": f["agent_expected_precision"],
                "likely_false_positives": " ".join(str(f["likely_false_positives"]).split()),
                # What the auditor actually observed, and documents to start from:
                # a test nobody can retrace is not reproducibly retrievable.
                "agent_evidence": " ".join(str(f.get("agent_evidence") or "").split()),
                "agent_example_ids": f.get("agent_example_ids") or [],
                "overlap_with_static_slices": f["baseline_overlap"],
                "human_decision": dec or "pending",
                "human_note": notes.get(f["id"], ""),
                "adjudication_group": group_of.get(f["id"], ""),
            },
        }
        (out / f"{f['id']}.yaml").write_text(
            yaml.safe_dump(test, allow_unicode=True, sort_keys=False))
        n += 1
    print(f"wrote {n} tests to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
