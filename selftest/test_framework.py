#!/usr/bin/env python
"""Self-tests for the audit framework.

Two kinds of check:

* unit checks on the pieces where a silent mistake changes reported numbers
  (selector classification, Wilson intervals, inspection-budget accounting);
* an end-to-end check that builds a *synthetic* corpus in the adapter's schema,
  runs the tool API and the YAML test runner against it, and verifies the
  reported prevalences. This is also the smallest worked example of adding a new
  corpus, so it doubles as documentation for another language community.

    .venv/bin/python -m selftest.test_framework
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import duckdb  # noqa: E402
import yaml  # noqa: E402

from src.corpusaudit.selectors import needs_text  # noqa: E402
from src.corpusaudit.testsuite import evaluate, run  # noqa: E402
from src.corpusaudit.tools import AGENT_COLUMNS, AuditSession, wilson  # noqa: E402

FAILURES: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + label + (f"  [{detail}]" if detail else ""))
    if not cond:
        FAILURES.append(f"{label} {detail}".strip())


def about(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


# ---------------------------------------------------------------- unit checks
def test_needs_text() -> None:
    print("needs_text")
    check(needs_text("regexp_matches(text, 'x')"), "regex over text is text-dependent")
    check(needs_text("length(text) > 100"), "length(text) is text-dependent")
    # the regression that motivated this file: 'fasttext' contains 'text'
    check(not needs_text("fasttext = 'cs'"), "fasttext is NOT text-dependent")
    check(not needs_text("fasttext='cs' AND langdetect='cs' AND lingua_top='cs'"),
          "three LID columns are NOT text-dependent")
    check(not needs_text("n_bad_words >= 3 AND domain LIKE '%.sk'"),
          "metadata-only selector is not text-dependent")


def test_wilson() -> None:
    print("wilson")
    lo, hi = wilson(0, 0)
    check((lo, hi) == (0.0, 1.0), "empty sample gives the whole interval")
    lo, hi = wilson(5, 10)
    check(lo < 0.5 < hi, "interval brackets the point estimate")
    lo1, _ = wilson(50, 100)
    lo2, _ = wilson(500, 1000)
    check(lo2 > lo1, "more evidence tightens the interval")
    lo, hi = wilson(10, 10)
    check(hi == 1.0 or about(hi, 1.0, 1e-9), "all-positive sample reaches 1.0")


# ------------------------------------------------------- synthetic corpus e2e
def synthetic_corpus(tmp: pathlib.Path) -> str:
    """Write a tiny corpus in the adapter schema: 1000 docs, 100 of them junk."""
    con = duckdb.connect()
    con.execute("""
        create table docs as
        select
            'doc' || i as id,
            case when i % 10 = 0
                 then 'BUY CHEAP PILLS ' || i || ' click here click here'
                 else 'Toto je normálny slovenský text číslo ' || i
                       || ', ktorý obsahuje niekoľko viet.' end as text,
            'https://' || (case when i % 10 = 0 then 'spam' || i || '.web.app'
                                else 'example' || (i % 7) || '.sk' end) || '/page' as url,
            case when i % 10 = 0 then 'spam' || i || '.web.app'
                 else 'example' || (i % 7) || '.sk' end as domain,
            'CC-MAIN-2024-18' as dump,
            '2024-04-01T00:00:00Z' as date,
            'slk' as language,
            case when i % 10 = 0 then 0.99 else 0.95 end as language_score,
            1 + (i % 3) as minhash_cluster_size,
            '{"slk_Latn_score": 0.95}' as top_langs,
            case when i % 10 = 0 then 'en' else 'sk' end as fasttext,
            'sk' as langdetect,
            '[(''sk'', 1.0)]' as lingua,
            'sk' as lingua_top,
            1.0 as lingua_top_p,
            case when i % 10 = 0 then 4 else 0 end as n_bad_words,
            length(text) as n_chars,
            30 as n_words,
            1 as n_lines
        from range(1, 1001) t(i)
    """)
    out = tmp / "derived"
    out.mkdir(parents=True, exist_ok=True)
    con.execute(f"copy (select * from docs) to '{out / 'docs.parquet'}' (format parquet)")
    con.execute(
        f"copy (select * exclude (text) from docs) to '{out / 'meta.parquet'}' (format parquet)")
    return str(out)


def test_budget_accounting(tmp: pathlib.Path) -> None:
    """Per-call charges must sum to the final count, including on re-reads."""
    print("budget accounting in the trajectory")
    import json as _json

    from src.corpusaudit.db import open_corpus
    from src.corpusaudit.tools import AGENT_COLUMNS, AuditSession

    derived = synthetic_corpus(tmp / "budget")
    corpus = open_corpus(derived)
    con = corpus.con
    con.execute("create view corpus as select text, top_langs, lingua, "
                + ", ".join(AGENT_COLUMNS) + " from docs")
    con.execute("create view corpus_meta as select top_langs, lingua, "
                + ", ".join(AGENT_COLUMNS) + " from meta")
    log = tmp / "budget.jsonl"
    s = AuditSession(con=con, n_total=corpus.n_total, n_sample=corpus.n_sample,
                     budget=10, log_path=str(log), findings_dir=str(tmp / "bf"))

    s.sample_documents("true", n=4, seed=1)
    s.sample_documents("true", n=4, seed=1)          # same documents again
    ids = sorted(s.inspected)
    s.inspect_document(ids[0])                        # already charged
    s.sample_documents("true", n=8, seed=2)           # some new, some seen
    s.aggregate("select count(*) as n from corpus_meta")

    recs = [_json.loads(line) for line in open(log)]
    charged = sum(r["inspections_spent"] for r in recs)
    final = max(r["inspections_used"] for r in recs)
    check(charged == final, "per-call charges sum to the final count",
          f"{charged} vs {final}")
    check(final == len(s.inspected), "the counter equals the charged set")
    check(all(r["inspections_spent"] >= 0 for r in recs), "no charge is negative")
    check(recs[1]["inspections_spent"] == 0, "re-sampling the same documents is free")
    check(final <= 10, "the budget is never exceeded")
    counters = [r["inspections_used"] for r in recs]
    check(counters == sorted(counters), "the counter never decreases")


def test_redaction() -> None:
    """Third-party addresses go; the corpus's placeholders stay; it is idempotent."""
    print("pii redaction")
    from src.corpusaudit.anon import REDACTED, has_real_email, redact_obj, redact_pii

    # RFC 2606 reserved: unmistakably fake, and nobody's address
    real = "Kontakt: niekto@firma.invalid, obchod@druha-firma.invalid"
    holder = "Napiste na email@example.com alebo firstname.lastname@example.org"
    check(not has_real_email(redact_pii(real)), "a real address is removed")
    check(redact_pii(real).count(REDACTED) == 2, "each address is replaced once")
    check(redact_pii(holder) == holder, "corpus placeholders are untouched")
    once = redact_pii(real + " " + holder)
    check(redact_pii(once) == once, "redaction is idempotent, so replay can compare")
    check(redact_pii("no addresses here") == "no addresses here", "plain text is unchanged")
    check(redact_obj({"a": [real]})["a"][0].endswith(REDACTED),
          "redaction reaches inside nested structures")
    check(not has_real_email("mail@example.com"), "a placeholder is not a real address")
    # the tool boundary must apply it: every row-returning tool goes through _fmt
    from src.corpusaudit.tools import AuditSession

    check(has_real_email(real) and not has_real_email(AuditSession._fmt([{"t": real}])),
          "the tools' row formatter redacts")


