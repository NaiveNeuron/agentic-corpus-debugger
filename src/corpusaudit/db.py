"""DuckDB-backed corpus view and one-off derived-metadata build.

Two tables are materialised once from the raw Parquet shards:

``meta``    one row per corpus document, no text.  Pipeline metadata plus
            cheap derived columns (domain, length, orthographic markers,
            parsed LID fields).  Used for exact corpus-wide prevalence.
``docs``    a deterministic uniform random subsample of the corpus *with*
            text, used for everything that needs to read documents
            (inspection, text regexes, detector evaluation).

The split exists because scanning 100\u202fGB of text per query is not
interactive, while metadata-only aggregates over 26.5M rows are.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import duckdb

# One in SAMPLE_MOD documents goes into the text-bearing ``docs`` table.
SAMPLE_MOD = 13

DEFAULT_SHARDS = "data/hf/data/train-*.parquet"
DEFAULT_OUT = "data/derived"

# Czech-only and Slovak-only orthographic characters.  Slovak has no
# <ř ě ů>; Czech has no <ľ ĺ ŕ ô ä>.
CZ_CHARS = "řěůŘĚŮ"
SK_CHARS = "ľĺŕôäĽĹŔÔÄ"


def _count_chars(col: str, chars: str) -> str:
    return " + ".join(f"length({col}) - length(replace({col}, '{c}', ''))" for c in chars)


# Columns the audit reads that only some releases ship.  Upstream FineWeb2 has
# the pipeline's own metadata; the ivykopal/fineweb2-slovak redistribution adds
# auxiliary LID predictions and a profanity-list count.  A release missing one
# is not an error: the column is materialised as NULL, every selector that
# touches it simply matches nothing, and the language-neutral tests still run.
OPTIONAL_COLUMNS = {
    "language_script": "varchar",
    "fasttext": "varchar",
    "langdetect": "varchar",
    "top_langs": "varchar",
    "lingua": "varchar",
    "bad_words": "varchar[]",
}


def shard_columns(shards: str, con: duckdb.DuckDBPyConnection | None = None) -> set[str]:
    """The column names present in the raw shards."""
    own = con or duckdb.connect()
    rows = own.execute(
        "select column_name from (describe select * from read_parquet($shards))",
        {"shards": shards},
    ).fetchall()
    return {r[0] for r in rows}


def _ranked_langs() -> str:
    """GlotLID's ``top_langs`` as a list of {s: score, k: language}, best first.

    Every FineWeb2 language ships this distribution, so the runner-up language
    and its score give a disagreement signal that names no language pair.
    """
    return ("list_sort(list_transform(json_keys(top_langs), lambda k: "
            "{'s': try_cast(json_extract_string(top_langs, '$.\"' || k || '\"') as double), "
            "'k': regexp_replace(k, '_score$', '')}), 'DESC')")


def derived_sql(present: set[str] | None = None, sample_mod: int = SAMPLE_MOD) -> str:
    """The derived-metadata query, with absent optional columns cast to NULL.

    One in ``sample_mod`` documents is marked ``in_sample`` for the text table.
    """
    have = present if present is not None else set(OPTIONAL_COLUMNS)

    def col(name: str) -> str:
        return name if name in have else f"cast(null as {OPTIONAL_COLUMNS[name]}) as {name}"

    if "top_langs" in have:
        second = ("_ranked[2].k as lid_second, "
                  "case when top_langs is null then null "
                  "else coalesce(_ranked[2].s, 0.0) end as lid_second_score")
        source = f"(select *, {_ranked_langs()} as _ranked from read_parquet($shards))"
    else:
        second = "cast(null as varchar) as lid_second, cast(null as double) as lid_second_score"
        source = "read_parquet($shards)"

    return f"""
