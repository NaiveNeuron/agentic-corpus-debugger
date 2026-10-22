#!/usr/bin/env python
"""Build the human finding-adjudication package, with mechanical grouping.

Candidate findings (from the agent runs and from the baselines) are clustered by
*document-set* overlap. Two candidates join the same group when either the
Jaccard similarity of the document sets their selectors retrieve is at least
``--threshold`` (equivalent slices), or one set is almost entirely contained in
the other (``--containment``) while being of comparable size (``--min_ratio``),
which is what a rule and a stricter version of the same rule look like. The size
guard matters: without it a very broad slice transitively merges unrelated narrow
ones. Grouping is purely mechanical -- no interpretation of the
descriptions -- so the human decides once per phenomenon instead of once per
proposed selector, and can still split a group by editing the decisions file.

Writes:
  out/adjudication/FINDINGS.md      one section per group, with fresh examples
  out/adjudication/groups.csv       group_id -> member finding ids and sources
  out/adjudication/decisions.csv    group_id, decision (approve/reject/unsure), note
"""

from __future__ import annotations

import argparse
import csv
import glob
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.corpusaudit.db import open_corpus  # noqa: E402
from src.corpusaudit.selectors import needs_text  # noqa: E402

BASELINE_SLICES = {
    "LID-Disagree": "fasttext <> 'sk' or langdetect <> 'sk' or lingua_top <> 'sk'",
    "LowConf": "language_score < 0.8",
    "HighDup": "minhash_cluster_size >= 100",
}


def load_candidates(runs: list[str]) -> list[dict]:
    out = []
    for run in runs:
        if pathlib.Path(run).name == "smoke":
            continue
        for path in sorted(glob.glob(f"{run}/findings/*.yaml")):
            t = yaml.safe_load(open(path))
            out.append({"id": t["id"], "source": f"agent:{pathlib.Path(run).name}",
                        "yaml": t, "selector": t["selector"].strip()})
    for path in sorted(glob.glob("out/baselines/*/findings/*.yaml")):
        t = yaml.safe_load(open(path))
        out.append({"id": t["id"], "source": f"baseline:{pathlib.Path(path).parent.parent.name}",
                    "yaml": t, "selector": t["selector"].strip()})
    return out


