#!/usr/bin/env python
"""Minimal terminal annotator for the blinded validation package.

Two keystrokes per document, resumable, appends to out/annotation/labels.csv.

    uv run python scripts/annotate.py            # continue where you left off
    uv run python scripts/annotate.py --limit 50 # do a batch of 50
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import sys

LANG = {"1": "sk", "2": "sk-pred", "3": "cs", "4": "mix", "5": "other", "0": "?"}
QUAL = {"1": "good", "2": "noisy", "3": "junk", "0": "?"}

PROMPT_LANG = "  language: 1=sk  2=sk-pred  3=cs  4=mix(sk/cs)  5=other  0=? (s=skip q=quit) > "
PROMPT_QUAL = "  quality : 1=good  2=noisy  3=junk  0=? > "


def read_key(prompt: str, table: dict[str, str]) -> str | None:
    while True:
        val = input(prompt).strip().lower()
        if val in ("q", "quit"):
            raise KeyboardInterrupt
        if val in ("s", "skip"):
            return None
        if val in table:
            return table[val]
        print("  ?")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="out/annotation")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--chars", type=int, default=1400)
    ap.add_argument("--annotator", default="",
                    help="second coder's name: writes labels.<name>.csv, so an "
                         "agreement figure can be computed without disturbing the "
                         "primary pass")
    ap.add_argument("--only-slices", default="",
                    help="comma-separated slice names to judge (see provenance.csv); "
                         "use to double-code just the contentious ones")
    ap.add_argument("--only-items", default="",
                    help="file of item_ids, one per line, to judge; use to re-code a "
                         "named subset after a coding rule is corrected")
    args = ap.parse_args()

    d = pathlib.Path(args.dir)
    items = list(csv.DictReader(open(d / "items.csv")))
    if args.only_slices:
        wanted = {s.strip() for s in args.only_slices.split(",") if s.strip()}
        slice_of = {r["item_id"]: r["slice"]
                    for r in csv.DictReader(open(d / "provenance.csv"))}
        items = [it for it in items if slice_of.get(it["item_id"]) in wanted]
        if not items:
            print(f"no items in slices {sorted(wanted)}")
            return 1
    if args.only_items:
        wanted_ids = {ln.strip() for ln in open(args.only_items) if ln.strip()}
        items = [it for it in items if it["item_id"] in wanted_ids]
        missing = wanted_ids - {it["item_id"] for it in items}
        if missing:
            print(f"{len(missing)} requested item(s) are not in items.csv, "
                  f"e.g. {sorted(missing)[:3]}")
            return 1
    labels_path = d / (f"labels.{args.annotator}.csv" if args.annotator
                       else "labels.csv")
    done: dict[str, dict] = {}
    if labels_path.exists():
        done = {r["item_id"]: r for r in csv.DictReader(open(labels_path))}

    # `--only-items` names documents to judge *again*, so an existing label must not
    # skip them: the whole point is that the coding rule changed since it was given.
    # Merging an earlier pass into labels.csv otherwise silences this mode entirely.
    # Resuming needs its own state, because the label a re-judgement produces may be
    # identical to the one it replaces and so cannot mark the work as done.
    recoded_path = d / (f"recoded.{args.annotator}.txt" if args.annotator
                        else "recoded.txt")
    recoded: set[str] = set()
    if args.only_items and recoded_path.exists():
        recoded = {ln.strip() for ln in open(recoded_path) if ln.strip()}

    if args.only_items:
        todo = [it for it in items if it["item_id"] not in recoded]
    else:
        todo = [it for it in items if it["item_id"] not in done]
    if args.limit:
        todo = todo[: args.limit]

    if args.only_items:
        carried = sum(1 for it in todo if it["item_id"] in done)
        print(f"{len(recoded)} of {len(items)} re-judged; {len(todo)} in this batch "
              f"({carried} carrying an earlier label, which this pass replaces).")
    else:
        # Counted within the selected subset: with --only-slices the labels file also
        # holds rows for items this run deliberately does not revisit.
        here = sum(1 for it in items if it["item_id"] in done)
        print(f"{here} of {len(items)} already labelled; {len(todo)} in this batch "
              f"({len(done)} rows in {labels_path.name}).")
    print((d / "GUIDELINES.md").read_text().split("## 1.")[0])

    new = 0

    def save(item_id: str, language: str, quality: str) -> None:
        """Persist one judgement, replacing any earlier row for the same document.

        Appending a second row would leave the file's meaning dependent on whether
        each reader keeps the first or the last one. Rewriting keeps exactly one row
        per document, which is what every consumer already assumes. The file is a few
        hundred rows, so cost does not matter, and it is written whole and then moved
        into place so an interrupt cannot truncate it.
        """
        done[item_id] = {"item_id": item_id, "language": language, "quality": quality}
        order = [r["item_id"] for r in items if r["item_id"] in done]
        order += [k for k in done if k not in set(order)]
        tmp = labels_path.with_suffix(".csv.tmp")
        with open(tmp, "w", newline="") as out:
            w = csv.DictWriter(out, fieldnames=["item_id", "language", "quality"])
            w.writeheader()
            for k in order:
                w.writerow(done[k])
        tmp.replace(labels_path)
        if args.only_items:
            with open(recoded_path, "a") as rf:
                rf.write(item_id + "\n")

    try:
        for i, it in enumerate(todo, 1):
            print("\n" + "=" * 78)
            print(f"[{i}/{len(todo)}]  {it['item_id']}   ({len(done) + new} done overall)")
            print("-" * 78)
            print(it["text"][: args.chars])
            print("-" * 78)
            lang = read_key(PROMPT_LANG, LANG)
            if lang is None:
                continue
            qual = read_key(PROMPT_QUAL, QUAL)
            if qual is None:
                continue
            # The earlier label is deliberately not shown: a re-judgement under a
            # changed rule has to be as blind as the first one.
            save(it["item_id"], lang, qual)
            new += 1
    except (KeyboardInterrupt, EOFError):
        print("\nstopping")
    what = "re-judged" if args.only_items else "wrote"
    print(f"{what} {new} labels in {labels_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