def test_portability(tmp: pathlib.Path) -> None:
    """A release that ships fewer columns must degrade, not lie.

    Builds two raw shards in the adapter's *input* schema -- one with the
    auxiliary LID columns of the Slovak redistribution, one with only what
    upstream FineWeb2 ships -- and checks that the suite reports Slovak tests as
    unmeasurable or out of scope rather than passing them vacuously.
    """
    print("portability to a release with fewer columns")
    from src.corpusaudit.db import OPTIONAL_COLUMNS, build, derived_sql, shard_columns
    from src.corpusaudit.testsuite import in_scope, run, unavailable_columns, unmeasurable_with
    from src.corpusaudit.db import open_corpus

    con = duckdb.connect()
    rich = tmp / "raw_rich.parquet"
    poor = tmp / "raw_poor.parquet"
    con.execute(f"""
        copy (select
            'd' || i as id,
            'Text číslo ' || i as text,
            'https://site' || (i % 5) || '.sk/p' || i as url,
            'CC-MAIN-2024-18' as dump, '2024-04-01T00:00:00Z' as date,
            'slk' as language, 'Latn' as language_script,
            case when i % 4 = 0 then 1.00001 else 0.9 end as language_score,
            1 as minhash_cluster_size,
            '{{"slk_Latn_score": 0.9}}' as top_langs,
            'sk' as fasttext, 'sk' as langdetect, '[(''sk'', 1.0)]' as lingua,
            [] as bad_words
        from range(1, 101) t(i)) to '{rich}' (format parquet)""")
    con.execute(f"""
        copy (select id, text, url, dump, date, language, language_score,
                     minhash_cluster_size
              from read_parquet('{rich}')) to '{poor}' (format parquet)""")

    check(shard_columns(str(rich)) >= set(OPTIONAL_COLUMNS),
          "the rich shard ships every optional column")
    check(not (shard_columns(str(poor)) & set(OPTIONAL_COLUMNS)),
          "the poor shard ships none of them")
    check("cast(null as varchar) as fasttext" in derived_sql(set()),
          "absent columns are materialised as NULL, not omitted")

    for name, shard in (("rich", rich), ("poor", poor)):
        build(str(shard), str(tmp / f"derived_{name}"), threads=2)
        corpus = open_corpus(str(tmp / f"derived_{name}"))
        check(corpus.n_total == 100, f"{name} release builds 100 documents")
        missing = unavailable_columns(corpus)
        if name == "rich":
            check(not missing, "no columns are reported missing when all are shipped")
        else:
            check(missing == {"fasttext", "langdetect", "top_langs", "lingua", "bad_words"},
                  "every unshipped column is detected as unavailable")
            check(unmeasurable_with("fasttext='cs' AND langdetect='cs'", missing)
                  == {"fasttext", "langdetect"},
                  "a selector's unmeasurable dependencies are named")
            check(not unmeasurable_with("domain LIKE '%.web.app'", missing),
                  "a metadata-only selector stays measurable")

    check(in_scope("any", "cym") and in_scope("slk_Latn", "slk_Latn"),
          "language-neutral tests run anywhere; scoped tests run in scope")
    check(not in_scope("slk_Latn", "cym"), "a scoped test does not run out of scope")

    # the suite itself, on the poor release: Slovak text tests must not pass
    rep = tmp / "poor_report.json"
    run(["tests/slk_Latn", "tests/metadata"], str(tmp / "derived_poor"), str(rep))
    got = json.loads(rep.read_text())
    ran = {t["id"]: t["status"] for t in got["tests"]}
    unmeasured = {u["id"] for u in got["unmeasurable"]}
    check(bool(unmeasured), "tests depending on absent columns are marked unmeasurable")
    check(not (unmeasured & set(ran)), "an unmeasurable test is never also reported as run")
    for tid in unmeasured:
        check(ran.get(tid) != "PASS", f"{tid} does not pass vacuously")
    check(ran.get("language_score_not_a_probability") == "FAIL",
          "the language-neutral invariant still catches the planted defect")


def test_end_to_end(tmp: pathlib.Path) -> None:
    print("end-to-end on a synthetic corpus")
    from src.corpusaudit.db import open_corpus

    derived = synthetic_corpus(tmp)
    corpus = open_corpus(derived)
    check(corpus.n_total == 1000 and corpus.n_sample == 1000, "adapter exposes 1000 documents")

    con = corpus.con
    con.execute("create view corpus as select text, top_langs, lingua, "
                + ", ".join(AGENT_COLUMNS) + " from docs")
    con.execute("create view corpus_meta as select top_langs, lingua, "
                + ", ".join(AGENT_COLUMNS) + " from meta")

    session = AuditSession(con=con, n_total=corpus.n_total, n_sample=corpus.n_sample,
                           budget=5, log_path=str(tmp / "traj.jsonl"),
                           findings_dir=str(tmp / "findings"))

    # aggregation is free
    out = session.aggregate("select count(*) as n from corpus_meta where n_bad_words >= 3")
    check(json.loads(out)[0]["n"] == 100, "aggregate finds the 100 planted junk documents")
    check(session.remaining() == 5, "aggregation costs no inspection budget")

    # inspection is budgeted, and charged once per distinct document
    session.sample_documents("n_bad_words >= 3", n=3)
    check(session.remaining() == 2, "sampling three documents costs three inspections")
    ids = sorted(session.inspected)
    session.inspect_document(ids[0])
    check(session.remaining() == 2, "re-reading a seen document is not charged again")
    session.sample_documents("true", n=10)
    check(session.remaining() == 0, "budget cannot be overspent")

    # prevalence: exact on metadata, and refused write attempts
    stats = json.loads(session.run_detector("junk", "n_bad_words >= 3"))
    check(stats["n_matched"] == 100 and about(stats["prevalence"], 0.1),
          "run_detector measures exact prevalence")
    check(stats["exact_on_full_corpus"], "metadata-only selector is measured exactly")
    try:
        session.aggregate("drop table meta")
        check(False, "write statements are refused")
    except ValueError:
        check(True, "write statements are refused")

    # a finding round-trips into an executable YAML test
    session.save_finding(
        finding_id="planted_spam",
        description="Planted spam documents on *.web.app hosts.",
        selector="domain LIKE '%.web.app'",
        evidence="Synthetic corpus with 100 planted spam documents.",
        expected_precision=1.0,
        assertion="prevalence <= 0.05",
    )
    path = tmp / "findings" / "planted_spam.yaml"
    check(path.exists(), "save_finding writes a YAML test")
    test = yaml.safe_load(open(path))
    check(about(test["evidence"]["prevalence"], 0.1), "test records the measured prevalence")

    got = evaluate(con, test["selector"], corpus.n_total, corpus.n_sample)
    check(got["n_matched"] == 100, "test runner reproduces the finding's count")

    # the runner fails a violated assertion and passes a satisfied one
    rc = run(str(tmp / "findings"), derived)
    check(rc == 1, "runner exits non-zero when an assertion is violated")
    test["assertion"] = "prevalence <= 0.2"
    path.write_text(yaml.safe_dump(test, allow_unicode=True, sort_keys=False))
    check(run(str(tmp / "findings"), derived) == 0, "runner exits zero when assertions hold")

    # the trajectory is replayable: every call logged, budget monotone
    recs = [json.loads(line) for line in open(tmp / "traj.jsonl")]
    tools_called = [r["tool"] for r in recs]
    check(len(recs) == 8, "every tool call is logged, including the internal one")
    check("refused" in tools_called, "a refused query is logged, not silently dropped")
    check(tools_called[-1] == "save_finding", "the finding is the last logged step")
    used = [r["inspections_used"] for r in recs]
    check(used == sorted(used) and max(used) <= 5, "logged budget is monotone and capped")


