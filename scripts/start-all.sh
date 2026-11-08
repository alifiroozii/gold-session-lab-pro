#!/usr/bin/env bash
# ==============================================================================
# Gold Session Lab Pro V3.0 — Comprehensive macOS Startup Script
# Starts FastAPI server locally on 127.0.0.1:8000 in background
# ==============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

echo "🪙 در حال راه‌اندازی آزمایشگاه خودکار طلا (Gold Autonomous Research Lab V3.0)..."

VENV_PATH=".venv"
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ محیط مجازی $VENV_PATH یافت نشد. لطفاً ابتدا اسکریپت نصب را اجرا کنید."
    exit 1
fi

# Ensure port 8000 is not already bound
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo "⚠️ پورت 8000 در حال حاضر اشغال است. در حال بستن سرویس قبلی..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# Set macOS friendly environment
export PYTHONPATH="."
export PYTHONUNBUFFERED=1

# Start server in background
nohup "$VENV_PATH/bin/python" app.py > "data/server.log" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "data/server.pid"

# Wait for server to boot
echo "⏳ در حال انتظار برای برقراری سلامت سرویس..."
for i in {1..10}; do
    if curl -s "http://127.0.0.1:8000/api/broker/account" >/dev/null ; then
        echo "✅ سرور محلی با موفقیت فعال شد!"
        echo "🌐 آدرس داشبورد فارسی: http://127.0.0.1:8000"
        echo "🆔 شناسه پروسس (PID): $SERVER_PID"
        echo "📝 لاگ سرور: data/server.log"
        exit 0
    fi
    sleep 0.5
done

echo "⚠️ سرور پس از ۵ ثانیه پاسخ نداد. لاگ خطا را بررسی کنید:"
tail -n 15 "data/server.log"
exit 1
