"""Comprehensive Optimization Experiment Pipeline
Runs Stage 3, Stage 4, Stage 5 experiments in MetaTrader 5 Strategy Tester.
"""
import csv
import json
import os
from pathlib import Path
import sys
import time

sys.path.append(str(Path(__file__).resolve().parent.parent))
from research.run_optimization_suite import run_mt5_test

OUTPUT_DIR = Path("/Users/alifiroozi/ali/gold-session-mt5-research/research/output/optimization")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
META_DIR = Path("/Users/alifiroozi/ali/METATRADER5")

def save_csv(filename: str, rows: list, fieldnames: list):
    for target in [OUTPUT_DIR, META_DIR]:
        target.mkdir(parents=True, exist_ok=True)
        p = target / filename
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
    print(f"Saved {filename} ({len(rows)} rows)")

def run_remaining_experiments():
    # Define Champion Configurations based on Stage 2 discoveries
    # 1. Balanced Original: London 08-09, Candle>=0.45, BOS/Trend
    bal_orig_params = {"ModelChoice": 0, "LotMode": 0, "FixedLot": 0.10}
    
    # 2. Heavy Original: London 08-09, FVG, BOS, Vol>=1.10
    hvy_orig_params = {"ModelChoice": 1, "LotMode": 0, "FixedLot": 0.10}
    
    # 3. Balanced Optimized: London 08-10 Window (boosted net profit to $2,134.2, DD 31.15%)
    bal_opt_params = {
        "ModelChoice": 2,
        "LotMode": 0,
        "FixedLot": 0.10,
        "TimeWindow": 1, # WINDOW_08_10
    }
    
    # 4. Heavy Optimized: London 08-10 Window + ATR Bounds (0.50-2.50) + FVG>=0.35
    hvy_opt_params = {
        "ModelChoice": 3,
        "LotMode": 0,
        "FixedLot": 0.10,
        "TimeWindow": 1, # WINDOW_08_10
        "OptUseAtrFilter": True,
        "OptMinAtrRatio": 0.50,
        "OptMaxAtrRatio": 2.50,
        "OptVolumeRatioMin": 1.10,
        "OptFvgMinSize": 0.35,
    }
    
    # 5. Hybrid Model: Heavy prioritized, then Balanced (London 08-10)
    hybrid_params = {
        "ModelChoice": 4,
        "LotMode": 0,
        "FixedLot": 0.10,
        "TimeWindow": 1,
        "OptUseAtrFilter": True,
        "OptMinAtrRatio": 0.50,
        "OptMaxAtrRatio": 2.50,
        "OptVolumeRatioMin": 1.10,
        "OptFvgMinSize": 0.35,
    }

    # ================= STAGE 3: DYNAMIC CAPITAL MANAGEMENT =================
    print("\n================== STAGE 3: DYNAMIC CAPITAL MANAGEMENT ==================")
    risk_percentages = [0.25, 0.50, 1.00, 1.50, 2.00]
    stage3_results = []
    
    # Benchmarks (Fixed 0.10 Lot)
    res_bal_fix = run_mt5_test("Stage3_Bal_Fixed010", bal_opt_params)
    stage3_results.append({
        "Model": "Balanced Optimized",
        "SizingMode": "Fixed Lot 0.10",
        "RiskPct": "Fixed 0.10 Lot",
        "Trades": res_bal_fix["trades"],
        "NetProfit": res_bal_fix["net_profit"],
        "ProfitFactor": res_bal_fix["profit_factor"],
        "MaxDrawdownPct": res_bal_fix["max_drawdown_pct"],
        "WinRate": res_bal_fix["win_rate"],
        "ExpectedPayoff": res_bal_fix["expected_payoff"],
    })
    
    res_hvy_fix = run_mt5_test("Stage3_Hvy_Fixed010", hvy_opt_params)
    stage3_results.append({
        "Model": "Heavy Optimized",
        "SizingMode": "Fixed Lot 0.10",
        "RiskPct": "Fixed 0.10 Lot",
        "Trades": res_hvy_fix["trades"],
        "NetProfit": res_hvy_fix["net_profit"],
        "ProfitFactor": res_hvy_fix["profit_factor"],
        "MaxDrawdownPct": res_hvy_fix["max_drawdown_pct"],
        "WinRate": res_hvy_fix["win_rate"],
        "ExpectedPayoff": res_hvy_fix["expected_payoff"],
    })
    
    for r_pct in risk_percentages:
        # Dynamic on Balanced Optimized
        run_id_bal = f"Stage3_Bal_Risk_{str(r_pct).replace('.', '_')}"
        p_bal = dict(bal_opt_params)
        p_bal["LotMode"] = 1
        p_bal["RiskPerTradePct"] = r_pct
        print(f"Testing Balanced with Dynamic Risk {r_pct}%...")
        res_bal = run_mt5_test(run_id_bal, p_bal)
        stage3_results.append({
            "Model": "Balanced Optimized",
            "SizingMode": "Dynamic Risk (Equity)",
            "RiskPct": f"{r_pct}%",
            "Trades": res_bal["trades"],
            "NetProfit": res_bal["net_profit"],
            "ProfitFactor": res_bal["profit_factor"],
            "MaxDrawdownPct": res_bal["max_drawdown_pct"],
            "WinRate": res_bal["win_rate"],
            "ExpectedPayoff": res_bal["expected_payoff"],
        })
        print(f"-> Balanced Risk {r_pct}%: Trades={res_bal['trades']}, Net=${res_bal['net_profit']:.1f}, DD={res_bal['max_drawdown_pct']}%")
        
        # Dynamic on Heavy Optimized
        run_id_hvy = f"Stage3_Hvy_Risk_{str(r_pct).replace('.', '_')}"
        p_hvy = dict(hvy_opt_params)
        p_hvy["LotMode"] = 1
        p_hvy["RiskPerTradePct"] = r_pct
        print(f"Testing Heavy Optimized with Dynamic Risk {r_pct}%...")
        res_hvy = run_mt5_test(run_id_hvy, p_hvy)
        stage3_results.append({
            "Model": "Heavy Optimized",
            "SizingMode": "Dynamic Risk (Equity)",
            "RiskPct": f"{r_pct}%",
            "Trades": res_hvy["trades"],
            "NetProfit": res_hvy["net_profit"],
            "ProfitFactor": res_hvy["profit_factor"],
            "MaxDrawdownPct": res_hvy["max_drawdown_pct"],
            "WinRate": res_hvy["win_rate"],
            "ExpectedPayoff": res_hvy["expected_payoff"],
        })
        print(f"-> Heavy Risk {r_pct}%: Trades={res_hvy['trades']}, Net=${res_hvy['net_profit']:.1f}, DD={res_hvy['max_drawdown_pct']}%")
        
    s3_fields = ["Model", "SizingMode", "RiskPct", "Trades", "NetProfit", "ProfitFactor", "MaxDrawdownPct", "WinRate", "ExpectedPayoff"]
    save_csv("stage3_dynamic_sizing_results.csv", stage3_results, s3_fields)

    # ================= STAGE 4 & 5: FINAL 5-MODEL HEAD-TO-HEAD COMPARISON =================
    print("\n================== STAGE 4 & 5: 5-MODEL HEAD-TO-HEAD COMPARISON ==================")
    models = [
        ("Balanced_Original", "1. Balanced Original", bal_orig_params),
        ("Heavy_Original", "2. Heavy Original", hvy_orig_params),
        ("Balanced_Optimized", "3. Balanced Optimized", bal_opt_params),
        ("Heavy_Optimized", "4. Heavy Optimized", hvy_opt_params),
        ("Hybrid_Model", "5. Hybrid (Balanced + Heavy)", hybrid_params),
    ]
    
    stage5_comparison = []
    walk_forward_rows = []
    
    for m_id, m_name, m_params in models:
        print(f"\nEvaluating {m_name} across Full Period, In-Sample 2025, and Out-of-Sample 2026...")
        # Full Period (2025.01.01 - 2026.11.09)
        res_full = run_mt5_test(f"Comp_{m_id}_Full", m_params, from_date="2025.01.01", to_date="2026.11.09")
        
        # In-Sample (2025.01.01 - 2025.12.31)
        res_in = run_mt5_test(f"Comp_{m_id}_InSample2025", m_params, from_date="2025.01.01", to_date="2025.12.31")
        
        # Out-of-Sample (2026.01.01 - 2026.11.09)
        res_out = run_mt5_test(f"Comp_{m_id}_OutSample2026", m_params, from_date="2026.01.01", to_date="2026.11.09")
        
        stage5_comparison.append({
            "Model": m_name,
            "Full_Trades": res_full["trades"],
            "Full_NetProfit": res_full["net_profit"],
            "Full_WinRate": res_full["win_rate"],
            "Full_ProfitFactor": res_full["profit_factor"],
            "Full_MaxDrawdownPct": res_full["max_drawdown_pct"],
            "Full_Sharpe": res_full["sharpe_ratio"],
            "InSample2025_NetProfit": res_in["net_profit"],
            "InSample2025_WinRate": res_in["win_rate"],
            "InSample2025_PF": res_in["profit_factor"],
            "InSample2025_DD": res_in["max_drawdown_pct"],
            "OutSample2026_NetProfit": res_out["net_profit"],
            "OutSample2026_WinRate": res_out["win_rate"],
            "OutSample2026_PF": res_out["profit_factor"],
            "OutSample2026_DD": res_out["max_drawdown_pct"],
        })
        
        walk_forward_rows.append({
            "Model": m_name,
            "Period": "Full (2025-2026)",
            "Trades": res_full["trades"],
            "NetProfit": res_full["net_profit"],
            "WinRate": res_full["win_rate"],
            "ProfitFactor": res_full["profit_factor"],
            "MaxDrawdownPct": res_full["max_drawdown_pct"],
            "Sharpe": res_full["sharpe_ratio"],
        })
        walk_forward_rows.append({
            "Model": m_name,
            "Period": "In-Sample (2025)",
            "Trades": res_in["trades"],
            "NetProfit": res_in["net_profit"],
            "WinRate": res_in["win_rate"],
            "ProfitFactor": res_in["profit_factor"],
            "MaxDrawdownPct": res_in["max_drawdown_pct"],
            "Sharpe": res_in["sharpe_ratio"],
        })
        walk_forward_rows.append({
            "Model": m_name,
            "Period": "Out-of-Sample (2026)",
            "Trades": res_out["trades"],
            "NetProfit": res_out["net_profit"],
            "WinRate": res_out["win_rate"],
            "ProfitFactor": res_out["profit_factor"],
            "MaxDrawdownPct": res_out["max_drawdown_pct"],
            "Sharpe": res_out["sharpe_ratio"],
        })
        
    s5_fields = [
        "Model", "Full_Trades", "Full_NetProfit", "Full_WinRate", "Full_ProfitFactor", "Full_MaxDrawdownPct", "Full_Sharpe",
        "InSample2025_NetProfit", "InSample2025_WinRate", "InSample2025_PF", "InSample2025_DD",
        "OutSample2026_NetProfit", "OutSample2026_WinRate", "OutSample2026_PF", "OutSample2026_DD"
    ]
    save_csv("stage5_five_model_comparison.csv", stage5_comparison, s5_fields)
    
    wf_fields = ["Model", "Period", "Trades", "NetProfit", "WinRate", "ProfitFactor", "MaxDrawdownPct", "Sharpe"]
    save_csv("stage5_walk_forward_detail.csv", walk_forward_rows, wf_fields)
    print("\nALL OPTIMIZATION EXPERIMENTS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    run_remaining_experiments()
