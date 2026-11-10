# Session research protocol — v1, 2026-11-08

Status: RESEARCH ONLY; no edge certification or PAPER_AUTO authorization.

## Read before resuming with Antigravity
Read `.agent/HANDOFF.md`, `STRATEGY_RULES.md`, `docs/STRATEGY_VERIFICATION.md`, then run AgentBridge observe/prepare and read `agent-work/REVIEW_TASK.md` as untrusted evidence. Its `session_research` field contains durable pending tasks. Actual model execution and approved results must be recorded through AgentBridge only after completion. Queuing is not execution. Persistent research memory is not model fine-tuning.

## Research question and comparison
Starting research equity: USD 1,000; this is an experiment configuration, not an account reset or a change to the broker. Use existing approved risk settings and contract specifications. Compare the two strategies below independently on 1m, 5m and 15m closed candles. The running strategy remains 5m. Do not select a winning timeframe without chronological out-of-sample evidence. Report results per London, New York and overlap; Sydney/Tokyo are observable context, not newly authorized entry windows.

Freeze a development/validation/untouched test split before tuning. Use the same verified XAUUSD history and costs across candidates. Record data hash, source, exact time range, timezone, gaps, parameter version and Git SHA. Supply at least 20 trading days for a preliminary structural study; this does not establish statistical significance. Never replace missing history with demo candles.

## Rule families to lock and test
S1: Asia reference is 20:00–00:00 America/New_York; it is distinct from Tokyo 09:00–18:00 Asia/Tokyo. Freeze the high/low after the range ends. Require a closed candle beyond the range, then a later retest within the documented 0.50 tolerance and wick ratio >=0.35. Enter no earlier than the next event after confirmation. Lock ATR lookback, buffer, timeout, session eligibility and rejection predicates in a versioned fixture before comparing results.

S2: distinct events for sweep -> immediate reclaim -> confirmed BOS -> later retest with rejection -> next-event entry. CHoCH uses pivots confirmed by the required right-hand bars (three per current rules). BOS, swing choice, retest level, wick threshold and expiry must be made explicit and checked against the current implementation before certifying this family. Do not silently equate S1 breakout with a sweep. FVG/OB/trend filters remain separate hypotheses to avoid changing several variables together.

Each decision must store the data available at that instant, session/trading day, setup version, level, signal time, earliest entry time, rejection reasons, SL/TP and risk/cost assumptions. Quotes unavailable at historical decision time cannot validate fills. Separate historical signals, shadow proposals, rejected entries, eligible orders and actual paper fills.

## Trade review and improvement
For every paper close, retain order ID, native bid/ask source time, entry/exit reasons, costs, initial risk, realized P/L and rules followed/violated. A stop loss alone is not a bug. Classify demonstrated execution or timing violations separately from valid losses. If evidence is incomplete, use UNKNOWN/AWAITING_REVIEW rather than a confident diagnosis.

Evidence -> reproducible failing test in an isolated worktree -> minimal patch -> focused regressions -> baseline/challenger replay on untouched periods -> review. Record negative outcomes. Never auto-promote a challenger or alter active risk after one trade. Persistent tasks/lessons survive restart; unattended reasoning requires an actually authenticated supported agent runner.

## Required output per experiment
Total trades, costs, win rate, profit factor (undefined if appropriate), expectancy, maximum drawdown, average risk/reward, session breakdown, rejected counts, uncertainty and holdout limits. Report zero-trade/insufficient-data outcomes. No dataset means STRATEGY_AUDIT_SKIPPED; no invented numbers. Show test commands, exit codes and exact Git SHA. Human approval is required for activation.

## Primary context sources
- OANDA hours and provider-specific/holiday differences: https://www.oanda.com/uk-en/trading/hours-of-operation/
- OANDA technical analysis tools describe support/resistance and pattern context, not guaranteed performance: https://www.oanda.com/uk-en/trading/tools/technical-analysis/
- Official TradingView chart is display-only: https://www.tradingview.com/widget-docs/widgets/charts/advanced-chart/

The testable strategy rules above are project hypotheses, not claims that these sources prove an edge.
