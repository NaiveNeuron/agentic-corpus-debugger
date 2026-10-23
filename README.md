# Agentic Corpus Debugger: pytest for web corpora

An LLM agent debugs a web corpus. It explores the corpus through a small,
read-only tool API, forms and tests hypotheses about systematic defects,
measures how common each one is, and saves what survives as
machine-readable **corpus tests**. The tests then run on every new release
without any LLM or GPU.

This repository holds the code and data for the paper
[*Can an Agent Debug a Web Corpus? Agentic Auditing of Slovak FineWeb2*](https://arxiv.org/abs/2610.31636)
(WaC-13, EMNLP 2026). On the Slovak part of FineWeb2 (26.47M documents) the
agent found, among other defects, a content farm of 1,408,437 documents
(5.32%) on Firebase subdomains that passes FineWeb2's language-ID and
deduplication filters. Each agent run cost $2.21-2.84; the resulting suite of
9 tests checks the metadata of the whole corpus in under a second.

## Quick check, no data needed

```bash
uv sync
uv run python -m selftest.test_framework
```

The self-test builds small synthetic corpora, runs the tools, the SQL guard,
the FineWeb2 runner and the test runner on them, and checks the numbers they
report. It ends with `all checks passed`.

## Try it on your language

Any of the 1,913 language configurations of
[FineWeb2](https://huggingface.co/datasets/HuggingFaceFW/fineweb-2) works.

```bash
# 1. Download and build the audit tables (start small: --split test)
uv run python -m src.corpusaudit.fineweb2 hun_Latn --shards 4

# 2. One agent audit (needs the Claude Code CLI; about $2-3 per run)
scripts/run_agent.sh hun_Latn_1 300 sonnet 250 data/fineweb2/hun_Latn/derived

# 3. Turn the agent's findings into candidate tests
uv run python scripts/findings_to_tests.py out/runs/hun_Latn_1

# 4. Run the suite
uv run python -m src.corpusaudit.testsuite tests/metadata tests/hun_Latn \
    --derived data/fineweb2/hun_Latn/derived
```

* **Step 1** picks the language's shards from the Hub, refuses downloads
  above `--max-gb` (default 100), and keeps text for about 2M documents
  (`--sample-docs`). Metadata stays complete, so metadata-only tests are exact
  over everything you downloaded. For very large languages, a subset of shards
  (`--shards`, `--step`) gives estimates, not exact corpus-wide counts.
* **Step 2** gives the agent only the audit tools: no shell, no files, no web.
  The prompt is `prompts/auditor_system.md` with your language's name and code
  filled in; the prompt used is saved in the run directory. If the language has
  no known English name, pass it as a sixth argument, e.g. `"Maltese"`.
* **Step 3** writes `tests/<scope>/<id>.yaml` with `status: candidate`. A
  candidate is measured but not validated. Before you call a test accepted,
  have a native speaker label a blinded sample of each slice, as in the paper.
* **Step 4** reports each test as `PASS`, `FAIL`, `skip` (another language) or
  `unmeasured` (needs a column this release does not ship).

What the agent sees on another language:

* Upstream FineWeb2 does not ship the extra language-ID columns of the Slovak
  redistribution (`fasttext`, `langdetect`, `lingua`, `bad_words`). They are
  empty, and the `schema` tool tells the agent so.
* Instead, `lid_second` and `lid_second_score` give the runner-up language in
  FineWeb2's own language-ID distribution (`top_langs`), which every FineWeb2
  language ships.
* `sentence_lid` uses Lingua, which covers 75 languages (87 FineWeb2
  configurations). For other languages it adds a note that its line labels are
  unreliable.

## Reproducing the Slovak results

The analysis needs only Python and the corpus, and recomputes every number from
the released trajectories. Re-running the agent needs the
[Claude Code CLI](https://www.anthropic.com/claude-code) with credentials.
`scripts/reproduce.sh` runs everything and skips agent runs whose logs already
exist, so a reader without credentials still reproduces all results.

```bash
uv sync
uv run python scripts/download_shards.py           # 63 GB from the Hub
uv run python -c "from src.corpusaudit.db import build; build()"   # ~4 min
scripts/run_agent.sh main 300 sonnet               # one audit run
uv run python scripts/run_baseline.py lid_disagree --budget 300
uv run python scripts/build_annotation.py          # blinded human package
uv run python scripts/annotate.py                  # native-speaker labels
uv run python scripts/analyze.py                   # every measurement
uv run python scripts/make_report.py               # out/REPORT.md
uv run python -m src.corpusaudit.testsuite         # both suites
uv run python scripts/apply_patches.py --candidates  # what a cleaned corpus loses
uv run python scripts/check_patch_effect.py        # does the patched corpus pass?
scripts/check_heldout.sh                           # the held-out split
uv run python scripts/check_cross_language.py --suite  # other FineWeb2 languages
uv run python scripts/check_temporal_stability.py  # the guards on new crawls
uv run python scripts/check_thresholds.py          # scope of the guard thresholds
uv run python scripts/check_experiment_integrity.py  # no taxonomy in the prompt, no extra tools
uv run python scripts/replay_trajectory.py         # do the logged trajectories reproduce?
uv run python scripts/measure_classification_cost.py  # cost of an LLM classifier instead
```

`out/REPORT.md` is the readable report of the audit, generated from
`out/analysis/`.

## Layout

```
src/corpusaudit/db.py          corpus adapter: DuckDB tables + derived metadata
src/corpusaudit/fineweb2.py    download and build any FineWeb2 language
src/corpusaudit/tools.py       the audit tool API (budgeted, logged, read-only)
src/corpusaudit/sqlguard.py    validates agent SQL; locks the connection
src/corpusaudit/mcp_server.py  exposes the tools to the agent over MCP
src/corpusaudit/prompt.py      the agent prompt for the audited language
src/corpusaudit/testsuite.py   the test runner
src/corpusaudit/lid.py         line-level language identification
prompts/                       agent and baseline prompts
tests/slk_Latn/                the Slovak tests found by the agent
tests/metadata/                language-neutral invariants
out/runs/<run>/                trajectory, findings and cost of each agent run
out/baselines/<strategy>/      the four static baselines
out/annotation/                blinded package, guidelines, labels
out/adjudication/              candidate groups and verdicts
out/analysis/                  every measurement behind the paper
scripts/                       agent and baseline runs, analysis, checks
selftest/                      the self-test (no data needed)
```

## Two kinds of test

* **Prevalence guards** (`tests/slk_Latn/`) say a slice must not grow in a
  future release: `prevalence <= 1.2x` the measured value. The bound is meant
  for corpus-wide evaluation; on a single crawl a guard can trip because of
  that crawl's make-up (`scripts/check_thresholds.py`). Each test carries the
  agent's evidence, the exact prevalence and the human validation.
* **Invariants** (`tests/metadata/`) say a condition never occurs. Two fail on
  Slovak FineWeb2: 10,691,128 documents (40.4%) have `language_score > 1.0`,
  and 13 document ids occur twice. A failing test is a live defect, not a broken
  harness.

A test is a YAML file; `scope: any` marks a language-neutral one:

```yaml
id: firebase_content_farm_spam
scope: slk_Latn
description: Machine-generated content-farm pages on random Firebase subdomains
selector: domain LIKE '%.firebaseapp.com' OR domain LIKE '%.web.app'
assertion: prevalence <= 0.06384940
```

Every test needs `id`, `scope`, `description`, `selector` and `assertion`.
Anything else is reported `MALFORMED` and the runner exits 2. Any directory
under `tests/` is found automatically.

## Other corpora

Write one adapter that produces the `meta` and `docs` tables with the same
column names and point `AUDIT_DERIVED` at it; the tools, the agent and the test
runner then work unchanged. For FineWeb2-shaped Parquet, `db.build()` is that
adapter: absent optional columns become NULL, and tests that need them are
reported `unmeasured` instead of passing.

## Changes since the paper's runs

The trajectories in `out/` were recorded with the code as it was for the
paper. Since then:

* A SQL guard validates agent SQL on DuckDB's parse tree. Free aggregate
  queries may use `text` only inside functions that return a number or a
  boolean, so they can no longer return document text without spending
  inspections. `scripts/replay_trajectory.py` reports logged calls the guard
  now refuses separately.
* The FineWeb2 runner, the `lid_second` columns, the `schema` note on empty
  columns, `sentence_lid` over all Lingua languages, findings scoped to the
  audited corpus, and the prompt for other languages were added. For the
  Slovak corpus the prompt is unchanged.

## Citation

```bibtex
@misc{suppa2026agentdebugwebcorpus,
  title         = {Can an Agent Debug a Web Corpus? Agentic Auditing of Slovak {FineWeb2}},
  author        = {{\v{S}}uppa, Marek and Vykopal, Ivan and Kop{\v{c}}an, Jaroslav},
  year          = {2026},
  eprint        = {2610.31636},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2610.31636}
}
```

## Licence

* **Code** (`src/`, `scripts/`, `selftest/`): MIT, see `LICENSE`.
* **Our data** (agent findings and trajectories as data, human labels,
  adjudication, analysis outputs, tests): Open Data Commons Attribution License
  (ODC-By) v1.0.
* **Document excerpts** in `out/` (tool results, baseline samples, the
  annotation package) come from FineWeb2 and its Slovak redistribution
  [`ivykopal/fineweb2-slovak`](https://huggingface.co/datasets/ivykopal/fineweb2-slovak).
  They remain under ODC-By v1.0 and
  [Common Crawl's terms of use](https://commoncrawl.org/terms-of-use); the
  underlying web pages belong to their owners. Like the corpus, they include
  adult content and spam. Email addresses are redacted.
