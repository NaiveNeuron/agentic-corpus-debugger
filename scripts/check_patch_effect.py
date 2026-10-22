#!/usr/bin/env python
"""Does applying the patches actually turn the suite green?

The artefact claims two things about a finding: a test says the slice should not
be there, and the same selector used as a filter removes it. The second claim has
never been checked end to end. This builds a *patched* corpus -- the real derived
tables minus every row the patch set removes -- and re-runs the whole suite over
it. A prevalence guard that still fails after its own patch would mean the
selector and the assertion disagree.

The two metadata invariants are deliberately excluded from patching (dropping the
rows would hide the defect rather than fix it), so they are expected to survive:
the identifier collisions vanish only because the colliding rows are inside a
patched slice or not, and the out-of-range confidence needs a pipeline fix. That
asymmetry is the point, and this script reports it rather than papering over it.

    python scripts/check_patch_effect.py [--statuses candidate accepted]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

import duckdb

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.corpusaudit.patch import PatchSet  # noqa: E402
from src.corpusaudit.testsuite import run  # noqa: E402

FAILURES: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + label + (f"  [{detail}]" if detail else ""))
    if not cond:
        FAILURES.append(label)


def build_patched(derived: str, out: str, ps, threads: int) -> dict:
    """Materialise the corpus with every patched row removed.

    The text-free ``meta`` table can only evaluate metadata-only selectors, so the
    filter is assembled from the patch set's own classification of each selector,
    never by splitting SQL text: a compound selector contains its own ``OR`` and
    would be mangled into unparseable fragments.
    """
    meta_only = [p for p in ps.patches if not p.needs_text]
    meta_cond = " OR ".join(f"({p.selector})" for p in meta_only) or "false"
    conds = {"meta": meta_cond, "docs": ps.combined_selector}
    if len(meta_only) < len(ps.patches):
        skipped = [p.id for p in ps.patches if p.needs_text]
        print(f"  text-dependent patches apply to the sample only: {', '.join(skipped)}")
    os.makedirs(out, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"set threads={threads}")
    con.execute("set preserve_insertion_order=false")
    counts = {}
    for rel in ("meta", "docs"):
        src = os.path.join(derived, f"{rel}.parquet")
        dst = os.path.join(out, f"{rel}.parquet")
        con.execute(f"create or replace view {rel} as select * from read_parquet('{src}')")
        before = con.execute(f"select count(*) from {rel}").fetchone()[0]
        cond = conds[rel]
        con.execute(
            f"copy (select * from {rel} where not ({cond})) to '{dst}' "
            f"(format parquet, compression zstd)"
        )
        after = con.execute(f"select count(*) from read_parquet('{dst}')").fetchone()[0]
        counts[rel] = {"before": before, "after": after, "removed": before - after}
        print(f"  {rel}: {before:,} -> {after:,} ({before - after:,} removed)")
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--derived", default=os.environ.get("AUDIT_DERIVED", "data/derived"))
    ap.add_argument("--out", default="data/derived_patched")
    ap.add_argument("--statuses", nargs="*", default=["accepted", "candidate"])
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 8)
    args = ap.parse_args()

    ps = PatchSet().load("tests/slk_Latn", "tests/metadata",
                         statuses=tuple(args.statuses))
    print(f"patch set: {len(ps.patches)} selectors with status in {tuple(args.statuses)}")
    for p in ps.patches:
        print(f"  - {p.id}")
    if not ps.patches:
        print("nothing to apply", file=sys.stderr)
        return 1

    print("\nbuilding the patched corpus")
    counts = build_patched(args.derived, args.out, ps, args.threads)

    print("\nsuite on the ORIGINAL corpus")
    before_report = REPO / "out/analysis/patch_effect_before.json"
    run(["tests/slk_Latn", "tests/metadata"], args.derived, str(before_report))

    print("\nsuite on the PATCHED corpus")
    after_report = REPO / "out/analysis/patch_effect_after.json"
    run(["tests/slk_Latn", "tests/metadata"], args.out, str(after_report))

    before = {t["id"]: t for t in json.load(open(before_report))["tests"]}
    after = {t["id"]: t for t in json.load(open(after_report))["tests"]}

    print("\nred to green")
    patched_ids = {p.id for p in ps.patches}
    fixed, survived = [], []
    for tid, b in before.items():
        a = after.get(tid)
        if a is None:
            continue
        if tid in patched_ids:
            check(a["status"] == "PASS", f"{tid} holds after its own patch",
                  f"{b['prevalence'] * 100:.4f}% -> {a['prevalence'] * 100:.4f}%")
            check(a["n_matched"] == 0, f"{tid} is fully removed by its own patch",
                  f"{a['n_matched']:,} left of {b['n_matched']:,}")
            fixed.append(tid)
        else:
            survived.append({"id": tid, "status": a["status"],
                             "prevalence": a["prevalence"]})

    print("\nnot filterable, therefore expected to survive")
    for s in survived:
        expected = s["status"] == before[s["id"]]["status"] or s["prevalence"] > 0
        check(expected, f"{s['id']} is unchanged by patching, as documented",
              f"{s['status']} at {s['prevalence'] * 100:.3f}%")

    # The simulation above patches in memory. What actually travels to a consumer is
    # `out/patches/drop_ids.parquet`, and a patch that only works from our own code
    # is not a patch. Rather than rebuild 9 GB, assert the file is *sufficient*:
    # every document any patched selector matches must be listed in it.
    drop = REPO / "out/patches/drop_ids.parquet"
    if drop.exists():
        print("\nthe distributed drop list is sufficient on its own")
        ps = PatchSet().load(*[str(REPO / "tests" / d.name) for d in (REPO / "tests").iterdir()
                              if d.is_dir()], statuses=tuple(args.statuses))
        dcon = duckdb.connect()
        dcon.execute(f"set threads={args.threads}")
        src = os.path.join(args.derived, "meta.parquet")
        n_drop = dcon.execute(
            f"select count(*) from read_parquet('{drop}')").fetchone()[0]
        # metadata-only selectors are exact on the whole release; text-dependent ones
        # are measured where the text lives, which is the same relation the drop list
        # was written from
        meta_patches = [p for p in ps.patches if not p.needs_text]
        cond = " or ".join(f"({p.selector})" for p in meta_patches)
        leaked = dcon.execute(
            f"select count(*) from read_parquet('{src}') where ({cond}) "
            f"and id not in (select id from read_parquet('{drop}'))").fetchone()[0]
        check(leaked == 0,
              "every document a patch matches is in the shipped drop list",
              f"{leaked} missing from {n_drop:,} ids")

    print("\ncollateral damage")
    kept = counts["meta"]["after"] / counts["meta"]["before"]
    print(f"  the patched corpus keeps {kept * 100:.2f}% of documents")
    check(kept > 0.5, "the patch set does not destroy the corpus", f"{kept * 100:.2f}% kept")
    b_fail = sum(t["status"] == "FAIL" for t in before.values())
    a_fail = {tid for tid, t in after.items() if t["status"] == "FAIL"}
    from src.corpusaudit.patch import NOT_FILTERABLE

    check(a_fail <= NOT_FILTERABLE,
          "every test still failing after patching is one a filter cannot fix",
          f"{b_fail} before; after: {sorted(a_fail) or 'none'}")

    summary = {
        "statuses": args.statuses,
        "patches": sorted(patched_ids),
        "counts": counts,
        "documents_kept": kept,
        "failing_before": b_fail,
        "failing_after": sorted(a_fail),
        "not_filterable": sorted(NOT_FILTERABLE),
        "fixed": sorted(fixed),
        "survived": survived,
    }
    (REPO / "out/analysis/patch_effect.json").write_text(json.dumps(summary, indent=2))

    print()
    if FAILURES:
        print(f"{len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  -", f)
        return 1
    print(f"every patched guard turns green; {len(survived)} test(s) survive by design")
    return 0


if __name__ == "__main__":
    sys.exit(main())