def test_mcp_dispatch() -> None:
    """The MCP layer must expose exactly the declared tools and nothing else."""
    print("mcp dispatch")
    from src.corpusaudit.mcp_server import TOOL_NAMES, TOOLS

    check(len(TOOLS) == 11, "eleven tools are declared", str(len(TOOLS)))
    check(TOOL_NAMES == {n for n, _, _ in TOOLS}, "tool-name set matches the declarations")
    for internal in ("_log", "_check", "log_error", "remaining", "con"):
        check(internal not in TOOL_NAMES, f"internal `{internal}` is not callable as a tool")
    from src.corpusaudit.tools import AuditSession as _S

    missing = [n for n in TOOL_NAMES if not callable(getattr(_S, n, None))]
    check(not missing, "every declared tool is implemented", ",".join(missing))



def test_default_suites_finds_a_new_community(tmp: pathlib.Path) -> None:
    """A second language community's tests must be discovered, not ignored.

    The default run used to name ``tests/slk_Latn`` explicitly, so a test added
    under ``tests/ces_Latn`` produced no output at all -- indistinguishable from
    having no defects. Scope filtering is what decides whether it executes; the
    default suite list only decides whether anyone hears about it.
    """
    from src.corpusaudit.testsuite import default_suites

    cwd = os.getcwd()
    os.chdir(tmp)
    try:
        (tmp / "tests" / "slk_Latn").mkdir(parents=True)
        (tmp / "tests" / "slk_Latn" / "a.yaml").write_text("id: a\n")
        assert default_suites() == ["tests/slk_Latn"], default_suites()
        (tmp / "tests" / "ces_Latn").mkdir()
        (tmp / "tests" / "ces_Latn" / "b.yaml").write_text("id: b\n")
        found = default_suites()
        assert found == ["tests/ces_Latn", "tests/slk_Latn"], found
        # a directory with no test files is not a suite
        (tmp / "tests" / "notes").mkdir()
        (tmp / "tests" / "notes" / "readme.md").write_text("x\n")
        assert "tests/notes" not in default_suites()
        print("ok   a second community's tests are discovered by default")
    finally:
        os.chdir(cwd)


def test_label_vocabulary_is_enforced(tmp: pathlib.Path) -> None:
    """Labels outside the vocabulary must raise, not read as "no defects".

    Every value in ``labels.csv`` that is not a known label counts as
    non-defective, so a hand edit or a tool writing the keypress digit instead of
    the word produces precision 0.00 with a tight Wilson interval -- the most
    load-bearing number in the paper, silently wrong in the safest-looking
    direction.
    """
    import csv as _csv
    from scripts.analyze import human_tables

    d = tmp / "annotation"
    d.mkdir(parents=True)

    def write(rows: list[tuple[str, str, str]]) -> None:
        with open(d / "provenance.csv", "w", newline="") as fh:
            w = _csv.writer(fh); w.writerow(["item_id", "slice"])
            for i, _, _ in rows: w.writerow([i, "s1"])
        with open(d / "labels.csv", "w", newline="") as fh:
            w = _csv.writer(fh); w.writerow(["item_id", "language", "quality"])
            for r in rows: w.writerow(r)

    write([("A1", "cs", "junk"), ("A2", "sk", "good")])
    prov, labels = human_tables(str(d))
    assert len(labels) == 2, labels

    for bad in (("A3", "3", "junk"), ("A4", "cs", "1"), ("A5", "czech", "junk")):
        write([("A1", "cs", "junk"), bad])
        try:
            human_tables(str(d))
        except SystemExit as e:
            assert "vocabulary" in str(e), str(e)
        else:
            raise AssertionError(f"accepted an out-of-vocabulary label: {bad}")

    # a labelled item with no provenance row would be dropped by the join
    write([("A1", "cs", "junk")])
    with open(d / "labels.csv", "a", newline="") as fh:
        _csv.writer(fh).writerow(["ZZZ", "cs", "junk"])
    try:
        human_tables(str(d))
    except SystemExit as e:
        assert "provenance" in str(e), str(e)
    else:
        raise AssertionError("accepted a label with no provenance row")
    print("ok   label vocabulary and the provenance join are enforced")


