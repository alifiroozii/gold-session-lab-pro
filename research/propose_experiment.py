"""Autonomous MT5 Strategy Tester Challenger Campaign Runner & Hypothesis Evaluator."""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time

from research.parse_report import parse_report
from research.run_backtest import REFERENCES, ROOT, SPLITS, STRATEGIES, MODES, SYMBOL, registry, source_hash

MT5_DIR = Path(
    "/Users/alifiroozi/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5"
)
WINE_BIN = Path("/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine64")
WINEPREFIX = Path("/Users/alifiroozi/Library/Application Support/net.metaquotes.wine.metatrader5")


DEFAULT_PARAMS = {
    "ExpectedSymbol": SYMBOL,
    "ServerClock": 2,
    "Reference": 0,
    "Strategy": 0,
    "Mode": 0,
    "SignalAuditOnly": "false",
    "MaxRangeWidth": 30.0,
    "MaxRangeATR": 0.0,
    "OneTradePerSidePerDay": "false",
    "RequireFreshBreakout": "false",
    "MinBreakoutBodyRatio": 0.0,
    "RequireH1Trend": "false",
    "MinH1ADX": 0.0,
    "RiskPerTradePct": 3.0,
    "DailyLossLimitPct": 6.0,
    "MaxTradesPerDay": 10,
    "MinStopATR": 0.0,
    "MaxStopATR": 0.0,
    "StopBufferATR": 0.0,
    "TargetRR": 1.5,
    "BreakEvenRR": 0.0,
    "TrailRR": 0.0,
    "MaxLotCap": 0.06,
    "SkipLondonLateNY": "false",
    "SkipOverlap": "false",
    "SkipNY": "false",
    "DynamicSessionRef": 0,
    "MinStopBps": 0.0,
    "MaxStopBps": 0.0,
    "MaxRangeBps": 0.0,
    "SkipWhipsawHours": "false",
}


