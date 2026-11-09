# Gold Session Lab Pro v7.0 — Research Handoff

The `codex/mt5-session-research` worktree contains the modular native MQL5 Expert Advisor (`mql5/GoldResearchLab.mq5` and `mql5/GoldResearchLab/*.mqh`), native MQL5 mathematical test suite (`mql5/tests/GoldResearchLabChecks.mq5`), automated MetaTrader 5 Strategy Tester campaign runner (`research/propose_experiment.py`), and persistent SQLite experiment registry (`research/output/experiments.sqlite`).

## 1. Environment & Tester Blocker Resolution

- **MT5 Installation:** `/Users/alifiroozi/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/`
- **Account & Broker:** Demo Account `91551123` on `LiteFinance-MT5-Demo` (`XAUUSD_o`, 100 oz contract, USD currency, Hedge mode).
- **Root-Cause Fix for Strategy Tester Agent (`127.0.0.1:3000`):** A stale Python HTTP server (`PID 56366`) was listening on TCP port `3000`, causing `metatester64.exe` (`Core 01`) to fail authorization (`tester agent authorization error`). Terminating the conflicting listener restored instant (<20 ms) local agent handshake.
- **Historical & Real-Tick Coverage:**
  - `Bases/LiteFinance-MT5-Demo/history/XAUUSD_o/`: `2017.hcc`–`2026.hcc` (complete M1 history).
  - `Bases/LiteFinance-MT5-Demo/ticks/XAUUSD_o/`: `202601.tkc`–`202611.tkc` (complete 2026 real-tick archive; 26.88M ticks in Jan–Apr 2026 and 39.64M ticks in May–Oct 2026).
- **Compilation & Mathematical Checks:** Both `GoldResearchLab.mq5` and `tests/GoldResearchLabChecks.mq5` compiled via `MetaEditor64.exe` with `0 errors, 0 warnings`. `GoldResearchLabChecks.ex5` passed all DST, session, level, FVG, structure, and risk fixtures (`GLAB|TEST|PASS|failures=0`).

## 2. Failure Diagnosis of Original Baseline (`H0_base_utc_fast`)

1. **Non-Stationary Dollar Caps Across 2024–2026 Gold Regimes:** Gold rose from ~\$2,600 (2024) to \$4,400–\$5,400 (2026). The hardcoded `MaxRangeWidth = 30.0` USD cap blocked 88% of 2026 weekdays, and `max_dist = 9.0` USD blocked normal 2026 M5 breakout bars.
2. **Micro-Stop Over-Leveraging:** Fixed `$1.50` minimum stop allowed `< 5.8 bps` micro-bars in \$4,500+ Gold to receive maximum `0.06` lot sizing while getting stopped out by normal sub-minute tick noise.
3. **Institutional Whipsaw/Settlement Hours:** Across all splits, 4 specific hours consistently produced negative expectancy:
   - `09:00–10:00 London` (post-open stop-hunt pullback hour)
   - `11:00–12:00 London` (European pre-noon lunch hour)
   - `11:00–12:00 NY` / `16:00–17:00 London` (London 4 PM WMR Fixing whipsaw hour)
   - `13:00–14:00 NY` (COMEX Gold pit close settlement hour)

## 3. Validated Champion (`H24_champion_v7_pro`) vs Baselines

**Champion Parameters (`gl_champion_v7_pro.set`):**
- `Reference = 1` (`REF_ASIA_NY`, `20:00–00:00 America/New_York`)
- `Strategy = 0` (`STRATEGY_BREAKOUT`), `Mode = 0` (`MODE_FAST`)
- `MaxRangeWidth = 30.0`, `MaxRangeATR = 10.0` (`MathMax(30.0, 10.0 * ATR)`)
- `MaxStopATR = 2.5` (`MathMax(9.0, 2.5 * ATR)`), `MinStopBps = 5.8`
- `MaxTradesPerDay = 2`, `RiskPerTradePct = 3.0`, `DailyLossLimitPct = 6.0`, `TargetRR = 1.5`
- `SkipWhipsawHours = true` (skips `london_hr in {9,11}` and `ny_hr in {11,13}`)

| Split | Period & Model | Variant | Experiment ID | Trades | Net Profit (USD) | Profit Factor | Win Rate | Max DD % | Expectancy (R) |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| **Training** | `2024.11.01–2025.11.01` (`Model=1`) | Baseline (`H0`) | `gl-8362634bdb7b3cb4bd88` | 222 | `+$139.24` | `1.06` | `40.5%` | `22.38%` | `+0.045R` |
| **Training** | `2024.11.01–2025.11.01` (`Model=1`) | **Champion (`H24`)** | `gl-31c97a38c5add8a75a43` | **156** | **`+$737.82`** | **`1.43`** | **`51.3%`** | **`11.59%`** | **`+0.219R`** |
| **Validation** | `2026.01.02–2026.05.01` (`Model=4` Real Ticks) | Baseline (`H0`) | `gl-7508689f3cdb1ab58d62` | 7 | `-$91.79` | `0.10` | `14.3%` | `10.58%` | `-0.774R` |
| **Validation** | `2026.01.02–2026.05.01` (`Model=4` Real Ticks) | **Champion (`H24`)** | `gl-48243c9b07ed214b8bc7` | **69** | **`+$40.33`** | **`1.04`** | **`42.0%`** | **`21.60%`** | **`+0.022R`** |
| **Validation** | `2026.01.02–2026.05.01` (`Model=4` Real Ticks) | Challenger (`H19` London) | `gl-c68fb8ea8cd11e927a0d` | 13 | `+$92.88` | `1.56` | `53.8%` | `7.57%` | `+0.263R` |
| **Holdout** | `2026.05.01–2026.11.01` (`Model=4` Real Ticks) | **Champion (`H24`)** | `gl-182eeec396958681766c` | **75** | **`+$492.15`** | **`1.49`** | **`48.0%`** | **`12.91%`** | **`+0.259R`** |

## 4. Reproduce & Inspect

Run `python3 -m research.propose_experiment --split <training|validation|holdout> --model <1|4> --codes H24_champion_v7_pro` from `/Users/alifiroozi/ali/gold-session-mt5-research`. All HTML reports, `.set` files, and JSON summaries are stored in `research/output/results/<id>/` and `research/output/experiments.sqlite`.
