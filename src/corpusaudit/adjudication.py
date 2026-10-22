"""Read the human adjudication decisions and map them onto findings.

Decisions are recorded per *group* of candidate findings (groups are formed
mechanically by document-set overlap, see ``scripts/build_adjudication.py``).
A row whose key is a finding id instead of a group id overrides that finding,
so a human can split a group after the fact.
"""

from __future__ import annotations

import csv
import pathlib

VALID = {"approve", "reject", "unsure"}


def load_decisions(
    adjudication_dir: str = "out/adjudication",
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Return (decision_by_finding, note_by_finding, group_by_finding)."""
    d = pathlib.Path(adjudication_dir)
    groups_path, dec_path = d / "groups.csv", d / "decisions.csv"
    if not groups_path.exists() or not dec_path.exists():
        return {}, {}, {}

    group_of: dict[str, str] = {}
    members: dict[str, list[str]] = {}
    for row in csv.DictReader(open(groups_path)):
        group_of[row["finding"]] = row["group"]
        members.setdefault(row["group"], []).append(row["finding"])

    decisions: dict[str, str] = {}
    notes: dict[str, str] = {}
    overrides: dict[str, tuple[str, str]] = {}
    bad_words: list[tuple[str, str]] = []
    bad_keys: list[str] = []
    for row in csv.DictReader(open(dec_path)):
        key = (row.get("group") or "").strip()
        dec = (row.get("decision") or "").strip().lower()
        # An empty decision means "not yet adjudicated" -- that is how the sheet
        # ships. A *non-empty* value outside the vocabulary is a typo, and skipping
        # it silently would demote an approved finding to `candidate` and make the
        # paper understate its own validation. Likewise a mistyped group id would
        # become an override for a finding that does not exist.
        if not key:
            continue
        if dec and dec not in VALID:
            bad_words.append((key, dec))
            continue
        if key not in members and key not in group_of:
            bad_keys.append(key)
            continue
        if not dec:
            continue
        note = (row.get("note") or "").strip()
        if key in members:
            for finding in members[key]:
                decisions[finding] = dec
                notes[finding] = note
        else:  # a per-finding override row
            overrides[key] = (dec, note)
    if bad_words or bad_keys:
        problems = []
        if bad_words:
            problems.append(
                f"{len(bad_words)} row(s) use a decision outside {sorted(VALID)}: "
                f"{bad_words[:4]}")
        if bad_keys:
            problems.append(
                f"{len(bad_keys)} row(s) name neither a group nor a finding: "
                f"{bad_keys[:4]}")
        raise SystemExit(
            f"{dec_path} is malformed; a silent skip would understate validation.\n  "
            + "\n  ".join(problems))
    for finding, (dec, note) in overrides.items():
        decisions[finding] = dec
        notes[finding] = note
    return decisions, notes, group_of
