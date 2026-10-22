#!/usr/bin/env python
"""Budget-matched non-agentic audit baselines.

Each baseline is a document-selection strategy.  It draws the same number of
documents as the agent's inspection budget, shows them to the same model with
the same epistemic standard but no tools and no exploration, and collects the
candidate findings it proposes.  Prevalence of each proposed selector is then
measured by us, exactly as for the agent's findings.

Usage: run_baseline.py <strategy> [--budget N] [--model M] [--derived DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.corpusaudit.db import open_corpus  # noqa: E402
from src.corpusaudit.selectors import needs_text  # noqa: E402
from src.corpusaudit.tools import AGENT_COLUMNS, wilson  # noqa: E402

# Strategies are defined only over the corpus's own published metadata, i.e.
# what a practitioner would reach for without any language-specific insight.
STRATEGIES = {
    "random": ("true", "hash(id || $seed)"),
    "lowconf": ("true", "language_score asc, hash(id || $seed)"),
    "lid_disagree": (
        "fasttext <> 'sk' or langdetect <> 'sk' or lingua_top <> 'sk'",
        "hash(id || $seed)",
    ),
    "highdup": ("true", "minhash_cluster_size desc, hash(id || $seed)"),
    # The corpus's own profanity counter.
    "highprof": ("true", "n_bad_words desc nulls last, hash(id || $seed)"),
}


def select(corpus, strategy: str, n: int, seed: int) -> list[dict]:
    where, order = STRATEGIES[strategy]
    order = order.replace("$seed", f"'{seed}'")
    cols = ", ".join(AGENT_COLUMNS)
    rel = corpus.con.execute(
        f"select {cols}, substr(text, 1, 400) as snippet from corpus_view "
        f"where ({where}) order by {order} limit {n}"
    )
    names = [d[0] for d in rel.description]
    return [dict(zip(names, r)) for r in rel.fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("strategy", choices=sorted(STRATEGIES))
    ap.add_argument("--budget", type=int, default=300)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--derived", default="data/derived")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out = pathlib.Path(args.out or f"out/baselines/{args.strategy}")
    out.mkdir(parents=True, exist_ok=True)

    corpus = open_corpus(args.derived)
    corpus.con.execute(
        "create view corpus_view as select text, " + ", ".join(AGENT_COLUMNS) + " from docs"
    )
    docs = select(corpus, args.strategy, args.budget, args.seed)
    (out / "sample.json").write_text(json.dumps(docs, ensure_ascii=False, default=str, indent=1))

    packet = "\n".join(json.dumps(d, ensure_ascii=False, default=str) for d in docs)
    prompt = (
        f"Here are {len(docs)} documents sampled from the corpus. "
        "Audit them and report your findings as the specified JSON array.\n\n" + packet
    )
    (out / "prompt.txt").write_text(prompt)

    cmd = [
        "claude", "-p",
        "--system-prompt", pathlib.Path("prompts/baseline_system.md").read_text(),
        "--allowed-tools", "",
        "--disallowed-tools", "Bash", "Read", "Write", "Edit", "Glob", "Grep",
        "WebFetch", "WebSearch", "Task", "TodoWrite", "ReportFindings", "ExitPlanMode",
        "--model", args.model, "--max-turns", "6",
        "--permission-mode", "bypassPermissions",
        "--output-format", "json",
    ]
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True)
    (out / "raw.json").write_text(proc.stdout or proc.stderr)
    try:
        res = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print("no parseable result; see", out / "raw.json", file=sys.stderr)
        return 1
    (out / "cost.json").write_text(
        json.dumps({k: res.get(k) for k in ("total_cost_usd", "num_turns", "usage")}, indent=2)
    )

    text = res.get("result", "")
    m = re.search(r"\[.*\]", text, re.S)
    findings = json.loads(m.group(0)) if m else []

    import yaml

    fdir = out / "findings"
    fdir.mkdir(exist_ok=True)
    for f in findings:
        sel = f.get("selector", "")
        uses_text = needs_text(sel)
        rel = "corpus_view" if uses_text else "meta"
        n = corpus.n_sample if uses_text else corpus.n_total
        try:
            k = corpus.con.execute(f"select count(*) from {rel} where ({sel})").fetchone()[0]
        except Exception as exc:
            k, err = 0, str(exc)
        else:
            err = None
        lo, hi = wilson(k, n)
        doc = {
            "id": f.get("finding_id"),
            "scope": "slk_Latn",
            "source": f"baseline:{args.strategy}",
            "description": f.get("description"),
            "selector": sel,
            "assertion": f"prevalence <= {k / n:.6f}" if n else "",
            "evidence": {
                "agent_evidence": f.get("evidence"),
                "prevalence": k / n if n else 0.0,
                "prevalence_ci95": [lo, hi],
                "n_matched": k,
                "evaluated_on": rel,
                "exact_on_full_corpus": not uses_text,
                "agent_expected_precision": f.get("expected_precision"),
                "likely_false_positives": f.get("likely_false_positives"),
                "example_ids": f.get("example_ids", []),
                "selector_error": err,
            },
        }
        name = re.sub(r"[^a-z0-9_]", "_", str(doc["id"]).lower())
        (fdir / f"{name}.yaml").write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)
        )
    print(f"{args.strategy}: {len(findings)} candidate findings, "
          f"cost {res.get('total_cost_usd')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
