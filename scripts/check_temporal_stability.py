#!/usr/bin/env python
"""Run the test suite per crawl: does it behave like a regression test?

The suite's promise is that a future crawl can be checked against it. The nearest
thing to a future crawl we hold today is the newest snapshots in the corpus, so
this evaluates every test on each Common Crawl snapshot separately and reports
where each slice actually lives in time. A detector that is stable over crawls is
a usable guard; one that appears in a single snapshot is a historical artefact and
should be read as such.

    .venv/bin/python scripts/check_temporal_stability.py
"""

from __future__ import annotations

import argparse
import glob
import json
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.corpusaudit.db import open_corpus  # noqa: E402
from src.corpusaudit.selectors import needs_text  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suites", nargs="*", default=["tests/slk_Latn", "tests/metadata"])
    ap.add_argument("--derived", default="data/derived")
    ap.add_argument("--recent", type=int, default=8, help="how many newest crawls count as recent")
    ap.add_argument("--out", default="out/analysis/temporal_stability.json")
    args = ap.parse_args()

    corpus = open_corpus(args.derived)
    con = corpus.con
    dumps = [r[0] for r in con.execute(
        "select dump from meta group by dump order by dump").fetchall()]
    recent = set(dumps[-args.recent:])
    old = set(dumps[: -args.recent])
    print(f"{len(dumps)} crawls, {dumps[0]} .. {dumps[-1]}; "
          f"'recent' = the newest {len(recent)}")

    def share(selector: str, rel: str, restrict: set[str] | None) -> tuple[int, int, float]:
        cond = f"({selector})"
        if restrict:
            names = ",".join(f"'{d}'" for d in sorted(restrict))
            base = f"dump in ({names})"
        else:
            base = "true"
        k = con.execute(f"select count(*) from {rel} where {cond} and {base}").fetchone()[0]
        n = con.execute(f"select count(*) from {rel} where {base}").fetchone()[0]
        return k, n, (k / n if n else 0.0)

    rows = []
    print(f"\n{'test':44s} {'all':>8s} {'older':>8s} {'recent':>8s}  {'span':>5s}  where it lives")
    for path in sorted(p for s in args.suites for p in glob.glob(f"{s}/*.yaml")):
        t = yaml.safe_load(open(path))
        rel = "docs" if needs_text(t["selector"]) else "meta"
        try:
            _, _, all_share = share(t["selector"], rel, None)
            _, _, old_share = share(t["selector"], rel, old)
            _, _, rec_share = share(t["selector"], rel, recent)
            per = con.execute(
                f"""select dump, count(*) filter (where ({t['selector']})) * 1.0
                           / count(*) as s
                    from {rel} group by dump having count(*) > 0 order by s desc"""
            ).fetchall()
        except Exception as exc:
            print(f"{t['id'][:44]:44s} selector failed: {exc}"[:120])
            continue
        nonzero = [d for d, s in per if s > 0]
        top = per[0] if per else ("--", 0.0)
        rows.append({"id": t["id"], "kind": t.get("kind", "prevalence_guard"),
                     "share_all": all_share, "share_older": old_share,
                     "share_recent": rec_share, "crawls_present": len(nonzero),
                     "crawls_total": len(dumps),
                     "peak_crawl": top[0], "peak_share": top[1],
                     "recent_over_older": (rec_share / old_share) if old_share else None})
        print(f"{t['id'][:44]:44s} {all_share:>7.3%} {old_share:>8.3%} {rec_share:>8.3%}  "
              f"{len(nonzero):>2d}/{len(dumps):<2d}  peak {top[0]} at {top[1]:.2%}")

    guards = [r for r in rows if r["kind"] != "metadata_invariant"]
    stable = [r for r in guards if r["crawls_present"] >= 0.5 * r["crawls_total"]]
    growing = [r for r in guards if (r["recent_over_older"] or 0) > 1.5]
    shrinking = [r for r in guards if r["recent_over_older"] is not None
                 and r["recent_over_older"] < 0.5]
    summary = {
        "crawls": len(dumps), "first": dumps[0], "last": dumps[-1],
        "recent_crawls": sorted(recent), "tests": rows,
        "guards": len(guards),
        "present_in_at_least_half_the_crawls": len(stable),
        "larger_in_recent_crawls": [r["id"] for r in growing],
        "smaller_in_recent_crawls": [r["id"] for r in shrinking],
    }
    pathlib.Path(args.out).write_text(json.dumps(summary, indent=2))
    print(f"\n{len(stable)} of {len(guards)} slice guards appear in at least half the crawls; "
          f"{len(growing)} are larger and {len(shrinking)} smaller in the newest "
          f"{len(recent)} crawls than before")
    return 0


if __name__ == "__main__":
    sys.exit(main())