TRAINING_HYPOTHESES = [
    {
        "code": "H0_base_utc_fast",
        "hypothesis": "Baseline UTC Asia Breakout Fast (Fixed $30 range, $9 stop, 10 trades/day, all sessions)",
        "overrides": {},
    },
    {
        "code": "H1_base_ny_fast",
        "hypothesis": "Baseline NY Asia Breakout Fast (20:00-00:00 NY range, fixed $30 range, $9 stop)",
        "overrides": {"Reference": 1},
    },
    {
        "code": "H2_atr_norm_cap2",
        "hypothesis": "ATR-normalized range (MaxRangeATR=12, MaxRangeWidth=90) and stop (MaxStopATR=2.5) + Max 2 trades/day + 1 trade/side/day",
        "overrides": {
            "MaxRangeWidth": 90.0,
            "MaxRangeATR": 12.0,
            "MaxStopATR": 2.5,
            "MaxTradesPerDay": 2,
            "OneTradePerSidePerDay": "true",
        },
    },
    {
        "code": "H3_skip_overlap_atr",
        "hypothesis": "Skip noisy NY/London overlap (SkipOverlap=true) + ATR-normalized range/stop + Max 2 trades/day",
        "overrides": {
            "MaxRangeWidth": 90.0,
            "MaxRangeATR": 12.0,
            "MaxStopATR": 2.5,
            "MaxTradesPerDay": 2,
            "OneTradePerSidePerDay": "true",
            "SkipOverlap": "true",
        },
    },
    {
        "code": "H4_fresh_trend_atr",
        "hypothesis": "Fresh breakout + H1 EMA50 trend alignment + BodyRatio>=0.40 + ATR-normalized range/stop (all sessions)",
        "overrides": {
            "MaxRangeWidth": 90.0,
            "MaxRangeATR": 12.0,
            "MaxStopATR": 2.5,
            "MinStopATR": 0.7,
            "MaxTradesPerDay": 2,
            "OneTradePerSidePerDay": "true",
            "RequireFreshBreakout": "true",
            "MinBreakoutBodyRatio": 0.40,
            "RequireH1Trend": "true",
        },
    },
    {
        "code": "H5_fresh_trend_no_overlap",
        "hypothesis": "Fresh breakout + H1 EMA50 trend alignment + SkipOverlap=true + ATR-normalized range/stop",
        "overrides": {
            "MaxRangeWidth": 90.0,
            "MaxRangeATR": 12.0,
            "MaxStopATR": 2.5,
            "MinStopATR": 0.7,
            "MaxTradesPerDay": 2,
            "OneTradePerSidePerDay": "true",
            "RequireFreshBreakout": "true",
            "MinBreakoutBodyRatio": 0.40,
            "RequireH1Trend": "true",
            "SkipOverlap": "true",
        },
    },
    {
        "code": "H6_dyn_london_ref",
        "hypothesis": "Dynamic Session Reference (Asia UTC in London, London UTC 07-13 in Overlap/NY) + Fresh + H1 Trend + ATR-norm",
        "overrides": {
            "MaxRangeWidth": 90.0,
            "MaxRangeATR": 14.0,
            "MaxStopATR": 2.5,
            "MinStopATR": 0.7,
            "MaxTradesPerDay": 2,
            "OneTradePerSidePerDay": "true",
            "RequireFreshBreakout": "true",
            "MinBreakoutBodyRatio": 0.40,
            "RequireH1Trend": "true",
            "DynamicSessionRef": 1,
        },
    },
    {
        "code": "H7_ny_asia_fresh_trend",
        "hypothesis": "NY Asia Reference (REF_ASIA_NY) + Fresh breakout + H1 Trend + ATR-normalized range/stop",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 90.0,
            "MaxRangeATR": 12.0,
            "MaxStopATR": 2.5,
            "MinStopATR": 0.7,
            "MaxTradesPerDay": 2,
            "OneTradePerSidePerDay": "true",
            "RequireFreshBreakout": "true",
            "MinBreakoutBodyRatio": 0.40,
            "RequireH1Trend": "true",
        },
    },
    {
        "code": "H8_standard_confirm_atr",
        "hypothesis": "Standard Confirmation Mode (>=2 of 4 votes: H1 EMA, FVG, Volume/ATR Momentum, M15 BOS) + ATR-normalized range/stop",
        "overrides": {
            "Mode": 1,
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 9.0,
            "MaxStopATR": 2.2,
            "MaxTradesPerDay": 2,
            "OneTradePerSidePerDay": "true",
        },
    },
    {
        "code": "H9_ny_asia_no_overlap",
        "hypothesis": "NY Asia Reference + SkipOverlap=true + MaxRange(30, 9*ATR) + MaxStop(9, 2.2*ATR) + Max 2 trades/day",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 9.0,
            "MaxStopATR": 2.2,
            "MaxTradesPerDay": 2,
            "SkipOverlap": "true",
        },
    },
    {
        "code": "H10_ny_asia_atr_cap2",
        "hypothesis": "NY Asia Reference + All Sessions + MaxRange(30, 9*ATR) + MaxStop(9, 2.2*ATR) + Max 2 trades/day",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 9.0,
            "MaxStopATR": 2.2,
            "MaxTradesPerDay": 2,
        },
    },
    {
        "code": "H11_ny_asia_london_only",
        "hypothesis": "NY Asia Reference + London Session Only (SkipOverlap=true, SkipNY=true) + MaxRange(30, 9*ATR) + MaxStop(9, 2.2*ATR)",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 9.0,
            "MaxStopATR": 2.2,
            "MaxTradesPerDay": 2,
            "SkipOverlap": "true",
            "SkipNY": "true",
        },
    },
    {
        "code": "H12_utc_asia_no_overlap",
        "hypothesis": "UTC Asia Reference + SkipOverlap=true + MaxRange(30, 9*ATR) + MaxStop(9, 2.2*ATR) + Max 2 trades/day",
        "overrides": {
            "Reference": 0,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 9.0,
            "MaxStopATR": 2.2,
            "MaxTradesPerDay": 2,
            "SkipOverlap": "true",
        },
    },
    {
        "code": "H13_ny_asia_fresh_trend",
        "hypothesis": "NY Asia Reference + Fresh Breakout + H1 Trend + Fixed 0.50*ATR Chase + MaxRange(30, 9*ATR) + MaxStop(9, 2.2*ATR)",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 9.0,
            "MaxStopATR": 2.2,
            "MaxTradesPerDay": 2,
            "OneTradePerSidePerDay": "true",
            "RequireFreshBreakout": "true",
            "MinBreakoutBodyRatio": 0.40,
            "RequireH1Trend": "true",
        },
    },
    {
        "code": "H14_ny_asia_hybrid_session",
        "hypothesis": "NY Asia Reference + Fast Breakout in London + Fresh & H1-Trend Filtered Breakout in Overlap/NY + MaxRange(30, 9*ATR) + MaxStop(9, 2.2*ATR)",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 9.0,
            "MaxStopATR": 2.2,
            "MaxTradesPerDay": 2,
            "DynamicSessionRef": 4,
        },
    },
    {
        "code": "H15_bps_structural_champion",
        "hypothesis": "NY Asia Reference + Scale-Invariant Stop Band (5.8-10.5 bps) + SkipOverlap + Skip 9AM London & 1PM NY Whipsaw Hours + MaxRange(30, 9*ATR)",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 9.0,
            "MaxStopATR": 2.2,
            "MaxTradesPerDay": 2,
            "SkipOverlap": "true",
            "MinStopBps": 5.8,
            "MaxStopBps": 10.5,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H16_bps_london_ny_allhours",
        "hypothesis": "NY Asia Reference + Scale-Invariant Stop Band (5.8-10.5 bps) + SkipOverlap + All London/NY hours + MaxRange(30, 9*ATR)",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 9.0,
            "MaxStopATR": 2.2,
            "MaxTradesPerDay": 2,
            "SkipOverlap": "true",
            "MinStopBps": 5.8,
            "MaxStopBps": 10.5,
            "SkipWhipsawHours": "false",
        },
    },
    {
        "code": "H17_london_impulse_champion",
        "hypothesis": "NY Asia Reference + London Impulse Windows (08-09 & 10-11 London) + Scale-Invariant Stop Band (5.8-10.5 bps) + MaxRange(30, 9*ATR)",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 9.0,
            "MaxStopATR": 2.2,
            "MaxTradesPerDay": 2,
            "SkipOverlap": "true",
            "SkipNY": "true",
            "MinStopBps": 5.8,
            "MaxStopBps": 10.5,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H18_london_ny_impulse",
        "hypothesis": "NY Asia Reference + London Impulse (08-09 & 10-11 London) + NY Impulse (skipping 1PM NY & 11AM London) + Stop Band (5.8-10.5 bps)",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 9.0,
            "MaxStopATR": 2.2,
            "MaxTradesPerDay": 2,
            "SkipOverlap": "true",
            "SkipNY": "false",
            "MinStopBps": 5.8,
            "MaxStopBps": 10.5,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H19_london_impulse_oneside",
        "hypothesis": "NY Asia Reference + London Impulse Windows (08-09 & 10-11 London) + OneTradePerSidePerDay + Stop Band (5.8-10.5 bps) + MaxRange(30, 9*ATR)",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 9.0,
            "MaxStopATR": 2.2,
            "MaxTradesPerDay": 2,
            "OneTradePerSidePerDay": "true",
            "SkipOverlap": "true",
            "SkipNY": "true",
            "MinStopBps": 5.8,
            "MaxStopBps": 10.5,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H20_atr_band_london",
        "hypothesis": "NY Asia Reference + London Impulse + True ATR Stop Rejection Band (0.90-1.60 ATR, 8.0-14.0 bps) + OneTradePerSidePerDay",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 10.0,
            "MinStopATR": 0.90,
            "MaxStopATR": 1.60,
            "MaxTradesPerDay": 2,
            "OneTradePerSidePerDay": "true",
            "SkipOverlap": "true",
            "SkipNY": "true",
            "MinStopBps": 8.0,
            "MaxStopBps": 14.0,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H21_atr_band_trend_london",
        "hypothesis": "NY Asia Reference + London Impulse + True ATR Stop Band (0.90-1.65 ATR, 8.0-14.5 bps) + H1 Trend + Fresh Breakout + OneTradePerSidePerDay",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 10.0,
            "MinStopATR": 0.90,
            "MaxStopATR": 1.65,
            "MaxTradesPerDay": 2,
            "OneTradePerSidePerDay": "true",
            "RequireFreshBreakout": "true",
            "RequireH1Trend": "true",
            "SkipOverlap": "true",
            "SkipNY": "true",
            "MinStopBps": 8.0,
            "MaxStopBps": 14.5,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H22_global_hybrid_champion",
        "hypothesis": "NY Asia Reference + All 3 Sessions (Fast in London, Fresh+H1Trend in Overlap/NY) + Skip 4 Institutional Whipsaw/Fix Hours + Stop Band (5.8-12.5 bps) + OneTradePerSidePerDay",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 10.0,
            "MaxStopATR": 2.5,
            "MaxTradesPerDay": 2,
            "OneTradePerSidePerDay": "true",
            "DynamicSessionRef": 4,
            "MinStopBps": 5.8,
            "MaxStopBps": 12.5,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H23_global_fast_champion",
        "hypothesis": "NY Asia Reference + All 3 Sessions + Skip 4 Institutional Whipsaw/Fix Hours (9AM/11AM LDN, 11AM/1PM NY) + Stop Band (5.8-12.5 bps) + OneTradePerSidePerDay",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 10.0,
            "MaxStopATR": 2.5,
            "MaxTradesPerDay": 2,
            "OneTradePerSidePerDay": "true",
            "MinStopBps": 5.8,
            "MaxStopBps": 12.5,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H24_champion_v7_pro",
        "hypothesis": "NY Asia Reference + All 3 Sessions + Skip 4 Institutional Whipsaw/Fix Hours (9AM/11AM LDN, 11AM/1PM NY) + MinStopBps=5.8 + MaxRange(30, 10*ATR) + MaxStop(9, 2.5*ATR)",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 10.0,
            "MaxStopATR": 2.5,
            "MaxTradesPerDay": 2,
            "MinStopBps": 5.8,
            "MaxStopBps": 0.0,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H25_champion_v7_oneside",
        "hypothesis": "NY Asia Reference + All 3 Sessions + Skip 4 Institutional Whipsaw/Fix Hours + OneTradePerSidePerDay + MinStopBps=5.8 + MaxRange(30, 10*ATR) + MaxStop(9, 2.5*ATR)",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 10.0,
            "MaxStopATR": 2.5,
            "MaxTradesPerDay": 2,
            "OneTradePerSidePerDay": "true",
            "MinStopBps": 5.8,
            "MaxStopBps": 0.0,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H26_stopband155_v7",
        "hypothesis": "Champion V7 + Stop Band [5.8, 15.5] bps (blocks overextended >15.5 bps climax spikes while preserving 2nd-breakout entries)",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 10.0,
            "MaxStopATR": 2.5,
            "MaxTradesPerDay": 2,
            "MinStopBps": 5.8,
            "MaxStopBps": 15.5,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H27_stopband145_v7",
        "hypothesis": "Champion V7 + Stop Band [5.8, 14.5] bps (blocks overextended >14.5 bps climax spikes while preserving 2nd-breakout entries)",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 10.0,
            "MaxStopATR": 2.5,
            "MaxTradesPerDay": 2,
            "MinStopBps": 5.8,
            "MaxStopBps": 14.5,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H28_ny_short_guard_v8",
        "hypothesis": "V8 Pro: NY Asia Ref + Stop Band [5.8, 15.5] bps + Skip NY Lunch (12-13 NY) + NY Short Bear-Trap Guard (requires H1 EMA50 + ADX>=20 + Fresh Body>=0.45 for Shorts in NY)",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 10.0,
            "MaxStopATR": 2.5,
            "MaxTradesPerDay": 2,
            "DynamicSessionRef": 5,
            "MinStopBps": 5.8,
            "MaxStopBps": 15.5,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H29_ny_short_guard_ldn10_v8",
        "hypothesis": "V8 Pro + London 10AM Trend Filter: Stop Band [5.8, 14.5] bps + Skip NY Lunch + NY Short Guard + London 10AM requires H1 EMA50 trend alignment",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 10.0,
            "MaxStopATR": 2.5,
            "MaxTradesPerDay": 2,
            "DynamicSessionRef": 6,
            "MinStopBps": 5.8,
            "MaxStopBps": 14.5,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H30_ny_short_strict_v8",
        "hypothesis": "V8 Pro Strict: Stop Band [5.8, 14.5] bps + Skip NY Lunch + NY Short Guard with >=2 Confirmations",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 10.0,
            "MaxStopATR": 2.5,
            "MaxTradesPerDay": 2,
            "DynamicSessionRef": 7,
            "MinStopBps": 5.8,
            "MaxStopBps": 14.5,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H31_v8_smart_session",
        "hypothesis": "V8 Smart Session: ATR Stop (MaxStopATR=2.5, MinStopBps=5.8) + London 10AM requires H1 Trend/ADX>=20/Body>=0.45 + Overlap Short requires H1 EMA50 alignment",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 10.0,
            "MaxStopATR": 2.5,
            "MaxTradesPerDay": 2,
            "DynamicSessionRef": 8,
            "MinStopBps": 5.8,
            "MaxStopBps": 0.0,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H32_v8_london10_skip",
        "hypothesis": "V8 Pure Impulse: ATR Stop (MaxStopATR=2.5, MinStopBps=5.8) + Skip Mid-London 10AM Chop + Overlap Short requires H1 EMA50 alignment",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 10.0,
            "MaxStopATR": 2.5,
            "MaxTradesPerDay": 2,
            "DynamicSessionRef": 9,
            "MinStopBps": 5.8,
            "MaxStopBps": 0.0,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H33_v8_ultimate_pro",
        "hypothesis": "V8 Ultimate Pro: NY Asia Ref + Stop Band [5.8, 17.2] bps + London 10AM Trend/Body Filter + Overlap Short requires H1 EMA50 or M15 BOS + Skip 4 Whipsaw Hours",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 10.0,
            "MaxStopATR": 2.5,
            "MaxTradesPerDay": 2,
            "DynamicSessionRef": 8,
            "MinStopBps": 5.8,
            "MaxStopBps": 17.2,
            "SkipWhipsawHours": "true",
        },
    },
    {
        "code": "H34_v9_adaptive_impulse",
        "hypothesis": "V9 Adaptive Impulse: NY Asia Ref + MinStopBps=5.8 + Wide-Stop (>15 bps) requires Marubozu Body>=0.60 & H1 Trend/ADX>=20 + London 10AM Filter + Overlap Short Guard",
        "overrides": {
            "Reference": 1,
            "MaxRangeWidth": 30.0,
            "MaxRangeATR": 10.0,
            "MaxStopATR": 2.5,
            "MaxTradesPerDay": 2,
            "DynamicSessionRef": 10,
            "MinStopBps": 5.8,
            "MaxStopBps": 0.0,
            "SkipWhipsawHours": "true",
        },
    },
]


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
                    "month": cols[0][:7].replace(".", "-"),
                    "side": cur_in[3],
                    "lots": float(cur_in[5]),
                    "entry": float(cur_in[6].replace(" ", "")),
                    "exit": float(cols[6].replace(" ", "")),
                    "pnl": pnl,
                    "session": cur_in[12],
                    "exit_reason": cols[12],
                })
                cur_in = None

    by_session = defaultdict(lambda: {"trades": 0, "wins": 0, "net": 0.0})
    by_month = defaultdict(float)
    longest_losing_streak = cur_streak = 0
    wins = losses = 0
    win_sum = loss_sum = 0.0
    for t in trades:
        s = by_session[t["session"]]
        s["trades"] += 1
        s["net"] = round(s["net"] + t["pnl"], 2)
        if t["pnl"] > 0:
            s["wins"] += 1
            wins += 1
            win_sum += t["pnl"]
            cur_streak = 0
        else:
            losses += 1
            loss_sum += abs(t["pnl"])
            cur_streak += 1
            longest_losing_streak = max(longest_losing_streak, cur_streak)
        by_month[t["month"]] = round(by_month[t["month"]] + t["pnl"], 2)

    avg_loss = (loss_sum / losses) if losses > 0 else 10.0
    expectancy_r = ((win_sum - loss_sum) / len(trades) / avg_loss) if (trades and avg_loss > 0) else 0.0
    return {
        "deal_count": len(trades),
        "expectancy_r": round(expectancy_r, 4),
        "longest_losing_streak": longest_losing_streak,
        "performance_by_session": dict(by_session),
        "monthly_net": dict(by_month),
    }


