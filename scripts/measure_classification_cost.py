#!/usr/bin/env python
"""Measure what LLM classification of this corpus would actually cost.

The paper claims the asymmetry between using an LLM once, to write a test, and
using it as a classifier over every document. That claim should rest on a
measurement rather than on token arithmetic, so we classify a small random
sample with the same model in the cheapest realistic configuration --- many
documents per call, labels only, no explanations --- and extrapolate the observed
cost per document to the full corpus.

Usage: measure_classification_cost.py [--n 200] [--batch 20] [--model sonnet]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.corpusaudit.db import open_corpus  # noqa: E402

SYSTEM = """\
You label documents from a web corpus that claims to be Slovak. For each
numbered document, output one line "<number>: <label>" and nothing else, where
label is one of: sk (usable Slovak text), notsk (not Slovak), junk (Slovak but
boilerplate, spam or machine-generated). No explanations."""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--chars", type=int, default=400)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--derived", default="data/derived")
    ap.add_argument("--out", default="out/analysis/classification_cost.json")
    args = ap.parse_args()

    corpus = open_corpus(args.derived)
    rows = corpus.con.execute(
        f"select id, replace(substr(text, 1, {args.chars}), chr(10), ' ') from docs "
        f"order by hash(id || 'costmeasure') limit {args.n}"
    ).fetchall()
    print(f"measuring on {len(rows)} documents, {args.batch} per call, {args.chars} chars each")

    total_usd = 0.0
    total_in = total_out = 0
    labels: dict[str, str] = {}
    calls = 0
    for start in range(0, len(rows), args.batch):
        chunk = rows[start : start + args.batch]
        prompt = "\n\n".join(f"{i + 1}. {text}" for i, (_, text) in enumerate(chunk))
        proc = subprocess.run(
            ["claude", "-p", "--system-prompt", SYSTEM,
             "--allowed-tools", "", "--disallowed-tools", "Bash", "Read", "Write", "Edit",
             "Glob", "Grep", "WebFetch", "WebSearch", "Task", "TodoWrite", "ReportFindings",
             "ExitPlanMode", "--model", args.model, "--max-turns", "4",
             "--permission-mode", "bypassPermissions", "--output-format", "json"],
            input=prompt, capture_output=True, text=True,
        )
        calls += 1
        try:
            res = json.loads(proc.stdout)
        except json.JSONDecodeError:
            print("  call failed; skipping", file=sys.stderr)
            continue
        total_usd += res.get("total_cost_usd") or 0.0
        usage = res.get("usage") or {}
        total_in += (usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
                     + usage.get("cache_read_input_tokens", 0))
        total_out += usage.get("output_tokens", 0)
        for line in (res.get("result") or "").splitlines():
            m = re.match(r"\s*(\d+)\s*:\s*(sk|notsk|junk)\b", line, re.I)
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(chunk):
                    labels[chunk[idx][0]] = m.group(2).lower()
        print(f"  call {calls}: cumulative ${total_usd:.4f}, {len(labels)} labels")

    n_labelled = len(labels)
    per_doc = total_usd / n_labelled if n_labelled else 0.0
    full = per_doc * corpus.n_total
    out = {
        "model": args.model,
        "n_documents": len(rows),
        "n_labelled": n_labelled,
        "documents_per_call": args.batch,
        "chars_per_document": args.chars,
        "calls": calls,
        "total_usd": total_usd,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "usd_per_document": per_doc,
        "usd_per_1000_documents": per_doc * 1000,
        "corpus_documents": corpus.n_total,
        "extrapolated_usd_full_corpus": full,
        "label_distribution": {k: sum(1 for v in labels.values() if v == k)
                               for k in ("sk", "notsk", "junk")},
        "note": "Cheapest realistic configuration: 400-character snippets, many per "
                "call, labels only. Extrapolation is linear in documents and ignores "
                "retries, so it is a lower bound.",
    }
    pathlib.Path(args.out).write_text(json.dumps(out, indent=2))
    print(json.dumps({k: out[k] for k in ("total_usd", "usd_per_1000_documents",
                                          "extrapolated_usd_full_corpus",
                                          "label_distribution")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
