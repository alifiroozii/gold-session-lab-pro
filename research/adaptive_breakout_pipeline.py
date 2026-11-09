"""ADAPTIVE BREAKOUT PIPELINE
Full 2025-2026 Evaluation, Multi-Stage Breakout Classification & Comparative Analysis
"""
import csv
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

MT5_DIR = Path("/Users/alifiroozi/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5")
WINE_BIN = Path("/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine64")
WINEPREFIX = Path("/Users/alifiroozi/Library/Application Support/net.metaquotes.wine.metatrader5")
COMMON_FILES = Path("/Users/alifiroozi/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/alifiroozi/AppData/Roaming/MetaQuotes/Terminal/Common/Files")
OUTPUT_DIR = Path("/Users/alifiroozi/ali/gold-session-mt5-research/research/output")
META_DIR = Path("/Users/alifiroozi/ali/METATRADER5")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
META_DIR.mkdir(parents=True, exist_ok=True)

def run_adaptive_test(ini_name: str, overrides: dict, from_date="2025.01.01", to_date="2026.11.09") -> dict:
    set_lines = [
        f"ExpectedSymbol=XAUUSD_o",
        f"ServerClock=2",
        f"Reference=1",
        f"LotMode={overrides.get('LotMode', 0)}",
        f"FixedLot={overrides.get('FixedLot', 0.10)}",
        f"EngineMode={overrides.get('EngineMode', 7)}",
        f"RiskPerTradePct={overrides.get('RiskPerTradePct', 3.0)}",
        f"DailyLossLimitPct=6.0",
        f"TargetRR=1.5",
        f"MaxRangeWidth={overrides.get('MaxRangeWidth', 30.0)}",
        f"MinStopBps=5.8",
    ]
    set_content = "\n".join(set_lines) + "\n"
    set_file = MT5_DIR / "MQL5" / "Profiles" / "Tester" / f"{ini_name}.set"
    set_file.write_text(set_content, encoding="ascii")
    
    report_rel = f"Reports\\Adaptive\\{ini_name}.htm"
    report_path = MT5_DIR / "Reports" / "Adaptive" / f"{ini_name}.htm"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.unlink(missing_ok=True)
    
    ini_content = f"""[Common]
Login=91551123
Server=LiteFinance-MT5-Demo
NewsEnable=0
[Experts]
AllowLiveTrading=0
AllowDllImport=0
Enabled=0
[Tester]
Expert=AdaptiveBreakoutLab.ex5
ExpertParameters={ini_name}.set
Symbol=XAUUSD_o
Period=M5
Model=1
FromDate={from_date}
ToDate={to_date}
Deposit=1000
Currency=USD
Leverage=1:100
ExecutionMode=0
Optimization=0
ForwardMode=0
Visual=0
UseLocal=1
UseRemote=0
UseCloud=0
Report={report_rel}
ReplaceReport=1
ShutdownTerminal=1
"""
    (MT5_DIR / f"{ini_name}.ini").write_text(ini_content, encoding="ascii")
    env = dict(**os.environ, WINEPREFIX=str(WINEPREFIX))
    cmd = [
        str(WINE_BIN),
        "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
        "/skipupdate:8C031038965130FBEA0639F074B5E35F",
        "/portable",
        f"/config:{ini_name}.ini",
    ]
    
    for attempt in range(3):
        subprocess.run(["pkill", "-f", "terminal64.exe"], check=False)
        time.sleep(1.5)
        subprocess.run(cmd, cwd=str(MT5_DIR), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        if report_path.is_file() and report_path.stat().st_size > 1000:
            break
        time.sleep(2.0)
        
    if not report_path.is_file():
        raise RuntimeError(f"Report not generated for {ini_name}")
        
    return parse_deals_summary(report_path)

def parse_deals_summary(report_path: Path) -> dict:
    text = report_path.read_text(encoding="utf-16", errors="ignore")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.S)
    trades = []
    cur_in = None
    for r in rows:
        cols = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", r, flags=re.S)]
        if len(cols) == 13 and cols[4] in ("in", "out"):
            if cols[4] == "in":
                cur_in = cols
            elif cols[4] == "out" and cur_in:
                pnl = float(cols[10].replace(" ", "") or 0.0) + float(cur_in[8].replace(" ", "") or 0.0)
                trades.append({
                    "pnl": pnl,
                    "lots": float(cur_in[5]),
                })
                cur_in = None
                
    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] < 0)
    win_sum = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    loss_sum = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    net_profit = win_sum - loss_sum
    pf = (win_sum / loss_sum) if loss_sum > 0 else (99.0 if win_sum > 0 else 0.0)
    wr = (wins / len(trades) * 100) if trades else 0.0
    avg_loss = (loss_sum / losses) if losses > 0 else 10.0
    exp_r = ((win_sum - loss_sum) / len(trades) / avg_loss) if (trades and avg_loss > 0) else 0.0
    
    # Calculate Max Equity Drawdown
    equity = 1000.0
    peak = 1000.0
    max_dd = 0.0
    for t in trades:
        equity += t["pnl"]
        if equity > peak: peak = equity
        dd = (peak - equity) / peak * 100.0
        if dd > max_dd: max_dd = dd
        
    return {
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "net_profit": round(net_profit, 2),
        "profit_factor": round(pf, 2),
        "win_rate": round(wr, 1),
        "max_drawdown": round(max_dd, 2),
        "expectancy_r": round(exp_r, 4),
        "avg_lot": round(sum(t["lots"] for t in trades) / len(trades), 2) if trades else 0.0,
    }

