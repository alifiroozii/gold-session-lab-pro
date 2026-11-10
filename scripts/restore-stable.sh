#!/usr/bin/env bash
# ==============================================================================
# Gold Session Lab Pro V3.0 — Emergency Rollback to Baseline Snapshot
# ==============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

echo "⚠️ --- عملیات بازیابی اضطراری وضعیت پایدار (Rollback to Stable) ---"
echo "این اسکریپت در صورت بروز ناپایداری یا تغییرات ناموفق کد، وضعیت را به برچسب مبنا بازمی‌گرداند."

SNAPSHOT_TAG="snapshot-v1-baseline"

read -p "آیا از بازگردانی وضعیت به تگ مبنا ($SNAPSHOT_TAG) اطمینان دارید؟ [y/N]: " -r confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "عملیات لغو شد."
    exit 0
fi

# Stop running services
./scripts/stop-all.sh || true

# Stash current uncommitted changes
git stash save "Emergency-Stash-$(date +%Y%m%d-%H%M%S)" || true

# Checkout clean baseline files
echo "🔄 بازگردانی فایل‌های اصلی به تگ $SNAPSHOT_TAG..."
git checkout "$SNAPSHOT_TAG" -- goldlab/ app.py

echo "✅ بازگردانی با موفقیت انجام شد. وضعیت سیستم پایدار است."
