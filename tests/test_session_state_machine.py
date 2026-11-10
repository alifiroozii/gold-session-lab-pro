"""
Unit tests for Causal Session Trading State Machine - Master Prompt V5.
"""
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from goldlab.state_machine import (
    SessionStrategyState,
    SessionTradingStateMachine,
)
from goldlab.types import Candle, SignalDirection

TZ_UTC = timezone.utc
TZ_NY = ZoneInfo("America/New_York")


def _make_candle(dt_ny: datetime, o: float, h: float, low_val: float, c: float) -> Candle:
    dt_utc = dt_ny.astimezone(TZ_UTC)
    return Candle(
        timestamp=dt_utc,
        open=o,
        high=h,
        low=low_val,
        close=c,
        volume=100.0,
        atr14=1.20,
    )


def test_state_machine_full_causal_lifecycle(tmp_path):
    db_file = str(tmp_path / "test_state_machine.sqlite")
    sm = SessionTradingStateMachine(db_path=db_file)

    assert sm.current_state == SessionStrategyState.WAITING_FOR_SESSION

    # 1. Day 1: 19:55 NY (Before Asia Range)
    c0 = _make_candle(datetime(2026, 11, 2, 19, 55, tzinfo=TZ_NY), 2730.0, 2731.0, 2729.0, 2730.5)
    sig0 = sm.process_candle(c0, [])
    assert sig0 is None
    assert sm.current_state == SessionStrategyState.WAITING_FOR_SESSION

    # 2. 20:00 NY (Enters Asia Range -> BUILDING_RANGE)
    c1 = _make_candle(datetime(2026, 11, 2, 20, 0, tzinfo=TZ_NY), 2730.5, 2735.0, 2728.0, 2732.0)
    sm.process_candle(c1, [c0])
    assert sm.current_state == SessionStrategyState.BUILDING_RANGE
    assert sm.ref_high == 2735.0
    assert sm.ref_low == 2728.0

    # 3. 23:00 NY (Higher high in Asia Range)
    c2 = _make_candle(datetime(2026, 11, 2, 23, 0, tzinfo=TZ_NY), 2732.0, 2738.0, 2730.0, 2736.0)
    sm.process_candle(c2, [c0, c1])
    assert sm.ref_high == 2738.0
    assert sm.ref_low == 2728.0

    # 4. 00:05 NY (Asia range completed -> RANGE_FINALIZED)
    c3 = _make_candle(datetime(2026, 11, 3, 0, 5, tzinfo=TZ_NY), 2736.0, 2737.0, 2734.0, 2735.0)
    sm.process_candle(c3, [c0, c1, c2], session_stats={"asia_complete": True})
    assert sm.current_state == SessionStrategyState.RANGE_FINALIZED
    assert sm.ref_high == 2738.0
    assert sm.ref_low == 2728.0

    # 5. 03:10 NY (London session: Sweep of Asia Low 2728.0)
    # Candle dips to 2726.0 (below 2728.0) -> SWEEP_DETECTED
    c_sweep = _make_candle(datetime(2026, 11, 3, 3, 10, tzinfo=TZ_NY), 2730.0, 2731.0, 2726.0, 2727.5)
    sm.process_candle(c_sweep, [c0, c1, c2, c3])
    assert sm.current_state == SessionStrategyState.SWEEP_DETECTED
    assert sm.active_setup is not None
    assert sm.active_setup.direction == SignalDirection.BUY
    assert sm.active_setup.target_level_val == 2728.0

    # 6. 03:15 NY (Reclaim: Closes back above 2728.0 -> RECLAIM_CONFIRMED)
    c_reclaim = _make_candle(datetime(2026, 11, 3, 3, 15, tzinfo=TZ_NY), 2727.5, 2731.0, 2727.0, 2730.0)
    sm.process_candle(c_reclaim, [c0, c1, c2, c3, c_sweep])
    assert sm.current_state == SessionStrategyState.RECLAIM_CONFIRMED
    assert sm.active_setup.reclaim_candle_high == 2731.0

    # 7. 03:20 NY (BOS: Closes above reclaim high 2731.0 -> STRUCTURE_CONFIRMED)
    c_bos = _make_candle(datetime(2026, 11, 3, 3, 20, tzinfo=TZ_NY), 2730.0, 2733.0, 2729.5, 2732.5)
    sm.process_candle(c_bos, [c0, c1, c2, c3, c_sweep, c_reclaim])
    assert sm.current_state == SessionStrategyState.STRUCTURE_CONFIRMED

    # 8. 03:25 NY (Retest with lower wick rejection -> RETEST_CONFIRMED)
    # Range = 2732.0 - 2728.1 = 3.9; lower_wick = 2731.0 - 2728.1 = 2.9 (>= 35% range)
    c_retest = _make_candle(datetime(2026, 11, 3, 3, 25, tzinfo=TZ_NY), 2731.0, 2732.0, 2728.1, 2731.5)
    sm.process_candle(c_retest, [c0, c1, c2, c3, c_sweep, c_reclaim, c_bos])
    assert sm.current_state == SessionStrategyState.RETEST_CONFIRMED

    # 9. Next bar formulation -> ENTRY_ELIGIBLE and emits SetupSignal
    c_entry = _make_candle(datetime(2026, 11, 3, 3, 30, tzinfo=TZ_NY), 2731.5, 2733.0, 2731.0, 2732.0)
    sig_eligible = sm.process_candle(c_entry, [c0, c1, c2, c3, c_sweep, c_reclaim, c_bos, c_retest])
    assert sm.current_state == SessionStrategyState.ENTRY_ELIGIBLE
    assert sig_eligible is not None
    assert sig_eligible.direction == SignalDirection.BUY
    assert sig_eligible.entry_price == 2732.0
    assert sig_eligible.tp_price > sig_eligible.entry_price
    assert sig_eligible.sl_price < sig_eligible.entry_price

    # 10. Order dispatch and fill
    sm.on_order_dispatched("ORD_TEST_001", c_entry)
    assert sm.current_state == SessionStrategyState.PAPER_ORDER

    sm.on_position_opened("POS_TEST_001", c_entry)
    assert sm.current_state == SessionStrategyState.POSITION_MANAGEMENT

    sm.on_position_closed(c_entry, "TAKE_PROFIT_HIT")
    assert sm.current_state == SessionStrategyState.CLOSED

    # Verify SQLite logging and summary
    summary = sm.get_state_summary()
    assert summary["current_state"] == "CLOSED"
    assert len(summary["recent_transitions"]) >= 8

    with sqlite3.connect(db_file) as conn:
        count = conn.execute("SELECT count(*) FROM strategy_state_transitions").fetchone()[0]
        assert count >= 8



def test_finalizing_asia_range_does_not_include_first_outside_bar(tmp_path):
    sm = SessionTradingStateMachine(db_path=str(tmp_path / "range.sqlite"))
    c20 = _make_candle(
        datetime(2026, 11, 2, 20, 0, tzinfo=TZ_NY),
        4400, 4405, 4395, 4401,
    )
    c23 = _make_candle(
        datetime(2026, 11, 2, 23, 55, tzinfo=TZ_NY),
        4401, 4408, 4392, 4402,
    )
    sm.process_candle(c20, [])
    sm.process_candle(c23, [c20])
    assert sm.ref_high == 4408
    assert sm.ref_low == 4392
    # The 00:05 bar is NOT part of the NY 20:00–00:00 range.
    # Its huge spike and dump MUST NOT rewrite the completed range.
    c00 = _make_candle(
        datetime(2026, 11, 3, 0, 5, tzinfo=TZ_NY),
        4402, 4450, 4350, 4400,
    )
    sm.process_candle(c00, [c20, c23], session_stats={"asia_complete": True})
    assert sm.current_state == SessionStrategyState.RANGE_FINALIZED
    assert sm.ref_high == 4408
    assert sm.ref_low == 4392
