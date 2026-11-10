#!/usr/bin/env bash
# Local workspace sync triggered by an explicitly installed Git hook.
# This does NOT autonomously connect a model or allow code modification.
set -u
root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$root" || exit 0
mkdir -p agent-work
stamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
commit="$(git rev-parse --short HEAD 2>/dev/null || printf unknown)"
{
  printf '# Antigravity git-pull handoff\n\n'
  printf 'Updated UTC: %s\n' "$stamp"
  printf 'Current commit: %s\n' "$commit"
  printf 'Action: Open this workspace in Antigravity and inspect `AGENTS.md` and `agent-work/REVIEW_TASK.md`.\n'
  printf 'Status: Workspace prepared only; AI execution not verified.\n'
} > agent-work/PULL_SYNC_STATUS.md
py=""
if [[ -x .venv/bin/python ]]; then
  py=.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then
  py="$(command -v python3)"
fi
if [[ -n "$py" ]]; then
  "$py" -m goldlab.agent_bridge observe >> agent-work/pull-hook.log 2>&1 || true
  "$py" -m goldlab.agent_bridge prepare >> agent-work/pull-hook.log 2>&1 || true
fi
if [[ "$(uname -s)" == "Darwin" && "${GOLDLAB_OPEN_ANTIGRAVITY:-1}" == "1" ]]; then
  if open -Ra "Antigravity" >/dev/null 2>&1; then
    open -a "Antigravity" "$root" >/dev/null 2>&1 || true
  elif open -Ra "Google Antigravity" >/dev/null 2>&1; then
    open -a "Google Antigravity" "$root" >/dev/null 2>&1 || true
  fi
fi
hooks="$(git rev-parse --git-path hooks)"
if [[ -f "$hooks/goldlab-agent-headless-enabled" && -f "$hooks/goldlab-agent-headless-review.sh" ]]; then
  # Explicit opt-in set at installation time. No direct code edits or trading.
  nohup /bin/bash "$hooks/goldlab-agent-headless-review.sh" "$root" \
    >> "$root/agent-work/agy-headless-supervisor.log" 2>&1 < /dev/null &
  printf '[goldlab] Started optional read-only agy CLI review; results are recorded only after verification.\n'
fi
printf '[goldlab] Synced Antigravity handoff at commit %s; agent activity NOT automatically started.\n' "$commit"
