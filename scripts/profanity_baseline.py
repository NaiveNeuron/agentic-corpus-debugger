"""Measure the HighProf baseline without touching summary.json.

Reads out/baselines/highprof/{sample.json,cost.json,findings/*.yaml} and the
agent findings in out/analysis/summary.json; writes
out/analysis/profanity_baseline.json.  Candidates are measured exactly as
analyze.py measures the other baselines' candidates.
"""
import glob
import json
import os
import pathlib
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.corpusaudit.db import open_corpus  # noqa: E402
from src.corpusaudit.selectors import needs_text  # noqa: E402
from src.corpusaudit.tools import wilson  # noqa: E402

SLICE = "n_bad_words >= 3"
BASE = pathlib.Path("out/baselines/highprof")
G04 = ("adult_spam_farm_wordsalad", "porn_spam_keyword_farm", "porn_doorway_spam_network")


def count(con, rel: str, where: str) -> int:
    return con.execute(f"select count(*) from {rel} where ({where})").fetchone()[0]


def main() -> int:
    corpus = open_corpus("data/derived")
    con = corpus.con
    summary = json.load(open("out/analysis/summary.json"))
    agent = [f for f in summary["findings"] if f["source"] == "agent" and "error" not in f]
    n_total = corpus.n_total

    k_slice = count(con, "meta", SLICE)
    lo, hi = wilson(k_slice, n_total)
    g04 = {}
    for f in agent:
        if f["id"] in G04:
            k = count(con, "meta", f["selector"])
            g04[f["id"]] = {"selector": f["selector"], "n": k,
                            "n_in_slice": count(con, "meta", f"({f['selector']}) and ({SLICE})"),
                            "share_covered": count(con, "meta", f"({f['selector']}) and ({SLICE})") / k}

    sample = json.load(open(BASE / "sample.json"))
    ids = [str(d["id"]) for d in sample]
    con.execute("create or replace temp table hp_sample(id varchar)")
    con.executemany("insert into hp_sample values (?)", [(i,) for i in ids])
    nbw = [d.get("n_bad_words") or 0 for d in sample]
    sample_in = {f["id"]: con.execute(
        f"select count(*) from meta where id::varchar in (select id from hp_sample) "
        f"and ({f['selector']})").fetchone()[0] for f in agent}

    agent_sel = {f["selector"].strip(): f["id"] for f in agent}
    candidates = []
    for path in sorted(glob.glob(str(BASE / "findings/*.yaml"))):
        t = yaml.safe_load(open(path))
        sel = t["selector"].strip()
        uses_text = needs_text(sel)
        rel = "docs" if uses_text else "meta"
        n_eval = corpus.n_sample if uses_text else n_total
        c = {"id": t["id"], "description": t.get("description"), "selector": sel,
             "byte_identical_to_agent": agent_sel.get(sel)}
        try:
            k = count(con, rel, sel)
        except Exception as exc:
            c["error"] = str(exc)[:200]
            candidates.append(c)
            continue
        clo, chi = wilson(k, n_eval)
        jac = {}
        for f in agent:
            r = "docs" if uses_text or needs_text(f["selector"]) else "meta"
            inter = count(con, r, f"({f['selector']}) and ({sel})")
            union = count(con, r, f"({f['selector']}) or ({sel})")
            jac[f["id"]] = inter / union if union else 0.0
        groups: dict[str, float] = {}
        for f in agent:
            g = f.get("adjudication_group") or "?"
            groups[g] = max(groups.get(g, 0.0), jac[f["id"]])
        c.update({"n_matched": k, "n_evaluated": n_eval, "evaluated_on": rel,
                  "prevalence": k / n_eval, "prevalence_ci95": [clo, chi],
                  "jaccard_with_agent": jac, "max_jaccard_by_group": groups})
        candidates.append(c)

    cost = json.load(open(BASE / "cost.json")) if (BASE / "cost.json").exists() else None
    raw = BASE / "raw.json"
    model = list(json.load(open(raw)).get("modelUsage", {})) if raw.exists() else None
    out = {
        "strategy": "highprof",
        "order": "n_bad_words desc nulls last, hash(id || '0')",
        "budget": len(sample),
        "n_total": n_total,
        "overlap_slice": {"selector": SLICE, "n": k_slice, "prevalence": k_slice / n_total,
                          "prevalence_ci95": [lo, hi]},
        "sample_n_bad_words": {"min": min(nbw), "max": max(nbw),
                               "n_ge_3": sum(1 for x in nbw if x >= 3)},
        "sample_in_agent_slice": sample_in,
        "g04_coverage_by_slice": g04,
        "llm_run": {"completed": cost is not None, "model_usage": model, "cost": cost},
        "candidates": candidates,
    }
    pathlib.Path("out/analysis/profanity_baseline.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=1)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
