"""Why static filters miss the content farm: farm vs rest on the three static signals."""

import json

import duckdb
import matplotlib.pyplot as plt
import numpy as np

import figstyle as fs

FARM = "(domain LIKE '%.firebaseapp.com' OR domain LIKE '%.web.app')"
AGREE = "(fasttext='sk' AND langdetect='sk' AND lingua_top='sk')"
PASS = f"(language_score >= 0.9 AND minhash_cluster_size <= 2 AND {AGREE})"

con = duckdb.connect()
con.execute("create view meta as select * from 'data/derived/meta.parquet'")

# language_score histogram, 0.01 bins over [0.6, 1.0]
ls = con.execute(f"""select {FARM} f, least(floor(language_score*100), 99)::int b, count(*)
    from meta group by all""").fetchall()
# cluster size histogram on log10 bins (0.25 dex)
cs = con.execute(f"""select {FARM} f, floor(log10(greatest(minhash_cluster_size,1))*4)::int b,
    count(*) from meta group by all""").fetchall()
agg = con.execute(f"""select {FARM} f, count(*), avg(language_score), avg(minhash_cluster_size),
    avg({AGREE}::int), sum({PASS}::int), sum((minhash_cluster_size>=100)::int),
    sum((language_score<0.8)::int) from meta group by all""").fetchall()
stats = {r[0]: r[1:] for r in agg}
fn, fls, fcs, fag, fpass, fhd, flc = stats[True]
print(f"farm n={fn} mean_ls={fls:.4f} mean_cs={fcs:.4f} agree={fag:.4f} "
      f"pass={fpass} ({fpass / fn:.4f}) highdup={fhd} lowconf={flc}")
print("rest", stats[False])

fs.apply()
fig, axes = plt.subplots(3, 1, figsize=(fs.COLUMN_IN, 4.1), layout="constrained",
                         gridspec_kw={"height_ratios": [1, 1, 0.7]})


def dens(rows, flag, lo, hi):
    h = np.zeros(hi - lo)
    for f, b, n in rows:
        if f == flag and b is not None:
            h[min(max(b, lo), hi - 1) - lo] += n
    return h / h.sum()


# Panel a: language_score
ax = axes[0]
lo = 65
edges = np.arange(lo, 101) / 100
for flag, col, lab, hatch in [(False, fs.GREY, "rest of corpus", None),
                              (True, fs.WARN, "content farm", None)]:
    d = dens(ls, flag, lo, 100)
    ax.stairs(d * 100, edges, color=col, lw=1.0, label=lab,
              fill=flag, alpha=0.35 if flag else 1.0)
    if flag:
        ax.stairs(d * 100, edges, color=col, lw=1.0)
for x, lab in [(0.667, "FineWeb2 0.667"), (0.8, "LowConf 0.8")]:
    ax.axvline(x, color=fs.ACC, lw=0.8, ls="--")
    ax.text(x + 0.004, 4e3, lab, color=fs.ACC, fontsize=6.5,
            va="top", ha="left")
ax.set_xlim(0.65, 1.0)
ax.set_yscale("log")
ax.set_ylim(1e-2, 1e4)
ax.set_yticks([1e-2, 1, 1e2])
ax.set_xlabel("language_score")
ax.set_ylabel("% of docs")
ax.legend(loc="center left", bbox_to_anchor=(0.43, 0.6), handlelength=1.2)
ax.set_title("(a) language identifier confidence", loc="left")

# Panel b: minhash_cluster_size
ax = axes[1]
nb = 21  # up to 10^5.25
cedges = 10 ** (np.arange(nb + 1) / 4)
for flag, col in [(False, fs.GREY), (True, fs.WARN)]:
    d = dens(cs, flag, 0, nb)
    ax.stairs(d * 100, cedges, color=col, lw=1.0, fill=flag, alpha=0.35 if flag else 1.0)
    if flag:
        ax.stairs(d * 100, cedges, color=col, lw=1.0)
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_ylim(1e-3, 150)
ax.axvline(100, color=fs.ACC, lw=0.8, ls="--")
ax.text(115, 30, "HighDup\n100", color=fs.ACC, fontsize=6.5, va="top")
ax.text(3.2, 4e-3, f"farm mean {fcs:.2f}", color=fs.WARN, fontsize=6.5, va="bottom")
ax.set_xlabel("minhash_cluster_size")
ax.set_ylabel("% of docs")
ax.set_title("(b) near-duplicate cluster size", loc="left")

# Panel c: three-way agreement and pass-all shares
ax = axes[2]
rn, _, _, rag, rpass, *_ = stats[False]
cats = ["three LIDs agree (sk)", "score$\\geq$0.9, cluster$\\leq$2,\nLIDs agree"]
y = np.arange(len(cats))
farm_v = [fag * 100, fpass / fn * 100]
rest_v = [rag * 100, rpass / rn * 100]
h = 0.36
ax.barh(y - h / 2, farm_v, h, color=fs.WARN_SOFT, edgecolor=fs.WARN, lw=0.8)
ax.barh(y + h / 2, rest_v, h, color="white", edgecolor=fs.GREY, lw=0.8)
for yi, fv, rv in zip(y, farm_v, rest_v):
    ax.text(fv + 1, yi - h / 2, f"{fv:.1f}%", va="center", fontsize=6.5, color=fs.WARN)
    ax.text(rv + 1, yi + h / 2, f"{rv:.1f}%", va="center", fontsize=6.5, color=fs.GREY)
ax.set_yticks(y, cats)
ax.invert_yaxis()
ax.set_xlim(0, 112)
ax.set_xticks([0, 25, 50, 75, 100])
ax.set_xlabel("% of docs")
ax.set_title("(c) share passing static signals", loc="left")

fs.save(fig, "fig_staticmiss")
json.dump({"farm_docs": int(fn), "farm_pass_all": int(fpass), "rest_docs": int(rn),
           "rest_pass_all": int(rpass), "farm_three_lid_agree": float(fag),
           "rest_three_lid_agree": float(rag)},
          open("out/analysis/fig_staticmiss.json", "w"), indent=1)
