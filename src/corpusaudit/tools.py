"""The audit tool environment exposed to the auditing agent.

Design constraints:

* **Read-only.**  The only mutating tool is ``save_finding``.
* **Budgeted.**  Every document whose text the caller sees counts once
  against a fixed inspection budget, tracked by document id.
* **Logged.**  Every call and its (truncated) result is appended to a JSONL
  trajectory, so an investigation can be replayed.
* **Taxonomy-free.**  The view exposed to the agent contains only fields
  the published corpus itself provides plus language-neutral derived
  columns (domain, character/word/line counts).  Nothing in the schema or
  the docstrings names a failure mode, a language pair, or a hypothesis.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import duckdb

from .anon import redact_obj
from .selectors import needs_text
from .sqlguard import UnsafeSQL, validate, validate_condition

# Columns the agent may see.  Deliberately: the corpus's own metadata plus
# neutral size/host derivations.
AGENT_COLUMNS = [
    "id",
    "url",
    "domain",
    "dump",
    "date",
    "language",
    "language_score",
    "minhash_cluster_size",
    "fasttext",
    "langdetect",
    "lingua_top",
    "lingua_top_p",
    "n_bad_words",
    "n_chars",
    "n_words",
    "n_lines",
]

SCHEMA_DOC = """\
Two relations are available.

  corpus      one row per document in the working sample, WITH the text.
  corpus_meta one row per document in the whole corpus, WITHOUT the text.

Columns (identical in both, except `text`, which only `corpus` has):
  id                    document identifier
  text                  document text (corpus only)
  url, domain           source URL and its host
  dump, date            crawl the document came from, and its timestamp
  language              language label assigned by the corpus pipeline
  language_score        the pipeline's confidence in that label
  minhash_cluster_size  size of the near-duplicate cluster the document
                        represented before deduplication (1 = unique)
  fasttext, langdetect  labels from two independent off-the-shelf language
                        identifiers, shipped with the corpus release
  lingua_top            top language from a third identifier, which reports
                        a distribution over languages within the document
  lingua_top_p          that identifier's proportion for lingua_top
  n_bad_words           number of profanity-list matches recorded by the
                        corpus release
  n_chars, n_words, n_lines  document size
Raw pipeline fields `top_langs` (JSON) and `lingua` (list of
(language, proportion) pairs, as text) are also available on both
relations if you want the full distributions.
"""

# Derived from the pipeline's own language-ID distribution (`top_langs`), which
# every FineWeb2 language ships. Tables built by older adapters lack them.
NEUTRAL_LID_COLUMNS = ["lid_second", "lid_second_score"]

NEUTRAL_LID_DOC = """\
  lid_second            runner-up language code in the pipeline's own
                        language-ID distribution (top_langs); NULL when
                        the distribution holds a single language
  lid_second_score      that runner-up's score (0 when there is none)
