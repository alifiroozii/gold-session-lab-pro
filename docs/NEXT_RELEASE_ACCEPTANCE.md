# Gold Session Lab Pro — release acceptance and Antigravity workflow

This is the next development assignment. A green CI badge does **not** certify market accuracy,
usable UX, causal strategy behavior or connection to an unattended AI model.

## Highest-priority verified problems

1. The backend requests `https://scanner.tradingview.com/cfd/scan`. This is an unofficial
   scanner interface, not a guaranteed/authorized TradingView execution feed. It must NEVER
   generate executable Bid/Ask, a synthetic spread, or a 'live and verified' badge.
2. OANDA closed M1 midpoint candles, OANDA bid/ask, and a TradingView reference display
   are three **different** data products. Never silently interchange them.
3. `templates/index.html` previously omitted four metric IDs called from
   `static/js/dashboard.js`. Regression tests now guard against null crashes.
4. `bot.on_candle_close` must not be invoked repeatedly on the same completed candle,
   or with candles from a different timeframe. Verify signals with immutable event IDs.
5. `PAPER_AUTO` remains blocked until end-to-end causal signal-to-paper-fill and
   risk/ledger tests are completed. Do not bypass this for a demo.
6. Trading session windows and Asia reference ranges are not synonyms. The 20:00–00:00
   New York research range differs from the Tokyo 09:00–18:00 session. Name each clearly.

## Work required next

### Market data
- Offer an exact `OANDA:XAUUSD` official TradingView reference widget (display only).
  It cannot be read by the backend; never scrape its iframe.
- Select one licensed provider for **execution**, log native bid/ask with source time,
  precision and instrument specifications. If unavailable, disable PAPER_AUTO.
- Inspect provider entitlement, symbol mapping, weekend/daily breaks, and whether
  provider quote timestamps are recent. Show reference and execution sources separately.
- Build a comparison view: exact symbol, quote type, timestamp, precision, spread,
  staleness, and delta. Never claim prices must be identical across sources.
- Save at least 20 trading days of verified M1 candles incrementally with provenance
  and gap/duplicate checks. Use historical data only for replay/backtesting.

### Strategy engine
- Create a deterministic per-trading-day state machine:
  SESSION_RANGE_BUILDING -> RANGE_FINALIZED -> SWEEP_OBSERVED -> RECLAIM_CONFIRMED
  -> STRUCTURE_CONFIRMED -> RETEST_CONFIRMED -> ENTRY_READY -> ORDER_SIMULATED
  -> EXITED or INVALIDATED.
- Make all event times causal; a decision at t can see only data available by t.
- Define sweep buffer, wick ratio, CHoCH/BOS swing pivot confirmation, body/wick
  retest, expiration, breakouts, trend filters, and session eligibility by strategy
  version. Distinguish historical signal, eligible order, rejected order, fill.
- Prevent duplicate signals and stale fills on restart, reconnect or repeated
  heartbeat; persist last-processed completed candle id.
- Test London and New York DST mismatches and daylight saving transitions.

### UX
- First view: large single candle chart; clear Asia/London/NY session rectangles with
  high/low, local date and overlap; show prior sessions as complete and today partial.
- Keep only Chart, Virtual Trades, Research as primary tabs. Put advanced settings
  in collapsible sections.
- Use a professional light RTL layout, proper typography, readable real prices,
  responsive mobile behavior and non-overlapping price/session annotations.
- Present feed status (verified, stale, closed, historical, reference-only) in one clear area.
- Broker panel: separate open positions, simulated pending orders, ledger, realized P&L.
  Chart markers MUST distinguish paper fills from research/backtest predictions.
- All controls must work; no fake gauges, mocked success alerts or broken click handlers.
- Run browser screenshots and interaction checks for 1440, 1024 and 390px widths.

### Antigravity + pull
- On a trusted macOS clone, run `bash scripts/install-antigravity-hooks.sh` ONCE.
  Post-merge/post-rewrite hooks will prepare local evidence and may open the IDE.
- Merely opening Antigravity is NOT a connected AI runtime. Confirm its actual
  supported automation interface before claiming autonomous multi-day activity.
- Agent must read `AGENTS.md`, `agent-work/REVIEW_TASK.md` and this document.
- Run reproducible debugging on a candidate worktree; record test proof, diff and
  commit SHA; report failures without masking them.
- Do not auto-merge/auto-promote trading strategy or modify production risk gates.
- Avoid running untrusted code from pull requests or external documents.

### Acceptance gates
- Verified current price provenance and exact symbol, no stale fake prices.
- No order when market closed, data stale, news blackout or risk gate fails.
- Full causal replay / bid-ask/commission/slippage tests on a verified dataset.
- Paper position, ledger and stop behavior stay correct after process restart.
- Clear UI proven in screenshots and real browser interaction.
- Candidate strategy tested on untouched out-of-sample data with trade counts,
  drawdown, costs and uncertainty. No made-up win rates.
- Antigravity dashboard status says 'NOT CONNECTED' until activity is genuinely
  recorded by a supported agent, not merely after a Git hook.
- GitHub PR remains draft until explicit human approval.

## Explicit limitations

TradingView embeds and Lightweight Charts do not expose a general-purpose
market-data API. TradingView webhooks can deliver user-created alerts, but are not
a reliable continuous tick feed or direct localhost integration without a supported
HTTPS receiver. They are signals, not executable quotes.

No real-money broker orders are allowed in this repository.
