"""Human-judged defect rate per agent finding, with Wilson 95% CIs."""

import json

import matplotlib.pyplot as plt

import figstyle

figstyle.apply()
S = json.load(open("out/analysis/summary.json"))
ctrl = S["control"]
SHORT = {
    "firebase_content_farm_spam": "Firebase content farm",
    "czech_text_mislabeled_as_slovak": "Czech labelled Slovak",
    "czech_slovak_code_switched_docs": "Czech–Slovak code-switching",
    "porn_spam_keyword_farm": "adult keyword farm",
    "porn_doorway_spam_network": "adult doorway network",
    "adult_spam_farm_wordsalad": "adult word salad",
    "slo_prefix_machine_translated_farm": "slo.* MT farm",
}
GROUPS = ["G01", "G02", "G04", "G05"]
rows = []
for g in GROUPS:
    for f in S["findings"]:
        if f["source"] == "agent" and f["adjudication_group"] == g:
            rows.append((g, f))

fig, ax = plt.subplots(figsize=(figstyle.COLUMN_IN, 2.2), layout="constrained")
lo, hi = ctrl["precision_ci95"]
ax.axvspan(lo, hi, color=figstyle.ZEBRA, zorder=0, lw=0)
ax.axvline(ctrl["precision"], color=figstyle.GREY, lw=0.7, zorder=1)
ax.axvline(0.5, color=figstyle.GREY, lw=0.8, ls=(0, (3, 2)), zorder=1)
n = len(rows)
labels = []
prev = None
for i, (g, f) in enumerate(rows):
    y = n - 1 - i
    h = f["human"]
    p, (a, b) = h["precision"], h["precision_ci95"]
    acc = p >= 0.5
    c = figstyle.RUN if acc else figstyle.WARN
    ax.plot([a, b], [y, y], color=c, lw=1.4, solid_capstyle="butt", zorder=2)
    ax.plot(p, y, marker="o" if acc else "D", ms=4.2, mfc=c if acc else "white",
            mec=c, mew=1.0, zorder=3, clip_on=False)
    ax.text(1.03, y, f"{h['n_defective']}/{h['n_judged']}", va="center",
            ha="left", fontsize=6.5, color=figstyle.GREY, transform=ax.get_yaxis_transform())
    labels.append(f"{g}  {SHORT[f['id']]}")
    if prev is not None and g != prev:
        ax.axhline(y + 0.5, color="#D5DBE1", lw=0.4, xmin=-0.9, clip_on=False)
    prev = g
ax.set_yticks(range(n - 1, -1, -1), labels)
ax.tick_params(axis="y", length=0)
ax.set_ylim(-0.6, n - 0.4)
ax.set_xlim(0, 1.02)
ax.set_xticks([0, 0.25, 0.5, 0.75, 1], ["0", ".25", ".5", ".75", "1"])
ax.set_xlabel("human-judged defect rate (95% Wilson CI)")
ax.spines["left"].set_visible(False)
ax.text(1.03, n - 0.35, "defective/n", ha="left", va="bottom", fontsize=6,
        color=figstyle.GREY, transform=ax.get_yaxis_transform())
# Reference-line labels sit above the plot area, level with "defective/n", so they
# never collide with each other or with the top row.
ax.text(0.5, n - 0.35, "accept", fontsize=6, color=figstyle.GREY, va="bottom", ha="center")
ax.text((lo + hi) / 2, n - 0.35, f"control {ctrl['n_defective']}/{ctrl['n_judged']}",
        fontsize=6, color=figstyle.GREY, va="bottom", ha="center")
figstyle.save(fig, "fig_validation")
