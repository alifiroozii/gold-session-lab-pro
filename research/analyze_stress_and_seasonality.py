#!/usr/bin/env python3
"""Advanced Stress Testing and Seasonality Intelligence Suite
Performs:
1. Day-of-Week Seasonality Analysis (Heavy & Balanced)
2. Day-of-Week Exclusion Simulation
3. Monte Carlo Simulation (Reshuffling & Random Drop)
4. Slippage & Execution Friction Stress Testing
"""

from collections import defaultdict
import csv
import datetime
from pathlib import Path
import random
import re
import statistics
import sys

REPORTS_DIR = Path("/Users/alifiroozi/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Reports/Optimization")
OUTPUT_DIR = Path("/Users/alifiroozi/ali/gold-session-mt5-research/research/output/optimization")
META_DIR = Path("/Users/alifiroozi/ali/METATRADER5")

def extract_trades(htm_path: Path):
    if not htm_path.is_file():
        raise FileNotFoundError(f"Report not found: {htm_path}")
    txt = htm_path.read_text(encoding="utf-16", errors="ignore")
    tables = re.findall(r"<table[^>]*>(.*?)</table>", txt, flags=re.S)
    if len(tables) < 2:
        raise ValueError(f"Could not find tables in {htm_path}")
    t1 = tables[1]
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t1, flags=re.S)
    
    deals_start = False
    in_deal = None
    trades = []
    
    for r in rows:
        cols = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, flags=re.S)
        clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cols]
        if "Deals" in clean:
            deals_start = True
            continue
        if not deals_start or len(clean) < 12:
            continue
        
        time_str, deal_id, symbol, deal_type, direction, volume, price, order_id, comm, swap, profit, balance = clean[:12]
        if deal_type in ["buy", "sell"]:
            comm_val = float(comm.replace(" ", ""))
            swap_val = float(swap.replace(" ", ""))
            profit_val = float(profit.replace(" ", ""))
            price_val = float(price.replace(" ", "")) if price else 0.0
            dt = datetime.datetime.strptime(time_str, "%Y.%m.%d %H:%M:%S")
            
            if direction == "in":
                in_deal = {
                    "entry_time": dt,
                    "type": deal_type,
                    "entry_price": price_val,
                    "volume": float(volume),
                    "comm_in": comm_val
                }
            elif direction == "out" and in_deal:
                net_pnl = profit_val + comm_val + in_deal["comm_in"] + swap_val
                trades.append({
                    "entry_time": in_deal["entry_time"],
                    "exit_time": dt,
                    "type": in_deal["type"],
                    "volume": in_deal["volume"],
                    "entry_price": in_deal["entry_price"],
                    "exit_price": price_val,
                    "gross_profit": profit_val,
                    "commission": comm_val + in_deal["comm_in"],
                    "swap": swap_val,
                    "net_pnl": net_pnl,
                    "day_name": in_deal["entry_time"].strftime("%A"),
                    "day_idx": in_deal["entry_time"].weekday(),
                    "year": in_deal["entry_time"].year
                })
                in_deal = None
    return trades

def compute_drawdown(pnls, initial_balance=1000.0):
    balance = initial_balance
    peak = initial_balance
    max_dd_usd = 0.0
    max_dd_pct = 0.0
    for p in pnls:
        balance += p
        if balance > peak:
            peak = balance
        dd_usd = peak - balance
        dd_pct = (dd_usd / peak * 100.0) if peak > 0 else 0.0
        if dd_usd > max_dd_usd:
            max_dd_usd = dd_usd
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
    return balance, max_dd_usd, max_dd_pct

