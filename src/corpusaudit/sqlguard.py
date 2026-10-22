"""Validation of agent-written SQL, and the connection lockdown it relies on.

The agent writes SQL in two places: whole queries for the free ``aggregate``
tool, and WHERE conditions for every other tool. Both run on the connection
that holds the corpus, so two things must be impossible:

* reaching anything except the two agent relations (other files, the full
  ``docs``/``meta`` views, system catalogues, settings);
* reading document text through a free tool, which would bypass the
  inspection budget the experiments are measured against.

The first is enforced twice: ``lock_down`` confines the connection to the
derived-data directory and freezes its configuration, and ``validate`` rejects
any table function or relation outside an allow-list. The second is enforced
on the parsed statement, not on its spelling: in a free query every reference
to ``text`` must sit under a function that returns a number or a boolean.

Parsing uses DuckDB's own parser (``json_serialize_sql``), so what is
validated is exactly what will run. That function only serialises SELECT
statements, so any other statement kind fails validation as a side effect.
"""

from __future__ import annotations

import json
import os
from typing import Any

import duckdb

AGENT_RELATIONS = frozenset({"corpus", "corpus_meta"})

# Functions that read document text but return only a number or a boolean.
TEXT_SAFE = frozenset({
    "regexp_matches", "regexp_full_match", "contains", "starts_with", "ends_with",
    "prefix", "suffix", "length", "strlen", "char_length", "length_grapheme",
    "strpos", "instr", "position", "~~", "!~~", "~~*", "!~~*", "~~~", "!~~~",
    "like_escape", "not_like_escape", "ilike_escape", "not_ilike_escape",
    "glob", "count",
})

# Scalar functions that expose the environment rather than the corpus.
_DENY_PREFIXES = ("read_", "sniff_", "parquet_", "duckdb_", "pragma_", "glob_", "icu_")
_DENY_NAMES = frozenset({
    "getenv", "current_setting", "query", "query_table", "which_secret",
    "current_database", "current_schema", "current_schemas",
})


class UnsafeSQL(ValueError):
    """The statement would reach outside the agent relations or leak text."""


class SQLSyntaxError(Exception):
    """The statement does not parse: an ordinary mistake, not a refusal.

    Not a ValueError, so the MCP layer logs it under the calling tool exactly
    as it logged DuckDB's own parser errors before this guard existed."""


def lock_down(con: duckdb.DuckDBPyConnection, directory: str) -> None:
    """Confine ``con`` to ``directory`` and make that irreversible.

    Call after every view the session needs has been created: views that read
    Parquet keep working because their files lie inside ``directory``.
    """
    path = os.path.abspath(directory).replace("'", "''")
    con.execute(f"set allowed_directories=['{path}']")
    con.execute("set enable_external_access=false")
    con.execute("set lock_configuration=true")


def _parse(con: duckdb.DuckDBPyConnection, sql: str) -> dict:
    raw = con.execute("select json_serialize_sql($q)", {"q": sql}).fetchone()[0]
    tree = json.loads(raw)
    if tree.get("error"):
        msg = str(tree.get("error_message", "parse error"))
        # json_serialize_sql serialises SELECT only; any other statement that
        # parses (SET, COPY, ATTACH, ...) comes back as "Only SELECT ...".
        if msg.startswith("Only SELECT"):
            raise UnsafeSQL("only a single read-only SELECT is allowed")
        raise SQLSyntaxError(msg)
    stmts = tree.get("statements") or []
    if len(stmts) != 1:
        raise UnsafeSQL("exactly one SELECT statement is allowed")
    return stmts[0]["node"]


def _names(node: Any, ctes: set[str], aliases: set[str]) -> None:
    """Collect CTE names and relation aliases before the main walk, which
    meets the select list (where an alias is used) before the FROM clause."""
    if isinstance(node, dict):
        for entry in (node.get("cte_map") or {}).get("map", []) or []:
            ctes.add(str(entry.get("key", "")).lower())
        if node.get("type") in ("BASE_TABLE", "SUBQUERY") and node.get("alias"):
            aliases.add(str(node["alias"]).lower())
        for v in node.values():
            _names(v, ctes, aliases)
    elif isinstance(node, list):
        for v in node:
            _names(v, ctes, aliases)


