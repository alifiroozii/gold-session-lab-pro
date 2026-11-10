#!/usr/bin/env bash
# ==============================================================================
# Gold Session Lab Pro V3.0 — Trigger Loop 6 (Nightly Evaluation & Daily Report)
# ==============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

echo "🌙 در حال اجرای ارزیابی شبانه و تولید گزارش جامع روزانه..."

if curl -s "http://127.0.0.1:8000/api/supervisor/status" >/dev/null 2>&1; then
    curl -s -X POST "http://127.0.0.1:8000/api/supervisor/trigger?cycle_type=NIGHTLY_EVALUATION" | python3 -m json.tool
else
    echo "ℹ️ اجرای مستقیم چرخه ارزیابی شبانه در پایتون..."
    .venv/bin/python -c '
from goldlab.supervisor import ResearchSupervisor
from goldlab.paper_broker import PaperBroker
sup = ResearchSupervisor()
broker = PaperBroker()
res = sup.run_nightly_evaluation(broker)
print("گزارش روزانه با موفقیت در مسیر زیر ثبت شد:")
print(res.get("report_path"))
'
fi