print("Adaptive Breakout Pipeline loaded.")

def main():
    print("=== STEP 1: RUNNING PRIMARY ADAPTIVE ENGINE (FIXED 0.10 LOT) ===")
    res_primary = run_adaptive_test(
        ini_name="run_adaptive_primary",
        overrides={"LotMode": 0, "FixedLot": 0.10, "EngineMode": 7},
        from_date="2025.01.01",
        to_date="2026.11.09"
    )
    print(f"Primary Adaptive Run: Net=${res_primary['net_profit']}, PF={res_primary['profit_factor']}, DD={res_primary['max_drawdown']}%, Trades={res_primary['trades']}")
    
    # Copy generated CSVs from COMMON_FILES to OUTPUT_DIR and META_DIR
    target_files = [
        "breakout_classification.csv",
        "trade_level_audit.csv",
        "missed_opportunities.csv",
        "daily_market_audit.csv"
    ]
    for fn in target_files:
        src = COMMON_FILES / fn
        if src.is_file():
            shutil.copy(src, OUTPUT_DIR / fn)
            shutil.copy(src, META_DIR / fn)
            print(f"Copied {fn} -> {OUTPUT_DIR / fn} and {META_DIR / fn}")
        else:
            print(f"WARNING: {src} not found!")

    print("\n=== STEP 2: RUNNING STRATEGY ENGINE COMPARISON (FIXED 0.10 LOT) ===")
    strategy_modes = [
        ("STRAT_BASELINE", 0, "Baseline Unfiltered London"),
        ("STRAT_EXP04_IMPULSE", 1, "London 08-09 Impulse"),
        ("STRAT_EXP12_LONDON_FVG", 2, "London 08-11 + FVG"),
        ("STRAT_EXP23_CHAMPION", 3, "Champion: London 08-09 + FVG"),
        ("STRAT_CONFIRM_LIGHT", 4, "Early Breakout (Candle Strength >= 0.45)"),
        ("STRAT_CONFIRM_BALANCED", 5, "Balanced (Light + M15 BOS / Trend)"),
        ("STRAT_CONFIRM_HEAVY", 6, "Heavy (FVG + BOS + Volume >= 1.10)"),
        ("STRAT_CONFIRM_ADAPTIVE", 7, "Adaptive Market Regime Engine"),
    ]
    
    strat_results = []
    for code, mode_val, desc in strategy_modes:
        print(f"Running {code} (mode={mode_val})...")
        r = run_adaptive_test(
            ini_name=f"strat_eval_{code}",
            overrides={"LotMode": 0, "FixedLot": 0.10, "EngineMode": mode_val},
            from_date="2025.01.01",
            to_date="2026.11.09"
        )
        r["strategy"] = code
        r["description"] = desc
        strat_results.append(r)
        print(f"  Done {code}: Net=${r['net_profit']}, PF={r['profit_factor']}, DD={r['max_drawdown']}%, Trades={r['trades']}, WinRate={r['win_rate']}%")

    # Save research/output/strategy_comparison.csv
    strat_csv = OUTPUT_DIR / "strategy_comparison.csv"
    with open(strat_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Strategy", "Description", "Trades", "Wins", "Losses", "WinRatePct", "NetProfitUSD", "ProfitFactor", "MaxDrawdownPct", "ExpectancyR", "AvgLot"])
        for r in strat_results:
            w.writerow([r["strategy"], r["description"], r["trades"], r["wins"], r["losses"], r["win_rate"], r["net_profit"], r["profit_factor"], r["max_drawdown"], r["expectancy_r"], r["avg_lot"]])
    shutil.copy(strat_csv, META_DIR / "strategy_comparison.csv")
    print(f"Saved: {strat_csv}")

    print("\n=== STEP 3: RUNNING LOT SIZE COMPARISON (FIXED 0.10 LOT vs DYNAMIC 3% RISK) ===")
    lot_comparisons = []
    for code, mode_val, desc in [("STRAT_EXP23_CHAMPION", 3, "EXP23 Champion"), ("STRAT_CONFIRM_ADAPTIVE", 7, "Adaptive Regime")]:
        # Fixed 0.10
        r_fix = run_adaptive_test(f"lot_fix_{code}", {"LotMode": 0, "FixedLot": 0.10, "EngineMode": mode_val})
        r_fix["strategy"] = code
        r_fix["lot_mode"] = "FIXED_0.10_LOT"
        lot_comparisons.append(r_fix)
        
        # Dynamic Risk 3%
        r_dyn = run_adaptive_test(f"lot_dyn_{code}", {"LotMode": 1, "EngineMode": mode_val, "RiskPerTradePct": 3.0})
        r_dyn["strategy"] = code
        r_dyn["lot_mode"] = "DYNAMIC_3PCT_RISK"
        lot_comparisons.append(r_dyn)

    lot_csv = OUTPUT_DIR / "lot_size_comparison.csv"
    with open(lot_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Strategy", "LotMode", "Trades", "WinRatePct", "NetProfitUSD", "ProfitFactor", "MaxDrawdownPct", "ExpectancyR", "AvgLot"])
        for r in lot_comparisons:
            w.writerow([r["strategy"], r["lot_mode"], r["trades"], r["win_rate"], r["net_profit"], r["profit_factor"], r["max_drawdown"], r["expectancy_r"], r["avg_lot"]])
    shutil.copy(lot_csv, META_DIR / "lot_size_comparison.csv")
    print(f"Saved: {lot_csv}")

    print("\n=== STEP 4: RUNNING WALK-FORWARD VALIDATION ===")
    splits = [
        ("Training_2025", "2025.01.01", "2025.10.01"),
        ("Validation_2025_Q4", "2025.10.01", "2026.01.01"),
        ("OutOfSample_2026", "2026.01.02", "2026.11.06"),
    ]
    wf_results = []
    for split_name, d_from, d_to in splits:
        for code, mode_val in [("EXP23_Champion", 3), ("Adaptive_Regime", 7)]:
            r = run_adaptive_test(f"wf_{code}_{split_name}", {"LotMode": 0, "FixedLot": 0.10, "EngineMode": mode_val}, from_date=d_from, to_date=d_to)
            r["split"] = split_name
            r["strategy"] = code
            r["from"] = d_from
            r["to"] = d_to
            wf_results.append(r)
            print(f"  {split_name} | {code}: Net=${r['net_profit']}, PF={r['profit_factor']}, DD={r['max_drawdown']}%, Trades={r['trades']}")

    wf_csv = OUTPUT_DIR / "walk_forward_results.csv"
    with open(wf_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Split", "FromDate", "ToDate", "Strategy", "Trades", "WinRatePct", "NetProfitUSD", "ProfitFactor", "MaxDrawdownPct", "ExpectancyR"])
        for r in wf_results:
            w.writerow([r["split"], r["from"], r["to"], r["strategy"], r["trades"], r["win_rate"], r["net_profit"], r["profit_factor"], r["max_drawdown"], r["expectancy_r"]])
    shutil.copy(wf_csv, META_DIR / "walk_forward_results.csv")
    print(f"Saved: {wf_csv}")

    print("\n=== PIPELINE EXECUTION COMPLETE ===")

if __name__ == "__main__":
    main()
