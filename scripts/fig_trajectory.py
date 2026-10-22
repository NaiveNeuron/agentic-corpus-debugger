"""Anatomy of one investigation: the tool-call trajectory of the main run.

Reads out/runs/main/tools.jsonl, the run that saved firebase_content_farm_spam.
"""

from __future__ import annotations

import json
import pathlib

import matplotlib.pyplot as plt

import figstyle

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOG = ROOT / "out/runs/main/tools.jsonl"
BUDGET = 300

ROWS = [  # (label, tools, colour, marker)
    ("aggregate / stats", {"schema", "aggregate", "domain_stats"}, figstyle.GREY, "|"),
    ("sample / inspect", {"sample_documents", "inspect_document"}, figstyle.HUM, "o"),
    ("search / LID", {"search_text", "sentence_lid"}, figstyle.HUM, "D"),
    ("detector", {"evaluate_detector", "run_detector"}, figstyle.ACC, "^"),
    ("save finding", {"save_finding"}, figstyle.RUN, "*"),
]


def main() -> None:
    calls = [json.loads(line) for line in LOG.read_text().splitlines() if line.strip()]
    known = set().union(*(r[1] for r in ROWS))
    assert all(c["tool"] in known for c in calls), {c["tool"] for c in calls} - known
    saved = [c for c in calls if c["tool"] == "save_finding"]
    assert saved[0]["args"]["id"] == "firebase_content_farm_spam"

    figstyle.apply()
    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(figstyle.COLUMN_IN, 2.2), sharex=True,
        gridspec_kw={"height_ratios": [2.3, 1], "hspace": 0.12},
    )
    nrow = len(ROWS)
    for i, (label, tools, col, mk) in enumerate(ROWS):
        y = nrow - 1 - i
        xs = [c["call"] for c in calls if c["tool"] in tools]
        ax.scatter(xs, [y] * len(xs), s=22 if mk == "*" else 9, marker=mk,
                   color=col, linewidths=0.9 if mk == "|" else 0, zorder=3)
        ax.axhline(y, color=figstyle.ZEBRA, lw=4, zorder=1)
    ax.set_yticks(range(nrow))
    ax.set_yticklabels([r[0] for r in ROWS][::-1])
    ax.set_ylim(-0.6, nrow - 0.4 + 1.1)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="x", length=0)
    ax.spines["bottom"].set_visible(False)

    # firebase segment (calls 41-49)
    ax.axvspan(40.5, 49.5, color=figstyle.WARN_SOFT, zorder=0, lw=0)
    ann = dict(fontsize=6.2, color="#222222", ha="center", va="bottom")
    ytop = nrow - 0.35
    ax.text(5.5, ytop, "LID and\nsize counts", **ann)
    ax.text(29, ytop, "adult\nword salad", **ann)
    ax.text(45, ytop, "firebase\n1.41M docs", **ann)
    ax.text(60, ytop, "short docs,\nduplicates", **ann)

    used = [c["inspections_used"] for c in calls]
    x = [c["call"] for c in calls]
    ax2.step(x, used, where="post", color=figstyle.ACC, lw=1.0)
    ax2.axhline(BUDGET, color=figstyle.RULE, lw=0.6, ls="--")
    ax2.text(1, BUDGET - 8, f"budget {BUDGET}", fontsize=6.2, color=figstyle.GREY,
             va="top")
    ax2.text(x[-1], used[-1] + 12, str(used[-1]), fontsize=6.2,
             color=figstyle.ACC, ha="right", va="bottom")
    ax2.axvspan(40.5, 49.5, color=figstyle.WARN_SOFT, zorder=0, lw=0)
    ax2.set_ylim(0, 320)
    ax2.set_yticks([0, 150, 300])
    ax2.set_ylabel("inspections\nused", fontsize=6.5)
    ax2.set_xlabel("tool call")
    ax2.set_xlim(0, len(calls) + 1)
    figstyle.save(fig, "fig_trajectory")


if __name__ == "__main__":
    main()