def test_annotation_tool_contract(tmp: pathlib.Path) -> None:
    """Drive the real annotation tool with keystrokes.

    This is the one component a person operates for an hour, and every earlier
    rehearsal wrote ``labels.csv`` directly, bypassing it. What must hold: it
    writes the label *words* the analysis expects (not the keypress digits), ``s``
    skips without recording, ``q`` stops cleanly, an interrupted document records
    nothing, and a resumed run offers exactly the undone items -- including the
    ones that were skipped.
    """
    import csv as _csv
    import subprocess as _sp

    d = tmp / "ann"
    d.mkdir(parents=True)
    ids = [f"A{i:04d}" for i in range(1, 6)]
    with open(d / "items.csv", "w", newline="") as fh:
        w = _csv.writer(fh); w.writerow(["item_id", "text"])
        for i in ids: w.writerow([i, f"text of {i}"])
    with open(d / "provenance.csv", "w", newline="") as fh:
        w = _csv.writer(fh); w.writerow(["item_id", "slice"])
        for i in ids: w.writerow([i, "s1"])
    (d / "GUIDELINES.md").write_text("# guidelines\n")

    def drive(keys: str, *extra: str) -> str:
        r = _sp.run([sys.executable, "scripts/annotate.py", "--dir", str(d), *extra],
                    input=keys, capture_output=True, text=True,
                    cwd=pathlib.Path(__file__).resolve().parents[1])
        assert r.returncode == 0, r.stderr[-400:]
        return r.stdout

    def rows() -> list[dict]:
        return list(_csv.DictReader(open(d / "labels.csv")))

    # label one, skip one, label one, quit
    drive("1\n1\n" "s\n" "3\n3\n" "q\n")
    got = rows()
    assert [r["item_id"] for r in got] == ["A0001", "A0003"], got
    assert got[0] == {"item_id": "A0001", "language": "sk", "quality": "good"}, got[0]
    assert got[1]["language"] == "cs" and got[1]["quality"] == "junk", got[1]

    # the skipped item is offered again on resume, and is offered first
    out = drive("q\n")
    assert "A0002" in out.split("language:")[0], out[:400]

    # a typo and an empty line re-prompt rather than recording garbage.
    # Rows are addressed by item, not by position: the tool keeps one row per
    # document so that a re-judgement can replace it, which leaves file order set by
    # the item list rather than by when each judgment happened.
    drive("\nx\n2\n2\nq\n")
    by_id = {r["item_id"]: r for r in rows()}
    assert by_id["A0002"] == {"item_id": "A0002", "language": "sk-pred",
                              "quality": "noisy"}, by_id["A0002"]
    assert len(by_id) == len(rows()), f"duplicate rows: {rows()}"

    # interrupted between the two questions: nothing is written
    n = len(rows())
    drive("1\n")
    assert len(rows()) == n, "a partial judgment was recorded"

    # every value the tool writes is one the analysis understands
    from scripts.analyze import DEFECT_LANG, DEFECT_QUAL
    langs = {"sk", "sk-pred", "cs", "mix", "other", "?"}
    assert DEFECT_LANG <= langs and DEFECT_QUAL <= {"good", "noisy", "junk", "?"}
    assert all(r["language"] in langs for r in rows()), rows()

    # --limit caps the session
    drive("1\n1\n1\n1\n1\n1\n", "--limit", "1")
    assert len(rows()) == n + 1, rows()

    # Re-judging an already-labelled document. Merging an earlier annotation pass
    # into labels.csv once made every listed item "already labelled", so this mode
    # silently had nothing to offer and the highest-value human work dead-ended at
    # its first command. It must present the document, replace the row in place, and
    # resume where it stopped.
    before = {r["item_id"]: r for r in rows()}
    target = "A0001"
    assert before[target]["language"] == "sk", before[target]
    (d / "recode.txt").write_text(f"{target}\n{ids[1]}\n")
    out = drive("3\n3\n" "q\n", "--only-items", str(d / "recode.txt"))
    assert target in out.split("language:")[0], out[:400]
    assert "re-judged" in out, out[:200]
    after = {r["item_id"]: r for r in rows()}
    assert after[target] == {"item_id": target, "language": "cs",
                             "quality": "junk"}, after[target]
    assert len(after) == len(before), f"a re-judgement duplicated a row: {rows()}"
    assert (d / "recoded.txt").read_text().split() == [target]
    # the second run offers the next item on the list, not the one just re-judged
    out = drive("q\n", "--only-items", str(d / "recode.txt"))
    assert ids[1] in out.split("language:")[0], out[:400]
    assert target not in out.split("language:")[0], out[:400]
    # the earlier label is never shown: a re-judgement stays as blind as the first
    assert "sk-pred" not in out.split("language:")[0], out[:400]
    print("ok   the annotation tool honours its contract under real keystrokes")


def test_adjudication_vocabulary_is_enforced(tmp: pathlib.Path) -> None:
    """A typo in the decision sheet must not silently mean "not yet decided".

    ``decisions.csv`` is hand-edited. A misspelled verdict used to be skipped, so
    an approved finding would ship as ``candidate`` and the paper would understate
    its own validation; a mistyped group id became an override for a finding that
    does not exist. Both now refuse to load. An *empty* verdict stays pending,
    because that is how the sheet ships.
    """
    import csv as _csv
    from src.corpusaudit.adjudication import VALID, load_decisions

    d = tmp / "adj"
    d.mkdir(parents=True)
    with open(d / "groups.csv", "w", newline="") as fh:
        w = _csv.writer(fh); w.writerow(["finding", "group"])
        w.writerow(["f_one", "G01"]); w.writerow(["f_two", "G01"])
        w.writerow(["f_three", "G02"])

    def sheet(rows: list[tuple[str, str, str]]) -> None:
        with open(d / "decisions.csv", "w", newline="") as fh:
            w = _csv.writer(fh); w.writerow(["group", "decision", "note"])
            for r in rows: w.writerow(r)

    # empty verdicts are pending, not errors
    sheet([("G01", "", ""), ("G02", "", "")])
    dec, notes, group_of = load_decisions(str(d))
    assert dec == {} and len(group_of) == 3, (dec, group_of)

    # a group verdict reaches every member; a finding-level row overrides it
    sheet([("G01", "approve", "ok"), ("f_two", "reject", "not this one")])
    dec, notes, _ = load_decisions(str(d))
    assert dec == {"f_one": "approve", "f_two": "reject"}, dec
    assert notes["f_two"] == "not this one", notes

    # every accepted word is honoured
    for word in sorted(VALID):
        sheet([("G02", word, "")])
        assert load_decisions(str(d))[0] == {"f_three": word}

    # a misspelling refuses to load rather than reading as pending
    for bad in ("approved", "aprove", "yes", "APPROVE!"):
        sheet([("G01", bad, "")])
        try:
            load_decisions(str(d))
        except SystemExit as e:
            assert "outside" in str(e), str(e)
        else:
            raise AssertionError(f"accepted a misspelled verdict: {bad}")

    # a key that is neither a group nor a finding is a typo, not an override
    sheet([("GO1", "approve", "")])
    try:
        load_decisions(str(d))
    except SystemExit as e:
        assert "neither a group nor a finding" in str(e), str(e)
    else:
        raise AssertionError("accepted a phantom group id")
    print("ok   the adjudication sheet refuses typos instead of reading them as pending")


def test_malformed_tests_never_pass(tmp: pathlib.Path) -> None:
    """A broken test file must be reported, never counted as passing.

    This is the centre of the "pytest for web corpora" claim. Before validation, a
    file whose ``assertion:`` key was misspelled ``assertions:`` was reported
    ``no-assert``, excluded from the failure count, and the suite exited 0 -- a
    contributor's typo produced a green suite. A missing ``selector`` crashed with
    a bare ``KeyError`` and an unparseable one dumped a DuckDB traceback, so a
    single bad contribution hid every other result.
    """
    from src.corpusaudit.testsuite import (OPTIONAL_FIELDS, REQUIRED_FIELDS,
                                           validate_test)

    good = {"id": "t", "scope": "slk_Latn", "description": "d",
            "selector": "language_score < 0.5", "assertion": "prevalence <= 0.01"}
    assert validate_test(good, "p") == []
    assert validate_test({**good, **{k: None for k in OPTIONAL_FIELDS}}, "p") == []

    for field in sorted(REQUIRED_FIELDS):
        missing = {k: v for k, v in good.items() if k != field}
        problems = validate_test(missing, "p")
        assert any(field in x for x in problems), (field, problems)

    # a misspelling is an unknown field, and that is exactly how it is caught
    typo = {**{k: v for k, v in good.items() if k != "assertion"},
            "assertions": "prevalence <= 0.01"}
    problems = validate_test(typo, "p")
    assert any("unknown field" in x and "assertions" in x for x in problems), problems

    # an assertion outside the permitted grammar is refused
    for bad in ("__import__('os').system('true')", "prevalence = 0.01", "open('x')"):
        assert validate_test({**good, "assertion": bad}, "p"), bad

    assert validate_test("not a mapping", "p")
    assert validate_test(None, "p")
    print("ok   a malformed test is reported, never counted as passing")


