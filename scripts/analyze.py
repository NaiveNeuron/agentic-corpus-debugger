#!/usr/bin/env python
"""Analysis for the paper: prevalence, baseline overlap, human precision, cost.

Writes out/analysis/summary.json plus LaTeX table bodies included by the paper.
Every number the paper reports about our own experiments comes from here.

Usage: analyze.py [--runs out/runs/main out/runs/rep1 out/runs/rep2]
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.corpusaudit.adjudication import load_decisions  # noqa: E402
from src.corpusaudit.db import open_corpus  # noqa: E402
from src.corpusaudit.anon import redact_pii
from src.corpusaudit.selectors import needs_text  # noqa: E402
from src.corpusaudit.tools import wilson  # noqa: E402

# The obvious static audit slices, defined only over published metadata.
BASELINE_SLICES = {
    "LID-Disagree": "fasttext <> 'sk' or langdetect <> 'sk' or lingua_top <> 'sk'",
    "LowConf": "language_score < 0.8",
    "HighDup": "minhash_cluster_size >= 100",
}
STRATEGY_LABELS = {"random": "Random", "lowconf": "LowConf",
                   "lid_disagree": "LID-Disagree", "highdup": "HighDup"}

MIN_JUDGMENTS = 5  # below this a slice's precision is too uncertain to report
DEFECT_LANG = {"cs", "mix", "other"}
DEFECT_QUAL = {"junk"}
PRECISION_ACCEPT = 0.5


def load_candidates(runs: list[str]) -> list[dict]:
    """All candidate findings, deduplicated by selector."""
    by_sel: dict[str, dict] = {}
    for run in runs:
        name = pathlib.Path(run).name
        for path in sorted(glob.glob(f"{run}/findings/*.yaml")):
            t = yaml.safe_load(open(path))
            sel = t["selector"].strip()
            if sel in by_sel:
                by_sel[sel]["runs"].append(name)
                continue
            by_sel[sel] = {"id": t["id"], "source": "agent", "runs": [name],
                           "yaml": t, "selector": sel}
    for path in sorted(glob.glob("out/baselines/*/findings/*.yaml")):
        t = yaml.safe_load(open(path))
        strategy = pathlib.Path(path).parent.parent.name
        sel = t["selector"].strip()
        if sel in by_sel:
            by_sel[sel].setdefault("also_baseline", []).append(strategy)
            continue
        by_sel[sel] = {"id": t["id"], "source": f"baseline:{strategy}", "runs": [],
                       "yaml": t, "selector": sel}
    return list(by_sel.values())


LANGS = {"sk", "sk-pred", "cs", "mix", "other", "?"}
QUALS = {"good", "noisy", "junk", "?"}


def _validate(rows: dict, path: pathlib.Path, prov: dict) -> None:
    bad = [(i, r.get("language"), r.get("quality")) for i, r in rows.items()
           if r.get("language") not in LANGS or r.get("quality") not in QUALS]
    if bad:
        raise SystemExit(
            f"{len(bad)} label row(s) in {path} use values outside the vocabulary, "
            f"e.g. {bad[:3]}.\nExpected language in {sorted(LANGS)} and quality in "
            f"{sorted(QUALS)} -- annotate.py writes these words, not the keypress "
            f"digits. Precision would otherwise read 0.00 for every slice.")
    unknown = [i for i in rows if i not in prov]
    if unknown:
        raise SystemExit(f"{len(unknown)} labelled item(s) in {path} are absent from "
                         f"provenance.csv, e.g. {unknown[:3]}: the join would drop them.")


def _is_defect(row: dict) -> bool:
    return row["language"] in DEFECT_LANG or row["quality"] in DEFECT_QUAL


def agreement(annotation_dir: str = "out/annotation") -> dict | None:
    """Cohen's kappa on the doubly-coded items, if a second coder exists.

    Precision is always taken from the primary pass; a second coder measures whether
    that judgment is reproducible, which matters most for the Czech/Slovak calls: an
    external benchmark puts 55% of such material in *both* languages at once, so the
    threshold a single annotator applies is otherwise unmeasurable.
    """
    d = pathlib.Path(annotation_dir)
    primary_path = d / "labels.csv"
    others = sorted(p for p in d.glob("labels.*.csv") if p.name != "labels.csv")
    if not primary_path.exists() or not others:
        return None
    prov = {r["item_id"]: r for r in csv.DictReader(open(d / "provenance.csv"))}
    primary = {r["item_id"]: r for r in csv.DictReader(open(primary_path))}
    _validate(primary, primary_path, prov)
    out = []
    for path in others:
        second = {r["item_id"]: r for r in csv.DictReader(open(path))}
        _validate(second, path, prov)
        shared = sorted(set(primary) & set(second))
        if not shared:
            continue
        a = [_is_defect(primary[i]) for i in shared]
        b = [_is_defect(second[i]) for i in shared]
        n = len(shared)
        obs = sum(x == y for x, y in zip(a, b)) / n
        pa, pb = sum(a) / n, sum(b) / n
        exp = pa * pb + (1 - pa) * (1 - pb)
        kappa = (obs - exp) / (1 - exp) if exp < 1 else 1.0
        lang_obs = sum(primary[i]["language"] == second[i]["language"]
                       for i in shared) / n
        out.append({
            "coder": path.name.split(".")[1], "n_shared": n,
            "defect_agreement": obs, "defect_kappa": kappa,
            "language_agreement": lang_obs,
            "slices": sorted({prov[i]["slice"] for i in shared}),
        })
    return {"coders": out} if out else None


def human_tables(annotation_dir: str = "out/annotation") -> tuple[dict, dict]:
    d = pathlib.Path(annotation_dir)
    if not (d / "labels.csv").exists():
        return {}, {}
    prov = {r["item_id"]: r for r in csv.DictReader(open(d / "provenance.csv"))}
    labels = {r["item_id"]: r for r in csv.DictReader(open(d / "labels.csv"))}
    _validate(labels, d / "labels.csv", prov)
    return prov, labels


def write_table(out: pathlib.Path, name: str, rows: list[str]) -> None:
    """Write a LaTeX tabular body to both the analysis and paper directories."""
    # \bottomrule lives inside the fragment: a \input boundary immediately
    # before a \noalign command inside tabular is a LaTeX error.
    body = "\n".join(rows) + "\n\\bottomrule\n"
    for d in (out, pathlib.Path("paper")):
        if d.exists():
            (d / name).write_text(body)


def is_validated(f: dict) -> bool:
    """A finding counts as validated when a human approved it and the blinded
    sample supports it (or, before adjudication, when only the sample can speak)."""
    h = f["human"]
    if h["n_judged"] < MIN_JUDGMENTS or h["precision"] is None:
        return False
    if f.get("human_decision") == "reject":
        return False
    return h["precision"] >= PRECISION_ACCEPT


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="*",
                    default=["out/runs/main", "out/runs/rep1", "out/runs/rep2"])
    ap.add_argument("--primary", default="main")
    ap.add_argument("--derived", default="data/derived")
    ap.add_argument("--out", default="out/analysis")
    ap.add_argument("--annotation", default="out/annotation")
    ap.add_argument("--adjudication", default="out/adjudication")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    corpus = open_corpus(args.derived)
    con = corpus.con

    base_sizes = {n: con.execute(f"select count(*) from meta where ({s})").fetchone()[0]
                  for n, s in BASELINE_SLICES.items()}

    prov, labels = human_tables(args.annotation)
    decisions, dec_notes, dec_group = load_decisions(args.adjudication)
    by_slice: dict[str, list[dict]] = {}
    for item_id, lab in labels.items():
        p = prov.get(item_id)
        if p:
            by_slice.setdefault(p["slice"], []).append(lab)

    def human_stats(slice_id: str) -> dict:
        rows = by_slice.get(slice_id, [])
        n = len(rows)
        bad = sum(1 for r in rows
                  if r["language"] in DEFECT_LANG or r["quality"] in DEFECT_QUAL)
        junk = sum(1 for r in rows if r["quality"] in DEFECT_QUAL)
        notsk = sum(1 for r in rows if r["language"] in DEFECT_LANG)
        lo, hi = wilson(bad, n)
        dist_l: dict[str, int] = {}
        dist_q: dict[str, int] = {}
        for r in rows:
            dist_l[r["language"]] = dist_l.get(r["language"], 0) + 1
            dist_q[r["quality"]] = dist_q.get(r["quality"], 0) + 1
        return {"n_judged": n, "n_defective": bad, "n_junk": junk, "n_not_slovak": notsk,
                "precision": bad / n if n else None,
                "precision_ci95": [lo, hi] if n else None,
                "language_labels": dist_l, "quality_labels": dist_q}

    findings = []
    for cand in load_candidates(args.runs):
        sel, t = cand["selector"], cand["yaml"]
        uses_text = needs_text(sel)
        rel = "docs" if uses_text else "meta"
        n_eval = corpus.n_sample if uses_text else corpus.n_total
        try:
            k = con.execute(f"select count(*) from {rel} where ({sel})").fetchone()[0]
        except Exception as exc:
            findings.append({"id": cand["id"], "source": cand["source"], "selector": sel,
                             "runs": cand["runs"], "error": str(exc)[:200],
                             "human": human_stats(cand["id"])})
            continue
        overlap = {}
        for name, bsel in BASELINE_SLICES.items():
            overlap[name] = (con.execute(
                f"select count(*) from {rel} where ({sel}) and ({bsel})").fetchone()[0] / k
                if k else None)
        lo, hi = wilson(k, n_eval)
        findings.append({
            "id": cand["id"], "source": cand["source"], "runs": cand["runs"],
            "also_baseline": cand.get("also_baseline", []),
            "description": t.get("description", ""), "selector": sel,
            "assertion": t.get("assertion", ""),
            "n_matched": k, "n_evaluated": n_eval, "exact_on_full_corpus": not uses_text,
            "prevalence": k / n_eval if n_eval else 0.0, "prevalence_ci95": [lo, hi],
            "estimated_docs_full_corpus": round(k / n_eval * corpus.n_total) if n_eval else 0,
            "agent_expected_precision": t["evidence"].get("agent_expected_precision"),
            "likely_false_positives": t["evidence"].get("likely_false_positives", ""),
            # Carried through so a released test is self-contained: why the auditor
            # believed it, and which documents to look at. Redacted like everything
            # else that leaves the environment.
            "agent_evidence": redact_pii(str(t["evidence"].get("agent_evidence", ""))),
            "agent_example_ids": [str(x) for x in (t["evidence"].get("example_ids") or [])][:5],
            "baseline_overlap": overlap,
            "max_baseline_overlap": max((v for v in overlap.values() if v is not None),
                                        default=None),
            "human": human_stats(cand["id"]),
            "human_decision": decisions.get(cand["id"], "pending"),
            "adjudication_group": dec_group.get(cand["id"], ""),
        })

    costs: dict[str, dict] = {}
    for path in glob.glob("out/runs/*/cost.json") + glob.glob("out/baselines/*/cost.json"):
        costs[pathlib.Path(path).parent.name] = json.load(open(path))
    for path in glob.glob("out/runs/*/tools.jsonl"):
        key = pathlib.Path(path).parent.name
        recs = [json.loads(l) for l in open(path) if l.strip()]
        costs.setdefault(key, {})["tool_calls"] = len(recs)
        costs[key]["inspections_used"] = max((r["inspections_used"] for r in recs), default=0)
        costs[key]["findings_saved"] = sum(1 for r in recs if r["tool"] == "save_finding")

    run_names = [pathlib.Path(r).name for r in args.runs]
    agent_findings = [f for f in findings if f["source"] == "agent"]
    per_strategy: dict[str, dict] = {}
    agent_selectors = {f["selector"] for f in agent_findings}
    for path in glob.glob("out/baselines/*/findings/*.yaml"):
        strategy = pathlib.Path(path).parent.parent.name
        sel = yaml.safe_load(open(path))["selector"].strip()
        d = per_strategy.setdefault(strategy, {"selectors": set(), "files": 0})
        d["selectors"].add(sel)
        d["files"] += 1
    for strategy, d in per_strategy.items():
        d["n_distinct"] = len(d["selectors"])
        d["n_same_as_agent"] = len(d["selectors"] & agent_selectors)

    # Which baseline strategies independently proposed an equivalent slice?
    # Equivalence is measured on documents (Jaccard), not on selector text.
    baseline_cands = [f for f in findings if f["source"].startswith("baseline") and "error" not in f]
    for f in agent_findings:
        if "error" in f:
            continue
        rediscovered: dict[str, float] = {}
        for b in baseline_cands:
            rel = ("docs" if needs_text(f["selector"]) or needs_text(b["selector"])
                   else "meta")
            try:
                inter = con.execute(
                    f"select count(*) from {rel} where ({f['selector']}) and ({b['selector']})"
                ).fetchone()[0]
                union = con.execute(
                    f"select count(*) from {rel} where ({f['selector']}) or ({b['selector']})"
                ).fetchone()[0]
            except Exception:
                continue
            j = inter / union if union else 0.0
            strategy = b["source"].split(":")[1]
            rediscovered[strategy] = max(rediscovered.get(strategy, 0.0), j)
        f["baseline_jaccard"] = rediscovered
        # a baseline that proposed a byte-identical selector was merged into this
        # finding by the deduplication above; count it as a rediscovery too
        for strategy in f.get("also_baseline", []):
            rediscovered[strategy] = 1.0
        f["rediscovered_by"] = sorted(k for k, v in rediscovered.items() if v >= 0.8)
        f["expected_hits_in_300_random"] = f["prevalence"] * 300
    # The realised validation size, computed before the summary that records it: the
    # paper must state how many documents actually back each precision cell, not how
    # many the package offers, or an annotator who stops early leaves the design's
    # "25 per finding" standing over cells resting on a handful.
    judged = sorted(f["human"]["n_judged"] for f in agent_findings if "error" not in f)
    # Labels predating a mid-annotation clarification of the `junk` criterion are
    # tracked separately: the annotator listed the items needing re-judgement, and
    # the ones still carrying an old-rule label are concentrated in a few slices, so
    # a reader must be able to see which precision cells rest on them.
    ann = pathlib.Path(args.annotation)
    p2 = ann / "pass2_labels.csv"
    recode = ann / "recode_items.txt"
    new_rule = ({r["item_id"] for r in csv.DictReader(open(p2))}
                if p2.exists() else set(labels))
    # Items judged again after the rule changed carry the current rule, whatever
    # label the re-judgement produced. Without this the caveat could never clear:
    # a re-judgement that confirms the old label would be indistinguishable from
    # one that never happened.
    redone = ann / "recoded.txt"
    if redone.exists():
        new_rule |= {x.strip() for x in open(redone) if x.strip()}
    carried = ({x.strip() for x in open(recode) if x.strip()} - new_rule
               if recode.exists() else set())
    # The annotator may review the carried labels and accept them instead of judging
    # each document again. That is a decision, not a measurement, so it is read from
    # a file the annotator owns and reported as acceptance -- never as re-coding,
    # which would claim an act that did not happen.
    dec_path = ann / "coding_decision.json"
    decision = (json.loads(dec_path.read_text()) if dec_path.exists() else {})
    accepted = decision.get("decision") == "accept_carried_labels"
    pending = set() if accepted else carried
    # The list the annotator was given holds every item the rule change could touch,
    # including the ones already re-judged. Writing out the remainder keeps the
    # pending list from presenting work that is finished, and removing it keeps it
    # from offering work that has been closed by a decision.
    pending_path = ann / "recode_pending.txt"
    if pending:
        pending_path.write_text("".join(f"{i}\n" for i in sorted(pending)))
    elif pending_path.exists():
        pending_path.unlink()
    per_finding_rule = {}
    for f in agent_findings:
        ids = [i for i, lab in labels.items()
               if prov.get(i, {}).get("slice") == f["id"]]
        per_finding_rule[f["id"]] = {
            "n": len(ids),
            "new_rule": sum(1 for i in ids if i in new_rule),
            "carried_from_first_pass": sum(1 for i in ids if i in carried),
            "old_rule_pending_recode": sum(1 for i in ids if i in pending),
        }
    summary_validation = {
        "agreement": agreement(args.annotation),
        "coding_rule": {
            "n_new_rule": len([i for i in labels if i in new_rule]),
            "n_carried_from_first_pass": len([i for i in labels if i in carried]),
            "carried_labels_accepted": accepted,
            "n_old_rule_pending_recode": len([i for i in labels if i in pending]),
            "n_recode_outstanding": len(pending),
            "per_finding": per_finding_rule,
        },
        "n_labels": len(labels),
        "per_finding": judged,
        "min": judged[0] if judged else 0,
        "max": judged[-1] if judged else 0,
        "median": judged[len(judged) // 2] if judged else 0,
    }

    summary = {
        "corpus": {"n_total": corpus.n_total, "n_sample": corpus.n_sample},
        "baseline_slices": {n: {"selector": s, "n": base_sizes[n],
                                "prevalence": base_sizes[n] / corpus.n_total}
                            for n, s in BASELINE_SLICES.items()},
        "control": human_stats("random_control"),
        "rediscovery": {f["id"]: {"by": f.get("rediscovered_by"),
                                  "jaccard": f.get("baseline_jaccard"),
                                  "expected_hits_300": f.get("expected_hits_in_300_random")}
                        for f in agent_findings},
        "baseline_candidate_counts": {k: {kk: vv for kk, vv in v.items()
                                          if kk != "selectors"}
                                      for k, v in per_strategy.items()},
        "n_candidates": {"agent_distinct_selectors": len(agent_findings),
                         "per_run": {r: costs.get(r, {}).get("findings_saved") for r in run_names}},
        "agent_cost_usd": sum(costs.get(r, {}).get("total_cost_usd", 0) for r in run_names),
        "agent_inspections": {r: costs.get(r, {}).get("inspections_used") for r in run_names},
        # Recorded, not merely printed: the release check and the paper checker
        # both need to know whether any human judgment exists at all.
        "n_human_labels": len(labels),
        "n_annotation_items": len(prov),
        "validation_size": summary_validation,
        "n_adjudicated_groups": sum(
            1 for r in csv.DictReader(open("out/adjudication/decisions.csv"))
            if (r.get("decision") or "").strip()
        ) if pathlib.Path("out/adjudication/decisions.csv").exists() else 0,
        "findings": findings,
        "costs": costs,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))

    # Corpus-level facts the setup and data paragraphs quote. Computed here so the
    # paper cannot quote a stale host count or slice prevalence.
    hosts = con.execute("select count(distinct domain) from meta").fetchone()[0]
    crawls = con.execute("select count(distinct dump) from meta").fetchone()[0]
    mean_words = con.execute("select avg(n_words) from meta").fetchone()[0]
    n_docs = con.execute("select count(*) from meta").fetchone()[0]
    slice_counts = {name: con.execute(
        f"select count(*) from meta where {cond}").fetchone()[0]
        for name, cond in BASELINE_SLICES.items()}
    (out / "corpus_facts.json").write_text(json.dumps({
        "corpus_docs": n_docs, "distinct_hosts": hosts, "crawls": crawls,
        "corpus_mean_words": mean_words,
        "static_slices": {k: {"n": v, "share": v / n_docs}
                          for k, v in slice_counts.items()},
    }, indent=2))

    # The counter-example numbers the results section leans on: a slice that looks
    # better than average to every static signal. Recomputed here so they cannot
    # drift from the paper, which asserts each one.
    FARM = "domain LIKE '%.firebaseapp.com' OR domain LIKE '%.web.app'"
    SLO = "domain LIKE 'slo.%'"
    AGREE = "fasttext='sk' AND langdetect='sk' AND lingua_top='sk'"
    tot, words_tot = con.execute("select count(*), sum(n_words) from meta").fetchone()
    fn, fls, fmh, fag, fw = con.execute(
        f"""select count(*), avg(language_score), avg(minhash_cluster_size),
                   avg(case when {AGREE} then 1.0 else 0.0 end), sum(n_words)
            from meta where {FARM}""").fetchone()
    clean = con.execute(
        f"""select count(*) from meta where ({FARM}) and language_score >= 0.9
            and minhash_cluster_size <= 2 and {AGREE}""").fetchone()[0]
    slo_n = con.execute(f"select count(*) from meta where {SLO}").fetchone()[0]
    slo_lc, slo_hd, slo_ld = con.execute(
        f"""select sum(case when language_score < 0.8 then 1 else 0 end),
                   sum(case when minhash_cluster_size >= 100 then 1 else 0 end),
                   sum(case when not ({AGREE}) then 1 else 0 end)
            from meta where {SLO}""").fetchone()
    (out / "farm_facts.json").write_text(json.dumps({
        "corpus_docs": tot, "corpus_words": int(words_tot),
        "farm_docs": fn, "farm_mean_language_score": fls,
        "farm_mean_cluster": fmh, "farm_three_way_agreement": fag,
        "farm_words": int(fw), "farm_word_share": fw / words_tot,
        "farm_pass_all_static": clean, "farm_pass_all_static_share": clean / tot,
        # measurements the paper quotes that nothing was checking: the farm's host
        # count, its peak single-crawl share, the corpus floor and the static
        # thresholds the "passes everything" figure was computed at
        "farm_hosts": con.execute(
            f"select count(distinct domain) from meta where ({FARM})").fetchone()[0],
        "farm_peak_crawl_share": con.execute(
            f"select max(s) from (select count(*) filter (where {FARM})*1.0/count(*) s "
            f"from meta group by dump)").fetchone()[0],
        "min_language_score": con.execute(
            "select min(language_score) from meta").fetchone()[0],
        "pass_all_static_thresholds": {"language_score_min": 0.9,
                                       "cluster_max": 2},
        "farm_mean_words": con.execute(
            f"select avg(n_words) from meta where {FARM}").fetchone()[0],
        "slo_docs": slo_n, "slo_overlap_lowconf": int(slo_lc or 0),
        "slo_overlap_highdup": int(slo_hd or 0),
        "slo_overlap_lid_disagree": int(slo_ld or 0),
    }, indent=2))

    def esc(s: str) -> str:
        for a, b in (("_", r"\_"), ("&", r"\&"), ("%", r"\%"), ("#", r"\#")):
            s = s.replace(a, b)
        return s

    # ---- Table: agent findings ---------------------------------------------
    lines = []
    for f in sorted(agent_findings, key=lambda x: -x["prevalence"]):
        if "error" in f:
            continue
        h = f["human"]
        def trim(x: float) -> str:
            """0.92 -> .92, to keep the table inside one ACL column."""
            return f"{x:.2f}".lstrip("0") or "0"

        prec = (f"{trim(h['precision'])}\\,[{trim(h['precision_ci95'][0])},"
                f"{trim(h['precision_ci95'][1])}]"
                if h["n_judged"] >= MIN_JUDGMENTS else r"\pendingP")
        ov = f["max_baseline_overlap"]
        lines.append(
            f"{{\\scriptsize {esc(f['id'])}}} & {f.get('adjudication_group') or '--'} & "
            f"{len(f['runs'])}/{len(f['rediscovered_by'])} & "
            f"{f['prevalence'] * 100:.2f} & {prec} & "
            f"{'--' if ov is None else f'{ov * 100:.0f}'} \\\\")
    write_table(out, "table_findings.tex", lines)


    # ---- Table: budget-matched comparison ---------------------------------
    rows = []
    for key, label in STRATEGY_LABELS.items():
        cand = [f for f in findings if f["source"] == f"baseline:{key}"]
        info = per_strategy.get(key, {"n_distinct": len(cand), "n_same_as_agent": 0})
        valid = [f for f in cand if is_validated(f)]
        usd = costs.get(key, {}).get("total_cost_usd")
        nv = (len(valid) if any(f["human"]["n_judged"] >= MIN_JUDGMENTS for f in cand)
              else None)
        rows.append(f"\\textsc{{{label}}} & 300 & {info['n_distinct']} & "
                    f"{info['n_same_as_agent']} & "
                    f"{r'\pendingV' if nv is None else nv} & "
                    f"{'--' if usd is None else f'{usd:.2f}'} \\\\")
    a_valid = [f for f in agent_findings if is_validated(f)]
    insp = sum(v or 0 for v in summary["agent_inspections"].values())
    n_groups = len({f.get("adjudication_group") for f in agent_findings})
    rows.append(f"\\textsc{{Agent}} ($\\times${len(run_names)}) & {insp} & "
                f"{len(agent_findings)} & {n_groups} & "
                f"{len(a_valid) if any(f['human']['n_judged'] >= MIN_JUDGMENTS for f in agent_findings) else r'\pendingV'} & "
                f"{summary['agent_cost_usd']:.2f} \\\\")
    write_table(out, "table_budget.tex", rows)

    print(json.dumps({
        "agent_distinct_findings": len(agent_findings),
        "per_run_findings": summary["n_candidates"]["per_run"],
        "agent_inspections": summary["agent_inspections"],
        "agent_cost_usd": round(summary["agent_cost_usd"], 2),
        "baseline_candidates": {k: sum(1 for f in findings if f["source"] == f"baseline:{k}")
                                for k in STRATEGY_LABELS},
        "baseline_cost_usd": round(sum(costs.get(k, {}).get("total_cost_usd", 0)
                                       for k in STRATEGY_LABELS), 2),
        "n_human_labels": len(labels),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
