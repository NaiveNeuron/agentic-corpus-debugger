#!/usr/bin/env python
"""Apply the test suite as patches and report what a cleaned corpus loses.

    .venv/bin/python scripts/apply_patches.py                 # accepted only
    .venv/bin/python scripts/apply_patches.py --candidates    # + pending findings
    .venv/bin/python scripts/apply_patches.py --candidates --write-drop-list

The drop list is the distributable form of a patch: a Parquet file of document
ids, so a language community can ship a correction without shipping the corpus.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.corpusaudit.db import open_corpus  # noqa: E402
from src.corpusaudit.patch import PatchSet  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suites", nargs="*", default=["tests/slk_Latn", "tests/metadata"])
    ap.add_argument("--derived", default="data/derived")
    ap.add_argument("--candidates", action="store_true",
                    help="also apply findings still awaiting human adjudication")
    ap.add_argument("--write-drop-list", action="store_true")
    ap.add_argument("--drop-list", default="out/patches/drop_ids.parquet")
    ap.add_argument("--report", default="out/analysis/patch_report.json")
    args = ap.parse_args()

    statuses = ("accepted", "candidate") if args.candidates else ("accepted",)
    ps = PatchSet().load(*args.suites, statuses=statuses)
    if not ps.patches:
        print(f"no patches with status in {statuses}; "
              "nothing is applied until a human accepts a finding")
        return 0

    corpus = open_corpus(args.derived)
    stats = ps.measure(corpus.con)
    stats["statuses_applied"] = list(statuses)

    print(f"{'patch':44s} {'status':10s} {'docs':>10s} {'of corpus':>10s} {'of words':>9s}")
    for p in sorted(stats["patches"], key=lambda x: -x["documents_removed"]):
        print(f"{p['id'][:44]:44s} {p['status']:10s} {p['documents_removed']:>10,d} "
              f"{p['document_share']:>9.3%} {p['word_share']:>9.3%}")
    c = stats["combined"]
    print(f"\ncombined: {c['documents_removed']:,} of {c['documents']:,} documents "
          f"({c['document_share']:.2%}) and {c['word_share']:.2%} of words "
          f"({'exact on the full corpus' if stats['relation'] == 'meta' else 'on the text sample'})")

    if args.write_drop_list:
        path = pathlib.Path(args.drop_list)
        path.parent.mkdir(parents=True, exist_ok=True)
        n = ps.write_drop_list(corpus.con, str(path))
        stats["drop_list"] = {"path": str(path), "ids": n,
                             "bytes": path.stat().st_size}
        print(f"drop list: {n:,} ids -> {path} ({path.stat().st_size / 1e6:.1f} MB)")

    pathlib.Path(args.report).write_text(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