def test_tools_distinguish_error_from_empty(tmp: pathlib.Path) -> None:
    """A broken query must not look like an honest "nothing matches".

    This is the validity of the research instrument, not a convenience: if a
    malformed condition returned zero rows, the agent would conclude the corpus
    contains no such documents and record a false negative. Errors are surfaced;
    a genuinely empty result says so.
    """
    import duckdb

    from src.corpusaudit.tools import AGENT_COLUMNS, AuditSession

    con = duckdb.connect()
    cols = ", ".join(f"null as {c}" for c in AGENT_COLUMNS
                     if c not in ("id", "domain", "language_score"))
    con.execute(
        "create view docs as select 'i1' as id, 'a.sk' as domain, "
        f"0.9 as language_score, 'text' as text, '{{}}' as top_langs, "
        f"'{{}}' as lingua, {cols}")
    con.execute("create view meta as select * exclude (text) from docs")
    con.execute("create view corpus as select text, top_langs, lingua, "
                + ", ".join(AGENT_COLUMNS) + " from docs")
    con.execute("create view corpus_meta as select top_langs, lingua, "
                + ", ".join(AGENT_COLUMNS) + " from meta")

    s = AuditSession(con=con, n_total=1, n_sample=1, budget=10,
                     log_path=str(tmp / "traj.jsonl"),
                     findings_dir=str(tmp / "findings"))

    # a genuinely empty answer is reported as empty, and is not an error
    empty = s.sample_documents("domain = 'no-such-host.example'", 3)
    assert "no rows" in str(empty).lower(), empty

    # a malformed condition raises, so the server marks it isError rather than
    # handing the agent an empty result
    for bad in ("bogus_column = 1", "language_score < ", "domain ==== 'x'"):
        try:
            s.sample_documents(bad, 3)
        except Exception:
            pass
        else:
            raise AssertionError(f"a malformed condition returned quietly: {bad}")

    # the same must hold for the detector path, which drives the findings
    try:
        s.run_detector("x", "bogus_column = 1")
    except Exception:
        pass
    else:
        raise AssertionError("run_detector swallowed an unknown column")
    print("ok   a broken query is an error, never an empty result")


def test_no_latex_escape_traps(tmp: pathlib.Path) -> None:
    """No checker may compare LaTeX against a string Python has mangled.

    In a non-raw Python string a backslash before certain letters is an escape:
    ``"\\validatedtrue"`` written without the doubling is a **vertical tab** followed
    by ``alidatedtrue``, so a check comparing it against the paper can never fire.
    Where the escape is merely *invalid* (``\\d``), the string survives by luck.

    Two rules, both mechanical: nothing in the project may contain an invalid escape
    sequence, and no string constant compared against the paper may contain a
    control character.
    """
    import ast as _ast
    import glob as _glob
    import warnings as _warnings

    root = pathlib.Path(__file__).resolve().parents[1]
    files = sorted(_glob.glob(str(root / "scripts" / "*.py"))) + \
        sorted(_glob.glob(str(root / "selftest" / "*.py"))) + \
        sorted(_glob.glob(str(root / "src" / "corpusaudit" / "*.py")))
    assert files, "no sources found"

    bad_escapes = []
    for f in files:
        src = pathlib.Path(f).read_text()
        with _warnings.catch_warnings():
            _warnings.simplefilter("error", SyntaxWarning)
            try:
                compile(src, f, "exec")
            except SyntaxWarning as exc:
                bad_escapes.append(f"{pathlib.Path(f).name}: {exc}")
    assert not bad_escapes, "invalid escape sequence(s): " + "; ".join(bad_escapes)

    # a string compared against the paper must survive Python's lexer intact
    CONTROL = "".join(chr(c) for c in list(range(0, 9)) + [11, 12] + list(range(14, 32)))
    mangled = []
    for f in files:
        tree = _ast.parse(pathlib.Path(f).read_text())
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.Compare):
                continue
            names = {n.id for n in _ast.walk(node) if isinstance(n, _ast.Name)}
            if not ({"tex", "body", "ptex", "flat"} & names):
                continue
            for sub in _ast.walk(node):
                if isinstance(sub, _ast.Constant) and isinstance(sub.value, str):
                    if any(ch in sub.value for ch in CONTROL):
                        mangled.append(f"{pathlib.Path(f).name}:{sub.lineno} {sub.value!r}")
    assert not mangled, "control character in a string compared to LaTeX: " + \
        "; ".join(mangled)
    print(f"ok   no LaTeX escape traps in {len(files)} source files")


def test_second_coder_agreement(tmp: pathlib.Path) -> None:
    """A second coder yields kappa; the primary pass still sets precision.

    Whether one annotator suffices is a judgment call, but the machinery must not
    be the reason it cannot be answered: before this, `labels.csv` was hardcoded and
    a second pass had nowhere to go.
    """
    import csv as _csv

    from scripts.analyze import agreement

    d = tmp / "ann-second"
    d.mkdir(parents=True, exist_ok=True)
    ids = [f"A{i:03d}" for i in range(20)]
    with open(d / "provenance.csv", "w", newline="") as fh:
        w = _csv.writer(fh); w.writerow(["item_id", "slice"])
        for i in ids: w.writerow([i, "czech_text_mislabeled_as_slovak"])

    def write(name: str, langs: list[str]) -> None:
        with open(d / name, "w", newline="") as fh:
            w = _csv.writer(fh); w.writerow(["item_id", "language", "quality"])
            for i, lang in zip(ids, langs): w.writerow([i, lang, "good"])

    # no second coder: nothing to report, and that is not an error
    write("labels.csv", ["cs"] * 10 + ["sk"] * 10)
    assert agreement(str(d)) is None

    # 16 of 20 defect judgments agree -> kappa 0.60 by hand
    write("labels.second.csv", ["cs"] * 8 + ["sk"] * 2 + ["sk"] * 8 + ["cs"] * 2)
    c = agreement(str(d))["coders"][0]
    assert c["n_shared"] == 20, c
    assert abs(c["defect_agreement"] - 0.8) < 1e-9, c
    assert abs(c["defect_kappa"] - 0.6) < 1e-9, c
    assert c["coder"] == "second", c

    write("labels.second.csv", ["cs"] * 10 + ["sk"] * 10)
    assert abs(agreement(str(d))["coders"][0]["defect_kappa"] - 1.0) < 1e-9

    # the vocabulary guard covers every coder's file, not just the primary
    write("labels.second.csv", ["3"] * 20)
    try:
        agreement(str(d))
    except SystemExit as e:
        assert "vocabulary" in str(e), str(e)
    else:
        raise AssertionError("a second coder's bad labels were accepted")
    print("ok   a second coder yields an agreement figure, validated like the first")


