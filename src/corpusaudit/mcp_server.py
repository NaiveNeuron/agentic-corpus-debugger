"""Minimal MCP stdio server exposing the audit tools.

Implemented directly against the JSON-RPC wire protocol to keep the
dependency surface (and therefore the reproduction cost) small.
"""

from __future__ import annotations

import json
import os
import sys
import traceback

from .db import open_corpus
from .sqlguard import lock_down
from .testsuite import corpus_scope
from .tools import AuditSession, create_agent_views

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    ("schema", "Describe the available relations, columns, and the remaining inspection budget.", {}),
    (
        "aggregate",
        "Run a read-only SQL query over the corpus relations (counts, distributions, group-bys). "
        "Costs no inspection budget.",
        {"sql": ("string", "A single read-only SELECT statement.", True)},
    ),
    (
        "sample_documents",
        "Draw a random sample of documents matching a SQL condition, returning metadata and a "
        "400-character snippet each. Costs one inspection per new document.",
        {
            "condition": ("string", "SQL condition over the corpus columns. Default 'true'.", False),
            "n": ("integer", "Number of documents (1-25).", False),
            "seed": ("integer", "Sampling seed; change it to draw a different sample.", False),
        },
    ),
    (
        "inspect_document",
        "Read one document in full (up to 6000 characters) together with all its metadata. "
        "Costs one inspection.",
        {"doc_id": ("string", "The document id.", True)},
    ),
    (
        "search_text",
        "Count and retrieve documents whose text matches a regular expression. "
        "Costs one inspection per returned document.",
        {
            "pattern": ("string", "RE2 regular expression matched against the document text.", True),
            "condition": ("string", "Additional SQL condition. Default 'true'.", False),
            "n": ("integer", "How many matching documents to return (0-25).", False),
        },
    ),
    (
        "domain_stats",
        "Most frequent hosts among documents matching a condition, with each host's share of its "
        "own documents. Costs no inspection budget.",
        {
            "condition": ("string", "SQL condition. Default 'true'.", False),
            "n": ("integer", "How many hosts to return (1-50).", False),
        },
    ),
    (
        "crawl_stats",
        "Rate of documents matching a condition in each crawl snapshot. Costs no inspection budget.",
        {"condition": ("string", "SQL condition. Default 'true'.", False)},
    ),
    (
        "sentence_lid",
        "Run a sentence-level language identifier over one document and report the language of each "
        "line plus the aggregate distribution. Costs one inspection.",
        {"doc_id": ("string", "The document id.", True)},
    ),
    (
        "run_detector",
        "Measure how much of the corpus a candidate rule (SQL condition) selects, exactly on the "
        "full corpus when the rule uses metadata only. Costs no inspection budget.",
        {
            "name": ("string", "Short name for the candidate rule.", True),
            "selector": ("string", "SQL condition defining the rule.", True),
        },
    ),
    (
        "evaluate_detector",
        "Inspect a random sample of the documents a candidate rule selects, to check its precision. "
        "Costs one inspection per returned document.",
        {
            "name": ("string", "Short name for the candidate rule.", True),
            "selector": ("string", "SQL condition defining the rule.", True),
            "n": ("integer", "How many documents to inspect (1-25).", False),
            "seed": ("integer", "Sampling seed.", False),
        },
    ),
    (
        "save_finding",
        "Record a supported finding as a machine-readable corpus test. Only record findings that are "
        "systematic, reproducibly retrievable by the selector, and supported by documents you "
        "inspected.",
        {
            "finding_id": ("string", "Short snake_case identifier.", True),
            "description": ("string", "What the defect is, in one or two sentences.", True),
            "selector": ("string", "SQL condition that retrieves the slice.", True),
            "evidence": ("string", "What you checked, what you found, and any counter-evidence.", True),
            "example_ids": ("array", "Ids of representative documents you inspected.", False),
            "expected_precision": ("number", "Your estimate of the fraction of matches that are "
                                             "genuine instances (0-1).", False),
            "likely_false_positives": ("string", "What kind of document the selector wrongly "
                                                 "catches.", False),
            "assertion": ("string", "Optional assertion a future corpus should satisfy.", False),
        },
    ),
]


TOOL_NAMES = frozenset(name for name, _, _ in TOOLS)


def _schema(params: dict) -> dict:
    props, required = {}, []
    for name, (typ, desc, req) in params.items():
        props[name] = {"type": typ, "description": desc}
        if typ == "array":
            props[name]["items"] = {"type": "string"}
        if req:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


def open_session(derived: str, budget: int, log_path: str, findings_dir: str) -> AuditSession:
    """An audit session over the derived tables, scoped to the corpus's language."""
    corpus = open_corpus(derived)
    con = corpus.con
    create_agent_views(con)
    scope = corpus_scope(corpus)
    # From here on the connection can reach nothing but the derived tables,
    # and the agent cannot change that.
    lock_down(con, derived)
    return AuditSession(
        con=con,
        n_total=corpus.n_total,
        n_sample=corpus.n_sample,
        budget=budget,
        log_path=log_path,
        findings_dir=findings_dir,
        scope=scope,
    )


def main() -> int:
    session = open_session(
        os.environ.get("AUDIT_DERIVED", "data/derived"),
        budget=int(os.environ.get("AUDIT_BUDGET", "300")),
        log_path=os.environ.get("AUDIT_LOG", "out/trajectory.jsonl"),
        findings_dir=os.environ.get("AUDIT_FINDINGS", "out/findings"),
    )

    def write(msg: dict) -> None:
        sys.stdout.write(json.dumps(msg) + "\n")
        sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, rid = req.get("method"), req.get("id")
        if method == "initialize":
            write({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "audit", "version": "0.1.0"},
            }})
        elif method in ("notifications/initialized", "notifications/cancelled"):
            continue
        elif method == "tools/list":
            write({"jsonrpc": "2.0", "id": rid, "result": {"tools": [
                {"name": n, "description": d, "inputSchema": _schema(p)} for n, d, p in TOOLS
            ]}})
        elif method == "tools/call":
            name = req["params"]["name"]
            args = req["params"].get("arguments") or {}
            try:
                if name not in TOOL_NAMES:  # never dispatch to session internals
                    raise ValueError(f"unknown tool: {name}")
                result = getattr(session, name)(**args)
                is_err = False
            except Exception as exc:  # surfaced to the agent so it can adapt
                result = f"{type(exc).__name__}: {exc}"
                is_err = True
                if not isinstance(exc, ValueError):  # ValueError already logged
                    session.log_error(name, args, result)
                print(traceback.format_exc(), file=sys.stderr)
            write({"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": str(result)}], "isError": is_err,
            }})
        elif rid is not None:
            write({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "not found"}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
