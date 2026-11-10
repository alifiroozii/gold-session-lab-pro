"""
Unit tests for Execution Simulator and Risk Engine.
Validates conservative dual-touch worst-case resolution,
next-bar execution, and spread/slippage adjustments.
"""

from datetime import datetime, timedelta, timezone

from goldlab.simulator import ExecutionSimulator, SimulatorConfig
from goldlab.types import Candle, SetupSignal, SignalDirection, TradeOutcome

TZ_UTC = timezone.utc


def test_dual_touch_worst_case_resolution() -> None:
    """
    If both Take Profit and Stop Loss levels are touched in the same candle bar,
    the simulator MUST resolve to the WORST CASE (Stop Loss hit / Loss).
    Never optimistic!
    """
    sim = ExecutionSimulator(SimulatorConfig(spread_pips=0.0, slippage_pips=0.0))
    start_t = datetime(2026, 11, 2, 8, 0, tzinfo=TZ_UTC)

    # Bar 0: Signal generated
    # Bar 1: Entry executed at Open = 2650.0 (SL = 2645.0, TP = 2660.0)
    # Bar 2: Extreme volatility bar (L = 2640.0, H = 2665.0) -> Touches BOTH SL and TP!
    candles = [
        Candle(timestamp=start_t, open=2648.0, high=2651.0, low=2647.0, close=2650.0),
        Candle(timestamp=start_t + timedelta(minutes=5), open=2650.0, high=2652.0, low=2649.0, close=2651.0),
        Candle(timestamp=start_t + timedelta(minutes=10), open=2651.0, high=2665.0, low=2640.0, close=2655.0),
    ]

    signal = SetupSignal(
        setup_id="TEST_SETUP",
        setup_name="Test Setup",
        direction=SignalDirection.BUY,
        signal_index=0,
        signal_time=candles[0].timestamp,
        entry_index=1,
        entry_price=2650.0,
        sl_price=2645.0,
        tp_price=2660.0,
        risk_r=5.0,
        reason="Test dual touch",
    )

    trades = sim.run_simulation(candles, [signal])
    assert len(trades) == 1
    t = trades[0]

    # Must resolve to Loss under worst-case dual-touch rule
    assert t.outcome == TradeOutcome.LOSS
    assert t.realized_r == -1.0
    assert t.exit_reason == "WORST_CASE_DUAL_TOUCH_SL"
    assert t.exit_price == 2645.0


def test_spread_and_slippage_adjustment() -> None:
    sim = ExecutionSimulator(SimulatorConfig(spread_pips=0.25, slippage_pips=0.10))
    start_t = datetime(2026, 11, 2, 8, 0, tzinfo=TZ_UTC)

    candles = [
        Candle(timestamp=start_t, open=2650.0, high=2651.0, low=2649.0, close=2650.0),
        Candle(timestamp=start_t + timedelta(minutes=5), open=2650.0, high=2652.0, low=2649.0, close=2651.0),
    ]

    signal = SetupSignal(
        setup_id="TEST_SETUP",
        setup_name="Test Setup",
        direction=SignalDirection.BUY,
        signal_index=0,
        signal_time=candles[0].timestamp,
        entry_index=1,
        entry_price=2650.0,
        sl_price=2645.0,
        tp_price=2660.0,
        risk_r=5.0,
        reason="Test spread adjustment",
    )

    trades = sim.run_simulation(candles, [signal])
    assert len(trades) == 1
    # Buy entry is adjusted: 2650.0 + 0.25 (spread) + 0.10 (slippage) = 2650.35
    assert trades[0].entry_price == 2650.35