"""


def create_agent_views(con: duckdb.DuckDBPyConnection) -> None:
    """Create the two relations the agent queries over the derived tables."""
    have = {r[0] for r in con.execute("describe select * from meta").fetchall()}
    cols = ", ".join(AGENT_COLUMNS + [c for c in NEUTRAL_LID_COLUMNS if c in have])
    con.execute(f"create view corpus as select text, top_langs, lingua, {cols} from docs")
    con.execute(f"create view corpus_meta as select top_langs, lingua, {cols} from meta")

MAX_ROWS = 60
SNIPPET = 400
FULL_TEXT = 6000


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


@dataclass
class AuditSession:
    """Tool implementations bound to one corpus and one budget."""

    con: duckdb.DuckDBPyConnection
    n_total: int
    n_sample: int
    budget: int = 300
    log_path: str = "out/trajectory.jsonl"
    findings_dir: str = "out/findings"
    # Language scope written into saved findings, e.g. ``slk_Latn``.
    scope: str = "any"
    inspected: set[str] = field(default_factory=set)
    n_calls: int = 0
    _logged_used: int = 0

    # -- infrastructure ---------------------------------------------------
    def __post_init__(self) -> None:
        os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
        os.makedirs(self.findings_dir, exist_ok=True)

    def _log(self, tool: str, args: dict, result: Any) -> None:
        """Append one call to the trajectory.

        ``inspections_spent`` is derived here, as the growth of the charged set,
        rather than passed in by each tool: a caller that reported the number of
        rows it returned would over-count a document the agent had already read,
        and the per-call charges would then not sum to the final count.
        """
        self.n_calls += 1
        used = len(self.inspected)
        rec = {
            "t": time.time(),
            "call": self.n_calls,
            "tool": tool,
            "args": args,
            "inspections_spent": used - self._logged_used,
            "inspections_used": used,
            "result": str(result)[:4000],
        }
        self._logged_used = used
        with open(self.log_path, "a") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _charge(self, ids: list[str]) -> list[str]:
        """Charge inspections; return the ids that fit in the budget."""
        allowed = []
        for doc_id in ids:
            if doc_id in self.inspected:
                allowed.append(doc_id)
            elif len(self.inspected) < self.budget:
                self.inspected.add(doc_id)
                allowed.append(doc_id)
        return allowed

    def log_error(self, tool: str, args: dict, message: str) -> None:
        """Record a refused or failed call: a rejected query is part of the
        investigation, so the trajectory must contain it."""
        self._log(tool, args, f"ERROR: {message}")

    def _check(self, condition: str) -> None:
        """Refuse a condition that reaches outside the agent relations."""
        try:
            validate_condition(self.con, condition)
        except UnsafeSQL as e:
            self.log_error("refused", {"condition": condition}, str(e))
            raise

    def _rows(self, sql: str, params: dict | None = None) -> list[dict]:
        rel = self.con.execute(sql, params or {})
        cols = [d[0] for d in rel.description]
        return [dict(zip(cols, r)) for r in rel.fetchmany(MAX_ROWS)]

    @staticmethod
    def _fmt(rows: list[dict]) -> str:
        """Serialise rows for the agent and the log.

        Every tool result passes through here, which is where third-party email
        addresses are redacted: the agent never needs one, and the trajectory is
        released. FineWeb2's own placeholders are kept, since a candidate finding
        is about them.
        """
        if not rows:
            return "(no rows)"
        return json.dumps(redact_obj(rows), ensure_ascii=False, indent=None, default=str)

    def remaining(self) -> int:
        return self.budget - len(self.inspected)

    # -- tools ------------------------------------------------------------
    def _columns(self) -> list[str]:
        return [r[0] for r in self.con.execute("describe select * from corpus_meta").fetchall()]

    def _empty_columns(self) -> list[str]:
        """Columns with no value anywhere in the corpus: the release does not ship them."""
        cols = [c for c in self._columns() if c != "id"]
        counts = self.con.execute(
            "select " + ", ".join(f'count("{c}")' for c in cols) + " from corpus_meta"
        ).fetchone()
        return [c for c, n in zip(cols, counts) if n == 0]

    def schema(self) -> str:
        """Describe the available relations and the state of the budget."""
        doc = SCHEMA_DOC
        if set(NEUTRAL_LID_COLUMNS) <= set(self._columns()):
            doc += NEUTRAL_LID_DOC
        empty = self._empty_columns()
        if empty:
            doc += ("empty in this corpus (the release does not ship them): "
                    + ", ".join(empty) + "\n")
        out = (
            f"{doc}\ncorpus: {self.n_sample:,} documents (working sample)\n"
            f"corpus_meta: {self.n_total:,} documents (full corpus)\n"
            f"inspection budget: {self.remaining()} of {self.budget} documents left\n"
        )
        self._log("schema", {}, "ok")
        return out

    def aggregate(self, sql: str) -> str:
        """Run a read-only SQL query. Free: costs no inspections.

        Use for counts, distributions, quantiles, group-bys.  `text` may only
        appear inside functions that return a number or a boolean, such as
        length, regexp_matches or contains; read documents with the document
        tools instead.
        """
        try:
            validate(self.con, sql, guard_text=True)
        except UnsafeSQL as e:
            self.log_error("refused", {"sql": sql}, str(e))
            raise
        rows = self._rows(sql)
        out = self._fmt(rows)
        self._log("aggregate", {"sql": sql}, out)
        return out

    def sample_documents(self, condition: str = "true", n: int = 5, seed: int = 0) -> str:
        """Draw a random sample of documents matching a SQL condition.

        Returns metadata plus a text snippet for each.  Costs one
        inspection per document not seen before.
        """
        n, seed = max(1, min(int(n), 25)), int(seed)
        self._check(condition)
        cols = ", ".join(AGENT_COLUMNS)
        rows = self._rows(
            f"select {cols}, substr(text, 1, {SNIPPET}) as snippet from corpus "
            f"where ({condition}) order by hash(id || '{seed}') limit {n}"
        )
        ids = self._charge([r["id"] for r in rows])
        rows = [r for r in rows if r["id"] in ids]
        out = self._fmt(rows) + f"\n[inspections left: {self.remaining()}]"
        self._log("sample_documents", {"condition": condition, "n": n, "seed": seed}, out)
        return out

    def inspect_document(self, doc_id: str) -> str:
        """Read one document in full (up to 6000 characters) with metadata."""
        charged = self._charge([doc_id])
        if not charged:
            return "[inspection budget exhausted]"
        cols = ", ".join(AGENT_COLUMNS)
        rows = self._rows(
            f"select {cols}, top_langs, lingua, substr(text, 1, {FULL_TEXT}) as text "
            "from corpus where id = $id",
            {"id": doc_id},
        )
        out = self._fmt(rows) + f"\n[inspections left: {self.remaining()}]"
        self._log("inspect_document", {"id": doc_id}, out)
        return out

    def search_text(self, pattern: str, condition: str = "true", n: int = 5) -> str:
        """Find documents whose text matches a regular expression.

        Reports how many documents in the working sample match, and returns
        up to `n` matching documents with a snippet (one inspection each).
        """
        n = max(0, min(int(n), 25))
        self._check(condition)
        cnt = self.con.execute(
            f"select count(*), count(*) * 1.0 / {self.n_sample} from corpus "
            "where regexp_matches(text, $p) and (" + condition + ")",
            {"p": pattern},
        ).fetchone()
        rows = []
        if n:
            rows = self._rows(
                f"select id, domain, dump, language_score, minhash_cluster_size, "
                f"substr(text, greatest(1, strpos(text, regexp_extract(text, $p)) - 100), {SNIPPET}) "
                f"as around_match from corpus where regexp_matches(text, $p) and ({condition}) "
                f"order by hash(id) limit {n}",
                {"p": pattern},
            )
            ids = self._charge([r["id"] for r in rows])
            rows = [r for r in rows if r["id"] in ids]
        out = (
            f"matches in working sample: {cnt[0]:,} documents ({cnt[1]:.4%})\n"
            + self._fmt(rows)
            + f"\n[inspections left: {self.remaining()}]"
        )
        self._log("search_text", {"pattern": pattern, "condition": condition, "n": n}, out)
        return out

    def domain_stats(self, condition: str = "true", n: int = 20, full_corpus: bool = True) -> str:
        """Most frequent hosts under a condition, with their corpus share."""
        self._check(condition)
        rel = "corpus_meta" if full_corpus else "corpus"
        rows = self._rows(
            f"""with s as (select domain, count(*) c from {rel} where ({condition}) group by 1),
                     t as (select domain, count(*) c from {rel} group by 1)
                select s.domain, s.c as matching_docs, t.c as domain_docs,
                       round(s.c * 1.0 / t.c, 4) as share_of_domain
                from s join t using (domain)
                -- domain breaks ties, so the result is a total order and the
                -- logged trajectory replays byte-for-byte
                order by s.c desc, s.domain limit {min(int(n), 50)}"""
        )
        out = self._fmt(rows)
        self._log("domain_stats", {"condition": condition, "n": n}, out)
        return out

    def crawl_stats(self, condition: str = "true", full_corpus: bool = True) -> str:
        """Distribution of matching documents over crawl snapshots."""
        self._check(condition)
        rel = "corpus_meta" if full_corpus else "corpus"
        rows = self._rows(
            f"""with s as (select dump, count(*) c from {rel} where ({condition}) group by 1),
                     t as (select dump, count(*) c from {rel} group by 1)
                select t.dump, coalesce(s.c, 0) as matching_docs, t.c as dump_docs,
                       round(coalesce(s.c, 0) * 1.0 / t.c, 5) as rate
                from t left join s using (dump) order by t.dump"""
        )
        out = self._fmt(rows)
        self._log("crawl_stats", {"condition": condition}, out)
        return out

    def sentence_lid(self, doc_id: str) -> str:
        """Run a sentence-level language identifier over one document.

        Returns, line by line, the identifier's top language and
        confidence, plus the aggregate distribution over the document.
        """
        from .lid import knows, line_lid

        charged = self._charge([doc_id])
        if not charged:
            return "[inspection budget exhausted]"
        row = self.con.execute(
            f"select substr(text, 1, {FULL_TEXT}) from corpus where id = $id", {"id": doc_id}
        ).fetchone()
        if not row:
            return "(no such document in the working sample)"
        result = line_lid(row[0])
        if not knows(self.scope):
            result["note"] = (f"this identifier does not cover the corpus language "
                              f"({self.scope}); its labels for lines in that language "
                              f"are unreliable")
        out = json.dumps(result, ensure_ascii=False, default=str)
        self._log("sentence_lid", {"id": doc_id}, out)
        return out

    def run_detector(self, name: str, selector: str) -> str:
        """Measure how much of the corpus a candidate rule selects.

        `selector` is a SQL condition.  If it only uses metadata columns it
        is evaluated exactly on the full corpus; if it needs `text` it is
        evaluated on the working sample and extrapolated with a 95%
        interval.  Costs no inspections.
        """
        self._check(selector)
        uses_text = needs_text(selector)
        rel, n = ("corpus", self.n_sample) if uses_text else ("corpus_meta", self.n_total)
        k = self.con.execute(f"select count(*) from {rel} where ({selector})").fetchone()[0]
        lo, hi = wilson(k, n)
        out = json.dumps(
            {
                "name": name,
                "evaluated_on": rel,
                "n_evaluated": n,
                "n_matched": k,
                "prevalence": k / n if n else 0.0,
                "prevalence_ci95": [lo, hi],
                "exact_on_full_corpus": not uses_text,
                "estimated_docs_in_full_corpus": round(k / n * self.n_total) if n else 0,
            },
            default=str,
        )
        self._log("run_detector", {"name": name, "selector": selector}, out)
        return out

    def evaluate_detector(self, name: str, selector: str, n: int = 10, seed: int = 0) -> str:
        """Inspect a random sample of what a candidate rule selects.

        Use this to check a rule's precision yourself before recording a
        finding.  Costs one inspection per returned document.
        """
        n, seed = max(1, min(int(n), 25)), int(seed)
        self._check(selector)
        rows = self._rows(
            f"select id, url, domain, language_score, minhash_cluster_size, fasttext, langdetect, "
            f"lingua_top, n_words, substr(text, 1, {SNIPPET}) as snippet from corpus "
            f"where ({selector}) order by hash(id || '{seed}') limit {n}"
        )
        ids = self._charge([r["id"] for r in rows])
        rows = [r for r in rows if r["id"] in ids]
        out = self._fmt(rows) + f"\n[inspections left: {self.remaining()}]"
        self._log("evaluate_detector", {"name": name, "selector": selector, "n": n}, out)
        return out

    def save_finding(
        self,
        finding_id: str,
        description: str,
        selector: str,
        evidence: str,
        example_ids: list[str] | None = None,
        expected_precision: float | None = None,
        likely_false_positives: str = "",
        assertion: str = "",
    ) -> str:
        """Record a supported finding as a machine-readable corpus test.

        Only record a finding that is systematic (not a single odd
        document), reproducibly retrievable by its selector, and supported
        by documents you actually inspected.  `evidence` should state what
        you checked and what you found, including counter-evidence.
        """
        import yaml

        stats = json.loads(self.run_detector(finding_id, selector))
        doc = {
            "id": finding_id,
            "scope": self.scope,
            "description": description,
            "selector": selector,
            "assertion": assertion or f"prevalence <= {stats['prevalence']:.6f}",
            "evidence": {
                "agent_evidence": evidence,
                "prevalence": stats["prevalence"],
                "prevalence_ci95": stats["prevalence_ci95"],
                "n_matched": stats["n_matched"],
                "evaluated_on": stats["evaluated_on"],
                "exact_on_full_corpus": stats["exact_on_full_corpus"],
                "agent_expected_precision": expected_precision,
                "likely_false_positives": likely_false_positives,
                "example_ids": example_ids or [],
                "inspections_used_when_saved": len(self.inspected),
            },
        }
        path = os.path.join(self.findings_dir, f"{re.sub(r'[^a-z0-9_]', '_', finding_id.lower())}.yaml")
        with open(path, "w") as fh:
            yaml.safe_dump(doc, fh, allow_unicode=True, sort_keys=False)
        out = f"saved {path} (prevalence {stats['prevalence']:.5%}, {stats['n_matched']:,} documents)"
        self._log("save_finding", {"id": finding_id, "selector": selector}, out)
        return out
