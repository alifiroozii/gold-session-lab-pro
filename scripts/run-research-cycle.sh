#!/usr/bin/env bash
# ==============================================================================
# Gold Session Lab Pro V3.0 — Trigger Loop 4 (Research & Hypothesis Backtest)
# ==============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

echo "🔬 در حال اجرای چرخه پژوهش و ارزیابی فرضیه‌ها (Research Cycle)..."

if curl -s "http://127.0.0.1:8000/api/supervisor/status" >/dev/null 2>&1; then
    curl -s -X POST "http://127.0.0.1:8000/api/supervisor/trigger?cycle_type=RESEARCH_CYCLE" | python3 -m json.tool
    echo "✅ چرخه پژوهش با موفقیت اجرا شد."
else
    echo "ℹ️ سرور زنده در حال اجرا نیست، اجرای مستقیم در محیط پایتون..."
    .venv/bin/python -c '
from goldlab.supervisor import ResearchSupervisor
sup = ResearchSupervisor()
res = sup.run_research_cycle()
print("نتایج چرخه پژوهش آفلاین:", res)
'
fi

# Optional automated historical verification after each research cycle.
# Only run when the operator provides an independently verified CSV.
if [[ -n "${GOLDLAB_STRATEGY_AUDIT_CSV:-}" ]]; then
    echo "🔎 Strategy verification gate (historical signals, not paper-auto certification)"
    if [[ -x ".venv/bin/python" ]]; then PYTHON_BIN=".venv/bin/python"; else PYTHON_BIN="python3"; fi
    "$PYTHON_BIN" -m scripts.verify_strategy "$GOLDLAB_STRATEGY_AUDIT_CSV" --timeframe 5m
else
    echo "STRATEGY_AUDIT_SKIPPED: no provenance-verified historical CSV configured."
fi
