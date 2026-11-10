# XAU/USD offline candidate screen

No candidate passed the validation gate. Keep the native MT5 campaign separate from this screen.

The standard native job returned process exit 191 before loading market data. The portable terminal journal reported “tester not started because the account is not specified.” The LiteFinance cache also lacked the training tick history. The offline replay uses pinned public mirrors whose publishers identify Dukascopy as the source. File integrity was checked against Git blob hashes. Direct reconciliation against the provider was unavailable.

## Study

- Training `2024-11-01` through `2025-10-31`. Compare three strategies, three confirmation modes and two Asia range definitions.
- Validation `2025-11-01` through `2026-04-30`. Advance the two training variants with 30 or more trades and positive net after the slippage stress. The cutoff was selected after reviewing training, before opening the validation results. The untouched May–October holdout was not used.
- Signals use M5 bid bars and completed M15/H1 features. For M1 input the momentum vote is unavailable because the mirror has no tick count. Crossed or malformed quotes and flat Bid/Ask minutes are excluded. A gap can reduce coverage. Results use USD 1,000 starting equity, a modeled 100 oz lot, 1:100 leverage, USD 10 commission per lot round trip, and USD 0.05 or 0.10 per oz market leg slippage. A stop wins when both brackets are touched inside one minute. This model approximates the tester rules. It lacks broker-specific fills, margin and fee verification. Drawdown uses closed trade equity.

## Outcome

UTC Asia breakout Fast earned USD 231.87 over 51 training trades and lost USD 51.79 over eight validation trades. The NY Asia breakout Fast earned USD 224.01 over 62 training trades and lost USD 254.29 over 29 validation trades. With higher slippage, validation losses were USD 54.54 and USD 285.90 respectively. Neither has positive validation expectancy. The UTC candidate also fell short of the 20 validation trade screen.

December 2024 tick sensitivity on a separate mirror returned USD −31.30 over 12 UTC reference trades and USD +49.24 over 16 NY reference trades. The January 2–9, 2026 tick sample yielded no fills for either variant. These small samples do not establish a profitable tick result. The M1 and tick archives have different coverage.

In the UTC Asia reference, median width increased from USD 23.07 to USD 51.46. The fixed USD 30 cap excluded 111 of 126 validation weekdays with sufficiently covered reference bars. That supports testing a range-width normalization as a new hypothesis on future separate data. The cap is unchanged in the candidate.

The complete summaries, shortlist and gap diagnostics are in [the evidence directory](../.agent/evidence/offline-2026-11-09/). No Champion was selected. `STRATEGY_AUDIT_SKIPPED` remains in effect for the repository's verified provider gate.

## Reproduce

Use the pinned [M1 mirror](https://github.com/kevingtlin/Market-Data-Lab/tree/b60bd71d0e34a42cb962daf688ff252e73f409ca) and [tick mirror](https://github.com/simom1/XAUUSD-history/tree/5d1bfa39cb8bb3715b027fa33815de7198fb1aca). Local snapshots are under `research/output/public-m1`, `research/output/public-ticks` and `research/output/tick-validation-sample`. Their manifests identify each Git blob. Raw price archives remain local. The run folders under `research/output/screens/final` include trade CSVs and machine-readable summaries.

```sh
python -m research.screen_candidates --data research/output/public-m1 --granularity m1 --split training --output research/output/training-rerun
python -m research.screen_candidates --data research/output/public-m1 --granularity m1 --split validation --variants asia-utc:breakout:fast asia-ny:breakout:fast --output research/output/validation-rerun
```

Tick mode uses PyArrow 23.0.1 and the `--start` and `--end` flags for a documented subperiod.