select
    id,
    regexp_replace(regexp_extract(url, '^[a-zA-Z]+://([^/:]+)', 1), '^www\\.', '') as domain,
    url,
    dump,
    date,
    language,
    {col('language_script')},
    language_score,
    minhash_cluster_size,
    {col('fasttext')},
    {col('langdetect')},
    {col('top_langs')},
    {col('lingua')},
    {second},
    try_cast(json_extract_string({'top_langs' if 'top_langs' in have else 'null'},
             '$.ces_Latn_score') as double) as glotlid_ces,
    try_cast(json_extract_string({'top_langs' if 'top_langs' in have else 'null'},
             '$.slk_Latn_score') as double) as glotlid_slk,
    {"regexp_extract(lingua, '^\\[\\(''([a-z]+)''', 1)" if 'lingua' in have
     else 'cast(null as varchar)'} as lingua_top,
    try_cast(regexp_extract({'lingua' if 'lingua' in have else "''"},
             '^\\[\\(''[a-z]+'', ([0-9.e-]+)\\)', 1) as double) as lingua_top_p,
    coalesce(try_cast(regexp_extract({'lingua' if 'lingua' in have else "''"},
             '\\(''sk'', ([0-9.e-]+)\\)', 1) as double), 0.0) as lingua_sk_p,
    coalesce(try_cast(regexp_extract({'lingua' if 'lingua' in have else "''"},
             '\\(''cs'', ([0-9.e-]+)\\)', 1) as double), 0.0) as lingua_cs_p,
    {"len(bad_words)" if 'bad_words' in have else "cast(null as bigint)"} as n_bad_words,
    length(text) as n_chars,
    length(text) - length(replace(text, ' ', '')) + 1 as n_words,
    length(text) - length(replace(text, chr(10), '')) + 1 as n_lines,
    {_count_chars('text', CZ_CHARS)} as cz_marks,
    {_count_chars('text', SK_CHARS)} as sk_marks,
    hash(id) % {int(sample_mod)} = 0 as in_sample
from {source}
"""


@dataclass
class Corpus:
    """Handle on the materialised audit tables."""

    con: duckdb.DuckDBPyConnection
    n_total: int
    n_sample: int
    sample_mod: int = SAMPLE_MOD

    def sql(self, query: str):
        return self.con.sql(query)


def build(shards: str = DEFAULT_SHARDS, out: str = DEFAULT_OUT, threads: int = 0,
          sample_mod: int = SAMPLE_MOD) -> None:
    """Materialise ``meta`` and ``docs`` Parquet files (one-off, ~2 passes).

    ``docs`` keeps the text of one in ``sample_mod`` documents.
    """
    os.makedirs(out, exist_ok=True)
    con = duckdb.connect()
    if threads:
        con.execute(f"set threads={threads}")
    con.execute("set preserve_insertion_order=false")
    con.execute("set enable_progress_bar=true")

    meta_path = os.path.join(out, "meta.parquet")
    docs_path = os.path.join(out, "docs.parquet")

    present = shard_columns(shards, con) & set(OPTIONAL_COLUMNS)
    missing = sorted(set(OPTIONAL_COLUMNS) - present)
    if missing:
        print(f"[adapter] release ships no {', '.join(missing)}; "
              f"materialising them as NULL")

    con.execute(
        f"copy ({derived_sql(present, sample_mod)}) to '{meta_path}' (format parquet, compression zstd)",
        {"shards": shards},
    )
    con.execute(
        f"""copy (
              select d.text, m.* exclude (in_sample)
              from read_parquet($shards) d
              join read_parquet('{meta_path}') m using (id)
              where m.in_sample
            ) to '{docs_path}' (format parquet, compression zstd)""",
        {"shards": shards},
    )


def open_corpus(out: str = DEFAULT_OUT, read_only_threads: int = 0) -> Corpus:
    """Open the materialised tables for querying."""
    # Without this, a user whose first command is the test suite gets a raw
    # DuckDB error pointing at a path they have never heard of, which reads as a
    # broken artefact rather than a missing download.
    absent = [n for n in ("meta.parquet", "docs.parquet")
              if not os.path.exists(os.path.join(out, n))]
    if absent:
        raise SystemExit(
            f"no derived tables in {out!r} ({', '.join(absent)} missing).\n"
            f"  build them:  python -c \"from src.corpusaudit.db import build; build()\"\n"
            f"  fetch the corpus first if needed: python scripts/download_shards.py\n"
            f"  to check the framework itself with no data at all (~1 s):\n"
            f"               python -m selftest.test_framework")
    con = duckdb.connect()
    if read_only_threads:
        con.execute(f"set threads={read_only_threads}")
    # Absolute paths, so that a session later confined to this directory
    # (``sqlguard.lock_down``) still resolves its own views.
    root = os.path.abspath(out)
    con.execute(
        f"create view meta as select * from read_parquet('{os.path.join(root, 'meta.parquet')}')"
    )
    con.execute(
        f"create view docs as select * from read_parquet('{os.path.join(root, 'docs.parquet')}')"
    )
    n_total = con.sql("select count(*) from meta").fetchone()[0]
    n_sample = con.sql("select count(*) from docs").fetchone()[0]
    return Corpus(con=con, n_total=n_total, n_sample=n_sample)


if __name__ == "__main__":
    import sys

    build(*(sys.argv[1:3] or []))
    print("built", DEFAULT_OUT)
