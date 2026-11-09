"""Chronological screening of the native EA rules in an offline Bid/Ask replay."""
import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from research.replay_quotes import checked_files, grouped, read_minutes, read_ticks
from research.run_backtest import MODES, SPLITS, STRATEGIES, months, source_hash


M5 = 300_000
DAY = 86_400_000
LONDON = ZoneInfo("Europe/London")
NY = ZoneInfo("America/New_York")
REFERENCES = ("asia-utc", "asia-ny")
ROUND_TURN_PER_LOT = 10.0
INITIAL_EQUITY = 1000.0
RISK_PCT = 0.03
DAY_LOSS_PCT = 0.06
SLIPPAGE_RESERVE = 0.20


def ms(value):
    return int(pd.Timestamp(value, tz="UTC").timestamp() * 1000)


def minute_of_day(times):
    return times.hour * 60 + times.minute


@dataclass(frozen=True)
class Signal:
    at: int
    quote: int
    side: int
    level: float
    stop: float
    target: float
    atr: float
    session: str


class Features:
    def __init__(self, quotes):
        bars = grouped(quotes, 300)
        clock = pd.to_datetime(bars.index, utc=True, unit="ms")
        ny_clock = clock.tz_convert(NY)
        ny, london = minute_of_day(ny_clock), minute_of_day(clock.tz_convert(LONDON))
        ld = (london >= 480) & (london < 1020)
        us = (ny >= 570) & (ny < 930)
        self.session = np.select(
            [(clock.day_of_week < 5) & rule for rule in (ld & us, us, ld & (london < 720))],
            ["overlap", "new-york", "london"], default="closed",
        )
        self.times = bars.index.to_numpy()
        self.o, self.h, self.l, self.c = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))
        self.quote_start = bars["quote_start"].to_numpy()
        self.refs = {}
        for day in pd.DatetimeIndex(clock.normalize().unique()):
            utc = int(day.timestamp() * 1000)
            previous_ny = (day + pd.Timedelta(hours=12)).tz_convert(NY).date() - timedelta(days=1)
            local_start = datetime.combine(previous_ny, datetime.min.time(), tzinfo=NY) + timedelta(hours=20)
            local_end = datetime.combine(previous_ny + timedelta(days=1), datetime.min.time(), tzinfo=NY)
            windows = ((utc, utc + 7 * 3600_000),
                       (int(local_start.timestamp()*1000), int(local_end.timestamp()*1000)))
            for ref, (start, end) in zip(REFERENCES, windows):
                left, right = np.searchsorted(self.times, [start, end])
                if (right-left >= np.ceil((end-start)/M5*0.8)
                    and self.times[left] == start and self.times[right-1] == end-M5):
                    low, high = self.l[left:right].min(), self.h[left:right].max()
                    if 2 <= high-low <= 30:
                        self.refs[ref, utc] = (end, low, high)

        def lagged(frame, seconds, series, target_times=None):
            ends = frame.index.to_numpy() + seconds*1000
            idx = np.searchsorted(ends, self.times if target_times is None else target_times, side="right") - 1
            return np.where(idx >= 0, series.to_numpy()[idx], np.nan)

        def true_range(frame):
            return pd.concat([frame.high-frame.low, (frame.high-frame.close.shift()).abs(),
                              (frame.low-frame.close.shift()).abs()], axis=1).max(axis=1)

        def wilder(series):
            return series.ewm(alpha=1/14, adjust=False, min_periods=14).mean()

        self.atr = wilder(true_range(bars)).shift(2).to_numpy()
        hr = grouped(quotes, 3600)
        up, down = hr.high.diff(), -hr.low.diff()
        plus = wilder(up.where((up > down) & (up > 0), 0))
        minus = wilder(down.where((down > up) & (down > 0), 0))
        adx = wilder((100*(plus-minus).abs()/(plus+minus)).fillna(0))
        self.adx = lagged(hr, 3600, adx)
        self.ema = lagged(hr, 3600, hr.close.ewm(span=50, adjust=False, min_periods=50).mean())
        self.hour_close = lagged(hr, 3600, hr.close)
        m15 = grouped(quotes, 900)
        breakout = (m15.close > m15.high.shift().rolling(3).max()).astype(int)
        breakdown = (m15.close < m15.low.shift().rolling(3).min()).astype(int)
        self.struct = lagged(m15, 900, breakout-breakdown)
        self.volume = (bars["count"].shift(1)/bars["count"].shift(2).rolling(20).mean()).to_numpy()
        self.has_tick_volume = quotes.is_tick
        self.quote_time = quotes.time

    def wick(self, i, side):
        span = self.h[i]-self.l[i]
        if span <= 0:
            return 0.0
        wick = (min(self.o[i],self.c[i])-self.l[i] if side > 0
                else self.h[i]-max(self.o[i],self.c[i]))
        return wick/span

    def confirmations(self, i, side):
        k = i+1
        trend = self.hour_close[k] >= self.ema[k] if side > 0 else self.hour_close[k] < self.ema[k]-1
        fvg = False
        for j in range(i,i-6,-1):
            low, high = ((self.h[j-2],self.l[j]) if side > 0 else (self.h[j],self.l[j-2]))
            if high-low < 0.20:
                continue
            invalidated = (np.any(self.l[j+1:i+1]<=low) if side > 0 else np.any(self.h[j+1:i+1]>=high))
            if not invalidated:
                fvg = True
                break
        span = self.h[i]-self.l[i]
        momentum = (self.has_tick_volume and self.volume[k] >= 0.60 and span >= self.atr[k]
                    and span > 0 and abs(self.c[i]-self.o[i])/span >= 0.45)
        return int(trend)+int(fvg)+int(momentum)+int(self.struct[k]==side)

    def pivot(self, i, side):
        prices = self.h if side > 0 else -self.l
        for j in range(i-4,i-29,-1):
            if prices[j] > max(prices[j-3:j].max(),prices[j+1:j+4].max()):
                return side*prices[j]
        return 0.0

    def signals(self, ref, strategy, mode, start, end):
        out = []
        pending = None
        for k in range(max(32, self.times.searchsorted(start)), self.times.searchsorted(end)):
            at, session = self.times[k], self.session[k]
            if (session == "closed" or self.session[k-1] != session or at-self.times[k-32] != 32*M5
                or self.quote_time[self.quote_start[k]]-at > 30_000
                or not np.isfinite(self.atr[k]+self.adx[k]+self.ema[k]+self.struct[k]) or self.atr[k]<=0):
                pending = None
                continue
            i = k-1
            o,h,l,c = self.o[i],self.h[i],self.l[i],self.c[i]
            emit = False
            if pending:
                stamp, old_session, side, level, stop, target, stage, pivot, low, high = pending
                if at-stamp>25*60_000 or session!=old_session or side*(c-stop)<=0:
                    pending = None
                elif stage == "sweep":
                    if (at-stamp!=M5 or not low<c<high or side*(c-o)<=0
                        or (mode!="fast" and self.confirmations(i,side)<2)):
                        pending = None
                    elif mode=="conservative":
                        pending = (stamp,session,side,level,stop,target,"bos",pivot,low,high)
                    else:
                        emit = True
                elif stage == "bos":
                    if side*(c-pivot)>0 and side*(self.c[i-1]-pivot)<=0:
                        pending = (stamp,session,side,pivot,stop,target,"retest",pivot,low,high)
                elif strategy=="range" and (self.adx[k]>=20 or h-l>1.5*self.atr[k]):
                    pending = None
                else:
                    emit = (l<=level+0.25 and h>=level-0.25 and side*(c-level)>0 and self.wick(i,side)>=0.35)
            else:
                window = self.refs.get((ref, at-at%DAY))
                if not window or window[0]>at-M5:
                    continue
                _, low, high = window
                target = 0.0
                pivot = 0.0
                if strategy == "breakout":
                    side = 1 if c>high+0.10 and c>o else -1 if c<low-0.10 and c<o else 0
                    level = high if side>0 else low
                elif strategy == "sweep":
                    above, below = h>high+0.10, l<low-0.10
                    side = 0 if above==below else 1 if below else -1
                    level = low if side>0 else high
                    if side and mode=="conservative":
                        pivot = self.pivot(i,side)
                        if not pivot or side*(c-pivot)>=0:
                            continue
                else:
                    if self.adx[k]>=20 or h-l>1.5*self.atr[k] or not low<c<high:
                        continue
                    edge = (high-low)*0.15
                    side = -1 if h>=high-edge and self.wick(i,-1)>=0.60 else 1 if l<=low+edge and self.wick(i,1)>=0.60 else 0
                    level = low+edge if side>0 else high-edge
                    target = (low+high)*0.5
                if not side or (strategy!="sweep" and mode!="fast" and self.confirmations(i,side)<2):
                    continue
                anchor = l if side>0 else h
                if strategy=="range":
                    anchor = min(l,low) if side>0 else max(h,high)
                stop = anchor-side*0.30
                if strategy=="sweep" or mode=="conservative":
                    stage = "sweep" if strategy=="sweep" else "retest"
                    pending = (at,session,side,level,stop,target,stage,pivot,low,high)
                else:
                    emit = True
            if emit:
                out.append(Signal(int(at), int(self.quote_start[k]), side, float(level),
                                  float(stop), float(target), float(self.atr[k]), str(session)))
                pending = None
        return out


