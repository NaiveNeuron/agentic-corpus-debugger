"""Prepare any FineWeb2 language for an audit.

Downloads a language's shards of ``HuggingFaceFW/fineweb-2`` from the Hub and
builds the derived audit tables, with a text sample sized for interactive use.

    python -m src.corpusaudit.fineweb2 hun_Latn --shards 4

Language codes are FineWeb2's own (``hun_Latn``, ``srp_Cyrl``, ...). The run
ends by printing the commands for an agent audit and for the test suite.
"""

from __future__ import annotations

import argparse
import math
import os
import sys

import duckdb

from .db import build
from .prompt import language_name

REPO = "HuggingFaceFW/fineweb-2"
DEFAULT_DATA = "data/fineweb2"
# About the size of the Slovak working sample (2.03M documents with text).
DEFAULT_SAMPLE_DOCS = 2_000_000


def select_shards(files: list[str], lang: str, split: str = "train",
                  n: int | None = None, step: int = 1) -> list[str]:
    """The Parquet shards of one language and split, in order, thinned by ``step``
    and cut at ``n``."""
    prefix = f"data/{lang}/{split}/"
    found = sorted(f for f in files if f.startswith(prefix) and f.endswith(".parquet"))
    if not found:
        raise SystemExit(f"FineWeb2 has no {split} shards for {lang!r}; "
                         f"language codes look like hun_Latn or srp_Cyrl")
    return found[::max(1, step)][:n]


def sample_mod_for(n_docs: int, target: int) -> int:
    """Keep one in this many documents with text to get about ``target`` of them."""
    return max(1, math.ceil(n_docs / max(1, target)))


def refuse_if_too_big(total_bytes: int, max_gb: float) -> None:
    if total_bytes > max_gb * 1e9:
        raise SystemExit(f"the selected shards hold {total_bytes / 1e9:.1f} GB, more than "
                         f"--max-gb {max_gb:g}; take fewer with --shards or --step, "
                         f"or raise --max-gb")


def prepare(shards: str | list[str], out: str, target_docs: int = DEFAULT_SAMPLE_DOCS,
            threads: int = 0) -> int:
    """Build the derived tables from local shards; return the sample modulus used."""
    n_docs = duckdb.connect().execute(
        "select count(*) from read_parquet($shards)", {"shards": shards}).fetchone()[0]
    mod = sample_mod_for(n_docs, target_docs)
    build(shards, out, threads=threads, sample_mod=mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("lang", help="FineWeb2 language code, e.g. hun_Latn")
    ap.add_argument("--split", default="train", choices=("train", "test"),
                    help="test is a small split, handy for a first try")
    ap.add_argument("--shards", type=int, default=None, help="at most this many shards")
    ap.add_argument("--step", type=int, default=1, help="take every k-th shard")
    ap.add_argument("--sample-docs", type=int, default=DEFAULT_SAMPLE_DOCS,
                    help="documents kept with text for reading and text search")
    ap.add_argument("--max-gb", type=float, default=100.0,
                    help="refuse to download more than this")
    ap.add_argument("--data", default=DEFAULT_DATA)
    args = ap.parse_args()

    from huggingface_hub import HfApi, snapshot_download

    api = HfApi()
    picked = select_shards(api.list_repo_files(REPO, repo_type="dataset"), args.lang,
                           args.split, args.shards, args.step)
    total = sum(i.size or 0 for i in api.get_paths_info(REPO, picked, repo_type="dataset"))
    refuse_if_too_big(total, args.max_gb)
    print(f"[fineweb2] {args.lang}: {len(picked)} {args.split} shard(s), "
          f"{total / 1e9:.1f} GB", flush=True)
    snapshot_download(REPO, repo_type="dataset", allow_patterns=picked,
                      local_dir=args.data, max_workers=8)

    out = os.path.join(args.data, args.lang, "derived")
    mod = prepare([os.path.join(args.data, p) for p in picked], out, args.sample_docs)
    run = f"{args.lang}_1"
    # Without a name the prompt would call the language by its code.
    name = "" if language_name(args.lang) != args.lang else ' "<English name>"'
    print(f"""
[fineweb2] derived tables in {out} (text kept for 1 in {mod} documents)

next steps:
  scripts/run_agent.sh {run} 300 sonnet 250 {out}{name}      # one audit, ~$2-3
  uv run python scripts/findings_to_tests.py out/runs/{run}
  uv run python -m src.corpusaudit.testsuite tests/metadata tests/{args.lang} --derived {out}
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