def run_mt5_experiment(
    code: str,
    hypothesis: str,
    split: str,
    overrides: dict,
    model: int = 1,
    from_date: str | None = None,
    to_date: str | None = None,
    shutdown: int = 1,
    output_dir: Path = ROOT / "research" / "output",
) -> dict:
    params = dict(DEFAULT_PARAMS)
    params.update(overrides)
    start_dt, end_dt = SPLITS[split]
    f_str = from_date or start_dt.strftime("%Y.%m.%d")
    t_str = to_date or end_dt.strftime("%Y.%m.%d")

    identity = {
        "code": code,
        "split": split,
        "from": f_str,
        "to": t_str,
        "model": model,
        "params": params,
        "source_sha256": source_hash(),
    }
    exp_id = "gl-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]

    set_lines = [f"{k}={v}" for k, v in params.items()]
    set_content = "\n".join(set_lines) + "\n"
    set_name = f"{exp_id}.set"
    set_path = MT5_DIR / "MQL5" / "Profiles" / "Tester" / set_name
    set_path.write_text(set_content, encoding="ascii")

    report_rel = f"Reports\\GoldLab\\{exp_id}.htm"
    report_path = MT5_DIR / "Reports" / "GoldLab" / f"{exp_id}.htm"
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
        f"FromDate={f_str}\r\n"
        f"ToDate={t_str}\r\n"
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
        f"ShutdownTerminal={shutdown}\r\n"
    )
    ini_path.write_text(ini_content, encoding="ascii")

    subprocess.run(["pkill", "-f", "terminal64.exe"], check=False)
    time.sleep(1.0)

    env = dict(**os.environ, WINEPREFIX=str(WINEPREFIX))
    cmd = [
        str(WINE_BIN),
        "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
        "/skipupdate:8C031038965130FBEA0639F074B5E35F",
        "/portable",
        f"/config:{ini_name}",
    ]
    if shutdown == 1:
        subprocess.run(cmd, cwd=str(MT5_DIR), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    else:
        subprocess.Popen(cmd, cwd=str(MT5_DIR), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(90):
            if report_path.is_file() and report_path.stat().st_size > 1000:
                time.sleep(1.5)
                break
            time.sleep(0.5)

    if not report_path.is_file():
        raise RuntimeError(f"MT5 report was not generated for {code} ({exp_id})")

    summary = parse_report(report_path)
    deal_stats = parse_deals(report_path)
    days = max(1, (end_dt - start_dt).days)
    summary.update({
        "code": code,
        "hypothesis": hypothesis,
        "split": split,
        "model": model,
        "from_date": f_str,
        "to_date": t_str,
        "average_trades_per_week": round(summary["trade_count"] * 7.0 / days, 2),
        "net_return_pct": round(100.0 * summary["net_profit"] / summary["initial_deposit"], 2),
        **deal_stats,
    })

    res_dir = output_dir / "results" / exp_id
    res_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(report_path, res_dir / "report.htm")
    shutil.copyfile(set_path, res_dir / set_name)
    shutil.copyfile(ini_path, res_dir / "tester.ini")
    (res_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    with closing(registry(output_dir)) as db, db:
        db.execute(
            """INSERT INTO experiments(id,config,status,detail,summary) VALUES(?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET config=excluded.config,status=excluded.status,
               detail=excluded.detail,summary=excluded.summary""",
            (
                exp_id,
                json.dumps(identity, sort_keys=True),
                "COMPLETED_MT5",
                json.dumps({"code": code, "hypothesis": hypothesis, "report": str(report_path)}),
                json.dumps(summary),
            ),
        )
    return {"id": exp_id, "summary": summary}


import os

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("training", "validation", "holdout"), default="training")
    parser.add_argument("--model", type=int, default=1)
    parser.add_argument("--from-date", default=None)
    parser.add_argument("--to-date", default=None)
    parser.add_argument("--shutdown", type=int, default=1)
    parser.add_argument("--codes", nargs="*", help="Subset of hypothesis codes to run")
    args = parser.parse_args()

    for item in TRAINING_HYPOTHESES:
        if args.codes and item["code"] not in args.codes:
            continue
        res = run_mt5_experiment(
            code=item["code"],
            hypothesis=item["hypothesis"],
            split=args.split,
            overrides=item["overrides"],
            model=args.model,
            from_date=args.from_date,
            to_date=args.to_date,
            shutdown=args.shutdown,
        )
        s = res["summary"]
        print(
            f"{item['code']:26s} | id={res['id']} | trades={s['trade_count']:3d} | "
            f"net={s['net_profit']:8.2f} | pf={str(s['profit_factor']):5s} | "
            f"win={(s['win_rate'] or 0)*100:5.1f}% | dd={s['equity_drawdown_pct']:5.2f}% | "
            f"expR={s['expectancy_r']:6.3f} | streak={s['longest_losing_streak']}",
            flush=True,
        )
