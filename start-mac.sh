#!/bin/bash
# ==============================================================================
# Gold Session Lab Pro — macOS Local Launch Script
# Runs strictly on macOS locally at 127.0.0.1:8000
# ==============================================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "--------------------------------------------------------"
echo "🪙 Gold Session Lab Pro — راه‌اندازی محلی پلتفرم طلا (macOS)"
echo "--------------------------------------------------------"

# 1. Check Virtual Environment
if [ ! -d ".venv" ]; then
    echo "⚙️ در حال ایجاد محیط مجازی Python..."
    if command -v python3.11 &>/dev/null; then
        python3.11 -m venv .venv
    else
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    echo "📦 نصب وابستگی‌های پایتون..."
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

# 2. Check Data
mkdir -p data output
if [ ! -f "data/demo_xauusd_1m.csv" ]; then
    echo "📊 در حال تولید داده‌های تستی استاندارد طلا..."
    .venv/bin/python -c "
import numpy as np, pandas as pd
from datetime import datetime, timedelta, timezone
np.random.seed(42)
start_dt = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)
records = []
p = 2650.0
for m in range(5000):
    dt = start_dt + timedelta(minutes=m)
    vol = 0.7 if 7 <= dt.hour < 18 else 0.25
    delta = np.random.normal(0, vol)
    o = p
    c = round(o + delta, 2)
    h = round(max(o, c) + abs(np.random.normal(0, vol * 0.5)), 2)
    l = round(min(o, c) - abs(np.random.normal(0, vol * 0.5)), 2)
    records.append({'timestamp': dt.isoformat(), 'open': o, 'high': h, 'low': l, 'close': c, 'volume': int(np.random.uniform(50, 300))})
    p = c
pd.DataFrame(records).to_csv('data/demo_xauusd_1m.csv', index=False)
"
fi

# 3. Stop previous instance if running
if [ -f ".server.pid" ]; then
    OLD_PID=$(cat .server.pid)
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "🛑 متوقف‌سازی فرآیند قبلی با PID: $OLD_PID"
        kill -15 "$OLD_PID" 2>/dev/null || true
        sleep 1
    fi
    rm -f .server.pid
fi

# 4. Start Server
echo "🚀 در حال اجرای سرور محلی روی 127.0.0.1:8000..."
nohup .venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000 > output/server.log 2>&1 &
SERVER_PID=$!
echo $SERVER_PID > .server.pid

# 5. Wait for readiness
echo "⏳ در حال بررسی سلامت سرویس..."
READY=0
for i in {1..15}; do
    if curl -s http://127.0.0.1:8000/api/market > /dev/null; then
        READY=1
        break
    fi
    sleep 1
done

if [ $READY -eq 1 ]; then
    echo "✅ سرور با موفقیت در آدرس زیر آماده خدمت‌رسانی است:"
    echo "🔗 http://127.0.0.1:8000"
    echo "💡 لاگ‌های سرور در output/server.log ذخیره می‌شوند."
    echo "🛑 برای توقف برنامه از دستور ./stop-mac.sh استفاده کنید."
    
    # Open browser on macOS
    if command -v open &>/dev/null; then
        open "http://127.0.0.1:8000"
    fi
else
    echo "❌ خطا در راه‌اندازی سرور! بررسی لاگ‌ها:"
    cat output/server.log
    exit 1
fi