def trade_exit(quotes, index, bound, side, stop, target, slippage):
    """Return a quote index and execution price; stop wins same-minute ambiguity."""
    if side > 0:
        opening, worst, best = quotes.bid_open, quotes.bid_low, quotes.bid_high
    else:
        opening, worst, best = quotes.ask_open, quotes.ask_high, quotes.ask_low
    cutoff = quotes.time[index]//DAY*DAY + 21*3_600_000
    time_exit = min(int(quotes.time.searchsorted(cutoff)), bound)
    adverse = side*(worst[index:time_exit]-stop)<=0
    favorable = side*(best[index:time_exit]-target)>=0
    hit = adverse | favorable
    if hit.any():
        offset = int(hit.argmax())
        j = index+offset
        if adverse[offset]:
            exit_at = min(opening[j], stop) if side>0 else max(opening[j],stop)
            return j, exit_at-side*slippage, "stop"
        return j, target, "target"
    if time_exit<bound:
        return time_exit, opening[time_exit]-side*slippage, "time"
    if side > 0:
        closing = quotes.bid_close[bound-1]
    else:
        closing = quotes.ask_close[bound-1]
    return bound-1, closing-side*slippage, "end"


def simulate(quotes, signals, end, slippage):
    balance = INITIAL_EQUITY
    last = -1
    day = None
    count = 0
    trades = []
    bound = quotes.time.searchsorted(end)
    for signal in signals:
        j, side = signal.quote, signal.side
        if j<=last:
            continue
        current_day = signal.at//DAY
        if current_day!=day:
            day, start_balance, count = current_day, balance, 0
        if count>=10:
            continue
        bid, ask = quotes.bid_open[j], quotes.ask_open[j]
        spread = ask-bid
        entry = ask if side>0 else bid
        if not 0<spread<=0.80 or side*(entry-signal.level)>0.5*signal.atr:
            continue
        stop = side*np.floor(side*signal.stop*100+1e-9)/100
        distance = side*(entry-stop)
        if not 1.50<=distance<=9.0 or spread>0.15*distance:
            continue
        raw_target = signal.target or entry+side*1.5*distance
        target = side*np.floor(side*raw_target*100+1e-9)/100
        if side*(target-entry)<1.2*distance:
            continue
        budget = min(RISK_PCT*balance, DAY_LOSS_PCT*start_balance + min(0,balance-start_balance))
        risk_per_lot = (distance+SLIPPAGE_RESERVE)*100+ROUND_TURN_PER_LOT
        margin_cap = balance/entry  # 100 oz per lot and modeled leverage of 1:100
        lots = np.floor(min(0.06,budget/risk_per_lot,margin_cap)*100+1e-9)/100
        if lots<0.01:
            continue
        entry += side*slippage
        last, exit_price, reason = trade_exit(quotes,j,bound,side,stop,target,slippage)
        pnl = (side*(exit_price-entry)*100-ROUND_TURN_PER_LOT)*lots
        balance += pnl
        count += 1
        trades.append(dict(entry_ms=int(quotes.time[j]), exit_ms=int(quotes.time[last]), side=side,
                           session=signal.session, lots=round(float(lots),2), entry=float(entry),
                           exit=float(exit_price), stop=float(stop), target=float(target), reason=reason,
                           pnl=float(pnl), risk=float(lots*risk_per_lot), equity=float(balance)))
    return trades