def _has_star(node: Any) -> bool:
    """A * in this select list, not counting nested subqueries."""
    if isinstance(node, list):
        return any(_has_star(v) for v in node)
    if not isinstance(node, dict) or node.get("type") == "SELECT_NODE":
        return False
    if node.get("class") == "STAR" or node.get("type") == "STAR":
        return True
    return any(_has_star(v) for v in node.values())


def _reads_corpus(from_table: Any) -> bool:
    """Whether a FROM clause scans ``corpus`` itself (directly or in a join),
    so that * would expand to its text column."""
    if not isinstance(from_table, dict):
        return False
    if from_table.get("type") == "BASE_TABLE":
        return str(from_table.get("table_name", "")).lower() == "corpus"
    if from_table.get("type") == "JOIN":
        return _reads_corpus(from_table.get("left")) or _reads_corpus(from_table.get("right"))
    return False


def _walk(node: Any, ctx: dict, under_safe: bool) -> None:
    if isinstance(node, list):
        for v in node:
            _walk(v, ctx, under_safe)
        return
    if not isinstance(node, dict):
        return
    kind = node.get("type")
    if kind == "TABLE_FUNCTION":
        raise UnsafeSQL("table functions are not available")
    if kind == "BASE_TABLE":
        name = str(node.get("table_name", "")).lower()
        if node.get("catalog_name") or node.get("schema_name") or name not in ctx["relations"]:
            raise UnsafeSQL(f"unknown relation {name!r}; use corpus or corpus_meta")
    cls = node.get("class")
    if cls == "FUNCTION":
        fname = str(node.get("function_name", "")).lower()
        if fname in _DENY_NAMES or fname.startswith(_DENY_PREFIXES):
            raise UnsafeSQL(f"function {fname!r} is not available")
        under_safe = under_safe or fname in TEXT_SAFE
    if ctx["guard_text"]:
        if (kind == "SELECT_NODE" and _has_star(node.get("select_list"))
                and _reads_corpus(node.get("from_table"))):
            raise UnsafeSQL("* over corpus would return document text; name the columns you need")
        if cls == "COLUMN_REF":
            names = [str(n).lower() for n in node.get("column_names", [])]
            if names and names[-1] == "text" and not under_safe:
                raise UnsafeSQL("text may only be used inside length/regexp_matches/contains-style "
                                "functions here; read documents with the document tools")
            if len(names) == 1 and names[0] in ctx["relations"] | ctx["aliases"]:
                raise UnsafeSQL("a whole row would include the text; name the columns you need")
    for v in node.values():
        _walk(v, ctx, under_safe)


def validate(con: duckdb.DuckDBPyConnection, sql: str, *, guard_text: bool) -> None:
    """Raise ``UnsafeSQL`` unless ``sql`` is one SELECT over the agent relations.

    With ``guard_text`` the result may not carry document text either.
    """
    node = _parse(con, sql)
    relations: set[str] = set(AGENT_RELATIONS)
    aliases: set[str] = set()
    _names(node, relations, aliases)
    ctx = {"relations": relations, "aliases": aliases, "guard_text": guard_text}
    _walk(node, ctx, False)


def validate_condition(con: duckdb.DuckDBPyConnection, condition: str) -> None:
    """Validate a WHERE condition that a tool will splice into its own query.

    The condition must stay a condition: wrapped in a query of known shape it
    has to parse back to that shape, so it cannot close the parenthesis and
    append a UNION, a second statement or a comment that swallows the rest.
    """
    if any(tok in condition for tok in (";", "--", "/*", "*/")):
        raise UnsafeSQL("comments and statement separators are not allowed in a condition")
    node = _parse(con, f"select 1 from corpus where ({condition})")
    if node.get("type") != "SELECT_NODE" or node.get("from_table", {}).get("type") != "BASE_TABLE":
        raise UnsafeSQL("a condition must be a single boolean expression")
    validate(con, f"select 1 from corpus where ({condition})", guard_text=False)
