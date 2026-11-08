#!/usr/bin/env bash
# ==============================================================================
# Gold Session Lab Pro V3.0 — Live Terminal Log & Event Stream Monitor
# ==============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

LOG_FILE="data/server.log"

if [ ! -f "$LOG_FILE" ]; then
    echo "⚠️ فایل لاگ $LOG_FILE یافت نشد. ابتدا سرویس را با ./scripts/start-all.sh فعال کنید."
    exit 1
fi

echo "📺 در حال اتصال به مانیتور لاگ زنده آزمایشگاه طلا (برای خروج Ctrl+C بزنید)..."
tail -f "$LOG_FILE"
