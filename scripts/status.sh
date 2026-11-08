#!/usr/bin/env bash
# ==============================================================================
# Gold Session Lab Pro V3.0 — Service & Database Health Status Inspector
# ==============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

echo "📊 --- وضعیت سیستم آزمایشگاه خودکار طلا (Status Report) ---"

# 1. Check Process & Port
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    PID=$(lsof -ti:8000 | head -n 1)
    echo "🟢 سرور FastAPI فعال است (PID: $PID روی 127.0.0.1:8000)"
else
    echo "🔴 سرور غیرفعال است (پورت 8000 آزاد است)"
fi

# 2. Check Database State
DB_FILE="data/xauusd_lab.sqlite"
if [ -f "$DB_FILE" ]; then
    DB_SIZE=$(du -h "$DB_FILE" | cut -f1)
    echo "💾 دیتابیس SQLite: موجود است (حجم: $DB_SIZE)"
    
    # Check WAL
    if [ -f "${DB_FILE}-wal" ]; then
        WAL_SIZE=$(du -h "${DB_FILE}-wal" | cut -f1)
        echo "📝 ژورنال تراکنش‌ها (WAL): فعال ($WAL_SIZE)"
    fi
else
    echo "⚠️ فایل دیتابیس SQLite هنوز تشکیل نشده است."
fi

# 3. Check Git Status
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "نامشخص")
echo "🌿 شاخه جاری گیت: $CURRENT_BRANCH"

# 4. Check Health Endpoint if running
if curl -s "http://127.0.0.1:8000/api/supervisor/status" >/dev/null 2>&1; then
    CHAMP=$(curl -s "http://127.0.0.1:8000/api/supervisor/status" | grep -o '"name":"[^"]*"' | head -n 1)
    echo "🏆 استراتژی فعال (Champion): $CHAMP"
    echo "✅ ارتباط API و سرپرست پژوهش برقرار است."
fi

echo "--------------------------------------------------------"