def analyze_day_of_week(trades, model_name="Heavy Optimized"):
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    day_stats = {d: {"trades": 0, "wins": 0, "losses": 0, "net": 0.0, "gross_win": 0.0, "gross_loss": 0.0, "pnls": []} for d in days}
    
    for t in trades:
        d = t["day_name"]
        if d in day_stats:
            p = t["net_pnl"]
            day_stats[d]["trades"] += 1
            day_stats[d]["net"] += p
            day_stats[d]["pnls"].append(p)
            if p > 0:
                day_stats[d]["wins"] += 1
                day_stats[d]["gross_win"] += p
            else:
                day_stats[d]["losses"] += 1
                day_stats[d]["gross_loss"] += abs(p)
                
    results = []
    for d in days:
        st = day_stats[d]
        tr = st["trades"]
        wr = (st["wins"] / tr * 100.0) if tr > 0 else 0.0
        pf = (st["gross_win"] / st["gross_loss"]) if st["gross_loss"] > 0 else (999.0 if st["gross_win"] > 0 else 0.0)
        avg = st["net"] / tr if tr > 0 else 0.0
        results.append({
            "model": model_name,
            "day": d,
            "trades": tr,
            "wins": st["wins"],
            "losses": st["losses"],
            "win_rate_pct": round(wr, 1),
            "net_profit_usd": round(st["net"], 2),
            "avg_trade_usd": round(avg, 2),
            "profit_factor": round(pf, 2)
        })
    return results

def run_monte_carlo(trades, num_simulations=2000, initial_balance=1000.0):
    pnls = [t["net_pnl"] for t in trades]
    n_trades = len(pnls)
    
    final_equities = []
    max_drawdowns_pct = []
    max_consec_losses_list = []
    ruin_count = 0 # Equity dropping below $500 (50% loss)
    
    random.seed(42)
    for _ in range(num_simulations):
        sim_pnls = random.choices(pnls, k=n_trades) # bootstrap sampling
        bal, _, max_dd_pct = compute_drawdown(sim_pnls, initial_balance)
        
        # Consec losses
        cur_loss = 0
        max_loss = 0
        for p in sim_pnls:
            if p <= 0:
                cur_loss += 1
                if cur_loss > max_loss:
                    max_loss = cur_loss
            else:
                cur_loss = 0
                
        final_equities.append(bal)
        max_drawdowns_pct.append(max_dd_pct)
        max_consec_losses_list.append(max_loss)
        
        if bal < 500.0 or max_dd_pct >= 50.0:
            ruin_count += 1
            
    final_equities.sort()
    max_drawdowns_pct.sort()
    max_consec_losses_list.sort()
    
    def pctl(arr, q):
        idx = int(len(arr) * q)
        return arr[min(idx, len(arr) - 1)]
        
    return {
        "num_simulations": num_simulations,
        "ruin_probability_pct": round((ruin_count / num_simulations) * 100.0, 2),
        "median_final_equity": round(pctl(final_equities, 0.50), 2),
        "p5_final_equity": round(pctl(final_equities, 0.05), 2),
        "p95_final_equity": round(pctl(final_equities, 0.95), 2),
        "median_max_dd_pct": round(pctl(max_drawdowns_pct, 0.50), 2),
        "p95_worst_dd_pct": round(pctl(max_drawdowns_pct, 0.95), 2),
        "median_consec_losses": int(pctl(max_consec_losses_list, 0.50)),
        "p95_consec_losses": int(pctl(max_consec_losses_list, 0.95)),
    }

