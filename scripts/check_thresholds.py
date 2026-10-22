#!/usr/bin/env python
"""What do the guards' thresholds actually mean?

Each prevalence guard asserts that a slice stays within 1.2x the prevalence we
measured over the whole corpus. That is a choice, and it has a scope: the guards are
calibrated for corpus-wide evaluation over many crawls. Run them over a narrow slice
of crawls and they can trip on the composition of that slice rather than on a
regression -- so the scope has to be stated, not assumed.

This reports, per guard, the corpus prevalence, the prevalence over the eight newest
crawls, the worst single crawl, and whether either would trip the assertion. Two of
the seven trip on the newest crawls, and for the content farm that is the guard
working: the slice really is 21.6 times larger there.
"""

from __future__ import annotations

import glob
import json
import pathlib
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
TEMPORAL = REPO / "out" / "analysis" / "temporal_stability.json"
OUT = REPO / "out" / "analysis" / "threshold_calibration.json"


def main() -> int:
    if not TEMPORAL.exists():
        print("run scripts/check_temporal_stability.py first", file=sys.stderr)
        return 1
    per = {t["id"]: t for t in json.load(open(TEMPORAL))["tests"]}

    rows = []
    print(f"{'guard':38s} {'corpus':>8s} {'newest8':>8s} {'worst':>8s} {'limit':>8s}  scope")
    for path in sorted(glob.glob(str(REPO / "tests/slk_Latn/*.yaml"))):
        spec = yaml.safe_load(open(path))
        assertion = str(spec.get("assertion", ""))
        if "<=" not in assertion:
            continue
        limit = float(assertion.split("<=")[1])
        t = per.get(spec["id"])
        if not t:
            continue
        note = []
        if t["share_recent"] > limit:
            note.append("newest-8 trips")
        if t["peak_share"] > limit:
            note.append("worst crawl trips")
        rows.append({"id": spec["id"], "corpus": t["share_all"],
                     "recent": t["share_recent"], "peak": t["peak_share"],
                     "limit": limit, "recent_trips": t["share_recent"] > limit,
                     "peak_trips": t["peak_share"] > limit})
        print(f"{spec['id'][:38]:38s} {t['share_all'] * 100:7.3f}% "
              f"{t['share_recent'] * 100:7.3f}% {t['peak_share'] * 100:7.3f}% "
              f"{limit * 100:7.3f}%  {', '.join(note) or 'safe on both'}")

    n_r = sum(r["recent_trips"] for r in rows)
    n_p = sum(r["peak_trips"] for r in rows)
    OUT.write_text(json.dumps({
        "guards": rows, "n_trip_recent": n_r, "n_trip_peak": n_p,
        "note": "The guards are calibrated for corpus-wide evaluation. On a narrow "
                "slice of crawls they can trip on that slice's composition, which is "
                "information about the crawl rather than a regression. For the content "
                "farm, tripping on recent crawls is the guard working as intended.",
    }, indent=2))
    print(f"\nof {len(rows)} guards, {n_r} trip on the newest eight crawls and {n_p} on "
          f"the worst single crawl; evaluate the suite corpus-wide")
    if not rows:
        print("no guards found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
