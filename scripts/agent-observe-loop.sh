#!/usr/bin/env bash
# Local evidence collector for Antigravity. This is NOT an AI agent.
set -euo pipefail
cd "$(dirname "$0")/.."
INTERVAL_SECONDS="${AGENT_OBSERVE_INTERVAL_SECONDS:-300}"
if ! [[ "$INTERVAL_SECONDS" =~ ^[0-9]+$ ]] || (( INTERVAL_SECONDS < 30 )); then
  echo "AGENT_OBSERVE_INTERVAL_SECONDS must be an integer >= 30" >&2
  exit 2
fi
PYTHON="./.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then PYTHON="$(command -v python3)"; fi
if [[ -z "$PYTHON" ]]; then echo "Python 3 is required" >&2; exit 1; fi
mkdir -p agent-work
echo "Observation only; no AI or paper orders triggered. Ctrl+C to stop."
while true; do
  "$PYTHON" -m goldlab.agent_bridge observe
  "$PYTHON" -m goldlab.agent_bridge prepare --output agent-work/REVIEW_TASK.md
  sleep "$INTERVAL_SECONDS"
done
