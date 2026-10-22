#!/usr/bin/env python
"""Run the released suite against other languages of upstream FineWeb2.

Two questions this answers, neither of which needs an annotator:

1. Does a community that is not us get anything by pointing the framework at
   their own corpus?  Upstream FineWeb2 ships fewer columns than the Slovak
   redistribution, so this also exercises the adapter's degradation path: the
   Slovak-specific tests must be reported as out of scope or unmeasurable,
   never as passing.
2. Is the invalid-confidence defect a property of the Slovak release or of the
   FineWeb2 pipeline?  The test is arithmetic, so it transfers verbatim.

Shards are the small ``test`` split of each configuration (8-70 MB each).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
import sys

import duckdb

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
OUT = REPO / "out" / "analysis"
FW2 = REPO / "data" / "fw2" / "data"

# Script of each configuration, for reporting breadth rather than count.
SCRIPTS = {
    "Latn": "Latin", "Ethi": "Ethiopic", "Hebr": "Hebrew", "Armn": "Armenian",
    "Khmr": "Khmer", "Thai": "Thai", "Grek": "Greek", "Cyrl": "Cyrillic",
    "Geor": "Georgian", "Hang": "Hangul", "Taml": "Tamil",
}

DEFAULT_CONFIGS = [
    "cym_Latn", "mlt_Latn", "isl_Latn", "slk_Latn", "ces_Latn",
    "amh_Ethi", "nno_Latn", "swh_Latn", "hye_Armn", "khm_Khmr",
    "heb_Hebr", "tha_Thai",
]


def fetch(config: str) -> str:
    """Local path to a config's test shard, downloading it if needed."""
    path = FW2 / config / "test" / "000_00000.parquet"
    if not path.exists():
        from huggingface_hub import hf_hub_download

        hf_hub_download(
            "HuggingFaceFW/fineweb-2",
            f"data/{config}/test/000_00000.parquet",
            repo_type="dataset",
            local_dir=str(REPO / "data" / "fw2"),
        )
    return str(path)


def raw_stats(con: duckdb.DuckDBPyConnection, shard: str) -> dict:
    """The invalid-confidence count straight off the raw shard."""
    n, gt1, mx = con.execute(
        f"""select count(*), sum(case when language_score > 1.0 then 1 else 0 end),
                   max(language_score) from read_parquet('{shard}')"""
    ).fetchone()
    dups = con.execute(
        f"select count(*) - count(distinct id) from read_parquet('{shard}')"
    ).fetchone()[0]
    gt1 = int(gt1 or 0)
    return {"n": n, "gt1": gt1, "share": gt1 / n if n else 0.0,
            "max_score": mx, "dup_ids": dups}


def suite_on(config: str, shard: str) -> dict:
    """Build the adapter over one config and run the whole suite."""
    from src.corpusaudit.db import build
    from src.corpusaudit.testsuite import run

    derived = REPO / "data" / f"derived_x_{config}"
    if not (derived / "meta.parquet").exists():
        build(shard, str(derived), threads=os.cpu_count() or 8)
    report = OUT / f"testsuite_x_{config}.json"
    run(["tests/slk_Latn", "tests/metadata"], str(derived), str(report))
    return json.load(open(report))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("configs", nargs="*", default=DEFAULT_CONFIGS)
    ap.add_argument("--suite", action="store_true",
                    help="also build the adapter and run the full suite per config")
    args = ap.parse_args()

    con = duckdb.connect()
    con.execute(f"set threads={os.cpu_count() or 8}")

    rows = []
    print(f"{'config':10s} {'script':10s} {'docs':>8s} {'score>1':>9s} {'share':>8s} "
          f"{'max(score)':>12s} {'dup ids':>8s}")
    for config in args.configs:
        shard = fetch(config)
        st = raw_stats(con, shard)
        script = SCRIPTS.get(config.split("_")[-1], config.split("_")[-1])
        rows.append({"config": config, "script": script, **st})
        print(f"{config:10s} {script:10s} {st['n']:>8,} {st['gt1']:>9,} "
              f"{st['share'] * 100:7.2f}% {st['max_score']:>12.6f} {st['dup_ids']:>8}")

    hit = [r for r in rows if r["gt1"] > 0]
    scripts = sorted({r["script"] for r in rows})
    summary = {
        "configs": len(rows),
        "configs_with_defect": len(hit),
        "scripts": scripts,
        "share_min": min(r["share"] for r in hit) if hit else 0.0,
        "share_max": max(r["share"] for r in hit) if hit else 0.0,
        "max_score_overall": max(r["max_score"] for r in rows),
        "clean_configs": [r["config"] for r in rows if r["gt1"] == 0],
        "duplicate_ids_anywhere": sum(r["dup_ids"] for r in rows),
        "per_config": rows,
    }
    print(f"\ninvalid confidence in {len(hit)}/{len(rows)} configurations across "
          f"{len(scripts)} scripts, {summary['share_min'] * 100:.1f}%-"
          f"{summary['share_max'] * 100:.1f}% of documents, "
          f"all bounded by {summary['max_score_overall']:.5f}")
    if summary["clean_configs"]:
        print(f"clean: {', '.join(summary['clean_configs'])}")

    if args.suite:
        print()
        per = {}
        for config in args.configs:
            rep = suite_on(config, fetch(config))
            ran = [t for t in rep["tests"]]
            per[config] = {
                "scope": rep["scope"],
                "ran": len(ran),
                "failing": sum(t["status"] == "FAIL" for t in ran),
                "out_of_scope": len(rep.get("skipped_out_of_scope", [])),
                "unmeasurable": len(rep.get("unmeasurable", [])),
                "passing_ids": [t["id"] for t in ran if t["status"] == "PASS"],
                "failing_ids": [t["id"] for t in ran if t["status"] == "FAIL"],
            }
            print(f"{config:10s} ran {per[config]['ran']}, "
                  f"failing {per[config]['failing']}, "
                  f"out of scope {per[config]['out_of_scope']}, "
                  f"unmeasurable {per[config]['unmeasurable']}")
        summary["suite_per_config"] = per
        wrong = [c for c, v in per.items()
                 if v["scope"] != "slk_Latn" and v["out_of_scope"] == 0]
        print("\nevery foreign corpus skipped the Slovak tests: " + ("yes" if not wrong
              else f"NO -- {wrong}"))

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cross_language.json").write_text(json.dumps(summary, indent=2))

    # A defect present in 11 of 12 unrelated configurations is a pipeline
    # property, and the paper says so; guard the claim.
    if len(hit) < 2:
        print("\nthe cross-language claim does not hold on this measurement",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
