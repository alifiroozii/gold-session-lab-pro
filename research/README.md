# Gold Session Lab Pro MT5 research candidate

This branch adds a native MQL5 EA for the nonvisual Strategy Tester. Its entry and close calls require the tester flag. The default is signal audit mode. The dashboard and the running Python simulator are outside this experiment.

## Migration audit

The separately described Python MT5 forward tester was unavailable. The working copy's untracked `goldlab/pro_session_engine.py` informed this reconstruction. Exact source parity remains unverified. Treat `GoldResearchLab` as a new reference candidate. Champion selection is pending.

| Area | Reference and MT5 candidate |
| --- | --- |
| Levels | Separate UTC Asia 00:00–07:00 and NY Asia 20:00–00:00 local. Also London 08:00–17:00 local, original London 07:00–13:00 UTC, NY opening range 09:30–10:00 local, and closed broker D1/W1 OHLC. M5 ranges require both boundary bars and at least 80% valid bars. |
| Clock | UTC or explicit LiteFinance EU server clock. London and NY use their own DST transitions. The EU switch instant is assumed at 01:00 UTC and ambiguous server timestamps are rejected. The actual broker history and holiday closures still require verification. |
| Decision | M5 closed bar, first tick of the next M5 bar within 30 seconds. Both the closed bar and the entry bar must be in the same London 08:00–12:00 local, NY 09:30–15:30 local, or overlap category. Require 32 contiguous closed M5 bars. ATR(14) uses the bar before the decision. EMA(50) and ADX(14) use completed H1. The last closed M15 close is compared to the prior three M15 bars. Native indicator initialization and M5 volume differ from the Python reference. |
| Breakout | Directional close strictly more than 0.10 above/below a finalized range of width 2.00–30.00. |
| Sweep | A one-sided wick strictly beyond the 0.10 buffer. The immediately following M5 close must reclaim the interior with a directional body. Conservative mode then requires a later cross of a pivot already confirmed before the sweep, then a later wick retest. This sequence differs from the local reference's same-bar reclaim. |
| Range | Inward close, rejection wick of at least 60% at the outer 15% of the range, H1 ADX below 20, and candle span no more than 1.5 ATR. The target is the midpoint. |
| Modes | Fast uses pattern rules. Standard adds two of trend, active M5 FVG, M15 breakout and body/volume/ATR momentum. Conservative adds the later retest. Retest tolerance is 0.25 and required wick ratio is 0.35. Pending setups expire after 25 minutes or a session change and invalidate on a close through the stop. |
| Sizing | Simulated USD balance of 1,000. Tester-only plan caps risk at 3% of equity, daily allowance at 6% of day opening balance, ten entries per UTC day, one position and 0.06 lots. Uses native profit and margin calculation, actual volume step and stops level, spread gates and conservative sizing reserves. The reserve does not charge a commission in the tester. Confirm actual commission and execution settings separately. |
| Exit | Stop beyond setup anchor by 0.30, gross target 1.5R or range midpoint with at least 1.2R, and exit on the first available tick after 21:00 UTC. No changes to current runtime risk settings. |

Equal highs/lows, news filtering, break-even, trailing stops, historical clock overrides, restart replay, and full event-level parity checks remain pending. The candidate's hard guards and MQL5 fixtures do not independently verify market execution.

## Windows terminal and bounded campaign

Use a dedicated portable installation with the intended broker's demo/research connection. The existing live profile must stay separate. Create an empty `.goldlab-research-terminal` marker in the dedicated directory and compile with its installed MetaEditor.

```powershell
.\research\compile_windows.ps1 -TerminalDirectory C:\GoldLabMT5
```

MetaEditor can return 1 on a successful compile. Check the diagnostic summary and the new EX5. The compiler script stages each build under a unique directory. To run, copy the verified EX5 to the dedicated terminal's `MQL5\Experts\GoldResearchLab.ex5`.

```powershell
python -m research.run_backtest prepare --split training --strategy breakout --mode standard --reference asia-utc --broker LiteFinance-MT5-Demo --tick-cache 'C:\GoldLabMT5\Bases\LiteFinance-MT5-Demo\ticks\XAUUSD_o' --hypothesis 'Closed-bar reference baseline'
```

`MISSING_TICKS` identifies absent monthly archives and emits no tester config. `COVERAGE_REVIEW_REQUIRED` means only that cache files exist. Verify trading-minute and quote coverage, timestamps, contract details, account currency, commissions and execution assumptions separately before launch. Keep source, data and executable hashes with the evidence.

After coverage review, place the generated SET in `MQL5\Profiles\Tester`, create a `Reports` directory, and launch the dedicated `terminal64.exe /portable /config:<absolute-path-to-tester.ini>`. Use the English report and one run's tester journal. The INI selects model 4, visual off, local agents and no optimization. MetaTrader can generate ticks for minutes with a bar but no real ticks. Review those messages and discard any fallback run. [Platform startup settings](https://www.metatrader5.com/en/terminal/help/start_advanced/start) · [Real tick fallback](https://www.metatrader5.com/en/terminal/help/algotrading/tick_generation)

Import with `python -m research.run_backtest import <id> --report <report.htm> --journal <journal.log> --coverage <coverage.json>`. The independently produced coverage JSON must specify `symbol`, `broker`, `from_inclusive`, `to_exclusive`, `missing_trading_minutes: 0`, `generated_ticks: 0`, `visual: false`, `data_sha256` and `evidence`. The journal must identify the actual EA inputs and show completed real-tick execution. Import retains the raw evidence and rejects known fallback messages. Deal-linked R, monthly/session attribution and cost sensitivity require additional exports. They are unavailable in the current summary.

Training ends 2025-11-01 exclusive. Validation runs from that date to 2026-05-01 exclusive. Holdout runs to 2026-11-01 exclusive. Compare the three strategies and three entry modes on training first. Screen up to twelve additional configurations on training and use validation for candidate comparison. Record all outcomes with `python -m research.compare_experiments --split training --broker LiteFinance-MT5-Demo`. The registry allows one holdout configuration, with matching source and parameters from the chosen validation experiment. `REVIEWABLE` means that evidence was imported and there are trades. It carries no promotion decision.

## Actual evidence

On the local macOS installation, MetaEditor build 6140 generated the EA and mathematical test EX5 files with zero errors and warnings. The tester agent reported `GLAB_CHECK|PASS|failures=0` and `OnTester result 1`. Its terminal wrapper reported an error after the mathematical pass. The account-free one-day model 4 smoke attempt on 2026-03-16 did not start. See the exact logs and the mathematical export under [.agent/evidence/mt5](../.agent/evidence/mt5).

The LiteFinance live cache had only February through August 2026 month files at inspection. Training has no cached real-tick months and validation has February through April. Neither period is runnable under the campaign's coverage gate. No market metrics or Champion candidate have been recorded. The holdout has not been run.
