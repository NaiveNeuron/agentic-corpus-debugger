#!/usr/bin/env python3
"""Generate the paper macros whose values are measurements, not choices.

Some numbers in the paper describe what *happened*: how many documents a person
labelled, how many tests the suite ended up containing after adjudication, how
long it takes. Written by hand they go stale silently -- the suite runtime sat at
an old value through 145 passing assertions once.

So they are generated here, after the measurements exist, and the paper reads
them. Run this after the test suite; `scripts/reproduce.sh` already does.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analyze import PRECISION_ACCEPT  # noqa: E402  the one definition of the rule

REPO = pathlib.Path(__file__).resolve().parents[1]
OUT = REPO / "out/analysis"


def adjudication_sentence() -> str:
    """One sentence on how the adjudication verdicts were reached.

    A reader is entitled to know that the verdicts were proposed from the label
    evidence and adopted, rather than formed independently for each group: the labels
    are the annotator's, but the triage was not. Empty until decisions exist, and
    generated so the paper cannot describe a process that did not happen.
    """
    prov = OUT.parent / "adjudication/decision_provenance.json"
    dec = OUT.parent / "adjudication/decisions.csv"
    if not prov.exists() or not dec.exists():
        return ""
    import csv as _csv
    n = sum(1 for r in _csv.DictReader(open(dec)) if (r.get("decision") or "").strip())
    if not n:
        return ""
    return (" The verdicts were proposed from that evidence and adopted, not "
            "deliberated group by group.")


def coding_rule_sentence(v: dict) -> str:
    """One sentence about labels predating the clarified `junk` criterion.

    Three states, because two of them are true at different times and the third is a
    decision. While items are outstanding the affected cells are lower bounds. Once
    every item has been re-judged the caveat is gone and the sentence is empty. If the
    annotator instead reviews the carried labels and accepts them, the paper says that
    -- accepting is not re-coding, and a reader has to be able to tell which happened.
    """
    c = v.get("coding_rule") or {}
    total = v.get("n_labels", 0)
    per = c.get("per_finding", {})
    n_pending = c.get("n_old_rule_pending_recode", 0)
    n_carried = c.get("n_carried_from_first_pass", 0)
    clarified = (" Labels were collected in two passes, and the criterion for "
                 "unusable text was clarified between them: a fluent page that exists "
                 "to place links or keywords counts as junk.")

    def where(key: str) -> str:
        worst = sorted(per.items(), key=lambda kv: -kv[1].get(key, 0))[:2]
        return " and ".join(f"{r[key]} of {r['n']}"
                            for _, r in worst if r.get(key))

    if n_pending:
        return (f"{clarified} {n_pending} of the {total} labels predate that "
                f"clarification and are concentrated in two slices "
                f"({where('old_rule_pending_recode')}), whose precision is therefore "
                f"a lower bound until they are re-coded.")
    if c.get("carried_labels_accepted") and n_carried:
        return (f"{clarified} {n_carried} of the {total} labels were given before it "
                f"and the annotator reviewed and kept them rather than judging "
                f"those documents again, which matters most for the two slices where "
                f"they dominate ({where('carried_from_first_pass')}).")
    return ""


def main() -> int:
    summary = json.loads((OUT / "summary.json").read_text())
    report_path = OUT / "testsuite_report.json"
    if not report_path.exists():
        print(f"{report_path} missing: run the test suite with --report first",
              file=sys.stderr)
        return 1
    report = json.loads(report_path.read_text())

    v = summary.get("validation_size") or {}
    ag = (v.get("agreement") or {}).get("coders") or []
    if ag:
        c = ag[0]
        iaa_sentence = (
            f" A second native speaker independently coded {c['n_shared']} of the "
            f"contentious items, agreeing with the primary coder on "
            f"{c['defect_agreement'] * 100:.0f}\\% of the defect judgments "
            f"($\\kappa={c['defect_kappa']:.2f}$) and on "
            f"{c['language_agreement'] * 100:.0f}\\% of the six-way language labels.")
    else:
        iaa_sentence = ""
    # The validated headline, generated so the paper cannot quote a precision the
    # labels do not support. The split is between slices the labels support and slices
    # they do not: a finding whose sample comes out below the acceptance threshold is
    # reported as unsupported rather than averaged into a range that would hide it.
    ag_f = [f for f in summary.get("findings", []) if f["source"] == "agent"]
    ctrl = summary.get("control") or {}
    from analyze import is_validated  # the one definition of the acceptance rule
    supported = [f for f in ag_f if is_validated(f)]
    scored = [f for f in ag_f if (f["human"] or {}).get("precision") is not None]
    unsupported = [f for f in scored if f not in supported]
    val_agent = str(len(supported))
    per_base: dict[str, int] = {}
    for f in summary.get("findings", []):
        if f["source"].startswith("baseline:"):
            k = f["source"].split(":", 1)[1]
            per_base[k] = per_base.get(k, 0) + (1 if is_validated(f) else 0)
    val_base = str(max(per_base.values()) if per_base else 0)

    def p2s(x: float) -> str:
        return f"{x:.2f}".lstrip("0") if x < 1 else "1.00"

    val_min = p2s(min(f["human"]["precision"] for f in supported)) if supported else ""
    val_max = p2s(max(f["human"]["precision"] for f in supported)) if supported else ""
    val_unsup = (p2s(max(f["human"]["precision"] for f in unsupported))
                 if unsupported else "")
    val_n_unsup = str(len(unsupported))
    val_ctrl = p2s(ctrl["precision"]) if ctrl.get("precision") is not None else ""
    val_ctrl_hi = (p2s(ctrl["precision_ci95"][1])
                   if ctrl.get("precision_ci95") else "")
    val_ctrl_n = str(ctrl.get("n_judged", "")) if ctrl else ""
    farm_path = OUT / "farm_facts.json"
    farm = json.loads(farm_path.read_text()) if farm_path.exists() else None
    invalid_share = None
    tests = report["tests"]
    # the inspection budget every strategy was given, and the largest share of any
    # finding that a static slice already retrieves: both quoted more than once
    integ = OUT / "integrity_report.json"
    budget = 300
    if integ.exists():
        budget = json.loads(integ.read_text()).get("budget", budget)
    ags = [f for f in summary.get("findings", []) if f["source"] == "agent"]
    overlaps = [f["max_baseline_overlap"] for f in ags
                if f.get("max_baseline_overlap") is not None
                and f["max_baseline_overlap"] < 1.0]
    max_overlap = max(overlaps) * 100 if overlaps else None
    inv = next((t for t in tests if t["id"] == "language_score_not_a_probability"), None)
    if inv is not None:
        invalid_share = inv["prevalence"] * 100
    slice_tests = [t for t in tests if t.get("kind") != "metadata_invariant"]

    macros = {
        # human validation, as collected
        "vallabels": v.get("n_labels", 0),
        "valcellmin": v.get("min", 0),
        "valcellmax": v.get("max", 0),
        "valcellmed": v.get("median", 0),
        # the suite, as it stands after adjudication
        "suiten": len(tests),
        "nretained": len(slice_tests),
        "suitesecs": f"{report['seconds']:.1f}",
        "suitedocs": f"{report['n_total']:,}".replace(",", "{,}"),
        # quantities the prose repeats: quoted once each, so two copies cannot
        # disagree and a single-site edit cannot go unnoticed
        "farmdocs": f"{farm['farm_docs']:,}".replace(",", "{,}") if farm else "",
        "agentcost": f"{summary['agent_cost_usd']:.2f}",
        "invalidshare": f"{invalid_share:.1f}" if invalid_share is not None else "",
        "corpusM": f"{report['n_total'] / 1e6:.1f}",
        "budget": budget,
        "maxoverlap": f"{max_overlap:.1f}" if max_overlap is not None else "",
        "farmwordshare": (f"{farm['farm_word_share'] * 100:.1f}" if farm else ""),
        # Either a reported agreement figure or nothing: the Limitations sentence
        # about a single annotator is true until a second coder exists, and this
        # macro makes the paper follow the artefacts instead of being edited by hand.
        "iaasentence": iaa_sentence,
        # Two coding passes: the `junk` criterion was clarified mid-annotation, so
        # some labels predate it. The sentence is generated from the split recorded
        # in summary.json and becomes empty on its own once the re-coding is done --
        # the caveat cannot outlive the condition it describes, or go missing while
        # it holds.
        "codingrulesentence": coding_rule_sentence(v),
        "adjsentence": adjudication_sentence(),
        # How many candidates the blinded labels support, per side. Generated, so the
        # sentence in RQ4 follows the adjudication instead of needing a rewrite after it.
        "validagent": val_agent,
        "validbase": val_base,
        # The acceptance threshold the Valid. column applies, read from the analysis so
        # the caption cannot describe a different rule from the one that ran.
        "thresholdaccept": f"{PRECISION_ACCEPT:.1f}".lstrip("0"),
        # The validated headline.
        "valpmin": val_min,
        "valpmax": val_max,
        "valunsup": val_unsup,
        "valnunsup": val_n_unsup,
        "valcontrol": val_ctrl,
        "valcontrolhi": val_ctrl_hi,
        "valcontroln": val_ctrl_n,
    }
    body = "".join(rf"\newcommand{{\{k}}}{{{val}}}" + "\n"
                   for k, val in macros.items())
    for d in (OUT, REPO / "paper"):
        if d.exists():
            (d / "paper_macros.tex").write_text(body)
    print(f"wrote paper_macros.tex: " +
          ", ".join(f"{k}={val}" for k, val in macros.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
