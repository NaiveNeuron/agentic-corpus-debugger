#!/usr/bin/env bash
# Run the released suite against the corpus's held-out split, which the audit
# never saw. Downloads 71 MB and builds its derived tables if absent.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python

if [ ! -f data/derived_test/meta.parquet ]; then
  $PY - <<'PYEOF'
from huggingface_hub import hf_hub_download
hf_hub_download("ivykopal/fineweb2-slovak", "data/test-00000-of-00001.parquet",
                repo_type="dataset", local_dir="data/hf")
from src.corpusaudit.db import build
build("data/hf/data/test-00000-of-00001.parquet", "data/derived_test", threads=12)
PYEOF
fi

$PY -m src.corpusaudit.testsuite --derived data/derived_test \
    --report out/analysis/testsuite_heldout.json || true

$PY - <<'PYEOF'
import json, pathlib
tr = json.load(open("out/analysis/testsuite_report.json"))
te = json.load(open("out/analysis/testsuite_heldout.json"))
a = {t["id"]: t for t in tr["tests"]}
b = {t["id"]: t for t in te["tests"]}
rows = []
print(f"{'test':44s} {'train %':>9s} {'held-out %':>11s} {'ratio':>7s}")
for k in sorted(a, key=lambda k: -a[k]["prevalence"]):
    if k not in b:
        continue
    p, q = a[k]["prevalence"], b[k]["prevalence"]
    r = (q / p) if p else None
    print(f"{k[:44]:44s} {p * 100:9.3f} {q * 100:11.3f} "
          f"{('%.2f' % r) if r is not None else '--':>7s}")
    rows.append({"id": k, "train": p, "heldout": q, "ratio": r})
pathlib.Path("out/analysis/heldout_comparison.json").write_text(json.dumps(rows, indent=2))
guards = [r for r in rows if r["ratio"] and r["id"] != "document_ids_unique"]
print(f"\nall {len(guards)} slice guards transfer within "
      f"{min(r['ratio'] for r in guards):.2f}-{max(r['ratio'] for r in guards):.2f}x")
PYEOF