def test_agent_sql_cannot_escape(tmp: pathlib.Path) -> None:
    """Agent SQL reaches only the agent relations and never reads text for free.

    The inspection budget is the cost model of an audit: reading a document
    costs one inspection, aggregates are free. If a free tool returned document
    text, or any tool could read a file, the budget would be fiction. Each
    attack below worked against an earlier version of the tools.
    """
    print("agent sql cannot escape")
    from src.corpusaudit.db import open_corpus
    from src.corpusaudit.sqlguard import lock_down

    derived = synthetic_corpus(tmp / "escape")
    secret = tmp / "secret.txt"
    secret.write_text("reference audit: do not show the agent")
    corpus = open_corpus(derived)
    con = corpus.con
    con.execute("create view corpus as select text, top_langs, lingua, "
                + ", ".join(AGENT_COLUMNS) + " from docs")
    con.execute("create view corpus_meta as select top_langs, lingua, "
                + ", ".join(AGENT_COLUMNS) + " from meta")
    lock_down(con, derived)
    s = AuditSession(con=con, n_total=corpus.n_total, n_sample=corpus.n_sample,
                     budget=3, log_path=str(tmp / "escape.jsonl"),
                     findings_dir=str(tmp / "escape_findings"))

    def refused(label: str, call) -> None:
        try:
            out = call()
        except Exception:
            check(True, f"refused: {label}")
        else:
            check(False, f"refused: {label}", str(out)[:120])

    docs_file = os.path.join(os.path.abspath(derived), "docs.parquet")
    refused("file read in a free query",
            lambda: s.aggregate(f"select count(*) from read_text('{secret}')"))
    refused("file read inside a detector selector",
            lambda: s.run_detector("x", f"exists (select 1 from read_text('{secret}'))"))
    refused("raw parquet of the text table",
            lambda: s.aggregate(f"select count(*) from read_parquet('{docs_file}')"))
    refused("the unrestricted docs view", lambda: s.aggregate("select count(*) from docs"))
    refused("system catalogue",
            lambda: s.domain_stats("id in (select table_name from information_schema.tables)"))
    refused("environment", lambda: s.aggregate("select getenv('HOME')"))
    refused("re-enabling external access",
            lambda: s.aggregate("set enable_external_access=true"))
    refused("substr of text in a free query",
            lambda: s.aggregate("select substr(text, 1, 50) from corpus limit 1"))
    refused("grouped text prefixes in a free query",
            lambda: s.aggregate("select substr(text, 1, 120), count(*) from corpus group by 1"))
    refused("string_agg of text", lambda: s.aggregate("select string_agg(text, '') from corpus"))
    refused("text behind a CASE",
            lambda: s.aggregate("select case when contains(text, 'a') then text end from corpus"))
    refused("star over corpus", lambda: s.aggregate("select * from corpus limit 1"))
    refused("whole row by alias", lambda: s.aggregate("select c from corpus c limit 1"))
    refused("text through a cte",
            lambda: s.aggregate("with t as (select text as x from corpus) select x from t"))
    refused("condition that closes its parenthesis",
            lambda: s.sample_documents("true) union all select * from corpus where (true", 1))
    refused("condition with a trailing comment",
            lambda: s.sample_documents("true) --", 1))
    refused("seed used as an injection vector",
            lambda: s.sample_documents("true", 1, seed="0') union select 1 --"))
    try:
        con.execute(f"select * from read_text('{secret}')").fetchall()
    except Exception:
        check(True, "the locked connection itself cannot read the file")
    else:
        check(False, "the locked connection itself cannot read the file")

    ok = s.aggregate("select count(*) as n, avg(length(text)) as mean_len from corpus "
                     "where regexp_matches(text, 'a')")
    check('"n"' in ok, "a counting query over text features still runs", ok[:80])
    ok = s.aggregate("with d as (select domain, count(*) c from corpus_meta group by 1) "
                     "select * from d order by c desc limit 2")
    check('"domain"' in ok, "select * from a text-free cte still runs", ok[:80])
    check(len(s.inspected) == 0, "no free call spent or bypassed the budget",
          str(len(s.inspected)))
    log = (tmp / "escape.jsonl").read_text()
    check(log.count('"tool": "refused"') >= 10, "refusals are logged in the trajectory",
          str(log.count('"tool": "refused"')))



def test_replay_reports_calls_the_guard_now_refuses(tmp: pathlib.Path) -> None:
    """A released log may hold calls that ran then but the SQL guard refuses now.

    Such a call is a property of the old run, disclosed in the replay report;
    counting it as an error would read as a failure to reproduce the log.
    """
    print("replay under the current guard")
    from scripts.replay_trajectory import replay

    derived = synthetic_corpus(tmp / "replay")
    run = tmp / "replay_run"
    run.mkdir()
    calls = [
        ("select count(*) as n from corpus_meta", '[{"n": 1000}]'),
        ("select substr(text, 1, 4) as p, count(*) as c from corpus group by 1",
         '[{"p": "Toto", "c": 900}, {"p": "BUY ", "c": 100}]'),
    ]
    with open(run / "tools.jsonl", "w") as fh:
        for i, (sql, result) in enumerate(calls, 1):
            fh.write(json.dumps({"call": i, "tool": "aggregate", "args": {"sql": sql},
                                 "result": result}) + "\n")
    st = replay(str(run), derived, budgeted=False)
    check(st.get("refused_now") == 1, "the text-reading call is reported as refused now",
          str(st.get("refused_now")))
    check(st["errors"] == 0, "a refused call is not counted as an error", str(st["errors"]))
    check(st["matched"] == 1, "the allowed call still reproduces", str(st["matched"]))



def upstream_shard(path: pathlib.Path, n: int = 100) -> None:
    """A raw shard with exactly the columns upstream FineWeb2 ships.

    Every fifth document carries a GlotLID runner-up: Czech at 0.20 behind
    Hungarian at 0.70, with English third at 0.05. The rest are single-language.
    """
    duckdb.connect().execute(f"""
        copy (select
            'Szöveg ' || i as text,
            'h' || i as id,
            'CC-MAIN-2024-18' as dump,
            'https://site' || (i % 5) || '.hu/p' || i as url,
            '2024-04-01T00:00:00Z' as date,
            's3://x/' || i as file_path,
            'hun' as language,
            case when i % 5 = 0 then 0.70 else 0.99 end as language_score,
            'Latn' as language_script,
            1 as minhash_cluster_size,
            case when i % 5 = 0
                 then '{{"hun_Latn_score": 0.70, "eng_Latn_score": 0.05, "ces_Latn_score": 0.20}}'
                 else '{{"hun_Latn_score": 0.99}}' end as top_langs
        from range(1, {n + 1}) t(i)) to '{path}' (format parquet)""")


