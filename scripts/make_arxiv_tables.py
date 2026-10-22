#!/usr/bin/env python3
"""Generate the run-by-run comparison tables and macros the paper reports.

Each agent run is compared with each baseline on its own, and a selector that
several conditions proposed byte-identically is credited to every one of them.
The script derives this from the released artefacts and writes new files only
(`out/analysis/arxiv_*.tex`); if a paper source directory `paper/` sits next to
the code, it copies them there too.

Inputs: out/analysis/summary.json (findings, runs, costs, human labels, adjudication
groups), out/adjudication/{decisions,groups}.csv and decision_provenance.json
(verdicts and how they were reached), out/annotation/*.csv (attrition of the
annotation package), out/analysis/{profanity_baseline,farm_facts,cross_language,
classification_cost,sample_clustering,replay_report}.json.
"""

from __future__ import annotations

import csv
import json
import pathlib
import shutil
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analyze import (  # noqa: E402  the one definition of the acceptance rule
    DEFECT_LANG,
    DEFECT_QUAL,
    MIN_JUDGMENTS,
    PRECISION_ACCEPT,
    STRATEGY_LABELS,
    wilson,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
OUT = REPO / "out/analysis"
ARXIV = REPO / "paper"  # the paper source, when it is checked out next to the code
RUNS = ["main", "rep1", "rep2"]
RUN_LABELS = {"main": "Agent run 1", "rep1": "Agent run 2", "rep2": "Agent run 3"}


def trim(x: float) -> str:
    """0.92 -> .92, as in the WaC tables."""
    return f"{x:.2f}".lstrip("0") or "0"


def thousands(n: int) -> str:
    return f"{n:,}".replace(",", "{,}")


def validated(f: dict, decisions: dict[str, str]) -> bool:
    """The labels branch of the adjudication rule: an `approve` verdict backed by
    >= MIN_JUDGMENTS blinded labels at a defect rate of at least PRECISION_ACCEPT.
    Per-finding verdicts override group verdicts, as in out/adjudication/decisions.csv.
    An approval reached without enough labels does not count."""
    h = f["human"]
    if h["n_judged"] < MIN_JUDGMENTS or h["precision"] is None:
        return False
    verdict = decisions.get(f["id"], decisions.get(f.get("adjudication_group", ""), ""))
    return verdict == "approve" and h["precision"] >= PRECISION_ACCEPT


def norm(sel: str) -> str:
    return "".join(sel.lower().split())


def relabel_by_selector(findings: list[dict]) -> list[dict]:
    """Attribute blinded labels by selector, not by slice name.

    The annotation package names each drawn slice after the candidate file it was
    drawn for. analyze.py merges byte-identical selectors under one candidate name and
    reads labels by that name only, so labels drawn under a merged duplicate's name
    were lost (Random's `english_documents_labeled_slovak`, identical to LowConf's
    `english_documents_mislabeled_as_slovak`). Here a finding's labels are those of
    every drawn slice whose candidate selector is byte-identical to its own."""
    slice_selector: dict[str, str] = {}
    paths = [p for run in RUNS for p in (REPO / "out/runs" / run / "findings").glob("*.yaml")]
    paths += list(REPO.glob("out/baselines/*/findings/*.yaml"))
    for p in paths:
        y = yaml.safe_load(open(p))
        slice_selector[y.get("id", p.stem)] = y["selector"].strip()
    prov = {r["item_id"]: r["slice"]
            for r in csv.DictReader(open(REPO / "out/annotation/provenance.csv"))}
    by_selector: dict[str, list[dict]] = {}
    for r in csv.DictReader(open(REPO / "out/annotation/labels.csv")):
        sel = slice_selector.get(prov[r["item_id"]])
        if sel is not None:
            by_selector.setdefault(sel, []).append(r)
    for f in findings:
        rows = by_selector.get(f["selector"].strip(), [])
        if len(rows) <= f["human"]["n_judged"]:
            continue
        bad = sum(1 for r in rows
                  if r["language"] in DEFECT_LANG or r["quality"] in DEFECT_QUAL)
        lo, hi = wilson(bad, len(rows))
        f["human"] = {**f["human"], "n_judged": len(rows), "n_defective": bad,
                      "precision": bad / len(rows), "precision_ci95": [lo, hi]}
    return findings


def load_findings(summary: dict) -> list[dict]:
    return relabel_by_selector([f for f in summary["findings"] if "error" not in f])


def credited(findings: list[dict], key: str) -> list[dict]:
    """A baseline's own candidates plus any finding it proposed byte-identically."""
    return [f for f in findings
            if f["source"] == f"baseline:{key}" or key in f.get("also_baseline", [])]


def main() -> int:
    summary = json.loads((OUT / "summary.json").read_text())
    decisions = {r["group"]: r["decision"]
                 for r in csv.DictReader(open(REPO / "out/adjudication/decisions.csv"))}
    findings = load_findings(summary)
    costs = summary["costs"]

    # ---- per-condition credit ------------------------------------------------
    # A baseline is credited with its own candidates, and with any finding it
    # proposed byte-identically (`also_baseline`): the deduplication merged those
    # into another condition's row, which is why the WaC table showed Random at zero.
    cond: dict[str, dict] = {}
    for run in RUNS:
        mine = [f for f in findings if f["source"] == "agent" and run in f["runs"]]
        cond[run] = {"cand": summary["n_candidates"]["per_run"][run], "findings": mine,
                     "insp": summary["agent_inspections"][run],
                     "usd": costs[run]["total_cost_usd"]}
    base_counts = summary["baseline_candidate_counts"]
    for key in STRATEGY_LABELS:
        mine = credited(findings, key)
        cond[key] = {"cand": base_counts[key]["n_distinct"], "findings": mine,
                     "insp": 300, "usd": costs[key]["total_cost_usd"]}
    for c in cond.values():
        v = [f for f in c["findings"] if validated(f, decisions)]
        c["valid"] = v
        c["groups"] = sorted({f["adjudication_group"] for f in v})

    def pooled(keys: list[str]) -> dict:
        fs = [f for k in keys for f in cond[k]["valid"]]
        # Selectors that are the same string up to whitespace, or that match exactly
        # the same number of documents within one phenomenon group, are counted once.
        seen, uniq = set(), []
        for f in fs:
            key = (f["adjudication_group"], f["n_matched"])
            if norm(f["selector"]) in seen or key in seen:
                continue
            seen |= {norm(f["selector"]), key}
            uniq.append(f)
        return {"valid": uniq, "groups": sorted({f["adjudication_group"] for f in uniq}),
                "insp": sum(cond[k]["insp"] for k in keys),
                "usd": sum(cond[k]["usd"] for k in keys)}

    pool_agent = pooled(RUNS)
    pool_base = pooled(list(STRATEGY_LABELS))
    pool_agent["cand"] = summary["n_candidates"]["agent_distinct_selectors"]
    # Per-row Cand. counts distinct selectors within one baseline; the pooled row
    # counts them distinct across baselines, since two baselines can propose the
    # same selector string.
    base_selectors = {
        yaml.safe_load(open(p))["selector"].strip()
        for p in REPO.glob("out/baselines/*/findings/*.yaml")
    }
    pool_base["cand"] = len(base_selectors)
    base_cand_sum = sum(base_counts[k]["n_distinct"] for k in STRATEGY_LABELS)

    def gcell(groups: list[str]) -> str:
        return ",".join(g.removeprefix("G").lstrip("0") for g in groups) or "--"

    def row(label: str, c: dict, shade: str = "") -> str:
        return (f"{shade}{label} & {thousands(c['insp'])} & {c['cand']} & {len(c['valid'])} & "
                f"{len(c['groups'])} & {gcell(c['groups'])} & {c['usd']:.2f} \\\\")

    def head(text: str) -> str:
        # \rlap, not \multicolumn: the rows are \input at the start of a cell.
        return f"\\rlap{{\\grouphead{{{text}}}}} & & & & & & \\\\"

    lines = [head("Baselines (single runs)")]
    lines += [row(f"\\textsc{{{lab}}}", cond[k]) for k, lab in STRATEGY_LABELS.items()]
    lines.append("\\midrule")
    lines.append(head("Agent (single runs)"))
    lines += [row(RUN_LABELS[r], cond[r], "\\rowcolor{accsoft}") for r in RUNS]
    lines.append("\\midrule")
    lines.append(head("Pooled"))
    lines.append(row("All 4 baselines", pool_base, "\\rowcolor{zebra}"))
    lines.append(row("All 3 agent runs", pool_agent, "\\rowcolor{zebra}"))
    table = "\n".join(lines) + "\n\\bottomrule\n"

    # ---- macros -----------------------------------------------------------------
    m: dict[str, str] = {}
    run_valid = [len(cond[r]["valid"]) for r in RUNS]
    run_groups = [len(cond[r]["groups"]) for r in RUNS]
    base_valid = {k: len(cond[k]["valid"]) for k in STRATEGY_LABELS}
    best = max(base_valid.values())
    m["runvalidmin"], m["runvalidmax"] = str(min(run_valid)), str(max(run_valid))
    m["rungroupsmin"], m["rungroupsmax"] = str(min(run_groups)), str(max(run_groups))
    m["basevalidmin"], m["basevalidbest"] = str(min(base_valid.values())), str(best)
    m["basevalidbestname"] = " and ".join(
        f"\\textsc{{{STRATEGY_LABELS[k]}}}" for k, v in base_valid.items() if v == best)
    m["poolagentvalid"] = str(len(pool_agent["valid"]))
    m["poolagentgroups"] = str(len(pool_agent["groups"]))
    m["poolbasevalid"] = str(len(pool_base["valid"]))
    m["poolbasegroups"] = str(len(pool_base["groups"]))
    m["poolbaseinsp"] = thousands(pool_base["insp"])
    m["poolagentinsp"] = str(pool_agent["insp"])
    m["poolbaseusd"] = f"{pool_base['usd']:.2f}"
    m["runusdmin"] = f"{min(cond[r]['usd'] for r in RUNS):.2f}"
    m["runusdmax"] = f"{max(cond[r]['usd'] for r in RUNS):.2f}"
    m["baseusdmin"] = f"{min(cond[k]['usd'] for k in STRATEGY_LABELS):.2f}"
    m["baseusdmax"] = f"{max(cond[k]['usd'] for k in STRATEGY_LABELS):.2f}"
    m["poolbasecand"] = str(pool_base["cand"])
    m["basecandsum"] = str(base_cand_sum)

    # Groups only the agent validated, and only the baselines.
    agent_only = sorted(set(pool_agent["groups"]) - set(pool_base["groups"]))
    base_only = sorted(set(pool_base["groups"]) - set(pool_agent["groups"]))
    m["agentonlygroups"] = ", ".join(agent_only)
    m["baseonlygroups"] = ", ".join(base_only)

    # Baselines with their own validated Czech (G02) selector.
    g02 = [f for k in STRATEGY_LABELS for f in cond[k]["valid"]
           if f["adjudication_group"] == "G02" and f["source"] == f"baseline:{k}"]
    m["gtwobaselines"] = str(len({f["source"] for f in g02}))
    m["gtwobasepmin"] = trim(min(f["human"]["precision"] for f in g02))
    m["gtwobasepmax"] = trim(max(f["human"]["precision"] for f in g02))

    # G04 prevalence range.
    g04 = [f for f in findings if f["source"] == "agent" and f["adjudication_group"] == "G04"]
    m["gfourpmin"] = f"{min(f['prevalence'] for f in g04) * 100:.2f}"
    m["gfourpmax"] = f"{max(f['prevalence'] for f in g04) * 100:.2f}"
    # LowConf's adult tag farm (G09) is G04's nearest validated baseline neighbour.
    g09 = [f for f in findings if f["adjudication_group"] == "G09"]
    if g09:
        h = g09[0]["human"]
        m["gnineprec"] = trim(h["precision"])
        m["gninen"] = str(h["n_judged"])
        m["gninedocs"] = thousands(g09[0]["n_matched"])
    # LID-Disagree's own adult selector: adjudicated into G04 and approved, but it
    # drew no labels, so the acceptance rule cannot count it.
    ld_adult = [f for f in findings if f["source"] == "baseline:lid_disagree"
                and f["adjudication_group"] == "G04"]
    if ld_adult:
        f = ld_adult[0]
        m["ldadultsel"] = f["selector"].replace("_", "\\_").replace("%", "\\%")
        m["ldadultpct"] = f"{f['prevalence'] * 100:.2f}"

    # ---- findings table, with status and label counts -------------------------
    status = {"approve": "\\accepted"}
    # Rows of one phenomenon group share a tint; single-finding groups stay white.
    gshade = {"G04": "\\rowcolor{zebra}", "G02": "\\rowcolor{accsoft}"}
    frows = []
    for f in sorted((f for f in findings if f["source"] == "agent"),
                    key=lambda x: -x["prevalence"]):
        h = f["human"]
        prec = (f"{trim(h['precision'])}\\,\\ci{{{trim(h['precision_ci95'][0])},"
                f"{trim(h['precision_ci95'][1])}}}" if h["n_judged"] >= MIN_JUDGMENTS
                else "--")
        ov = f["max_baseline_overlap"]
        short = {"random": "R", "lowconf": "LC", "lid_disagree": "LD", "highdup": "HD"}
        by = ", ".join(short[b] for b in f["rediscovered_by"]) or "--"
        grp = f.get('adjudication_group') or '--'
        frows.append(
            f"{gshade.get(grp, '')}\\texttt{{{f['id'].replace('_', '\\_')}}} & "
            f"{grp} & {len(f['runs'])}/3 & {by} & "
            f"{f['prevalence'] * 100:.2f} & {h['n_judged']} & {prec} & "
            f"{'--' if ov is None else f'{ov * 100:.0f}'} & "
            f"{status.get(f['human_decision'], '\\candidate')} \\\\")
    ftable = "\n".join(frows) + "\n\\bottomrule\n"

    # ---- annotation attrition ---------------------------------------------------
    ann = REPO / "out/annotation"
    prov = list(csv.DictReader(open(ann / "provenance.csv")))
    labels = {r["item_id"] for r in csv.DictReader(open(ann / "labels.csv"))}
    p1 = {r["item_id"] for r in csv.DictReader(open(ann / "pass1_labels.csv"))}
    p2 = {r["item_id"] for r in csv.DictReader(open(ann / "pass2_labels.csv"))}
    recode = {l.strip() for l in open(ann / "recode_items.txt") if l.strip()}
    m["anndrawn"] = str(len(prov))
    m["annlabelled"] = str(len(labels))
    m["annpassone"] = str(len(p1))
    m["annpasstwo"] = str(len(p2))
    m["annpasstwonew"] = str(len(p2 - p1))
    m["annrecodelisted"] = str(len(recode))
    # Baseline candidates that drew a sample, and how many documents each.
    per_cand: dict[str, int] = {}
    for r in prov:
        if r["source"].startswith("baseline:"):
            per_cand[r["slice"]] = per_cand.get(r["slice"], 0) + 1
    m["annbasecand"] = str(len(per_cand))
    m["annbasemin"], m["annbasemax"] = str(min(per_cand.values())), str(max(per_cand.values()))
    m["anncontrol"] = str(sum(r["source"] == "control" for r in prov))
    # The defect criterion in terms of the label scales the annotator used.
    m["defectlang"] = ", ".join(f"\\texttt{{{x}}}" for x in sorted(DEFECT_LANG))
    m["defectqual"] = ", ".join(f"\\texttt{{{x}}}" for x in sorted(DEFECT_QUAL))
    sc = json.loads((OUT / "sample_clustering.json").read_text())
    m["annminhosts"] = str(sc["agent_min_hosts_in_sample"])
    m["anntophost"] = f"{sc['agent_max_top_host_share'] * 100:.0f}"

    # ---- adjudication: what was decided, by whom, by which rule --------------------
    adj = REPO / "out/adjudication"
    dec_rows = list(csv.DictReader(open(adj / "decisions.csv")))
    grp_rows = list(csv.DictReader(open(adj / "groups.csv")))
    group_ids = {r["group"] for r in grp_rows}
    m["adjndecisions"] = str(len(dec_rows))
    m["adjnclusters"] = str(len(group_ids))
    m["adjncandraw"] = str(len(grp_rows))
    m["adjngrouprows"] = str(sum(r["group"] in group_ids for r in dec_rows))
    m["adjnmemberrows"] = str(sum(r["group"] not in group_ids for r in dec_rows))
    for verdict in ("approve", "reject", "unsure"):
        m[f"adjn{verdict}"] = str(sum(r["decision"] == verdict for r in dec_rows))
    split = sorted({r["group"] for r in grp_rows
                    if r["finding"] in {d["group"] for d in dec_rows}})
    m["adjsplitgroup"] = ", ".join(split)
    split_prec = [f["human"]["precision"] for f in findings
                  if f["adjudication_group"] in split and f["human"]["precision"] is not None
                  and f["human"]["n_judged"] >= MIN_JUDGMENTS]
    m["adjsplitpmin"], m["adjsplitpmax"] = trim(min(split_prec)), trim(max(split_prec))
    dprov = json.loads((adj / "decision_provenance.json").read_text())
    assert "proposed a verdict" in dprov["how"] and "adopted" in dprov["how"], \
        "decision_provenance.json no longer describes proposed-and-adopted verdicts"
    # Groups that hold no validated selector, for the Table 2 caption.
    validated_groups = set(pool_agent["groups"]) | set(pool_base["groups"])
    m["unvalidatedgroups"] = ", ".join(sorted(group_ids - validated_groups))

    # ---- facts quoted in the abstract and contributions ---------------------------
    farm = json.loads((OUT / "farm_facts.json").read_text())
    m["farmpct"] = f"{farm['farm_docs'] / summary['corpus']['n_total'] * 100:.2f}"
    m["farmpassall"] = f"{farm['farm_pass_all_static'] / farm['farm_docs'] * 100:.1f}"
    m["farmpassalldocs"] = thousands(farm["farm_pass_all_static"])
    m["farmpassallcorpus"] = f"{farm['farm_pass_all_static_share'] * 100:.1f}"
    sm = json.loads((OUT / "fig_staticmiss.json").read_text())
    assert sm["farm_pass_all"] == farm["farm_pass_all_static"], \
        "fig_staticmiss.json and farm_facts.json disagree on the farm's pass-all count"
    m["restpassall"] = f"{sm['rest_pass_all'] / sm['rest_docs'] * 100:.1f}"
    xl = json.loads((OUT / "cross_language.json").read_text())
    m["xlnconf"], m["xlnfail"] = str(xl["configs"]), str(xl["configs_with_defect"])
    m["xlpctmin"] = f"{xl['share_min'] * 100:.1f}"
    m["xlpctmax"] = f"{xl['share_max'] * 100:.1f}"
    cls = json.loads((OUT / "classification_cost.json").read_text())
    m["clsperk"] = f"{cls['usd_per_1000_documents']:.2f}"
    m["clsfull"] = thousands(round(cls["extrapolated_usd_full_corpus"]))
    m["clstoken"] = thousands(round(cls["token_pricing_lower_bound_usd"]))
    m["clsfullk"] = f"{cls['extrapolated_usd_full_corpus'] / 1000:.0f}k"
    m["clstokenk"] = f"{cls['token_pricing_lower_bound_usd'] / 1000:.0f}k"
    opus = costs["model_opus"]["total_cost_usd"]
    m["opususd"] = f"{opus:.2f}"
    m["opusturns"] = str(costs["model_opus"]["num_turns"])
    m["opusratiomin"] = f"{opus / max(cond[r]['usd'] for r in RUNS):.1f}"
    m["opusratiomax"] = f"{opus / min(cond[r]['usd'] for r in RUNS):.1f}"
    rp = json.loads((OUT / "replay_report.json").read_text())
    m["replayn"] = str(rp["replayed"])
    m["replayset"] = str(rp["matched_as_set"])
    m["replayexact"] = str(rp["matched_exactly"])
    m["replaysetpct"] = f"{rp['set_rate'] * 100:.1f}"
    m["replayexactpct"] = f"{rp['exact_rate'] * 100:.1f}"
    m["replaysetdiff"] = str(rp["replayed"] - rp["matched_as_set"])
    m["replayorderonly"] = str(rp["matched_as_set"] - rp["matched_exactly"])
    src_label = {"agent": "agent slices", "baseline:highdup": "\\textsc{HighDup}",
                 "baseline:lid_disagree": "\\textsc{LID-Disagree}",
                 "baseline:lowconf": "\\textsc{LowConf}",
                 "baseline:random": "\\textsc{Random}", "control": "control"}
    by_src: dict[str, list[int]] = {}
    for r in prov:
        c = by_src.setdefault(r["source"], [0, 0])
        c[1] += 1
        c[0] += r["item_id"] in labels
    order = ["agent", "baseline:lowconf", "baseline:lid_disagree", "baseline:highdup",
             "baseline:random", "control"]
    m["annbysource"] = ", ".join(
        f"{src_label.get(s, s)} {by_src[s][0]}/{by_src[s][1]}"
        for s in order + sorted(set(by_src) - set(order)) if s in by_src)

    # ---- profanity-ranked sample --------------------------------------------------
    prof_path = OUT / "profanity_baseline.json"
    if prof_path.exists():
        p = json.loads(prof_path.read_text())
        s = p["sample_n_bad_words"]
        m["profbudget"] = str(p["budget"])
        m["profbwmin"], m["profbwmax"] = str(s["min"]), str(s["max"])
        inside = p["sample_in_agent_slice"]
        g04_ids = [f["id"] for f in g04]
        # one G04 selector *is* n_bad_words >= 3, so membership in G04 is by
        # definition; the measurement is that no sampled document is in any other
        # agent finding
        m["profoutside"] = str(sum(v for k, v in inside.items() if k not in g04_ids))
        m["profslicedocs"] = thousands(p["overlap_slice"]["n"])
        m["profslicepct"] = f"{p['overlap_slice']['prevalence'] * 100:.2f}"
        cov = p["g04_coverage_by_slice"]
        m["profcoversall"] = ("all three" if all(v["share_covered"] == 1.0
                                                 for v in cov.values()) else "not all")

    macros = "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in m.items())

    OUT.joinpath("arxiv_table_perrun.tex").write_text(table)
    OUT.joinpath("arxiv_table_findings.tex").write_text(ftable)
    OUT.joinpath("arxiv_macros.tex").write_text(macros)
    if ARXIV.exists():
        # Only the files this script generates; the table_*.tex row files in paper/
        # carry arXiv-specific styling and must not be overwritten from out/analysis.
        for name in ("arxiv_table_perrun.tex", "arxiv_table_findings.tex", "arxiv_macros.tex"):
            shutil.copy(OUT / name, ARXIV / name)
        # made by: scripts/make_figure.py --out out/analysis/arxiv_fig_overlap.pdf
        #          --band-label "low overlap with these three slices"
        fig = OUT / "arxiv_fig_overlap.pdf"
        if fig.exists():
            shutil.copy(fig, ARXIV / "fig_overlap.pdf")
    print(table)
    print(ftable)
    print(macros)
    return 0


if __name__ == "__main__":
    sys.exit(main())
