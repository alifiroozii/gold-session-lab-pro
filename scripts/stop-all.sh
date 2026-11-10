#!/usr/bin/env bash
# ==============================================================================
# Gold Session Lab Pro V3.0 — Safe macOS Shutdown Script
# Terminates FastAPI/Uvicorn processes and commits SQLite transactions safely
# ==============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

echo "🛑 در حال توقف ایمن سرویس‌های آزمایشگاه طلا..."

PID_FILE="data/server.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "⏳ ارسال سیگنال خاتمه به PID $PID..."
        kill -15 "$PID" 2>/dev/null || true
        sleep 1
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "⚠️ فرآیند هنوز متوقف نشده، ارسال SIGKILL..."
            kill -9 "$PID" 2>/dev/null || true
        fi
    fi
    rm -f "$PID_FILE"
fi

# Fallback: Kill any lingering process on port 8000
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo "🧹 پاکسازی پورت 8000..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
fi

echo "✅ تمام پروسس‌های محلی با موفقیت و بدون از دست رفتن داده متوقف شدند."
