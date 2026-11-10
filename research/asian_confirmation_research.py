"""ASIAN RANGE BREAKOUT CONFIRMATION RESEARCH RUNNER
Automated MT5 Strategy Tester Research Pipeline
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time

from research.parse_report import parse_report
from research.run_backtest import ROOT, SYMBOL, source_hash

MT5_DIR = Path(
    "/Users/alifiroozi/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5"
)
WINE_BIN = Path("/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine64")
WINEPREFIX = Path("/Users/alifiroozi/Library/Application Support/net.metaquotes.wine.metatrader5")

DB_PATH = ROOT / "research" / "output" / "asian_confirmation.sqlite"

DEFAULT_PARAMS = {
    "ExpectedSymbol": SYMBOL,
    "ServerClock": 2,          # CLOCK_LITEFINANCE_EU
    "Reference": 1,            # REF_ASIA_NY
    "Strategy": 0,             # STRATEGY_BREAKOUT
    "Mode": 0,                 # MODE_FAST
    "SignalAuditOnly": "false",
    "MaxRangeWidth": 30.0,
    "MaxRangeATR": 10.0,
    "OneTradePerSidePerDay": "false",
    "RequireFreshBreakout": "false",
    "MinBreakoutBodyRatio": 0.0,
    "RequireH1Trend": "false",
    "MinH1ADX": 0.0,
    "RiskPerTradePct": 3.0,
    "DailyLossLimitPct": 6.0,
    "MaxTradesPerDay": 2,
    "MinStopATR": 0.0,
    "MaxStopATR": 2.5,
    "StopBufferATR": 0.0,
    "TargetRR": 1.5,
    "BreakEvenRR": 0.0,
    "TrailRR": 0.0,
    "MaxLotCap": 0.06,
    "SkipLondonLateNY": "false",
    "SkipOverlap": "true",
    "SkipNY": "true",
    "DynamicSessionRef": 0,
    "MinStopBps": 5.8,
    "MaxStopBps": 0.0,
    "MaxRangeBps": 0.0,
    "SkipWhipsawHours": "false",
    "Confirmation": 0,
    "EuropeWindow": 5,         # EUROPE_LONDON_ALL (08-11 London)
    "EuropeOnly": "true",
    "MinConfidenceScore": 0,
}

RESEARCH_HYPOTHESES = [
    # --- PART A: ASIAN RANGE DEFINITION ---
    {
        "code": "EXP01_RangeNY_Base",
        "description": "Asian Range Option A: REF_ASIA_NY (20:00-00:00 NY) | London Session 08-11 | Fast Baseline",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 0},
    },
    {
        "code": "EXP02_RangeFrankfurt_Base",
        "description": "Asian Range Option B: REF_ASIA_FRANKFURT (00:00-07:00 London) | London Session 08-11 | Fast Baseline",
        "overrides": {"Reference": 7, "EuropeWindow": 5, "Confirmation": 0},
    },
    # --- PART B: EUROPEAN SESSION WINDOW BREAKDOWN ---
    {
        "code": "EXP03_Frankfurt_07_08",
        "description": "Window: Frankfurt Only (07:00-08:00 London) | REF_ASIA_NY",
        "overrides": {"Reference": 1, "EuropeWindow": 1, "Confirmation": 0},
    },
    {
        "code": "EXP04_London_08_09",
        "description": "Window: London Opening Impulse (08:00-09:00 London) | REF_ASIA_NY",
        "overrides": {"Reference": 1, "EuropeWindow": 2, "Confirmation": 0},
    },
    {
        "code": "EXP05_London_09_10",
        "description": "Window: London Post-Open (09:00-10:00 London) | REF_ASIA_NY",
        "overrides": {"Reference": 1, "EuropeWindow": 3, "Confirmation": 0},
    },
    {
        "code": "EXP06_London_10_11",
        "description": "Window: London Mid-Session (10:00-11:00 London) | REF_ASIA_NY",
        "overrides": {"Reference": 1, "EuropeWindow": 4, "Confirmation": 0},
    },
    {
        "code": "EXP07_London_Full_08_11",
        "description": "Window: Full London 3h (08:00-11:00 London) | REF_ASIA_NY",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 0},
    },
    {
        "code": "EXP08_Europe_All_07_11",
        "description": "Window: Frankfurt + London Combined (07:00-11:00 London) | REF_ASIA_NY",
        "overrides": {"Reference": 1, "EuropeWindow": 0, "Confirmation": 0},
    },
    # --- PART C: INDEPENDENT CONFIRMATION METHODS ---
    {
        "code": "EXP09_Confirm_A_CandleQuality",
        "description": "Method A: Candle Quality (BodyRatio>=0.45, Low Wick, Size 0.6-2.5 ATR, Dist<=1.8 ATR)",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 1},
    },
    {
        "code": "EXP10_Confirm_B_NextCandle",
        "description": "Method B: Next Candle Continuation Confirmation",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 2},
    },
    {
        "code": "EXP11_Confirm_C_Retest",
        "description": "Method C: Retest of Broken Asian Level with Rejection Wick",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 3},
    },
    {
        "code": "EXP12_Confirm_D_FVG",
        "description": "Method D: Fair Value Gap (FVG) Imbalance in Breakout Direction",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 4},
    },
    {
        "code": "EXP13_Confirm_E_M15_BOS",
        "description": "Method E: Market Structure Break (M15 BOS)",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 5},
    },
    {
        "code": "EXP14_Confirm_F_LiquiditySweep",
        "description": "Method F: Liquidity Sweep of Opposite Asian Side First (Judas Swing)",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 6},
    },
    {
        "code": "EXP15_Confirm_G_H1_Trend",
        "description": "Method G: Higher-Timeframe Trend Confirmation (H1 EMA50 + ADX>=18)",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 7},
    },
    {
        "code": "EXP16_Confirm_H_MomentumVol",
        "description": "Method H: Momentum & Volume (VolRatio>=1.15x + Displacement>=0.9 ATR)",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 8},
    },
    # --- PART D: COMBINATIONS & QUALITY SCORING ---
    {
        "code": "EXP17_Combo_Retest_FVG",
        "description": "Combo 1: Retest + FVG",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 9},
    },
    {
        "code": "EXP18_Combo_FVG_BOS",
        "description": "Combo 2: FVG + M15 BOS",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 10},
    },
    {
        "code": "EXP19_Combo_Sweep_BOS",
        "description": "Combo 3: Opposite Liquidity Sweep + M15 BOS",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 11},
    },
    {
        "code": "EXP20_Score_Calibrated_50",
        "description": "Breakout Quality Score >= 50 (Calibrated Empirical Weights + NO TRADE option)",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 12, "MinConfidenceScore": 50},
    },
    {
        "code": "EXP21_Score_Calibrated_60",
        "description": "Breakout Quality Score >= 60 (High Conviction + NO TRADE option)",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 12, "MinConfidenceScore": 60},
    },
    {
        "code": "EXP22_Score_Calibrated_70",
        "description": "Breakout Quality Score >= 70 (Ultra-Selective + NO TRADE option)",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 12, "MinConfidenceScore": 70},
    },
    # --- PART E: FOCUSED DISCOVERY COMBINATIONS ---
    {
        "code": "EXP23_London0809_FVG",
        "description": "Best Window + Best Confirmation: London 08-09 Impulse + FVG Imbalance",
        "overrides": {"Reference": 1, "EuropeWindow": 2, "Confirmation": 4},
    },
    {
        "code": "EXP24_London0809_Candle_FVG",
        "description": "London 08-09 Impulse + Candle Quality (Body>=0.45) + FVG",
        "overrides": {"Reference": 1, "EuropeWindow": 2, "Confirmation": 4, "MinBreakoutBodyRatio": 0.45},
    },
    {
        "code": "EXP25_LondonFull_FVG",
        "description": "Full London 08-11 + FVG Imbalance",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 4},
    },
]


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS asian_confirmation_runs (
                id TEXT PRIMARY KEY,
                code TEXT,
                description TEXT,
                split TEXT,
                model INTEGER,
                from_date TEXT,
                to_date TEXT,
                trades INTEGER,
                net_profit REAL,
                profit_factor REAL,
                win_rate REAL,
                drawdown_pct REAL,
                expectancy_r REAL,
                trades_per_month REAL,
                summary_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


def parse_deals(report_path: Path) -> dict:
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
                    "entry_time": cur_in[0],
                    "exit_time": cols[0],
                    "side": cur_in[3],
                    "lots": float(cur_in[5]),
                    "entry": float(cur_in[6].replace(" ", "")),
                    "exit": float(cols[6].replace(" ", "")),
                    "pnl": pnl,
                    "session": cur_in[12],
                    "exit_reason": cols[12],
                })
                cur_in = None

    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] < 0)
    win_sum = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    loss_sum = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    avg_loss = (loss_sum / losses) if losses > 0 else 10.0
    expectancy_r = ((win_sum - loss_sum) / len(trades) / avg_loss) if (trades and avg_loss > 0) else 0.0
    return {
        "deal_count": len(trades),
        "wins": wins,
        "losses": losses,
        "expectancy_r": round(expectancy_r, 4),
    }


def run_single_test(code: str, description: str, overrides: dict, split: str, from_date: str, to_date: str, model: int = 1) -> dict:
    params = dict(DEFAULT_PARAMS)
    params.update(overrides)

    identity = {
        "code": code,
        "split": split,
        "from": from_date,
        "to": to_date,
        "model": model,
        "params": params,
        "sha": source_hash(),
    }
    exp_id = "ac-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:18]

    set_lines = [f"{k}={v}" for k, v in params.items()]
    set_content = "\n".join(set_lines) + "\n"
    set_name = f"{exp_id}.set"
    set_path = MT5_DIR / "MQL5" / "Profiles" / "Tester" / set_name
    set_path.write_text(set_content, encoding="ascii")

    report_rel = f"Reports\\AsianConfirmation\\{exp_id}.htm"
    report_path = MT5_DIR / "Reports" / "AsianConfirmation" / f"{exp_id}.htm"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.unlink(missing_ok=True)

    ini_name = f"{exp_id}.ini"
    ini_path = MT5_DIR / ini_name
    ini_content = (
        "[Common]\r\n"
        "Login=91551123\r\n"
        "Server=LiteFinance-MT5-Demo\r\n"
        "NewsEnable=0\r\n"
        "[Experts]\r\n"
        "AllowLiveTrading=0\r\n"
        "AllowDllImport=0\r\n"
        "Enabled=0\r\n"
        "[Tester]\r\n"
        "Expert=GoldResearchLab.ex5\r\n"
        f"ExpertParameters={set_name}\r\n"
        f"Symbol={SYMBOL}\r\n"
        "Period=M5\r\n"
        f"Model={model}\r\n"
        f"FromDate={from_date}\r\n"
        f"ToDate={to_date}\r\n"
        "Deposit=1000\r\n"
        "Currency=USD\r\n"
        "Leverage=1:100\r\n"
        "ExecutionMode=0\r\n"
        "Optimization=0\r\n"
        "ForwardMode=0\r\n"
        "Visual=0\r\n"
        "UseLocal=1\r\n"
        "UseRemote=0\r\n"
        "UseCloud=0\r\n"
        f"Report={report_rel}\r\n"
        "ReplaceReport=1\r\n"
        "ShutdownTerminal=1\r\n"
    )
    ini_path.write_text(ini_content, encoding="ascii")

    env = dict(**os.environ, WINEPREFIX=str(WINEPREFIX))
    cmd = [
        str(WINE_BIN),
        "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
        "/skipupdate:8C031038965130FBEA0639F074B5E35F",
        "/portable",
        f"/config:{ini_name}",
    ]

    for attempt in range(3):
        subprocess.run(["pkill", "-f", "terminal64.exe"], check=False)
        time.sleep(1.5)
        subprocess.run(cmd, cwd=str(MT5_DIR), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        if report_path.is_file() and report_path.stat().st_size > 1000:
            break
        time.sleep(3.0)

    if not report_path.is_file():
        raise RuntimeError(f"MT5 report was not generated for {code} ({exp_id})")

    summary = parse_report(report_path)
    deal_stats = parse_deals(report_path)

    d1 = datetime.strptime(from_date, "%Y.%m.%d")
    d2 = datetime.strptime(to_date, "%Y.%m.%d")
    months = max(1.0, (d2 - d1).days / 30.4)
    trades_per_month = round(summary["trade_count"] / months, 1)

    summary.update({
        "code": code,
        "description": description,
        "split": split,
        "model": model,
        "from_date": from_date,
        "to_date": to_date,
        "trades_per_month": trades_per_month,
        **deal_stats,
    })

    # Save to SQLite
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO asian_confirmation_runs
            (id, code, description, split, model, from_date, to_date, trades, net_profit, profit_factor, win_rate, drawdown_pct, expectancy_r, trades_per_month, summary_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
            trades=excluded.trades, net_profit=excluded.net_profit, profit_factor=excluded.profit_factor,
            win_rate=excluded.win_rate, drawdown_pct=excluded.drawdown_pct, expectancy_r=excluded.expectancy_r,
            trades_per_month=excluded.trades_per_month, summary_json=excluded.summary_json
        """, (
            exp_id, code, description, split, model, from_date, to_date,
            summary["trade_count"], summary["net_profit"], summary["profit_factor"],
            summary["win_rate"], summary["equity_drawdown_pct"], summary["expectancy_r"],
            trades_per_month, json.dumps(summary)
        ))

    return {"id": exp_id, "summary": summary}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("training", "validation", "historical"), default="training")
    parser.add_argument("--model", type=int, default=1)
    parser.add_argument("--codes", nargs="*")
    args = parser.parse_args()

    init_db()

    splits_dates = {
        "training": ("2025.01.01", "2025.10.01"),
        "validation": ("2025.10.01", "2026.01.01"),
        "historical": ("2026.01.02", "2026.11.01"),
    }
    f_date, t_date = splits_dates[args.split]

    print(f"\n=========================================================================================================")
    print(f"ASIAN RANGE BREAKOUT CONFIRMATION RESEARCH | Split: {args.split.upper()} ({f_date} to {t_date}) | Model={args.model}")
    print(f"=========================================================================================================")

    for item in RESEARCH_HYPOTHESES:
        if args.codes and item["code"] not in args.codes:
            continue
        t0 = time.time()
        res = run_single_test(
            code=item["code"],
            description=item["description"],
            overrides=item["overrides"],
            split=args.split,
            from_date=f_date,
            to_date=t_date,
            model=args.model,
        )
        elapsed = time.time() - t0
        s = res["summary"]
        pf_str = f"{s['profit_factor']:5.2f}" if s['profit_factor'] is not None else " N/A "
        win_str = f"{(s['win_rate'] or 0)*100:5.1f}%"
        print(
            f"{item['code']:28s} | n={s['trade_count']:3d} | net=${s['net_profit']:7.2f} | "
            f"pf={pf_str} | win={win_str} | dd={s['equity_drawdown_pct']:5.2f}% | "
            f"expR={s['expectancy_r']:6.3f} | t/m={s['trades_per_month']:4.1f} | {elapsed:4.1f}s",
            flush=True,
        )
