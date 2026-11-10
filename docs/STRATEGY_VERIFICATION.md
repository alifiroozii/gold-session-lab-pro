# Strategy Verification Gate — Research-only audit

**Status: NOT CERTIFIED FOR PAPER AUTO.** Passing a unit test or historical signal check
does **not** mean the strategy is profitable or authorized to trade. Keep PAPER_AUTO
blocked until market data, execution and rulebook checks have been independently resolved.

## Two separate questions

1. **Implementation correctness**: Does the code follow a precisely specified strategy
   using only data known at decision time?
2. **Trading edge**: Does the strategy retain positive risk-adjusted expectancy on a
   truly unseen time period after spread, bid/ask, slippage, commissions and execution
   uncertainty? A losing trade can be completely valid; a winning trade can be invalid.

## Verified code risks on this branch (as of initial audit)

- `goldlab/setups.py` scans only `range(..., n-1)`, so every emitted historical signal
  references an existing next candle; `goldlab/bot.py` filters
  `signal_index == len(current_candles)-1`. This contract mismatch must be fixed
  through a closed-candle / next-quote event-driven design, **not** merely by
  submitting stale signals one bar late.
- `goldlab/sessions.py:calculate_session_stats` summarizes Asia / London / New York
  and prior-day levels relative to the **last** candle in the supplied dataset, while
  `goldlab/engine.py:run_pipeline` passes those levels to setup evaluation across
  the entire history. Consequently, historical signals may use session context that
  did not exist when the original decision would have been made. Replace with
  per-decision as-of session levels and add regression fixtures.
- `goldlab/backtester.py` currently treats 30 trades as sufficient evidence. This is
  only a screening count, not a statistically justified proof of an edge.

## Now implemented

`goldlab/strategy_verification.py` checks historical signal structure:
bar times, next-bar entry contract, candle closure, stop/take-profit brackets,
duplicate signals and price consistency. The point-in-time audit rebuilds the
research pipeline on a history truncated immediately after each sampled signal's
next-open bar and compares decisions to the full historical run. Differences are
reported as `HISTORICAL_SIGNAL_CHANGED`. This check is necessary but not sufficient
for absence of lookahead and does not certify market-data authenticity.

Run (after installing project requirements):

```bash
python -m pytest -q tests/test_strategy_verification.py
python -m scripts.verify_strategy /path/to/actual_xauusd_m1.csv --timeframe 5m
```

Review `reports/STRATEGY_VALIDATION.json`. This artifact never claims the input CSV
is live or verified. The bundled `data/demo_xauusd_1m.csv` is only a fixture,
**not** evidence of market performance.

## Required subsequent gates for Antigravity

**Gate A — Rulebook:** Lock one human-readable *and machine-readable* spec per strategy
with ID/version/market session/window, exact Sweep -> Reclaim -> confirmed BOS ->
Retest conditions, direction, candle-close timing, invalidation, minimum spread,
SL/TP, risk and event timestamps. For every rule, create positive and negative
synthetic fixtures reviewed on the chart.

**Gate B — Temporal correctness:** Run deterministic bar-by-bar replay, no future
session highs/lows, confirmed pivots only, no candles from unknown future, no
retroactive signals. Compare the streaming engine to the full-history engine.
Block if a single critical divergence is unexplained.

**Gate C — Independent evidence:** Use licensed, real and provenance-tracked XAUUSD
data; split chronologically into development, validation and untouched test
periods. Include bid/ask and realistic costs, market closure and exchange/provider
status, parameter sensitivity, multiple-trial history, uncertainty intervals,
and holdout evaluation. Do not treat 30 trades alone as sufficient.

**Gate D — Forward paper monitoring:** Compare Champion vs Challenger on a separate
paper account and unchanged rules. Audit every signal and execution, record
reason codes for rejected signals, count errors and ordinary losses separately.
Require operator approval before any change to an active strategy, risk guard,
ledger or paper-order path.

For Antigravity: after each patch, show a reproducible bug, regression test,
exact git ref, before/after evidence, dataset provenance and holdout results.
If an item is unverified, label it **UNKNOWN**, not **FIXED** or **LEARNED**.
