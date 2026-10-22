#!/usr/bin/env python
"""Turn one audit run's findings into candidate corpus tests.

    python scripts/findings_to_tests.py out/runs/<run> [--out tests]

Each finding in ``<run>/findings/`` becomes ``tests/<scope>/<id>.yaml`` with
``status: candidate``: the agent measured it, but no person has validated it
yet. The assertion lets the selected share grow by at most 20% over the
prevalence the agent measured; the agent's own wording is kept as evidence.
Validate a sample of each slice by hand before calling a test accepted.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import yaml


def write_candidate_tests(run: str, out: str = "tests") -> list[pathlib.Path]:
    """Write one candidate test per finding of ``run``; return the paths written."""
    written = []
    for path in sorted(pathlib.Path(run, "findings").glob("*.yaml")):
        f = yaml.safe_load(path.read_text())
        evidence = dict(f.get("evidence") or {})
        if f.get("assertion"):
            evidence["agent_assertion"] = f["assertion"]
        threshold = max(float(evidence["prevalence"]) * 1.2, 1e-6)
        test = {
            "id": f["id"],
            "scope": f["scope"],
            "status": "candidate",
            "description": " ".join(str(f["description"]).split()),
            "selector": f["selector"],
            "assertion": f"prevalence <= {threshold:.8f}",
            "discovered_by": "agent",
            "found_in_runs": [pathlib.Path(run).name],
            "evidence": evidence,
        }
        dest = pathlib.Path(out, f["scope"], f"{f['id']}.yaml")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(yaml.safe_dump(test, sort_keys=False, allow_unicode=True))
        written.append(dest)
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", help="an audit run directory, e.g. out/runs/hun_Latn_1")
    ap.add_argument("--out", default="tests")
    args = ap.parse_args()
    paths = write_candidate_tests(args.run, args.out)
    for p in paths:
        print(p)
    if not paths:
        print(f"no findings in {args.run}/findings", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