def test_upstream_fineweb2_shard(tmp: pathlib.Path) -> None:
    """Any FineWeb2 language builds, with a language-neutral runner-up signal."""
    print("upstream FineWeb2 shard of another language")
    from src.corpusaudit.db import build, open_corpus
    from src.corpusaudit.testsuite import corpus_scope

    shard = tmp / "hun.parquet"
    upstream_shard(shard)
    build(str(shard), str(tmp / "hun_derived"), threads=2, sample_mod=1)
    corpus = open_corpus(str(tmp / "hun_derived"))
    check(corpus.n_total == 100 and corpus.n_sample == 100,
          "sample_mod=1 puts every document in the text sample",
          f"{corpus.n_total} / {corpus.n_sample}")
    rows = corpus.con.execute(
        "select lid_second, lid_second_score, count(*) from meta group by 1, 2 order by 3"
    ).fetchall()
    check(rows == [("ces_Latn", 0.20, 20), (None, 0.0, 80)],
          "the GlotLID runner-up is the second-highest score, suffix stripped", str(rows))
    check(corpus_scope(corpus) == "hun_Latn", "the corpus scope carries the script",
          corpus_scope(corpus))

    build(str(shard), str(tmp / "hun_quarter"), threads=2, sample_mod=4)
    quarter = open_corpus(str(tmp / "hun_quarter"))
    check(quarter.n_total == 100 and 10 <= quarter.n_sample <= 45,
          "sample_mod=4 keeps about a quarter of the documents with text",
          str(quarter.n_sample))


def test_scope_respects_script() -> None:
    print("scope and script")
    from src.corpusaudit.testsuite import in_scope

    check(not in_scope("srp_Latn", "srp_Cyrl"),
          "a Latin-script test does not run on the Cyrillic corpus of the same language")
    check(in_scope("slk_Latn", "slk"), "a scoped test runs on a corpus labelled without script")
    check(in_scope("hun_Latn", "hun_Latn"), "an exact scope runs")



def test_agent_view_of_another_language(tmp: pathlib.Path) -> None:
    """The agent sees the neutral LID signal and is told which columns are empty."""
    print("agent view of another language")
    from src.corpusaudit.db import build, open_corpus
    from src.corpusaudit.tools import create_agent_views

    shard = tmp / "hun_view.parquet"
    upstream_shard(shard)
    build(str(shard), str(tmp / "hun_view"), threads=2, sample_mod=1)
    corpus = open_corpus(str(tmp / "hun_view"))
    create_agent_views(corpus.con)
    s = AuditSession(con=corpus.con, n_total=corpus.n_total, n_sample=corpus.n_sample,
                     budget=3, log_path=str(tmp / "view.jsonl"),
                     findings_dir=str(tmp / "view_findings"))
    out = s.aggregate("select lid_second, count(*) as n from corpus_meta "
                      "where lid_second_score > 0.1 group by 1")
    check(json.loads(out) == [{"lid_second": "ces_Latn", "n": 20}],
          "the runner-up language is queryable by the agent", out)
    schema = s.schema()
    empty_line = next((ln for ln in schema.splitlines() if ln.startswith("empty in this corpus")), "")
    empty = {c.strip() for c in empty_line.partition(":")[2].split(",")}
    for col in ("fasttext", "langdetect", "lingua_top", "lingua_top_p", "n_bad_words"):
        check(col in empty, f"schema names {col} as empty", empty_line)
    for col in ("lid_second", "language_score", "domain"):
        check(col not in empty, f"schema does not call {col} empty", empty_line)
    check("lid_second" in schema.split("empty in this corpus")[0],
          "schema documents the runner-up columns")

    old = open_corpus(synthetic_corpus(tmp / "old_tables"))
    create_agent_views(old.con)
    n = old.con.execute("select count(*) from corpus_meta").fetchone()[0]
    check(n == 1000, "tables built without the new columns still open for the agent", str(n))



def test_sentence_lid_covers_other_scripts() -> None:
    """Line-level LID must work for every script FineWeb2 holds, not just Latin."""
    print("sentence-level language ID beyond Latin script")
    from src.corpusaudit.lid import line_lid

    text = "\n".join([
        "Москва является столицей Российской Федерации и крупнейшим городом страны.",
        "Η Αθήνα είναι η πρωτεύουσα και η μεγαλύτερη πόλη της Ελλάδας.",
        "Bratislava je hlavné mesto Slovenskej republiky a jej najväčšie mesto.",
    ])
    got = [ln["lang"] for ln in line_lid(text)["lines"]]
    check(got == ["ru", "el", "sk"], "Cyrillic, Greek and Latin lines are each identified",
          str(got))



def test_findings_take_the_corpus_scope(tmp: pathlib.Path) -> None:
    """A finding saved while auditing Hungarian is a Hungarian test."""
    print("finding scope follows the corpus")
    import yaml as _yaml

    from src.corpusaudit.db import build
    from src.corpusaudit.mcp_server import open_session

    shard = tmp / "hun_scope.parquet"
    upstream_shard(shard)
    build(str(shard), str(tmp / "hun_scope"), threads=2, sample_mod=1)
    s = open_session(str(tmp / "hun_scope"), budget=5, log_path=str(tmp / "scope.jsonl"),
                     findings_dir=str(tmp / "scope_findings"))
    s.save_finding("czech_runner_up", "Czech is the runner-up language",
                   "lid_second = 'ces_Latn'", "checked 3 documents")
    saved = _yaml.safe_load(open(tmp / "scope_findings" / "czech_runner_up.yaml"))
    check(saved["scope"] == "hun_Latn", "the saved finding is scoped to the audited corpus",
          saved["scope"])



def test_fineweb2_runner_preparation(tmp: pathlib.Path) -> None:
    """Pick a language's shards from the Hub listing and size the text sample."""
    print("fineweb2 runner: shards and sample size")
    from src.corpusaudit.db import open_corpus
    from src.corpusaudit.fineweb2 import prepare, sample_mod_for, select_shards

    files = [
        "README.md",
        "data/hun_Latn/test/000_00000.parquet",
        "data/hun_Latn/train/001_00000.parquet",
        "data/hun_Latn/train/000_00001.parquet",
        "data/hun_Latn/train/000_00000.parquet",
        "data/hun_Latn_removed/train/000_00000.parquet",
        "data/slk_Latn/train/000_00000.parquet",
    ]
    check(select_shards(files, "hun_Latn") == [
        "data/hun_Latn/train/000_00000.parquet",
        "data/hun_Latn/train/000_00001.parquet",
        "data/hun_Latn/train/001_00000.parquet",
    ], "all train shards of the language, in order, without the removed set")
    check(select_shards(files, "hun_Latn", n=2, step=2) == [
        "data/hun_Latn/train/000_00000.parquet",
        "data/hun_Latn/train/001_00000.parquet",
    ], "n and step thin the shard list")
    check(select_shards(files, "hun_Latn", split="test") == ["data/hun_Latn/test/000_00000.parquet"],
          "the small test split can be chosen")
    try:
        select_shards(files, "xyz_Latn")
    except SystemExit as e:
        check("xyz_Latn" in str(e), "an unknown language is named in the error", str(e))
    else:
        check(False, "an unknown language is refused")

    from src.corpusaudit.fineweb2 import refuse_if_too_big

    refuse_if_too_big(int(99e9), 100)
    try:
        refuse_if_too_big(int(101e9), 100)
    except SystemExit as e:
        check("101.0 GB" in str(e), "a download over --max-gb is refused with its size", str(e))
    else:
        check(False, "a download over --max-gb is refused")

    check([sample_mod_for(n, t) for n, t in ((100, 25), (100, 30), (100, 1000), (0, 10))]
          == [4, 4, 1, 1], "sample_mod is the ceiling of documents over the target")

    shard = tmp / "prep" / "000_00000.parquet"
    shard.parent.mkdir()
    upstream_shard(shard)
    mod = prepare(str(tmp / "prep" / "*.parquet"), str(tmp / "prep_derived"), target_docs=25)
    corpus = open_corpus(str(tmp / "prep_derived"))
    check(mod == 4 and corpus.n_total == 100 and corpus.n_sample < 50,
          "prepare builds the tables with the sample sized to the target",
          f"mod={mod} sample={corpus.n_sample}")



