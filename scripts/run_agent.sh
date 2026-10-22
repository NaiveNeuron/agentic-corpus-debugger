#!/usr/bin/env bash
# Run one audit trajectory.  Usage:
#   scripts/run_agent.sh <run-name> [budget] [model] [max-turns] [derived-dir] [language-name]
#
# The agent gets ONLY the MCP audit tools: no bash, no file access, no web.
# Its system prompt replaces the default assistant prompt entirely, so the
# instructions it sees are exactly prompts/auditor_system.md, with the
# language of the corpus in derived-dir substituted (unchanged for Slovak).
# The prompt used is saved as out/runs/<run-name>/system_prompt.md.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v claude >/dev/null 2>&1; then
  cat >&2 <<'MSG'
scripts/run_agent.sh needs the Claude Code CLI on PATH, and credentials for it.

  npm i -g @anthropic-ai/claude-code     # or see anthropic.com/claude-code
  export ANTHROPIC_API_KEY=...           # or log in with `claude`

One run reads a few hundred documents and costs roughly $2-3 at Sonnet prices.
You do not need it to reproduce the paper: the three frozen trajectories, their
findings and their costs are in out/runs/, and every number in the paper is
recomputed from those by scripts/analyze.py.
MSG
  exit 127
fi

RUN="${1:?run name}"
BUDGET="${2:-300}"
MODEL="${3:-sonnet}"
TURNS="${4:-250}"
DERIVED="${5:-data/derived}"
LANG_NAME="${6:-}"

OUT="out/runs/$RUN"
mkdir -p "$OUT"

export AUDIT_DERIVED="$DERIVED"
export AUDIT_BUDGET="$BUDGET"
export AUDIT_LOG="$OUT/tools.jsonl"
export AUDIT_FINDINGS="$OUT/findings"

"$PWD/.venv/bin/python" -m src.corpusaudit.prompt "$DERIVED" \
  ${LANG_NAME:+--name "$LANG_NAME"} > "$OUT/system_prompt.md"

cat > "$OUT/mcp.json" <<JSON
{"mcpServers": {"audit": {"command": "$PWD/.venv/bin/python",
  "args": ["-m", "src.corpusaudit.mcp_server"], "cwd": "$PWD",
  "env": {"AUDIT_DERIVED": "$AUDIT_DERIVED", "AUDIT_BUDGET": "$AUDIT_BUDGET",
          "AUDIT_LOG": "$AUDIT_LOG", "AUDIT_FINDINGS": "$AUDIT_FINDINGS"}}}}
JSON

TOOLS=$(printf 'mcp__audit__%s ' schema aggregate sample_documents inspect_document \
  search_text domain_stats crawl_stats sentence_lid run_detector evaluate_detector save_finding)

echo "[run_agent] $RUN budget=$BUDGET model=$MODEL derived=$DERIVED" >&2
claude -p "Audit this corpus. Begin." \
  --system-prompt "$(cat "$OUT/system_prompt.md")" \
  --mcp-config "$OUT/mcp.json" --strict-mcp-config \
  --allowed-tools $TOOLS \
  --disallowed-tools Bash Read Write Edit MultiEdit Glob Grep WebFetch WebSearch Task TodoWrite NotebookEdit \
  --model "$MODEL" --max-turns "$TURNS" \
  --permission-mode bypassPermissions \
  --output-format stream-json --verbose --include-partial-messages \
  > "$OUT/stream.jsonl" 2> "$OUT/stderr.log" || echo "[run_agent] claude exited $?" >&2

python3 - "$OUT" <<'PY'
import json, sys, pathlib
out = pathlib.Path(sys.argv[1])
res = None
for line in (out / "stream.jsonl").read_text().splitlines():
    try:
        m = json.loads(line)
    except json.JSONDecodeError:
        continue
    if m.get("type") == "result":
        res = m
if res:
    keep = {k: res.get(k) for k in ("subtype", "num_turns", "duration_ms", "total_cost_usd", "usage")}
    (out / "cost.json").write_text(json.dumps(keep, indent=2))
    print("[run_agent] cost:", json.dumps(keep.get("total_cost_usd")), "turns:", keep.get("num_turns"))
PY
echo "[run_agent] findings: $(ls "$OUT/findings" 2>/dev/null | wc -l)" >&2
