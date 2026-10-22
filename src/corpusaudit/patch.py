"""Apply findings as patches: what would a cleaned corpus look like?

A test says "this slice should not be here". A patch is the same selector used to
remove it. This module measures what each patch takes out, in documents and in
words, and can emit the drop list so a patch travels without the corpus.

Patches are deliberately conservative. A selector retained for review is not
automatically a filter, so the caller chooses which statuses to apply; figures are
reported per patch and combined, and the combined figure is not the sum, because
patches overlap. Invariants that describe a corpus property rather than a
removable slice (identifier uniqueness, a confidence that exceeds one) are tests
only and are never applied as filters.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

import yaml

from .selectors import needs_text

# Findings whose defect is a property of the metadata, not of the documents:
# dropping the rows would hide the bug instead of fixing it.
NOT_FILTERABLE = {"document_ids_unique", "language_score_not_a_probability"}


@dataclass
class Patch:
    id: str
    selector: str
    status: str
    kind: str
    description: str

    @property
    def needs_text(self) -> bool:
        return needs_text(self.selector)


@dataclass
class PatchSet:
    patches: list[Patch] = field(default_factory=list)

    def load(self, *suites: str, statuses: tuple[str, ...] = ("accepted",)) -> "PatchSet":
        for suite in suites:
            for path in sorted(glob.glob(os.path.join(suite, "*.yaml"))):
                t = yaml.safe_load(open(path))
                if t.get("status") not in statuses or t["id"] in NOT_FILTERABLE:
                    continue
                self.patches.append(Patch(
                    id=t["id"], selector=t["selector"],
                    status=t.get("status", "candidate"),
                    kind=t.get("kind", "prevalence_guard"),
                    description=" ".join(str(t.get("description", "")).split())))
        return self

    @property
    def combined_selector(self) -> str:
        if not self.patches:
            return "false"
        return " OR ".join(f"({p.selector})" for p in self.patches)

    @property
    def relation(self) -> str:
        return "docs" if any(p.needs_text for p in self.patches) else "meta"

    def measure(self, con) -> dict:
        """Documents and words removed, per patch and combined."""
        out: dict = {"relation": self.relation, "patches": []}
        for p in self.patches:
            rel = "docs" if p.needs_text else "meta"
            d, w = con.execute(
                f"select count(*), coalesce(sum(n_words), 0) from {rel} "
                f"where ({p.selector})").fetchone()
            base_d, base_w = con.execute(
                f"select count(*), coalesce(sum(n_words), 0) from {rel}").fetchone()
            out["patches"].append({
                "id": p.id, "status": p.status, "evaluated_on": rel,
                "documents_removed": d, "words_removed": int(w),
                "document_share": d / base_d if base_d else 0.0,
                "word_share": w / base_w if base_w else 0.0,
                "selector": p.selector, "description": p.description,
            })
        if self.patches:
            rel = self.relation
            d, w = con.execute(
                f"select count(*), coalesce(sum(n_words), 0) from {rel} "
                f"where ({self.combined_selector})").fetchone()
            base_d, base_w = con.execute(
                f"select count(*), coalesce(sum(n_words), 0) from {rel}").fetchone()
            out["combined"] = {
                "documents": base_d, "words": int(base_w),
                "documents_removed": d, "words_removed": int(w),
                "document_share": d / base_d if base_d else 0.0,
                "word_share": w / base_w if base_w else 0.0,
                "note": "not the sum of the patches, which overlap",
            }
        return out

    def write_drop_list(self, con, path: str) -> int:
        """Write the ids the patch set removes, sorted, as Parquet."""
        con.execute(
            f"copy (select id from {self.relation} where ({self.combined_selector}) "
            f"order by id) to '{path}' (format parquet, compression zstd)")
        return con.execute(
            f"select count(*) from {self.relation} "
            f"where ({self.combined_selector})").fetchone()[0]
