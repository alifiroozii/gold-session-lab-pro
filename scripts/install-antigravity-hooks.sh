#!/usr/bin/env bash
# Opt-in per-clone Git hooks for Antigravity workspace handoff on pull/merge/rebase.
# Run once from a trusted local clone: bash scripts/install-antigravity-hooks.sh
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
cd "$root"
hooks="$(git rev-parse --git-path hooks)"
mkdir -p "$hooks"
managed="# goldlab-managed-antigravity-hook"
for hook in post-merge post-rewrite; do
  file="$hooks/$hook"
  if [[ -e "$file" ]] && ! grep -Fq "$managed" "$file"; then
    printf 'Refusing to overwrite existing hook: %s\n' "$file" >&2
    printf 'Manually integrate the GoldLab handoff with your existing hook.\n' >&2
    exit 2
  fi
done
# A copy remains outside the repository files, so updating the remote branch
# does not immediately replace arbitrary code executed by Git hooks.
cp "$root/scripts/antigravity-after-pull.sh" "$hooks/goldlab-agent-sync.sh"
chmod 700 "$hooks/goldlab-agent-sync.sh"
if [[ "${1:-}" == "--with-agent" ]]; then
  if ! command -v agy >/dev/null 2>&1; then
    echo "Antigravity CLI agy is not installed; hooks installed without headless AI."
    rm -f "$hooks/goldlab-agent-headless-enabled"
  else
    cp "$root/scripts/antigravity-headless-review.sh" "$hooks/goldlab-agent-headless-review.sh"
    chmod 700 "$hooks/goldlab-agent-headless-review.sh"
    touch "$hooks/goldlab-agent-headless-enabled"
    echo "Opted in to one read-only agy -p review after each git pull/rebase."
  fi
else
  rm -f "$hooks/goldlab-agent-headless-enabled"
fi
for hook in post-merge post-rewrite; do
  cat > "$hooks/$hook" <<'HOOK'
#!/bin/sh
# goldlab-managed-antigravity-hook
git_dir="$(git rev-parse --git-path hooks)"
if [ -f "$git_dir/goldlab-agent-sync.sh" ]; then
  /bin/bash "$git_dir/goldlab-agent-sync.sh" || true
fi
exit 0
HOOK
  chmod 700 "$hooks/$hook"
done
echo 'Antigravity handoff hooks installed for this local clone.'
echo 'After git pull (merge/rebase), a task snapshot is generated, and on macOS the Antigravity app may open if installed.'
echo 'Opening an IDE alone is not evidence of an active agent.'
echo 'Use --with-agent only after installing and authenticating official Antigravity CLI.'
echo 'The optional CLI run is read-only; it does not deploy changes or activate PAPER_AUTO.'
