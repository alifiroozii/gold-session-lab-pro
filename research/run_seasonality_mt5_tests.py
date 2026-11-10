"""MetaTrader 5 Real Execution for Day-of-Week Seasonality Filters
Runs Heavy Champion and Balanced Champion under Day-of-Week filters.
"""
import csv
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
from research.run_optimization_suite import run_mt5_test

OUTPUT_DIR = Path("/Users/alifiroozi/ali/gold-session-mt5-research/research/output/optimization")
META_DIR = Path("/Users/alifiroozi/ali/METATRADER5")

def main():
    # Base champion parameters
    hvy_params = {
        "ModelChoice": 3, # MODEL_HEAVY_OPTIMIZED
        "LotMode": 0,
        "FixedLot": 0.10,
        "TimeWindow": 1, # WINDOW_08_10
        "OptUseAtrFilter": True,
        "OptMinAtrRatio": 0.50,
        "OptMaxAtrRatio": 2.50,
        "OptVolumeRatioMin": 1.10,
        "OptFvgMinSize": 0.35,
    }
    
    bal_params = {
        "ModelChoice": 2, # MODEL_BALANCED_OPTIMIZED
        "LotMode": 0,
        "FixedLot": 0.10,
        "TimeWindow": 1, # WINDOW_08_10
    }

    test_configs = [
        # Heavy Model Tests
        ("Test_Hvy_Baseline", dict(hvy_params, DayFilter=0), "2025.01.01", "2026.11.09", "Heavy Baseline (All Days)", "Full 2025-2026"),
        ("Test_Hvy_NoFriday", dict(hvy_params, DayFilter=1), "2025.01.01", "2026.11.09", "Heavy No-Friday (Mon-Thu)", "Full 2025-2026"),
        ("Test_Hvy_Core_TueThu", dict(hvy_params, DayFilter=2), "2025.01.01", "2026.11.09", "Heavy Core (Tue-Wed-Thu)", "Full 2025-2026"),
        
        # Heavy Out-of-Sample 2026 Verification
        ("Test_Hvy_Baseline_2026", dict(hvy_params, DayFilter=0), "2026.01.01", "2026.11.09", "Heavy Baseline", "OOS 2026"),
        ("Test_Hvy_NoFriday_2026", dict(hvy_params, DayFilter=1), "2026.01.01", "2026.11.09", "Heavy No-Friday", "OOS 2026"),
        ("Test_Hvy_Core_2026", dict(hvy_params, DayFilter=2), "2026.01.01", "2026.11.09", "Heavy Core (Tue-Thu)", "OOS 2026"),

        # Balanced Model Tests
        ("Test_Bal_Baseline", dict(bal_params, DayFilter=0), "2025.01.01", "2026.11.09", "Balanced Baseline", "Full 2025-2026"),
        ("Test_Bal_NoMonday", dict(bal_params, DayFilter=3), "2025.01.01", "2026.11.09", "Balanced No-Monday", "Full 2025-2026"),
        ("Test_Bal_NoMonday_2026", dict(bal_params, DayFilter=3), "2026.01.01", "2026.11.09", "Balanced No-Monday", "OOS 2026"),
    ]

    results = []
    print("\n================== RUNNING MT5 STRATEGY TESTER SEASONALITY TESTS ==================")
    for run_id, overrides, from_d, to_d, label, period in test_configs:
        print(f"\n>>> Running {run_id} ({label} | {period})...")
        res = run_mt5_test(run_id, overrides, from_date=from_d, to_date=to_d)
        row = {
            "run_id": run_id,
            "model_variant": label,
            "period": period,
            "trades": res.get("trades", 0),
            "net_profit_usd": res.get("net_profit", 0.0),
            "profit_factor": res.get("profit_factor", 0.0),
            "max_drawdown_usd": res.get("max_drawdown_usd", 0.0),
            "max_drawdown_pct": res.get("max_drawdown_pct", 0.0),
            "win_rate_pct": res.get("win_rate", 0.0),
            "sharpe_ratio": res.get("sharpe_ratio", 0.0),
            "expected_payoff": res.get("expected_payoff", 0.0)
        }
        results.append(row)
        print(f"    Trades: {row['trades']} | Net Profit: ${row['net_profit_usd']:.2f} | PF: {row['profit_factor']:.2f} | Max DD: {row['max_drawdown_pct']:.2f}% | WinRate: {row['win_rate_pct']:.1f}%")

    fieldnames = list(results[0].keys())
    for target in [OUTPUT_DIR, META_DIR]:
        target.mkdir(parents=True, exist_ok=True)
        with open(target / "seasonality_mt5_live_backtest_results.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(results)
    print("\nSuccessfully saved seasonality_mt5_live_backtest_results.csv!")

if __name__ == "__main__":
    main()
