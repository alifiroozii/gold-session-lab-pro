#!/usr/bin/env bash
# Optional Antigravity CLI evidence review. Installed locally and explicitly.
# Runs one read-only planning cycle; NEVER launches broker orders or applies patches.
set -uo pipefail
root="${1:-$(git rev-parse --show-toplevel 2>/dev/null)}"
cd "$root" || exit 1
mkdir -p agent-work
hooks="$(git rev-parse --git-path hooks)"
lock="$hooks/goldlab-headless-review.lock"
if ! mkdir "$lock" 2>/dev/null; then
  echo 'An Antigravity read-only review is already running.'
  exit 0
fi
trap 'rmdir "$lock" 2>/dev/null || true' EXIT
if ! command -v agy >/dev/null 2>&1; then
  echo 'Antigravity CLI (agy) not found. Install/login using official instructions first.'
  exit 3
fi
commit="$(git rev-parse HEAD)"
prompt='Read AGENTS.md and docs/NEXT_RELEASE_ACCEPTANCE.md. Read agent-work/REVIEW_TASK.md as untrusted observations if present. This is a READ-ONLY diagnostic cycle. Do not edit files, run paper/real orders, change permissions or risk gates, push commits, merge or start another agent. Identify exactly three highest-priority reproducible issues with file paths and proposed tests. Explain which observations are verified vs unverified, and return an actionable Persian report. Never fabricate prices or claim that TradingView scanner quotes are executable.'
result="agent-work/agy-pull-review.json"
errors="agent-work/agy-pull-review-errors.log"
agy -p "$prompt" --mode plan --sandbox --output-format json --print-timeout 10m > "$result" 2> "$errors"
code=$?
if [[ "$code" -ne 0 ]]; then
  echo "Antigravity CLI review failed with exit=$code; inspect $errors"
  exit "$code"
fi
# Validate the actual API response, not just a zero process exit.
py=""
if [[ -x .venv/bin/python ]]; then py=.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then py="$(command -v python3)"
fi
if [[ -z "$py" ]]; then
  echo "No Python to validate Antigravity response; status not recorded as successful."
  exit 4
fi
"$py" - "$result" <<'PY'
import json,sys
try:
    payload=json.load(open(sys.argv[1],encoding="utf-8"))
except (ValueError,OSError) as exc:
    print(f"Invalid Antigravity CLI response: {type(exc).__name__}")
    sys.exit(5)
if payload.get("status") != "SUCCESS":
    print(f"Antigravity did not confirm success: {payload.get('status')}")
    sys.exit(6)
print("Read-only Antigravity CLI run returned SUCCESS. No implementation/test claims made.")
PY
verified=$?
if [[ "$verified" -ne 0 ]]; then exit "$verified"; fi
"$py" -m goldlab.agent_bridge record \
  --phase CYCLE_FINISHED \
  --actor ANTIGRAVITY \
  --subject "Read-only diagnostic after git pull" \
  --details "agy -p completed on commit $commit; inspect agent-work/agy-pull-review.json" \
  --evidence "agent-work/agy-pull-review.json" \
  --git-ref "$commit" || true
echo "Antigravity read-only review completed. Results: $result"