def test_sentence_lid_warns_outside_its_languages(tmp: pathlib.Path) -> None:
    """On a language Lingua does not know, the tool must say its labels are unreliable."""
    print("sentence-level language ID outside its languages")
    from src.corpusaudit.db import open_corpus
    from src.corpusaudit.lid import knows

    check(knows("hun_Latn") and knows("slk_Latn"), "languages Lingua covers are known")
    check(knows("lvs_Latn") and knows("ekk_Latn") and knows("cmn_Hani"),
          "FineWeb2's individual-language codes map to Lingua's (Latvian, Estonian, Chinese)")
    check(not knows("mlt_Latn"), "Maltese is not known")
    check(knows("any"), "an unscoped corpus raises no warning")

    corpus = open_corpus(synthetic_corpus(tmp / "lid_scope"))
    con = corpus.con
    con.execute("create view corpus as select text, top_langs, lingua, "
                + ", ".join(AGENT_COLUMNS) + " from docs")
    for scope, warned in (("mlt_Latn", True), ("slk_Latn", False)):
        s = AuditSession(con=con, n_total=corpus.n_total, n_sample=corpus.n_sample, budget=3,
                         log_path=str(tmp / f"lid_{scope}.jsonl"),
                         findings_dir=str(tmp / f"lid_{scope}"), scope=scope)
        out = json.loads(s.sentence_lid("doc1"))
        check(("note" in out) == warned and (not warned or scope in out["note"]),
              f"{scope}: a warning appears exactly when the language is unknown",
              out.get("note", "no note"))



def test_findings_become_candidate_tests(tmp: pathlib.Path) -> None:
    """An agent's findings on a new language turn into runnable candidate tests."""
    print("findings to candidate tests")
    import yaml as _yaml

    from scripts.findings_to_tests import write_candidate_tests
    from src.corpusaudit.db import build

    shard = tmp / "hun_tests.parquet"
    upstream_shard(shard)
    build(str(shard), str(tmp / "hun_tests"), threads=2, sample_mod=1)
    run_dir = tmp / "runs" / "hun_Latn_1"
    (run_dir / "findings").mkdir(parents=True)
    finding = {
        "id": "czech_runner_up", "scope": "hun_Latn",
        "description": "Czech is the runner-up language",
        "selector": "lid_second = 'ces_Latn'",
        "assertion": "A clean corpus should not contain these pages",
        "evidence": {"prevalence": 0.2, "n_matched": 20, "agent_evidence": "read 3"},
    }
    (run_dir / "findings" / "czech_runner_up.yaml").write_text(_yaml.safe_dump(finding))

    paths = write_candidate_tests(str(run_dir), str(tmp / "suite"))
    check([p.relative_to(tmp / "suite").as_posix() for p in paths]
          == ["hun_Latn/czech_runner_up.yaml"], "one test per finding, under its scope",
          str(paths))
    test = _yaml.safe_load(paths[0].read_text())
    check(test["status"] == "candidate", "a test without human validation is a candidate")
    check(test["assertion"] == "prevalence <= 0.24000000",
          "the assertion allows 20% growth over the measured prevalence", test["assertion"])
    check(test["evidence"]["agent_assertion"] == finding["assertion"],
          "the agent's own wording is kept as evidence")
    check(test["found_in_runs"] == ["hun_Latn_1"], "the run is recorded")

    rep = tmp / "hun_suite.json"
    run([str(tmp / "suite" / "hun_Latn")], str(tmp / "hun_tests"), str(rep))
    got = {t["id"]: t["status"] for t in json.loads(rep.read_text())["tests"]}
    check(got == {"czech_runner_up": "PASS"}, "the suite runs the new test on its corpus",
          str(got))



def test_prompt_names_the_audited_language() -> None:
    """The prompt tells the agent which language the slice claims to be."""
    print("auditor prompt per language")
    from src.corpusaudit.prompt import auditor_prompt, language_name

    root = pathlib.Path(__file__).resolve().parents[1]
    original = (root / "prompts" / "auditor_system.md").read_text()
    check(auditor_prompt("slk_Latn") == original,
          "the Slovak prompt is byte-identical to the one the paper used")
    hun = auditor_prompt("hun_Latn")
    check("labelled every document in it as Hungarian\n(`hun_Latn`)" in hun
          and "linguistic resource for Hungarian." in hun,
          "another language is named with its code")
    check("Slovak" not in hun and "slk_Latn" not in hun, "no trace of Slovak remains")
    check("as Maltese\n(`mlt_Latn`)" in auditor_prompt("mlt_Latn", name="Maltese"),
          "a name can be given for a language Lingua does not know")
    check([language_name(c) for c in ("hun_Latn", "lvs_Latn", "srp_Cyrl", "mlt_Latn")]
          == ["Hungarian", "Latvian", "Serbian", "mlt_Latn"],
          "names come from Lingua, else the code itself")


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        test_needs_text()
        test_wilson()
        test_mcp_dispatch()
        test_end_to_end(tmp)
        test_portability(tmp)
        test_redaction()
        test_budget_accounting(tmp)
        test_default_suites_finds_a_new_community(tmp)
        test_label_vocabulary_is_enforced(tmp)
        test_second_coder_agreement(tmp)
        test_annotation_tool_contract(tmp)
        test_adjudication_vocabulary_is_enforced(tmp)
        test_no_latex_escape_traps(tmp)
        test_malformed_tests_never_pass(tmp)
        test_tools_distinguish_error_from_empty(tmp)
        test_agent_sql_cannot_escape(tmp)
        test_replay_reports_calls_the_guard_now_refuses(tmp)
        test_upstream_fineweb2_shard(tmp)
        test_scope_respects_script()
        test_agent_view_of_another_language(tmp)
        test_sentence_lid_covers_other_scripts()
        test_findings_take_the_corpus_scope(tmp)
        test_fineweb2_runner_preparation(tmp)
        test_sentence_lid_warns_outside_its_languages(tmp)
        test_findings_become_candidate_tests(tmp)
        test_prompt_names_the_audited_language()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failing check(s):")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("AUDIT_DERIVED", "data/derived")
    sys.exit(main())
