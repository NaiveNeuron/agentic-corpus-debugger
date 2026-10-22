"""Figure: validated selectors per run against USD cost.

Same per-condition credit as scripts/make_arxiv_tables.py (its `validated` rule,
inputs and the baseline credit for byte-identical agent selectors).
"""

from __future__ import annotations

import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import figstyle  # noqa: E402
from make_arxiv_tables import (  # noqa: E402
    OUT, REPO, RUNS, RUN_LABELS, credited, load_findings, validated,
)
from analyze import STRATEGY_LABELS  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402

BASE_LABELS = {"random": "Random", "lowconf": "LowConf",
               "lid_disagree": "LID-Disagree", "highdup": "HighDup"}


def conditions() -> dict[str, dict]:
    summary = json.loads((OUT / "summary.json").read_text())
    decisions = {r["group"]: r["decision"]
                 for r in csv.DictReader(open(REPO / "out/adjudication/decisions.csv"))}
    findings = load_findings(summary)
    costs = summary["costs"]
    cond: dict[str, dict] = {}
    for run in RUNS:
        mine = [f for f in findings if f["source"] == "agent" and run in f["runs"]]
        cond[run] = {"findings": mine, "usd": costs[run]["total_cost_usd"],
                     "label": RUN_LABELS[run], "agent": True}
    for key in STRATEGY_LABELS:
        mine = credited(findings, key)
        cond[key] = {"findings": mine, "usd": costs[key]["total_cost_usd"],
                     "label": BASE_LABELS[key], "agent": False}
    for c in cond.values():
        v = [f for f in c["findings"] if validated(f, decisions)]
        c["sel"] = len(v)
        c["grp"] = len({f["adjudication_group"] for f in v})
    return cond


# Label offsets (points) chosen so the three baselines clustered at y=2 do not collide.
OFFSET = {"random": (6, 0, "left"), "lowconf": (6, 0, "left"),
          "lid_disagree": (0, 8, "center"), "highdup": (-6, 0, "right"),
          "main": (6, 0, "left"), "rep1": (6, 0, "left"), "rep2": (-6, 0, "right")}


def main() -> None:
    figstyle.apply()
    cond = conditions()
    for k, c in cond.items():
        print(f"{k:13s} usd={c['usd']:.2f} sel={c['sel']} grp={c['grp']}")
    fig, ax = plt.subplots(figsize=(figstyle.COLUMN_IN, 1.75))
    best = max(c["sel"] for c in cond.values() if not c["agent"])
    ax.axhline(best, color=figstyle.RULE, lw=0.6, ls=(0, (3, 2)), zorder=0)
    ax.text(3.18, best + 0.12, "best baseline", color=figstyle.GREY,
            fontsize=6.5, ha="right", va="bottom")
    for k, c in cond.items():
        col = figstyle.ACC if c["agent"] else figstyle.GREY
        mk = "o" if c["agent"] else "s"
        ax.scatter(c["usd"], c["sel"], s=22, color=col, marker=mk, zorder=3)
        dx, dy, ha = OFFSET[k]
        ax.annotate(c["label"], (c["usd"], c["sel"]), xytext=(dx * 1.2, dy),
                    textcoords="offset points", ha=ha, va="center",
                    fontsize=6.5, color=col)
    ax.set_xlim(0.4, 3.2)
    ax.set_ylim(0, 4.9)
    ax.set_yticks([0, 1, 2, 3, 4])
    ax.set_xlabel("Cost per run (USD)")
    ax.set_ylabel("Validated selectors per run")
    ax.grid(axis="y")
    ax.set_axisbelow(True)
    figstyle.save(fig, "fig_perrun")


if __name__ == "__main__":
    main()