def summarize(trades):
    pnl = np.array([t["pnl"] for t in trades])
    balance = INITIAL_EQUITY + np.r_[0, pnl.cumsum()]
    peak = np.maximum.accumulate(balance)
    month, session = defaultdict(float), defaultdict(float)
    for trade in trades:
        month[pd.to_datetime(trade["exit_ms"], unit="ms",utc=True).strftime("%Y-%m")] += trade["pnl"]
        session[trade["session"]] += trade["pnl"]
    longest = streak = 0
    for profit in pnl:
        streak = streak+1 if profit<0 else 0
        longest = max(longest,streak)
    loss = -pnl[pnl<0].sum()
    return dict(trades=len(trades), net=round(float(pnl.sum()),2),
                return_pct=round(float(100*pnl.sum()/INITIAL_EQUITY),2),
                profit_factor=round(float(pnl[pnl>0].sum()/loss),4) if loss>0 else None,
                win_pct=round(float(100*(pnl>0).mean()),2) if len(trades) else None,
                mean_r=round(float(np.mean([t["pnl"]/t["risk"] for t in trades])),4) if trades else None,
                closed_trade_drawdown_pct=round(float(100*((peak-balance)/peak).max()),2),
                longest_losing_streak=longest,
                month_net={k: round(v,2) for k,v in month.items()},
                session_net={k: round(v,2) for k,v in session.items()})