def run_slippage_stress(trades, slippage_points_list=[0, 10, 20, 30, 50], initial_balance=1000.0):
    # In XAUUSD_o, 0.10 lot has $0.10 tick value per 0.01 price move ($1 per 1.0 point / 100 points = $10.0 per $1 gold move)
    # LiteFinance digits = 2 (e.g. 2643.47). 1 pip = 0.10 (10 points).
    # For 0.10 lot: 1 point = $0.01. 10 points (1 pip) = $0.10 per point * 0.1 lot = $1.00 adverse impact.
    # Adverse slippage on entry + exit = 2 * slippage_points * $0.10 for 0.1 lot.
    # Wait, in XAUUSD: Contract size = 100 oz. 0.10 lot = 10 oz.
    # A $1.00 move in Gold (100 points) on 10 oz is $10.00.
    # So 1 point ($0.01) = $0.10.
    # 10 points (0.10 USD price difference) = $1.00.
    # 20 points (0.20 USD price difference) = $2.00.
    
    results = []
    for slip in slippage_points_list:
        cost_per_trade = (slip / 100.0) * 10.0 # for 0.1 lot: (slip / 100) * 100 oz * 0.1 lot = slip * 0.10
        # If applied on entry and exit (round-turn adverse execution)
        round_turn_cost = cost_per_trade * 2.0
        
        sim_pnls = [t["net_pnl"] - round_turn_cost for t in trades]
        net_profit = sum(sim_pnls)
        wins = sum(1 for p in sim_pnls if p > 0)
        losses = sum(1 for p in sim_pnls if p <= 0)
        gross_win = sum(p for p in sim_pnls if p > 0)
        gross_loss = abs(sum(p for p in sim_pnls if p <= 0))
        pf = (gross_win / gross_loss) if gross_loss > 0 else 999.0
        bal, max_dd_usd, max_dd_pct = compute_drawdown(sim_pnls, initial_balance)
        
        results.append({
            "slippage_points": slip,
            "slippage_pips": round(slip / 10.0, 1),
            "cost_per_trade_usd": round(round_turn_cost, 2),
            "net_profit_usd": round(net_profit, 2),
            "win_rate_pct": round((wins / len(trades)) * 100.0, 1),
            "profit_factor": round(pf, 2),
            "max_drawdown_usd": round(max_dd_usd, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "final_balance": round(bal, 2)
        })
    return results

def main():
    print("Extracting trades from Strategy Tester reports...")
    hvy_report = REPORTS_DIR / "Comp_Heavy_Optimized_Full.htm"
    bal_report = REPORTS_DIR / "Comp_Balanced_Optimized_Full.htm"
    
    hvy_trades = extract_trades(hvy_report)
    bal_trades = extract_trades(bal_report)
    
    print(f"Extracted {len(hvy_trades)} Heavy trades and {len(bal_trades)} Balanced trades.")
    
    # 1. Day of week analysis
    hvy_dow = analyze_day_of_week(hvy_trades, "Heavy Optimized")
    bal_dow = analyze_day_of_week(bal_trades, "Balanced Optimized")
    
    print("\n================== HEAVY OPTIMIZED: DAY OF WEEK ==================")
    for r in hvy_dow:
        print(f"{r['day']:<10} | Trades: {r['trades']:<3} | WinRate: {r['win_rate_pct']:>5.1f}% | Net: ${r['net_profit_usd']:>8.2f} | PF: {r['profit_factor']:>5.2f} | Avg: ${r['avg_trade_usd']:>6.2f}")
        
    print("\n================== BALANCED OPTIMIZED: DAY OF WEEK ==================")
    for r in bal_dow:
        print(f"{r['day']:<10} | Trades: {r['trades']:<3} | WinRate: {r['win_rate_pct']:>5.1f}% | Net: ${r['net_profit_usd']:>8.2f} | PF: {r['profit_factor']:>5.2f} | Avg: ${r['avg_trade_usd']:>6.2f}")
        
    # 2. Monte Carlo
    print("\n================== MONTE CARLO SIMULATION (2000 RUNS) ==================")
    hvy_mc = run_monte_carlo(hvy_trades, num_simulations=2000)
    bal_mc = run_monte_carlo(bal_trades, num_simulations=2000)
    print("Heavy Optimized Monte Carlo:", hvy_mc)
    print("Balanced Optimized Monte Carlo:", bal_mc)
    
    # 3. Slippage Stress
    print("\n================== SLIPPAGE & FRICTION STRESS TEST ==================")
    hvy_slip = run_slippage_stress(hvy_trades)
    bal_slip = run_slippage_stress(bal_trades)
    print("Heavy Slippage Stress:")
    for s in hvy_slip:
        print(f"  Slippage {s['slippage_points']:>2} pts ({s['slippage_pips']} pips): Net=${s['net_profit_usd']:>8.2f} | PF={s['profit_factor']:>4.2f} | DD={s['max_drawdown_pct']:>5.2f}% | Final=${s['final_balance']:>8.2f}")
        
    # 4. Day-of-Week Exclusion Analysis
    print("\n================== DAY-OF-WEEK FILTERING EXPERIMENTS ==================")
    # Baseline Heavy (all days)
    hvy_all_pnls = [t["net_pnl"] for t in hvy_trades]
    _, hvy_all_dd_usd, hvy_all_dd_pct = compute_drawdown(hvy_all_pnls)
    print(f"Heavy Baseline (All 5 Days)  : Trades={len(hvy_trades):>3} | Net=${sum(hvy_all_pnls):>8.2f} | PF={sum(p for p in hvy_all_pnls if p>0)/abs(sum(p for p in hvy_all_pnls if p<=0)):>4.2f} | DD={hvy_all_dd_pct:>5.2f}%")
    
    # Exclude Friday
    hvy_no_fri = [t["net_pnl"] for t in hvy_trades if t["day_name"] != "Friday"]
    _, _, hvy_no_fri_dd_pct = compute_drawdown(hvy_no_fri)
    pf_no_fri = sum(p for p in hvy_no_fri if p>0)/abs(sum(p for p in hvy_no_fri if p<=0))
    print(f"Heavy No-Friday (Mon-Thu)    : Trades={len(hvy_no_fri):>3} | Net=${sum(hvy_no_fri):>8.2f} | PF={pf_no_fri:>4.2f} | DD={hvy_no_fri_dd_pct:>5.2f}%")

    # Exclude Friday & Monday (Tue-Wed-Thu Core Golden Days)
    hvy_core = [t["net_pnl"] for t in hvy_trades if t["day_name"] in ["Tuesday", "Wednesday", "Thursday"]]
    _, _, hvy_core_dd_pct = compute_drawdown(hvy_core)
    pf_core = sum(p for p in hvy_core if p>0)/abs(sum(p for p in hvy_core if p<=0))
    print(f"Heavy Core (Tue-Wed-Thu only): Trades={len(hvy_core):>3} | Net=${sum(hvy_core):>8.2f} | PF={pf_core:>4.2f} | DD={hvy_core_dd_pct:>5.2f}%")

    # Balanced Exclusion
    bal_all_pnls = [t["net_pnl"] for t in bal_trades]
    _, _, bal_all_dd_pct = compute_drawdown(bal_all_pnls)
    bal_no_mon = [t["net_pnl"] for t in bal_trades if t["day_name"] != "Monday"]
    _, _, bal_no_mon_dd_pct = compute_drawdown(bal_no_mon)
    pf_bal_no_mon = sum(p for p in bal_no_mon if p>0)/abs(sum(p for p in bal_no_mon if p<=0))
    print(f"Balanced Baseline (All Days) : Trades={len(bal_trades):>3} | Net=${sum(bal_all_pnls):>8.2f} | DD={bal_all_dd_pct:>5.2f}%")
    print(f"Balanced No-Monday (Tue-Fri) : Trades={len(bal_no_mon):>3} | Net=${sum(bal_no_mon):>8.2f} | PF={pf_bal_no_mon:>4.2f} | DD={bal_no_mon_dd_pct:>5.2f}%")

    # Save CSVs
    dow_combined = hvy_dow + bal_dow
    fieldnames_dow = list(dow_combined[0].keys())
    with open(OUTPUT_DIR / "day_of_week_seasonality.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames_dow)
        w.writeheader()
        w.writerows(dow_combined)
        
    with open(META_DIR / "day_of_week_seasonality.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames_dow)
        w.writeheader()
        w.writerows(dow_combined)
        
    slip_combined = []
    for row in hvy_slip:
        slip_combined.append(dict(row, model="Heavy Optimized"))
    for row in bal_slip:
        slip_combined.append(dict(row, model="Balanced Optimized"))

    fieldnames_slip = ["model"] + list(hvy_slip[0].keys())
    with open(OUTPUT_DIR / "slippage_stress_test.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames_slip)
        w.writeheader()
        w.writerows(slip_combined)

    with open(META_DIR / "slippage_stress_test.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames_slip)
        w.writeheader()
        w.writerows(slip_combined)

    print("\nSaved CSV reports to optimization and METATRADER5 directories.")

if __name__ == "__main__":
    main()
