"""Per-crawl prevalence of the content farm, adult spam and Czech text.

Selectors come from tests/slk_Latn/*.yaml; shares are computed per crawl
('dump') over data/derived/meta.parquet. Recent crawls follow
out/analysis/temporal_stability.json.
"""

from __future__ import annotations

import json
import pathlib

import duckdb
import yaml

import figstyle
import matplotlib.pyplot as plt

figstyle.apply()

TESTS = pathlib.Path("tests/slk_Latn")


def sel(name: str) -> str:
    return yaml.safe_load((TESTS / f"{name}.yaml").read_text())["selector"]


def union(names: list[str]) -> str:
    return " OR ".join(f"({sel(n)})" for n in names)


groups = {
    "farm": f"({sel('firebase_content_farm_spam')})",
    "adult": f"({union(['adult_spam_farm_wordsalad', 'porn_spam_keyword_farm', 'porn_doorway_spam_network'])})",
    "czech": f"({union(['czech_text_mislabeled_as_slovak', 'czech_slovak_code_switched_docs'])})",
}

recent = set(json.loads(pathlib.Path("out/analysis/temporal_stability.json").read_text())["recent_crawls"])

con = duckdb.connect()
cols = ", ".join(f"sum(CASE WHEN {w} THEN 1 ELSE 0 END)::BIGINT AS {k}" for k, w in groups.items())
rows = con.execute(
    f"SELECT dump, count(*) AS n, {cols} FROM 'data/derived/meta.parquet' GROUP BY dump ORDER BY dump"
).fetchall()
# containment check: adult union equals n_bad_words >= 3
extra = con.execute(
    f"SELECT count(*) FROM 'data/derived/meta.parquet' WHERE {groups['adult']} AND NOT (n_bad_words >= 3)"
).fetchone()[0]

dumps = [r[0] for r in rows]
n = [r[1] for r in rows]
series = {k: [r[2 + i] / r[1] * 100 for r in rows] for i, k in enumerate(groups)}

summary = {}
for i, k in enumerate(groups):
    tot = sum(r[2 + i] for r in rows)
    o = [(r[2 + i], r[1]) for r in rows if r[0] not in recent]
    rc = [(r[2 + i], r[1]) for r in rows if r[0] in recent]
    pk = max(range(len(rows)), key=lambda j: series[k][j])
    summary[k] = {
        "all": tot / sum(n) * 100,
        "older": sum(a for a, _ in o) / sum(b for _, b in o) * 100,
        "recent": sum(a for a, _ in rc) / sum(b for _, b in rc) * 100,
        "peak": dumps[pk],
        "peak_share": series[k][pk],
    }
summary["adult_outside_nbw3"] = extra
summary["crawls"] = len(dumps)
summary["docs"] = sum(n)
print(json.dumps(summary, indent=1))
pathlib.Path("out/analysis/fig_temporal.json").write_text(json.dumps(summary, indent=1))

x = list(range(len(dumps)))
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(figstyle.COLUMN_IN, 2.6), sharex=True,
                               gridspec_kw={"height_ratios": [1.25, 1], "hspace": 0.12})
first_recent = min(i for i, d in enumerate(dumps) if d in recent)
for ax in (ax1, ax2):
    ax.axvspan(first_recent - 0.5, len(dumps) - 0.5, color="#E3E7EB", lw=0, zorder=0)
    ax.grid(axis="y", zorder=0)
    ax.set_axisbelow(True)

ax1.plot(x, series["farm"], color=figstyle.WARN, lw=1.0, zorder=3)
pk = series["farm"].index(max(series["farm"]))
ax1.plot([pk], [series["farm"][pk]], "o", ms=3, color=figstyle.WARN, zorder=4)
ax1.annotate(f"{series['farm'][pk]:.1f}% in {dumps[pk][8:]}", (pk, series["farm"][pk]),
             xytext=(-6, -2), textcoords="offset points", ha="right", va="top", fontsize=6.5)
ax1.set_ylabel("Content farm\n(% of crawl)")
ax1.set_ylim(0, 42)
ax1.text(first_recent - 1.2, 20, "8 recent\ncrawls", fontsize=6.5, color=figstyle.GREY,
         va="center", ha="right")

ax2.plot(x, series["adult"], color=figstyle.ACC, lw=1.0, label="Adult spam (G04)", zorder=3)
ax2.plot(x, series["czech"], color=figstyle.HUM, lw=1.0, ls=(0, (3, 1.5)), label="Czech text (G02)", zorder=3)
ax2.set_ylabel("% of crawl")
ax2.set_ylim(0, 2.6)
ax2.legend(loc="upper left", handlelength=2.2)

ticks, labels, seen = [], [], set()
for i, d in enumerate(dumps):
    y = d.split("-")[2]
    if y not in seen and int(y) % 2 == 1:
        ticks.append(i)
        labels.append(y)
    seen.add(y)
ax2.set_xticks(ticks, labels)
ax2.set_xlim(-0.5, len(dumps) - 0.5)
ax2.set_xlabel("Common Crawl snapshot (96, in order)")

figstyle.save(fig, "fig_temporal")
