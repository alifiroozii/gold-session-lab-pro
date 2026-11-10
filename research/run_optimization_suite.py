"""OPTIMIZATION SUITE
Systematic execution of Stage 1, Stage 2, Stage 3, Stage 4, Stage 5 in MetaTrader 5 Strategy Tester.
"""
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import time

MT5_DIR = Path("/Users/alifiroozi/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5")
WINE_BIN = Path("/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine64")
WINEPREFIX = Path("/Users/alifiroozi/Library/Application Support/net.metaquotes.wine.metatrader5")
OUTPUT_DIR = Path("/Users/alifiroozi/ali/gold-session-mt5-research/research/output/optimization")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def run_mt5_test(run_id: str, overrides: dict, from_date="2025.01.01", to_date="2026.11.09") -> dict:
    set_lines = [
        "ExpectedSymbol=XAUUSD_o",
        "ServerClock=2",
        "Reference=1",
        f"LotMode={overrides.get('LotMode', 0)}",
        f"FixedLot={overrides.get('FixedLot', 0.10)}",
        f"ModelChoice={overrides.get('ModelChoice', 2)}",
        f"RiskPerTradePct={overrides.get('RiskPerTradePct', 1.0)}",
        f"DailyLossLimitPct=6.0",
        f"TargetRR={overrides.get('TargetRR', 1.5)}",
        f"MaxRangeWidth={overrides.get('MaxRangeWidth', 30.0)}",
        f"MinStopBps=5.8",
        f"TimeWindow={overrides.get('TimeWindow', 0)}",
        f"SLTPMode={overrides.get('SLTPMode', 0)}",
        f"OptRequireRetest={'true' if overrides.get('OptRequireRetest', False) else 'false'}",
        f"OptUseAtrFilter={'true' if overrides.get('OptUseAtrFilter', False) else 'false'}",
        f"OptMinAtrRatio={overrides.get('OptMinAtrRatio', 0.50)}",
        f"OptMaxAtrRatio={overrides.get('OptMaxAtrRatio', 2.50)}",
        f"OptRequireCloseLocation={'true' if overrides.get('OptRequireCloseLocation', False) else 'false'}",
        f"OptVolumeRatioMin={overrides.get('OptVolumeRatioMin', 1.10)}",
        f"OptFvgMinSize={overrides.get('OptFvgMinSize', 0.20)}",
        f"OptOpposingSweepBonus={'true' if overrides.get('OptOpposingSweepBonus', False) else 'false'}",
        f"OptUseRangeWidthFilter={'true' if overrides.get('OptUseRangeWidthFilter', False) else 'false'}",
    ]
    set_content = "\n".join(set_lines) + "\n"
    set_file = MT5_DIR / "MQL5" / "Profiles" / "Tester" / f"{run_id}.set"
    set_file.parent.mkdir(parents=True, exist_ok=True)
    set_file.write_text(set_content, encoding="ascii")
    
    report_rel = f"Reports\\Optimization\\{run_id}.htm"
    report_path = MT5_DIR / "Reports" / "Optimization" / f"{run_id}.htm"
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
Expert=OptimizedBreakoutLab.ex5
ExpertParameters={run_id}.set
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
    (MT5_DIR / f"{run_id}.ini").write_text(ini_content, encoding="ascii")
    env = dict(**os.environ, WINEPREFIX=str(WINEPREFIX))
    cmd = [
        str(WINE_BIN),
        "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
        "/skipupdate:8C031038965130FBEA0639F074B5E35F",
        "/portable",
        f"/config:{run_id}.ini",
    ]
    
    for attempt in range(3):
        subprocess.run(["pkill", "-f", "terminal64.exe"], check=False)
        time.sleep(1.0)
        subprocess.run(cmd, cwd=str(MT5_DIR), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        if report_path.is_file() and report_path.stat().st_size > 1000:
            break
        time.sleep(1.5)
        
    if not report_path.is_file():
        raise RuntimeError(f"Report not generated for {run_id}")
        
    return parse_report(report_path)

def parse_report(report_path: Path) -> dict:
    txt = report_path.read_text(encoding="utf-16", errors="ignore")
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', txt, flags=re.S)
    
    metrics = {
        "trades": 0,
        "net_profit": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "profit_factor": 0.0,
        "expected_payoff": 0.0,
        "max_drawdown_usd": 0.0,
        "max_drawdown_pct": 0.0,
        "equity_drawdown_pct": 0.0,
        "win_rate": 0.0,
        "wins": 0,
        "losses": 0,
        "short_trades": 0,
        "long_trades": 0,
        "avg_profit_trade": 0.0,
        "avg_loss_trade": 0.0,
        "sharpe_ratio": 0.0,
    }
    
    trades = []
    cur_in = None
    for r in rows:
        cols = [re.sub(r'<[^>]+>', '', c).strip() for c in re.findall(r'<td[^>]*>(.*?)</td>', r, flags=re.S)]
        if len(cols) == 13 and cols[4] in ("in", "out"):
            if cols[4] == "in":
                cur_in = cols
            elif cols[4] == "out" and cur_in:
                pnl = float(cols[10].replace(" ", "") or 0.0) + float(cur_in[8].replace(" ", "") or 0.0)
                trades.append({
                    "deal_out": cols[0],
                    "time_in": cur_in[1],
                    "time_out": cols[1],
                    "dir": cur_in[3],
                    "lot": float(cur_in[5]),
                    "pnl": pnl,
                })
                cur_in = None
                
        for i, c in enumerate(cols):
            if "Total Net Profit:" in c and i + 1 < len(cols):
                metrics["net_profit"] = float(cols[i+1].replace(" ", "") or 0.0)
            elif "Gross Profit:" in c and i + 1 < len(cols):
                metrics["gross_profit"] = float(cols[i+1].replace(" ", "") or 0.0)
            elif "Gross Loss:" in c and i + 1 < len(cols):
                metrics["gross_loss"] = float(cols[i+1].replace(" ", "") or 0.0)
            elif "Profit Factor:" in c and i + 1 < len(cols):
                metrics["profit_factor"] = float(cols[i+1].replace(" ", "") or 0.0)
            elif "Expected Payoff:" in c and i + 1 < len(cols):
                metrics["expected_payoff"] = float(cols[i+1].replace(" ", "") or 0.0)
            elif "Total Trades:" in c and i + 1 < len(cols):
                metrics["trades"] = int(cols[i+1].replace(" ", "") or 0)
            elif "Balance Drawdown Maximal:" in c and i + 1 < len(cols):
                m = re.search(r'([\d\.\s]+)\s*\(([\d\.]+)\%\)', cols[i+1])
                if m:
                    metrics["max_drawdown_usd"] = float(m.group(1).replace(" ", ""))
                    metrics["max_drawdown_pct"] = float(m.group(2))
            elif "Equity Drawdown Maximal:" in c and i + 1 < len(cols):
                m = re.search(r'([\d\.\s]+)\s*\(([\d\.]+)\%\)', cols[i+1])
                if m:
                    metrics["equity_drawdown_pct"] = float(m.group(2))
            elif "Sharpe Ratio:" in c and i + 1 < len(cols):
                metrics["sharpe_ratio"] = float(cols[i+1].replace(" ", "") or 0.0)
                
    if metrics["trades"] == 0 and trades:
        metrics["trades"] = len(trades)
        metrics["net_profit"] = sum(t["pnl"] for t in trades)
        
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    metrics["wins"] = len(wins)
    metrics["losses"] = len(losses)
    metrics["win_rate"] = round(len(wins) / len(trades) * 100.0, 1) if trades else 0.0
    metrics["avg_profit_trade"] = round(sum(t["pnl"] for t in wins) / len(wins), 2) if wins else 0.0
    metrics["avg_loss_trade"] = round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else 0.0
    metrics["trade_list"] = trades
    return metrics

print("run_optimization_suite module ready.")
