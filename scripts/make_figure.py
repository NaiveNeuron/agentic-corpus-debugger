#!/usr/bin/env python
"""Draw the figure the overlap argument deserves.

Each candidate slice is placed by its corpus prevalence (log scale) and by how
much of it an obvious static audit slice already retrieves. The agent's retained
findings and the baselines' candidates are drawn differently, so the reader can
see at a glance which discovered slices are orthogonal to the static signals and
which are not.

    .venv/bin/python scripts/make_figure.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import figstyle  # noqa: E402

SHORT = {
    "firebase_content_farm_spam": "content farm",
    "adult_spam_farm_wordsalad": "adult spam",
    "porn_spam_keyword_farm": "adult spam (hosts)",
    "porn_doorway_spam_network": "adult spam (strict)",
    "slo_prefix_machine_translated_farm": "MT farm",
    "czech_slovak_code_switched_docs": "Czech / code-switched",
    "czech_text_mislabeled_as_slovak": "Czech (excl. farm)",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", default="out/analysis/summary.json")
    ap.add_argument("--out", default="out/analysis/fig_overlap.pdf")
    ap.add_argument("--band-label", default="orthogonal to the static signals",
                    help="caption of the low-overlap band")
    args = ap.parse_args()

    summary = json.load(open(args.summary))
    agent, base = [], []
    for f in summary["findings"]:
        if "error" in f or not f["n_matched"]:
            continue
        ov = f.get("max_baseline_overlap")
        if ov is None:
            continue
        point = (f["prevalence"] * 100, ov * 100, f["id"])
        (agent if f["source"] == "agent" else base).append(point)

    figstyle.apply()
    fig, ax = plt.subplots(figsize=(figstyle.COLUMN_IN, 2.3))
    ax.axhspan(-6, 20, color=figstyle.ZEBRA, zorder=0, lw=0)
    ax.text(0.0105, 16, args.band_label, fontsize=6.5, color=figstyle.GREY,
            style="italic")
    if base:
        ax.scatter([p[0] for p in base], [p[1] for p in base], marker="x", s=16,
                   color=figstyle.GREY, linewidths=0.8, label="baseline candidates",
                   zorder=2)
    ax.scatter([p[0] for p in agent], [p[1] for p in agent], marker="o", s=24,
               facecolor=figstyle.ACC, edgecolor="white", linewidths=0.5,
               label="agent findings", zorder=3)

    # label one representative per phenomenon group, so the figure stays legible
    groups: dict[str, tuple] = {}
    for f in summary["findings"]:
        if f["source"] != "agent" or "error" in f:
            continue
        g = f.get("adjudication_group") or f["id"]
        best = groups.get(g)
        if best is None or f["prevalence"] > best[0]:
            groups[g] = (f["prevalence"], f["id"],
                         f["prevalence"] * 100, (f["max_baseline_overlap"] or 0) * 100)
    OFFSET = {  # (x multiplier, y shift, alignment) tuned to avoid collisions
        "content farm": (0.55, 9, "center"),
        "adult spam": (1.35, -1, "left"),
        "MT farm": (1.4, -4.5, "left"),
        "Czech / code-switched": (0.30, -12, "left"),
    }
    for _, fid, x, y in groups.values():
        label = SHORT.get(fid, fid)
        mx, dy, ha = OFFSET.get(label, (1.3, 3, "left"))
        ax.annotate(label, (x, y), (x * mx, y + dy), fontsize=6.5, ha=ha,
                    color=figstyle.ACC)

    ax.set_xscale("log")
    ax.set_xlabel("prevalence in the corpus (%, log scale)")
    ax.set_ylabel("largest overlap with a\nstatic audit slice (%)")
    ax.set_ylim(-6, 112)
    ax.set_xlim(0.008, 12)
    ax.legend(loc="center left", bbox_to_anchor=(0.02, 0.55), frameon=False)
    ax.grid(axis="y", zorder=0)
    ax.set_axisbelow(True)
    out = pathlib.Path(args.out)
    # Without this, matplotlib stamps the build time into the PDF, so the figure
    # differs on every run and the paper repository always looks dirty -- which
    # makes "did this run change anything?" unanswerable and hides real changes.
    fig.savefig(out, format="pdf", metadata={"CreationDate": None})
    plt.close(fig)
    print(f"wrote {out} ({len(agent)} agent findings, {len(base)} baseline candidates)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
