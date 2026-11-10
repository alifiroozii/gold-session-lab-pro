"""Historical signal integrity check. Does not enable real/paper trading.

Usage: python -m scripts.verify_strategy data/your_verified_xauusd_1m.csv --timeframe 5m
The input provenance must be independently verified before drawing conclusions.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from goldlab.engine import ResearchEngine
from goldlab.strategy_verification import audit_point_in_time, verify_signal_contract


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed XAUUSD strategy audit")
    parser.add_argument("csv", type=Path, help="Existing historical OHLCV CSV file")
    parser.add_argument("--timeframe", default="5m", choices=["1m", "5m", "15m", "30m", "1h"])
    parser.add_argument("--max-signals", type=int, default=12)
    parser.add_argument("--output", type=Path, default=Path("reports/STRATEGY_VALIDATION.json"))
    args = parser.parse_args()
    if not args.csv.is_file():
        parser.error(f"CSV file not found: {args.csv}")
    with tempfile.TemporaryDirectory(prefix="goldlab-strategy-audit-") as work:
        engine = ResearchEngine(db_path=str(Path(work) / "audit.sqlite"))
        engine.load_from_csv(args.csv, timeframe=args.timeframe)
        summary = engine.run_pipeline()
        contract = verify_signal_contract(engine.current_candles, engine.signals)
        temporal = audit_point_in_time(engine, max_signals=args.max_signals)
    result = {
        "dataset": str(args.csv),
        "data_provenance_verified": False,
        "strategy_profitable": None,
        "authorizes_paper_auto": False,
        "timeframe": args.timeframe,
        "trades_in_backtest": summary.total_trades,
        "signal_contract": contract,
        "point_in_time": temporal,
        "outcome": (
            "FAIL" if "FAIL" in (contract["status"], temporal["status"])
            else "INSUFFICIENT_EVIDENCE" if not engine.signals
            else "STRUCTURAL_CHECKS_ONLY"
        ),
        "limitations": (
            "Does not prove profitability, market-data provenance, tradeable quotes, "
            "bid/ask execution or forward-testing performance."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 2 if result["outcome"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