def coverage_summary(quotes, start, end):
    observed = pd.to_datetime(np.unique(quotes.time//60_000)*60_000, unit="ms", utc=True)
    observed = observed[(observed >= pd.to_datetime(start, unit="ms", utc=True))
                        & (observed < pd.to_datetime(end, unit="ms", utc=True))]
    counts = pd.Series(1,index=observed).resample("D").sum() if len(observed) else pd.Series(dtype=int)
    return dict(first=str(observed.min()),last=str(observed.max()),observed_minutes=len(observed),
                weekdays_under_1000_minutes=[str(t.date()) for t,n in counts.items() if t.day_of_week<5 and n<1000],
                monthly_observed_minutes={t.strftime("%Y-%m"): int(n) for t,n in counts.resample("MS").sum().items()}
                if len(counts) else {})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,required=True)
    parser.add_argument("--granularity",choices=("m1","tick"),required=True)
    parser.add_argument("--split",choices=("training","validation"),required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--variants",nargs="+")
    parser.add_argument("--start",type=date.fromisoformat)
    parser.add_argument("--end",type=date.fromisoformat)
    args = parser.parse_args()
    choices = {f"{ref}:{strategy}:{mode}" for ref in REFERENCES
               for strategy in STRATEGIES for mode in MODES}
    if args.variants and not set(args.variants)<=choices:
        parser.error(f"Unknown variants: {sorted(set(args.variants)-choices)}")
    manifest, files = checked_files(args.data)
    split_start, split_end = SPLITS[args.split]
    window_start, window_end = args.start or split_start, args.end or split_end
    if not split_start<=window_start<window_end<=split_end:
        parser.error("The replay window must stay inside its chronological split")
    start, end = map(ms,(window_start,window_end))
    if args.granularity == "m1":
        expected = {f"xauusd_{side}_m1_{month[:4]}_{month[4:]}.csv"
                    for month in months(window_start,window_end) for side in ("bid","ask")}
        missing = expected-{p.name for p,_ in files}
        if missing:
            parser.error(f"Required quote files are missing: {sorted(missing)}")
    if args.output.exists():
        parser.error("Use a fresh output directory for each immutable run")
    quotes, quality = (read_minutes if args.granularity=="m1" else read_ticks)(files)
    coverage = coverage_summary(quotes,start,end)
    if not coverage["observed_minutes"]:
        parser.error("No observed market data in the requested split")
    features = Features(quotes)
    result = dict(split=args.split, from_inclusive=window_start.isoformat(), to_exclusive=window_end.isoformat(), source=manifest["repo"], revision=manifest["revision"],
                  replay_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  quote_loader_sha256=hashlib.sha256(Path(__file__).with_name("replay_quotes.py").read_bytes()).hexdigest(),
                  native_source_sha256=source_hash(), granularity=args.granularity,
                  cost_model={"balance_usd": INITIAL_EQUITY, "round_turn_usd_per_lot": ROUND_TURN_PER_LOT,
                              "base_slippage_usd_per_oz_per_market_leg": 0.05,
                              "stress_slippage_usd_per_oz_per_market_leg": 0.10},
                  files={p.name:sha for p,sha in files},quality=quality,
                  coverage=coverage, results={})
    args.output.mkdir(parents=True)
    for ref in REFERENCES:
        for strategy in STRATEGIES:
            for mode in MODES:
                key = f"{ref}:{strategy}:{mode}"
                if args.variants and key not in args.variants:
                    continue
                signals = features.signals(ref,strategy,mode,start,end)
                base = simulate(quotes,signals,end,0.05)
                stress = simulate(quotes,signals,end,0.10)
                result["results"][key] = dict(signals=len(signals), base=summarize(base), stress=summarize(stress))
                pd.DataFrame(base).to_csv(args.output/(key.replace(":","_")+".csv"),index=False)
                print(key,result["results"][key]["base"]["trades"],result["results"][key]["base"]["net"],flush=True)
    (args.output/"summary.json").write_text(json.dumps(result,indent=2)+"\n")


if __name__ == "__main__":
    main()
