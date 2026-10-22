#!/usr/bin/env python
"""Calibrate the Czech/Slovak identifier against an external benchmark.

The two Czech findings rest on three auxiliary identifiers agreeing, so the obvious
question is how reliable one identifier is on this pair. CHALIS (Tichy and Libovicky,
2026) is a benchmark of hard language-identification cases that, usefully, separates
sentences with a single correct label from sentences that are *equally valid* Czech and
Slovak.

Only Lingua is exercised: it is the identifier this project already depends on, and
installing the other two would add a 130 MB model for one number. The setting is the
hardest one, forced binary Czech versus Slovak.
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "chalis" / "dataset.json"
OUT = REPO / "out" / "analysis" / "chalis_calibration.json"

CS, SK = "ces_Latn", "slk_Latn"


def main() -> int:
    if not DATA.exists():
        from huggingface_hub import hf_hub_download

        hf_hub_download("michal-tichy/CHALIS", "dataset.json", repo_type="dataset",
                        local_dir=str(REPO / "data" / "chalis"))
    d = json.load(open(DATA))
    single = [r for r in d["single"] if r["label"] and set(r["label"]) <= {CS, SK}]
    joint = [r for r in d["joint"] if set(r["label"]) == {CS, SK}]

    from lingua import Language, LanguageDetectorBuilder

    det = LanguageDetectorBuilder.from_languages(Language.CZECH, Language.SLOVAK).build()
    code = {"CZECH": CS, "SLOVAK": SK}

    def guess(text: str) -> str | None:
        r = det.detect_language_of(text)
        return code.get(r.name) if r else None

    ok: collections.Counter = collections.Counter()
    tot: collections.Counter = collections.Counter()
    for r in single:
        gold = r["label"][0]
        tot[gold] += 1
        ok[gold] += guess(r["text"]) == gold
    jg = collections.Counter(guess(r["text"]) for r in joint)

    print("Lingua, forced binary Czech vs Slovak, on single-label CHALIS sentences:")
    for g in sorted(tot):
        print(f"  {g}: {ok[g]}/{tot[g]} = {ok[g] / tot[g] * 100:.1f}% correct")
    amb = len(joint) / (len(joint) + len(single))
    print(f"\n{len(joint)} sentences are equally valid in both languages "
          f"({amb * 100:.1f}% of the benchmark's Czech/Slovak material); it answers "
          f"Czech for {jg[CS] / len(joint) * 100:.0f}% of them")

    # The rule the finding actually uses is the conjunction, which needs the other
    # two identifiers. They are an optional extra: without them we report Lingua
    # alone rather than nothing.
    triple = None
    try:
        import fasttext
        from langdetect import DetectorFactory, detect_langs

        DetectorFactory.seed = 0
        model = REPO / "data" / "lid" / "lid.176.bin"
        if model.exists():
            ft = fasttext.load_model(str(model))

            def three(text: str):
                t = text.replace("\n", " ")
                f = ft.predict(t, k=1)[0][0].replace("__label__", "")
                try:
                    ld = max(detect_langs(t), key=lambda x: x.prob).lang
                except Exception:
                    ld = None
                r = det.detect_language_of(t)
                return f, ld, {"CZECH": "cs", "SLOVAK": "sk"}.get(r.name) if r else None

            def fires(text: str) -> bool:
                return three(text) == ("cs", "cs", "cs")

            fired = [r for r in single if fires(r["text"])]
            right = sum(1 for r in fired if r["label"][0] == CS)
            jf = sum(1 for r in joint if fires(r["text"]))
            per = {}
            sk_only = [r for r in single if r["label"][0] == SK]
            for i, name in enumerate(("fasttext", "langdetect", "lingua")):
                per[name] = sum(1 for r in sk_only if three(r["text"])[i] == "sk") / len(sk_only)
            triple = {"triple_fired": len(fired), "triple_correct": right,
                      "triple_precision": right / len(fired) if fired else None,
                      "triple_fired_on_joint": jf, "triple_joint_rate": jf / len(joint),
                      "slovak_side_accuracy": per}
            print(f"\nall three saying Czech: {right}/{len(fired)} correct = "
                  f"{right / len(fired) * 100:.1f}% precision; fires on "
                  f"{jf / len(joint) * 100:.1f}% of the ambiguous sentences")
            (REPO / "out/analysis/chalis_triple.json").write_text(json.dumps(triple, indent=2))
    except ImportError:
        print("\n(fasttext/langdetect absent: reporting Lingua alone. "
              "install the 'lid' extra for the conjunction)")

    OUT.write_text(json.dumps({
        "single_cs": tot[CS], "single_sk": tot[SK],
        "acc_cs": ok[CS] / tot[CS], "acc_sk": ok[SK] / tot[SK],
        "joint": len(joint), "joint_called_czech": jg[CS],
        "joint_called_czech_share": jg[CS] / len(joint),
        "ambiguous_share_of_cs_sk_material": amb,
        "median_joint_chars": sorted(len(r["text"]) for r in joint)[len(joint) // 2],
        "note": "External calibration from CHALIS (Tichy and Libovicky, 2026). Only "
                "lingua is exercised: it is the identifier this project already depends "
                "on. Forced binary Czech-vs-Slovak, the hardest setting.",
    }, indent=2))
    if ok[SK] / tot[SK] >= ok[CS] / tot[CS]:
        print("\nthe Slovak side is not the weaker one on this run", file=sys.stderr)
        return 1
    print("one identifier is a weak witness on this pair, which is why the selector "
          "requires all three")
    return 0


if __name__ == "__main__":
    sys.exit(main())
