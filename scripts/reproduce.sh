#!/usr/bin/env bash
# End-to-end reproduction of the Slovak FineWeb2 audit.
# Human steps (annotation, adjudication) are marked and must be run by a person.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python
BUDGET="${BUDGET:-300}"
MODEL="${MODEL:-sonnet}"

step() { printf '\n=== %s ===\n' "$1"; }

step "0. environment"
command -v uv >/dev/null || { echo "install uv first"; exit 1; }
uv sync

step "0b. self-test (no corpus needed)"
$PY -m selftest.test_framework

step "1. corpus (63 GB from the Hub; skipped if already present)"
[ -d data/hf/data ] || $PY scripts/download_shards.py

step "2. derived tables (~4 min: meta over 26.5M docs, docs over the 1-in-13 sample)"
[ -f data/derived/meta.parquet ] || $PY -c "from src.corpusaudit.db import build; build()"

# Skipped when the logs are already present. Re-running needs the Claude Code CLI and
# credentials (see README); every number in the paper is recomputed from the released
# logs, so a reader without credentials loses nothing.
step "3. three audit runs (skipped if already present)"
for run in main rep1 rep2; do
  [ -d "out/runs/$run/findings" ] || scripts/run_agent.sh "$run" "$BUDGET" "$MODEL"
done

step "4. budget-matched baselines"
for s in random lowconf lid_disagree highdup; do
  [ -d "out/baselines/$s/findings" ] || \
    $PY scripts/run_baseline.py "$s" --budget "$BUDGET" --model "$MODEL"
done

step "5. analysis, packages"
$PY scripts/analyze.py
$PY scripts/build_annotation.py
$PY scripts/build_adjudication.py

step "6. HUMAN: annotate and adjudicate"
cat <<'TXT'
  .venv/bin/python scripts/annotate.py        # 358 blinded documents
  $EDITOR out/adjudication/decisions.csv      # 11 grouped findings
Then re-run this script to fold the judgments into the results.
TXT

step "7. results, test suite, report"
$PY scripts/analyze.py
$PY scripts/compile_tests.py
$PY scripts/make_figure.py
$PY -m src.corpusaudit.testsuite --report out/analysis/testsuite_report.json || true
$PY scripts/make_paper_macros.py   # numbers the paper quotes about itself
$PY scripts/apply_patches.py --candidates
bash scripts/check_heldout.sh
$PY scripts/check_cross_language.py --suite
$PY scripts/check_chalis.py
$PY scripts/check_temporal_stability.py
$PY scripts/check_thresholds.py
$PY scripts/check_experiment_integrity.py
$PY scripts/replay_trajectory.py out/runs/main out/runs/rep1 out/runs/rep2
$PY scripts/check_sample_clustering.py
$PY scripts/check_patch_effect.py
$PY scripts/make_report.py

