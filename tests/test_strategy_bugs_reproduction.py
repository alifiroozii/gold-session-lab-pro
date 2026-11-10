"""Tests verifying the reproduction and resolution of Bug 1 and Bug 2.

Bug 1: Signal timing mismatch between setups.py and bot.py (signals on latest closed bar).
Bug 2: Future session high/low leakage in historical session calculations.
"""
from datetime import datetime

from goldlab.bot import AutomatedPaperBot, BotState
from goldlab.fixtures import generate_sweep_reclaim_bos_retest_fixture
from goldlab.market_structure import MarketStructureAnalyzer
from goldlab.paper_broker import PaperBroker
from goldlab.sessions import TZ_NEW_YORK, SessionManager
from goldlab.setups import SetupConfig, SetupEngine
from goldlab.types import Candle, SignalDirection


def test_bug_1_signal_generation_on_latest_closed_candle() -> None:
    """Proves that when a setup completes on the latest closed candle (n - 1),

    setups.py generates the signal with signal_index == n - 1, and bot.py
    receives it on on_candle_close without lag.
    """
    # 8 candles: candle 7 is the retest candle where setup completes
    candles = generate_sweep_reclaim_bos_retest_fixture()[:8]
    assert len(candles) == 8

    analyzer = MarketStructureAnalyzer()
    analyzer.enrich_candle_metrics(candles)
    swings = analyzer.find_swing_points(candles)
    fvgs = analyzer.find_fair_value_gaps(candles)
    obs = analyzer.detect_order_block_proxies(candles, swings)
    session_stats = {"asia": {"low": 2650.0, "high": 2670.0}}

    cfg = SetupConfig(enable_sweep_reclaim_bos=True)
    setup_engine = SetupEngine(config=cfg, structure=analyzer)

    # When allow_pending is True (as in bot.on_candle_close):
    signals = setup_engine.evaluate_all(
        candles, swings, fvgs, obs, session_stats, allow_pending=True
    )

    sweep_signals = [s for s in signals if s.setup_id == "SETUP_2_SWEEP_RECLAIM_BOS"]
    assert len(sweep_signals) == 1, "Setup 2 must generate signal on the latest closed candle"
    sig = sweep_signals[0]
    assert sig.signal_index == 7, "Signal index must match candle 7 (the latest closed candle)"
    assert sig.entry_index == 8, "Entry index must be next bar (8)"
    assert sig.direction == SignalDirection.BUY

    # Now verify bot.on_candle_close receives it
    broker = PaperBroker()
    bot = AutomatedPaperBot(broker=broker)
    bot.state = BotState.ANALYSIS_ONLY
    bot.engine.calendar.is_blackout = lambda ts: (False, "")  # Bypass news blackout for unit fixture
    bot.engine.session_mgr.calculate_as_of_session_stats_series = lambda c: [
        {"asia": {"low": 2650.0, "high": 2670.0}} for _ in c
    ]

    bot_signals = bot.on_candle_close(
        candles,
        current_bid=2654.0,
        current_ask=2654.5,
        current_time=candles[-1].timestamp,
    )
    assert any(s.setup_id == "SETUP_2_SWEEP_RECLAIM_BOS" and s.signal_index == 7 for s in bot_signals), (
        "Bot must receive the signal emitted on the latest candle close"
    )


def test_bug_2_point_in_time_session_no_lookahead() -> None:
    """Proves that session statistics calculated point-in-time do not leak

    future intraday candles or future days into historical evaluations.
    """
    sm = SessionManager()
    tz = TZ_NEW_YORK

    # Create candles across Day 1 and Day 2
    d1_asia = datetime(2026, 11, 3, 21, 0, tzinfo=tz)
    d1_ny_close = datetime(2026, 11, 4, 16, 0, tzinfo=tz)
    d2_asia = datetime(2026, 11, 4, 21, 0, tzinfo=tz)
    d2_ny_close = datetime(2026, 11, 5, 16, 0, tzinfo=tz)

    candles = [
        # Day 1 Asia
        Candle(timestamp=d1_asia, open=2650.0, high=2655.0, low=2648.0, close=2652.0),
        # Day 1 NY (close of Day 1)
        Candle(timestamp=d1_ny_close, open=2652.0, high=2670.0, low=2645.0, close=2665.0),
        # Day 2 Asia
        Candle(timestamp=d2_asia, open=2665.0, high=2680.0, low=2662.0, close=2678.0),
        # Day 2 NY afternoon
        Candle(timestamp=d2_ny_close, open=2678.0, high=2710.0, low=2675.0, close=2705.0),
    ]

    series = sm.calculate_as_of_session_stats_series(candles)
    assert len(series) == len(candles)

    # At bar 0 (Day 1 Asia):
    # Asia high must be 2655.0, low 2648.0
    assert series[0]["asia"]["high"] == 2655.0
    assert series[0]["asia"]["low"] == 2648.0
    # London and NY have not happened yet
    assert series[0]["london"]["high"] is None
    assert series[0]["ny"]["high"] is None

    # At bar 2 (Day 2 Asia):
    # Asia high must be 2680.0, low 2662.0 (Day 2 Asia, NOT Day 1 Asia!)
    assert series[2]["asia"]["high"] == 2680.0
    assert series[2]["asia"]["low"] == 2662.0

    # Prior day levels at bar 2 must reflect completed Day 1 (high 2670.0, low 2645.0)
    assert series[2]["pd"]["high"] == 2670.0
    assert series[2]["pd"]["low"] == 2645.0

    # At bar 2, Day 2 NY high (2710.0 from bar 3) must NOT be known yet!
    assert series[2]["ny"]["high"] is None, "Future bar 3 NY high must not leak into bar 2"

    # Truncating candles up to bar 2 must give bit-for-bit identical stats as series[2]
    truncated_series = sm.calculate_as_of_session_stats_series(candles[:3])
    assert truncated_series[-1] == series[2], "Point-in-time calculation must be invariant to future truncation"
