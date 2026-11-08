"""Auditable strategy signal contract and point-in-time replay checks.

Research-only: passing these checks never enables PAPER_AUTO.
The replay check detects historical signal instability when candles after a decision
are removed; it does not establish trading profitability or simulate bid/ask fills.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Sequence

from goldlab.types import Candle, SetupSignal, SignalDirection

if TYPE_CHECKING:
    from goldlab.engine import ResearchEngine


@dataclass(frozen=True)
class VerificationFinding:
    code: str
    message: str
    signal_index: int | None = None


def verify_signal_contract(
    candles: Sequence[Candle], signals: Sequence[SetupSignal],
) -> dict:
    """Check invariants for already-generated historical signals.

    This cannot infer whether the entry rule itself is profitable or whether
    the strategy used future session levels. Use audit_point_in_time() as well.
    """
    findings: list[VerificationFinding] = []
    for i, candle in enumerate(candles):
        if candle.timestamp.tzinfo is None or candle.timestamp.utcoffset() is None:
            findings.append(VerificationFinding("NAIVE_TIMESTAMP", "UTC-aware timestamps required", i))
        if i and candle.timestamp <= candles[i - 1].timestamp:
            findings.append(VerificationFinding("UNORDERED_CANDLES", "Timestamps must strictly increase", i))
        if not all(math.isfinite(x) and x > 0 for x in
                   (candle.open, candle.high, candle.low, candle.close)):
            findings.append(VerificationFinding("INVALID_PRICE", "Invalid OHLC price", i))

    seen: set[tuple] = set()
    for signal in signals:
        idx = signal.signal_index
        if not (0 <= idx < len(candles)):
            findings.append(VerificationFinding("INVALID_SIGNAL_INDEX", "Signal candle missing", idx))
            continue
        if signal.entry_index != idx + 1 or signal.entry_index >= len(candles):
            findings.append(VerificationFinding(
                "INVALID_NEXT_BAR_ENTRY", "Historical entry must be on available next bar", idx,
            ))
            continue
        source_bar, entry_bar = candles[idx], candles[signal.entry_index]
        if not source_bar.is_closed or signal.signal_time != source_bar.timestamp:
            findings.append(VerificationFinding(
                "SIGNAL_TIME_MISMATCH", "Signal must match a confirmed closed bar", idx,
            ))
        if entry_bar.timestamp <= signal.signal_time:
            findings.append(VerificationFinding(
                "NONCAUSAL_ENTRY_TIME", "Entry must occur after confirmed signal", idx,
            ))
        if not math.isclose(signal.entry_price, entry_bar.open, rel_tol=0, abs_tol=1e-4):
            findings.append(VerificationFinding(
                "ENTRY_PRICE_MISMATCH", "Entry price must match the historical next open", idx,
            ))
        vals = (signal.entry_price, signal.sl_price, signal.tp_price, signal.risk_r)
        if not all(math.isfinite(x) for x in vals):
            findings.append(VerificationFinding("NONFINITE_ORDER", "Order prices must be finite", idx))
            continue
        if signal.direction == SignalDirection.BUY:
            bracket_ok = signal.sl_price < signal.entry_price < signal.tp_price
        elif signal.direction == SignalDirection.SELL:
            bracket_ok = signal.tp_price < signal.entry_price < signal.sl_price
        else:
            bracket_ok = False
        if not bracket_ok or signal.risk_r <= 0:
            findings.append(VerificationFinding(
                "INVALID_RISK_BRACKET", "Invalid direction, SL/TP or risk distance", idx,
            ))
        key = (signal.setup_id, signal.direction.value, idx, signal.entry_index)
        if key in seen:
            findings.append(VerificationFinding("DUPLICATE_SIGNAL", "Duplicate setup at same bar", idx))
        seen.add(key)

    return {
        "status": "FAIL" if findings else "PASS",
        "checked_signals": len(signals),
        "checked_candles": len(candles),
        "findings": [asdict(item) for item in findings],
        "authorizes_paper_auto": False,
    }


def audit_point_in_time(engine: "ResearchEngine", max_signals: int = 12) -> dict:
    """Replay selected signals with only the bars that existed by their next open.

    A changed or missing signal flags potential lookahead/context leakage.
    Any matching result is necessary but not sufficient to validate a strategy.
    """
    from goldlab.engine import ResearchEngine

    if max_signals < 1:
        raise ValueError("max_signals must be positive")
    candles = engine.current_candles
    candidates = [s for s in engine.signals if 0 <= s.signal_index <
                  s.entry_index < len(candles)]
    # Check signals across the history rather than cherry-picking only latest trades.
    if len(candidates) > max_signals:
        positions = [(i * (len(candidates) - 1)) // (max_signals - 1)
                     for i in range(max_signals)] if max_signals > 1 else [0]
        candidates = [candidates[p] for p in sorted(set(positions))]
    findings: list[VerificationFinding] = []
    for signal in candidates:
        # At entry time only the next bar OPEN is known, never its future H/L/C.
        # Explicitly hide next-bar completion and all later bars from the replay.
        next_bar = candles[signal.entry_index]
        open_only = Candle(
            timestamp=next_bar.timestamp, open=next_bar.open, high=next_bar.open,
            low=next_bar.open, close=next_bar.open, is_closed=False,
        )
        prefix = list(candles[:signal.entry_index]) + [open_only]
        replay = ResearchEngine(setup_config=engine.setups.config, db_path=str(engine.data_pipeline.db_path))
        replay.load_candles(prefix, timeframe=engine.current_timeframe)
        replay.run_pipeline()
        matches = [
            s for s in replay.signals
            if s.setup_id == signal.setup_id
            and s.direction == signal.direction
            and s.signal_index == signal.signal_index
            and s.entry_index == signal.entry_index
            and math.isclose(s.entry_price, signal.entry_price, abs_tol=1e-4)
            and math.isclose(s.sl_price, signal.sl_price, abs_tol=1e-4)
            and math.isclose(s.tp_price, signal.tp_price, abs_tol=1e-4)
        ]
        if not matches:
            findings.append(VerificationFinding(
                "HISTORICAL_SIGNAL_CHANGED",
                "Signal disappeared/changed when future candles were removed; inspect session levels and structure confirmation",
                signal.signal_index,
            ))

    return {
        "status": "FAIL" if findings else ("PASS" if candidates else "INSUFFICIENT_EVIDENCE"),
        "sampled_signals": len(candidates),
        "total_signals": len(engine.signals),
        "findings": [asdict(item) for item in findings],
        "authorizes_paper_auto": False,
    }
