#!/usr/bin/env python
"""Check whether the validation samples are clustered on a few hosts.

Precision intervals assume roughly independent draws. If a slice's 25 annotated
documents came from two hosts, the effective sample size would be nearer two than
25 and the interval would be optimistic. This measures the concentration so the
paper can state the caveat with a number instead of hand-waving.

    .venv/bin/python scripts/check_sample_clustering.py
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import pathlib
import sys

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.corpusaudit.selectors import needs_text  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--derived", default="data/derived")
    ap.add_argument("--annotation", default="out/annotation")
    ap.add_argument("--summary", default="out/analysis/summary.json")
    ap.add_argument("--out", default="out/analysis/sample_clustering.json")
    args = ap.parse_args()

    prov = list(csv.DictReader(open(pathlib.Path(args.annotation) / "provenance.csv")))
    by_slice: dict[str, list[str]] = collections.defaultdict(list)
    source: dict[str, str] = {}
    for row in prov:
        by_slice[row["slice"]].append(row["doc_id"])
        source[row["slice"]] = row["source"]

    con = duckdb.connect()
    con.execute("set threads=12")
    for name in ("meta", "docs"):
        con.execute(f"create view {name} as select * from "
                    f"read_parquet('{pathlib.Path(args.derived) / (name + '.parquet')}')")
    selectors = {f["id"]: f["selector"]
                 for f in json.load(open(args.summary))["findings"] if "error" not in f}

    print(f"{'slice':42s} {'src':9s} {'items':>5s} {'hosts':>5s} {'top host':>9s} {'in slice':>9s}")
    rows = []
    for slice_id, ids in sorted(by_slice.items(), key=lambda kv: (source[kv[0]], kv[0])):
        placeholders = ",".join("?" * len(ids))
        hosts = con.execute(
            f"select domain, count(*) c from meta where id in ({placeholders}) "
            "group by 1 order by c desc", ids).fetchall()
        n_hosts = len(hosts)
        top = hosts[0][1] / len(ids) if hosts else 0.0
        slice_hosts = None
        sel = selectors.get(slice_id)
        if sel:
            rel = "docs" if needs_text(sel) else "meta"
            try:
                slice_hosts = con.execute(
                    f"select count(distinct domain) from {rel} where ({sel})").fetchone()[0]
            except Exception:
                slice_hosts = None
        print(f"{slice_id[:42]:42s} {source[slice_id][:9]:9s} {len(ids):>5d} {n_hosts:>5d} "
              f"{top:>8.0%} {str(slice_hosts or '-'):>9s}")
        rows.append({"slice": slice_id, "source": source[slice_id], "items": len(ids),
                     "hosts_in_sample": n_hosts, "top_host_share": top,
                     "hosts_in_slice": slice_hosts})

    agent = [r for r in rows if r["source"] == "agent"]
    worst_hosts = min(r["hosts_in_sample"] for r in agent)
    worst_top = max(r["top_host_share"] for r in agent)
    summary = {"slices": rows,
               "agent_min_hosts_in_sample": worst_hosts,
               "agent_max_top_host_share": worst_top,
               "verdict": ("samples are spread over many hosts, so precision intervals "
                           "are close to the independent-draw case")
               if worst_hosts >= 15 and worst_top <= 0.25 else
               ("at least one sample is concentrated on few hosts; precision intervals "
                "are optimistic")}
    pathlib.Path(args.out).write_text(json.dumps(summary, indent=2))
    print(f"\nagent slices: at least {worst_hosts} distinct hosts per sample, "
          f"largest single host {worst_top:.0%}")
    print(summary["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
