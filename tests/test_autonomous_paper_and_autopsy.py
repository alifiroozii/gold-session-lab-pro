"""Tests for Autonomous Paper Trading, 8 Strategies Causal Invariance, and Trade Autopsy."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app import app
from goldlab.bot import AutomatedPaperBot, BotRiskSettings, BotState
from goldlab.fixtures import generate_sweep_reclaim_bos_retest_fixture
from goldlab.learning import FailureCategory, MistakeAnalyzerAndHypothesisRegistry
from goldlab.paper_broker import OrderDirection, OrderStatus, OrderType, PaperBroker
from goldlab.setups import SetupConfig, SetupEngine
from goldlab.types import Candle, SignalDirection

UTC = timezone.utc
NY = ZoneInfo("America/New_York")


def test_setup_7_bearish_continuation() -> None:
    """Setup 7: Bearish trend continuation with displacement and shallow pullback."""
    engine = SetupEngine(config=SetupConfig())
    # Create 15 warmup candles plus displacement + shallow pullback
    candles = [
        Candle(
            timestamp=datetime(2026, 11, 4, 10, i, tzinfo=UTC),
            open=2650.0,
            high=2652.0,
            low=2648.0,
            close=2650.0,
            volume=100.0,
            atr14=2.0,
        )
        for i in range(15)
    ]
    # Bar 15: Strong bearish displacement candle
    candles.append(
        Candle(
            timestamp=datetime(2026, 11, 4, 10, 15, tzinfo=UTC),
            open=2650.0,
            high=2650.5,
            low=2642.0,
            close=2643.0,
            volume=500.0,
            atr14=2.0,
            displacement=True,
        )
    )
    # Bar 16: Shallow pullback holding lower half (half_level = 2646.5)
    candles.append(
        Candle(
            timestamp=datetime(2026, 11, 4, 10, 16, tzinfo=UTC),
            open=2643.5,
            high=2645.0,
            low=2643.0,
            close=2644.0,
            volume=200.0,
            atr14=2.0,
        )
    )
    # Bar 17: Follow-through
    candles.append(
        Candle(
            timestamp=datetime(2026, 11, 4, 10, 17, tzinfo=UTC),
            open=2643.8,
            high=2644.5,
            low=2640.0,
            close=2641.0,
            volume=300.0,
            atr14=2.0,
        )
    )

    signals = engine.evaluate_all(candles, swings=[], fvgs=[], obs=[], session_stats={}, allow_pending=True)
    bear_signals = [s for s in signals if s.setup_id == "SETUP_7_TREND_CONTINUATION" and s.direction == SignalDirection.SELL]
    assert len(bear_signals) >= 1
    sig = bear_signals[0]
    assert sig.signal_index == 16
    assert sig.entry_index == 17
    assert sig.sl_price == 2650.5


def test_setup_8_combined_structural_model() -> None:
    """Setup 8: Combined Structural Model with sweep, reclaim, and wick rejection."""
    engine = SetupEngine(config=SetupConfig())
    asia_high = 2660.0
    asia_low = 2640.0
    session_stats = {"asia": {"high": asia_high, "low": asia_low}}

    candles = [
        Candle(
            timestamp=datetime(2026, 11, 4, 10, i, tzinfo=UTC),
            open=2645.0,
            high=2648.0,
            low=2642.0,
            close=2645.0,
            volume=100.0,
            atr14=2.0,
        )
        for i in range(15)
    ]
    # Bar 15: Sweeps Asia Low
    candles.append(
        Candle(
            timestamp=datetime(2026, 11, 4, 10, 15, tzinfo=UTC),
            open=2642.0,
            high=2643.0,
            low=2638.0,  # Sweeps 2640.0
            close=2639.0,
            volume=400.0,
            atr14=2.0,
        )
    )
    # Bar 16: Reclaims above Asia Low
    candles.append(
        Candle(
            timestamp=datetime(2026, 11, 4, 10, 16, tzinfo=UTC),
            open=2639.0,
            high=2643.0,
            low=2639.0,
            close=2642.0,  # Reclaimed above 2640.0
            volume=350.0,
            atr14=2.0,
        )
    )
    # Bar 17: Retest with strong lower wick rejection
    candles.append(
        Candle(
            timestamp=datetime(2026, 11, 4, 10, 17, tzinfo=UTC),
            open=2642.0,
            high=2644.0,
            low=2640.5,
            close=2643.5,
            volume=300.0,
            atr14=2.0,
            lower_wick=2.5,
            upper_wick=0.5,
            body=1.5,
            range=3.5,
        )
    )
    # Bar 18: Next bar for entry
    candles.append(
        Candle(
            timestamp=datetime(2026, 11, 4, 10, 18, tzinfo=UTC),
            open=2643.5,
            high=2646.0,
            low=2643.0,
            close=2645.5,
            volume=250.0,
            atr14=2.0,
        )
    )

    signals = engine.evaluate_all(candles, swings=[], fvgs=[], obs=[], session_stats=session_stats, allow_pending=True)
    setup8_signals = [s for s in signals if s.setup_id == "SETUP_8_COMBINED_STRUCTURAL"]
    assert len(setup8_signals) >= 1
    sig = setup8_signals[0]
    assert sig.direction == SignalDirection.BUY
    assert sig.signal_index == 17
    assert sig.entry_index == 18


def test_causal_bar_by_bar_lookahead_invariance() -> None:
    """Proves that future bars do not alter historical signals across any of the 8 setups."""
    engine = SetupEngine(config=SetupConfig())
    base_fixture = generate_sweep_reclaim_bos_retest_fixture()
    assert len(base_fixture) >= 8

    # Replicate to create a sequence of 25 bars with warmup
    candles: list[Candle] = []
    for cycle in range(3):
        for idx, c in enumerate(base_fixture):
            candles.append(
                Candle(
                    timestamp=datetime(2026, 11, 4, 10, len(candles), tzinfo=UTC),
                    open=c.open,
                    high=c.high,
                    low=c.low,
                    close=c.close,
                    volume=c.volume,
                    atr14=2.0,
                    lower_wick=c.lower_wick,
                    upper_wick=c.upper_wick,
                    body=c.body,
                    range=c.range,
                )
            )

    stats_series = [{"asia": {"low": 2650.0, "high": 2670.0}} for _ in candles]

    # Evaluate at bar 18
    subset_18 = candles[:19]
    signals_18 = engine.evaluate_all(
        subset_18,
        swings=[],
        fvgs=[],
        obs=[],
        session_stats=stats_series[:19],
        allow_pending=True,
    )

    # Evaluate at bar 24 (future bars added)
    signals_full = engine.evaluate_all(
        candles,
        swings=[],
        fvgs=[],
        obs=[],
        session_stats=stats_series,
        allow_pending=True,
    )

    # Signals on or before index 18 MUST be identical
    signals_18_keys = {(s.setup_id, s.direction, s.signal_index, s.entry_price) for s in signals_18 if s.signal_index <= 18}
    signals_full_keys = {(s.setup_id, s.direction, s.signal_index, s.entry_price) for s in signals_full if s.signal_index <= 18}
    assert signals_18_keys == signals_full_keys


def test_paper_broker_cancel_order(tmp_path: Path) -> None:
    """Verifies pending order submission and cancellation."""
    db_file = str(tmp_path / "broker_cancel.sqlite")
    broker = PaperBroker(db_path=db_file)

    # Submit a BUY LIMIT order
    order = broker.submit_order(
        account_id="ACC_DEFAULT",
        direction=OrderDirection.BUY,
        order_type=OrderType.LIMIT,
        quantity_lots=0.2,
        target_price=2640.0,
        sl_price=2635.0,
        tp_price=2650.0,
    )
    assert order.status == OrderStatus.PENDING

    # Cancel the order
    cancelled = broker.cancel_order(order.order_id)
    assert cancelled.status == OrderStatus.CANCELLED
    assert broker.orders[order.order_id].status == OrderStatus.CANCELLED

    # Attempting to cancel already cancelled order must raise ValueError
    import pytest
    with pytest.raises(ValueError, match="تنها سفارش‌های در انتظار"):
        broker.cancel_order(order.order_id)


def test_bot_emergency_stop_and_resume(tmp_path: Path) -> None:
    """Verifies emergency stop locks the bot and manual reactivation resumes it."""
    db_file = str(tmp_path / "bot_emergency.sqlite")
    bot = AutomatedPaperBot(bot_id="TEST_EMERGENCY", db_path=db_file)
    bot.set_state(BotState.PAPER_AUTO)

    # Trigger emergency stop
    bot.emergency_stop("اپراتور دکمه توقف اضطراری را زد")
    assert bot.state == BotState.STOPPED

    # on_candle_close must not dispatch or execute anything in STOPPED state
    candles = generate_sweep_reclaim_bos_retest_fixture()
    signals = bot.on_candle_close(candles, current_bid=2650.0, current_ask=2650.4)
    assert signals == []

    # Resume bot
    bot.resume_after_emergency_stop(target_state=BotState.ANALYSIS_ONLY)
    assert bot.state == BotState.ANALYSIS_ONLY


def test_bot_consecutive_loss_cooldown(tmp_path: Path) -> None:
    """Verifies consecutive loss limit triggers cooldown bars."""
    db_file = str(tmp_path / "bot_cooldown.sqlite")
    risk = BotRiskSettings(consecutive_losses_limit=2, cooldown_bars=4)
    bot = AutomatedPaperBot(bot_id="TEST_COOLDOWN", risk_settings=risk, db_path=db_file)

    bot.on_trade_closed(-50.0)
    assert bot.consecutive_losses == 1
    assert bot.cooldown_remaining_bars == 0

    bot.on_trade_closed(-30.0)
    assert bot.consecutive_losses == 2
    assert bot.cooldown_remaining_bars == 4

    # Win resets the counter
    bot.on_trade_closed(100.0)
    assert bot.consecutive_losses == 0


def test_trade_autopsy_4_class_categorization(tmp_path: Path) -> None:
    """Verifies autopsy categorizes into 4 classes and produces actionable guidance."""
    db_file = str(tmp_path / "autopsy_4class.sqlite")
    registry = MistakeAnalyzerAndHypothesisRegistry(db_path=db_file)

    # Class A: Normal statistical loss
    auto_a = registry.perform_autopsy(
        trade_id="TR_NORMAL",
        setup_id="SETUP_1_ASIA_BO_RETEST",
        side="BUY",
        pnl=-25.0,
        r_multiple=-1.0,
        entry_price=2650.0,
        exit_price=2648.0,
        sl_price=2648.0,
        tp_price=2654.0,
        entry_regime="RANGING",
        entry_wick_ratio=0.20,
    )
    assert auto_a.failure_category == FailureCategory.NORMAL_STATISTICAL_LOSS
    assert "ضرر عادی" in auto_a.what_went_wrong

    # Class B: Execution defect (risk violation / oversized)
    auto_b = registry.perform_autopsy(
        trade_id="TR_DEFECT",
        setup_id="SETUP_2_SWEEP_RECLAIM_BOS",
        side="SELL",
        pnl=-150.0,
        r_multiple=-2.5,
        entry_price=2660.0,
        exit_price=2665.0,
        sl_price=2663.0,
        tp_price=2654.0,
        risk_violations="MAX_RISK_PER_TRADE_EXCEEDED",
        lot_size=3.5,
    )
    assert auto_b.failure_category == FailureCategory.EXECUTION_DEFECT
    assert "نقص در مدیریت ریسک" in auto_b.what_went_wrong

    # Class C: Strategy weakness (counter-trend in strong trend)
    auto_c = registry.perform_autopsy(
        trade_id="TR_WEAKNESS",
        setup_id="SETUP_1_ASIA_BO_RETEST",
        side="BUY",
        pnl=-40.0,
        r_multiple=-1.0,
        entry_price=2650.0,
        exit_price=2647.0,
        sl_price=2647.0,
        tp_price=2656.0,
        entry_regime="TRENDING",
        entry_wick_ratio=0.65,
    )
    assert auto_c.failure_category == FailureCategory.STRATEGY_WEAKNESS
    assert "رژیم بازار" in auto_c.what_went_wrong

    # Class D: Data failure (excessive spread)
    auto_d = registry.perform_autopsy(
        trade_id="TR_DATA_FAIL",
        setup_id="SETUP_4_FVG_RETEST",
        side="BUY",
        pnl=-35.0,
        r_multiple=-1.0,
        entry_price=2650.0,
        exit_price=2647.5,
        sl_price=2647.5,
        tp_price=2655.0,
        spread_at_entry=0.75,
    )
    assert auto_d.failure_category == FailureCategory.DATA_FAILURE
    assert "اسپرد" in auto_d.what_went_wrong

    # Query next time guidance
    guidance = registry.get_next_time_guidance(limit=10)
    assert len(guidance) == 4
    categories = {g["failure_category"] for g in guidance}
    assert categories == {
        FailureCategory.NORMAL_STATISTICAL_LOSS.value,
        FailureCategory.EXECUTION_DEFECT.value,
        FailureCategory.STRATEGY_WEAKNESS.value,
        FailureCategory.DATA_FAILURE.value,
    }


def test_api_emergency_and_cancel_endpoints() -> None:
    """Verifies FastAPI endpoints for emergency stop, resume, and order cancel."""
    client = TestClient(app)

    # 1. Emergency Stop
    res_stop = client.post("/api/bot/emergency-stop")
    assert res_stop.status_code == 200
    assert "توقف اضطراری فعال شد" in res_stop.json()["message"]

    # Check bot status reflects STOPPED
    status = client.get("/api/bot/status").json()
    assert status["state"] == "STOPPED"

    # 2. Resume
    res_resume = client.post("/api/bot/resume")
    assert res_resume.status_code == 200
    assert "خارج" in res_resume.json()["message"]

    status_after = client.get("/api/bot/status").json()
    assert status_after["state"] == "ANALYSIS_ONLY"

    # 3. Advice endpoint returns both safety lessons and trade guidance
    res_advice = client.get("/api/agent/advice")
    assert res_advice.status_code == 200
    advice_data = res_advice.json()
    assert "safety_lessons" in advice_data
    assert "trade_guidance" in advice_data
