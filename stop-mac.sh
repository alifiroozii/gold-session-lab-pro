#!/bin/bash
# ==============================================================================
# Gold Session Lab Pro — macOS Local Shutdown Script
# ==============================================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "🛑 در حال توقف سرویس‌های محلی Gold Session Lab Pro..."

if [ -f ".server.pid" ]; then
    PID=$(cat .server.pid)
    if ps -p "$PID" > /dev/null 2>&1; then
        kill -15 "$PID" 2>/dev/null || true
        echo "✅ فرآیند با شناسه $PID با موفقیت متوقف شد."
    else
        echo "ℹ️ فرآیند با شناسه $PID در حال اجرا نبود."
    fi
    rm -f .server.pid
fi

# Double check port 8000
PIDS=$(lsof -ti :8000 2>/dev/null || true)
if [ -n "$PIDS" ]; then
    echo "⚠️ آزادسازی پورت 8000 (PIDs: $PIDS)..."
    kill -9 $PIDS 2>/dev/null || true
fi

echo "✨ تمامی سرویس‌های برنامه با موفقیت متوقف شدند."
