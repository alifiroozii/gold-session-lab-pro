# Gold Session Lab Pro research handoff

The `codex/mt5-session-research` worktree adds a standalone, nonvisual MT5 tester EA, modular MQL5 sources, native mathematical checks, a Windows compilation script and a SQLite experiment registry. Start with [research/README.md](../research/README.md) for exact rules, migration differences and operator steps.

## Verified local evidence

- Source baseline for this branch was `b59051db1f0e330c26e40b0b93a1479e151081d4`. Use `git rev-parse HEAD` for the delivered commit and the registry for the MQL source hash.
- MetaEditor process exit 1 produced a new EX5 and a diagnostic summary of zero errors and zero warnings. The mathematical check EA compiled and reported zero fixture failures and custom result 1. The terminal recorded an error after the mathematical pass. Evidence is in `.agent/evidence/mt5/`.
- The account-free model 4 attempt was blocked before market simulation. Terminal launcher exit was 191 and the terminal journal reported that an account was not specified.
- Local LiteFinance `XAUUSD_o` real-tick cache files covered February–August 2026 by filename only. The training and validation preflight results are in `.agent/evidence/mt5/campaign-preflight.json`. The SQLite registry is local at `research/output/experiments.sqlite`.
- `STRATEGY_AUDIT_SKIPPED`. No provenance-verified CSV is configured. Python suite evidence is in `.agent/evidence/mt5/pytest.txt`. The synthetic MQL fixtures cover DST, session windows, swing confirmation, FVG, range regime and retest conditions.

## Next steps

1. Use an isolated portable MT5 installation with a broker research/demo account and verify symbol specifications, actual server-time alignment, cost configuration and complete real-tick coverage. Confirm the broker and contract match the study.
2. Run the nine prepared training variants and retain all reports and journals. Complete the trade-level attribution, causal replay and cost sensitivity gates before selecting any validation candidate.
3. Freeze the selected configuration and source before opening the holdout. No MT5 Champion has been established. User review is required for any promotion.
4. Original Python forward-bot parity remains unverified. The implementation uses documented reconstruction rules and differs from the local `ProSessionEngine` where noted in the research guide.

For prior Python dashboard work, read this file at `b59051d`. No background researcher is running.