class Union:
    def __init__(self, n: int) -> None:
        self.p = list(range(n))

    def find(self, a: int) -> int:
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def join(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="*",
                    default=["out/runs/main", "out/runs/rep1", "out/runs/rep2"])
    ap.add_argument("--derived", default="data/derived")
    ap.add_argument("--out", default="out/adjudication")
    ap.add_argument("--threshold", type=float, default=0.8)
    ap.add_argument("--containment", type=float, default=0.9)
    ap.add_argument("--min-ratio", type=float, default=0.25,
                    help="nested merge also needs comparable sizes")
    ap.add_argument("--examples", type=int, default=3)
    ap.add_argument("--force", action="store_true",
                    help="regroup even if decisions already exist")
    ap.add_argument("--chars", type=int, default=700)
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # Group ids are positional, so rebuilding after decisions exist would silently
    # reattach them to different findings.
    dec = out / "decisions.csv"
    if dec.exists() and not args.force:
        decided = [r for r in csv.DictReader(open(dec)) if (r.get("decision") or "").strip()]
        if decided:
            print(f"{dec} already holds {len(decided)} decisions; refusing to "
                  "regroup and reattach them. Pass --force to override.")
            return 0
    corpus = open_corpus(args.derived)
    con = corpus.con

    cands = load_candidates(args.runs)
    # measure each candidate once
    for c in cands:
        rel = "docs" if needs_text(c["selector"]) else "meta"
        c["rel"] = rel
        c["n_eval"] = corpus.n_sample if rel == "docs" else corpus.n_total
        try:
            c["n"] = con.execute(
                f"select count(*) from {rel} where ({c['selector']})").fetchone()[0]
        except Exception as exc:
            c["n"], c["error"] = 0, str(exc)[:160]
    live = [c for c in cands if c.get("n") and "error" not in c]
    dead = [c for c in cands if c not in live]
    print(f"{len(cands)} candidates: {len(live)} measurable, {len(dead)} empty or broken")

    uf = Union(len(live))
    for i in range(len(live)):
        for j in range(i + 1, len(live)):
            a, b = live[i], live[j]
            if a["selector"] == b["selector"]:
                uf.join(i, j)
                continue
            rel = "docs" if "docs" in (a["rel"], b["rel"]) else "meta"
            inter = con.execute(f"select count(*) from {rel} where ({a['selector']}) "
                                f"and ({b['selector']})").fetchone()[0]
            union = con.execute(f"select count(*) from {rel} where ({a['selector']}) "
                                f"or ({b['selector']})").fetchone()[0]
            j_sim = inter / union if union else 0.0
            contain = max(inter / a["n"] if a["n"] else 0.0,
                          inter / b["n"] if b["n"] else 0.0)
            # The size guard stops a very broad slice from bridging two narrow
            # unrelated ones: without it, "at least two identifiers disagree"
            # transitively merges Czech contamination with English contamination.
            ratio = min(a["n"], b["n"]) / max(a["n"], b["n"]) if max(a["n"], b["n"]) else 0.0
            nested = contain >= args.containment and ratio >= args.min_ratio
            if j_sim >= args.threshold or nested:
                uf.join(i, j)

    groups: dict[int, list[dict]] = {}
    for idx, c in enumerate(live):
        groups.setdefault(uf.find(idx), []).append(c)
    ordered = sorted(groups.values(), key=lambda g: -max(x["n"] for x in g))

    md = [
        "# Finding adjudication package",
        "",
        f"{len(live)} candidate findings, clustered mechanically into "
        f"{len(ordered)} groups by document-set overlap (Jaccard $\\geq$ "
        f"{args.threshold}, or containment $\\geq$ {args.containment} between "
        f"slices of comparable size, for nested selectors). Members of a group retrieve substantially the same "
        "documents, so one decision per group is enough; split a group by adding "
        "rows for individual finding ids to `decisions.csv` if you disagree.",
        "",
        "For each group decide **approve**, **reject** or **unsure** in "
        "`decisions.csv`: is this a genuine, coherent, systematic defect of a "
        "corpus that claims to be Slovak web text? Which audit strategy produced "
        "each candidate is shown, since the grouping already reveals it; ignore it "
        "when judging.",
        "",
    ]
    grows, drows = [], []
    for gi, members in enumerate(ordered, 1):
        gid = f"G{gi:02d}"
        canon = max(members, key=lambda x: (x["source"].startswith("agent"), x["n"]))
        ov = []
        for name, bsel in BASELINE_SLICES.items():
            inter = con.execute(f"select count(*) from {canon['rel']} where "
                               f"({canon['selector']}) and ({bsel})").fetchone()[0]
            ov.append(f"{name} {inter / canon['n']:.0%}")
        ex = con.execute(
            f"select id, url, substr(text, 1, {args.chars}) from docs "
            f"where ({canon['selector']}) order by hash(id || 'adjud') "
            f"limit {args.examples}").fetchall()
        ev = canon["yaml"].get("evidence", {})
        md += [
            f"## {gid}: {canon['id']}",
            "",
            f"**Members ({len(members)}).** A large group can mix related but "
            "distinct claims; if so, add a row per finding id to `decisions.csv` "
            "instead of one row for the group.",
            "",
        ] + [
            f"* `{m['id']}` ({m['source']}, {m['n']:,} docs): "
            + " ".join(str(m["yaml"].get("description", "")).split())[:200]
            + f"  \n  `{m['selector'][:150]}`"
            for m in sorted(members, key=lambda x: -x["n"])
        ] + [
            "",
            f"**Description.** {' '.join(str(canon['yaml'].get('description', '')).split())}",
            "",
            f"**Selector.** `{canon['selector']}`",
            "",
            f"**Prevalence.** {canon['n']:,} of {canon['n_eval']:,} "
            f"({canon['n'] / canon['n_eval']:.4%}), "
            + ("exact on the full corpus" if canon["rel"] == "meta"
               else "measured on the 1-in-13 text sample") + ".",
            "",
            f"**Overlap with the obvious static slices.** {', '.join(ov)}",
            "",
            f"**Auditor's own precision estimate.** {ev.get('agent_expected_precision')}",
            "",
            f"**Auditor's stated likely false positives.** "
            f"{' '.join(str(ev.get('likely_false_positives', '')).split())}",
            "",
            "**Fresh examples the auditor never saw:**",
            "",
        ]
        for doc_id, url, text in ex:
            md += [f"* `{doc_id}` <{url}>", "", "  ```"]
            md += [f"  {line}" for line in text.splitlines()[:14]]
            md += ["  ```", ""]
        drows.append({"group": gid, "decision": "", "note": ""})
        for m in members:
            grows.append({"group": gid, "finding": m["id"], "source": m["source"],
                          "n_matched": m["n"], "selector": m["selector"]})

    if dead:
        md += ["## Not adjudicable", "",
               "These candidates match no documents or have an invalid selector, so "
               "they are dropped automatically:", ""]
        md += [f"* `{c['id']}` ({c['source']}): {c.get('error', 'zero matches')}"
               for c in dead] + [""]

    (out / "FINDINGS.md").write_text("\n".join(md))
    with open(out / "groups.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["group", "finding", "source", "n_matched",
                                          "selector"])
        w.writeheader()
        w.writerows(grows)
    dec = out / "decisions.csv"
    if dec.exists():
        old = {r["group"]: r for r in csv.DictReader(open(dec))}
        for r in drows:
            if r["group"] in old:
                r.update({k: old[r["group"]].get(k, "") for k in ("decision", "note")})
    with open(dec, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["group", "decision", "note"])
        w.writeheader()
        w.writerows(drows)
    print(f"{len(ordered)} groups -> {out}/FINDINGS.md ; decide in {dec}")
    for gi, members in enumerate(ordered, 1):
        print(f"  G{gi:02d} {max(x['n'] for x in members):>9,d} docs  "
              f"{len(members)} member(s): {', '.join(sorted({m['id'] for m in members}))[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
