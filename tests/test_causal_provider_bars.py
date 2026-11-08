"""Causal provider candles, session reference and restart-safe event regression.

These tests verify software timing only; they are not evidence of a profitable
trading strategy or approval to activate PAPER_AUTO.
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from goldlab.bot import AutomatedPaperBot, BotState
from goldlab.data import DataPipeline
from goldlab.paper_broker import PaperBroker
from goldlab.sessions import TZ_NEW_YORK, SessionManager
from goldlab.types import Candle

UTC = timezone.utc


def candle_at(t: datetime, p: float = 4400.0) -> Candle:
    return Candle(timestamp=t, open=p, high=p + 1, low=p - 1, close=p + 0.2)


def m1_series(n: int, *, base: datetime) -> list[Candle]:
    return [candle_at(base + timedelta(minutes=i)) for i in range(n)]


def test_provider_m1_partial_final_bucket_is_not_tradable(tmp_path: Path) -> None:
    data = DataPipeline(db_path=str(tmp_path / "candles.sqlite"))
    base = datetime(2026, 11, 9, 14, 0, tzinfo=UTC)
    # 14:00–14:04 is complete; 14:05–14:07 is not.
    bars = m1_series(8, base=base)
    loose = data.aggregate_candles(bars, "5m")
    strict = data.aggregate_candles(bars, "5m", require_complete=True)
    assert len(loose) == 2
    assert len(strict) == 1
    assert strict[0].timestamp == base


def test_provider_m1_missing_or_duplicate_cannot_create_complete_bucket(tmp_path: Path) -> None:
    data = DataPipeline(db_path=str(tmp_path / "candles.sqlite"))
    base = datetime(2026, 11, 9, 14, 0, tzinfo=UTC)
    bars = m1_series(5, base=base)
    assert len(data.aggregate_candles(bars, "5m", require_complete=True)) == 1
    missing = [bars[0], bars[1], bars[3], bars[4]]
    assert data.aggregate_candles(missing, "5m", require_complete=True) == []
    with pytest.raises(ValueError, match="Duplicate"):
        data.aggregate_candles(bars + [bars[2]], "5m", require_complete=True)


def test_asia_reference_is_frozen_after_midnight_not_combined_with_tokyo() -> None:
    mgr = SessionManager()
    ny_start = datetime(2026, 11, 4, 21, 0, tzinfo=TZ_NEW_YORK)
    ny_after = datetime(2026, 11, 5, 0, 30, tzinfo=TZ_NEW_YORK)
    # Tokyo is open at NY 00:30, but the defined 20:00–00:00 NY
    # Asia reference has already finalized.
    candle1 = Candle(timestamp=ny_start, open=4400, high=4405, low=4395, close=4400)
    candle2 = Candle(timestamp=ny_after, open=4400, high=4450, low=4380, close=4410)
    result = mgr.calculate_as_of_session_stats_series([candle1, candle2])
    assert result[0]["asia"]["high"] == 4405
    assert result[0]["asia_complete"] is False
    assert result[1]["asia_complete"] is True
    assert result[1]["asia"]["high"] == 4405
    assert result[1]["asia"]["low"] == 4395


def test_strict_provider_same_closed_bar_ignored_across_poll_and_restart(tmp_path: Path) -> None:
    db_path = str(tmp_path / "bot.sqlite")
    broker = PaperBroker(db_path=db_path)
    base = datetime(2026, 11, 9, 14, 0, tzinfo=UTC)
    bars = m1_series(10, base=base)
    tick_time = base + timedelta(minutes=10, seconds=10)
    first = AutomatedPaperBot(bot_id="STRICT_IDEMPOTENT", broker=broker, db_path=db_path)
    first.state = BotState.ANALYSIS_ONLY
    first.on_candle_close(bars, 4400.0, 4400.2, current_time=tick_time, strict_provider=True)
    first.on_candle_close(bars, 4400.0, 4400.2, current_time=tick_time, strict_provider=True)
    second = AutomatedPaperBot(bot_id="STRICT_IDEMPOTENT", broker=broker, db_path=db_path)
    second.state = BotState.ANALYSIS_ONLY
    second.on_candle_close(bars, 4400.0, 4400.2, current_time=tick_time, strict_provider=True)
    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT count(*) FROM bot_processed_candles WHERE bot_id=?",
            ("STRICT_IDEMPOTENT",)
        ).fetchone()[0]
    assert count == 1
    assert not broker.orders


def test_strict_provider_old_completed_bucket_cannot_trigger(tmp_path: Path) -> None:
    db_path = str(tmp_path / "bot.sqlite")
    broker = PaperBroker(db_path=db_path)
    bot = AutomatedPaperBot(bot_id="STRICT_DELAY", broker=broker, db_path=db_path)
    base = datetime(2026, 11, 9, 14, 0, tzinfo=UTC)
    bars = m1_series(8, base=base)
    # 14:05 bucket is partial; last completed bucket closed at 14:05.
    # At 14:08 it is too late to enter as if it were the next-bar quote.
    bot.on_candle_close(
        bars, 4400, 4400.2,
        current_time=base + timedelta(minutes=8, seconds=5),
        strict_provider=True,
    )
    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT count(*) FROM bot_processed_candles WHERE bot_id=?", ("STRICT_DELAY",)
        ).fetchone()[0]
    assert count == 0



def test_daily_risk_limits_survive_restart_and_claim_atomically(tmp_path: Path) -> None:
    db_path = str(tmp_path / "limits.sqlite")
    broker = PaperBroker(db_path=db_path)
    from goldlab.bot import BotRiskSettings
    at = datetime(2026, 11, 9, 14, 11, tzinfo=UTC)
    bot = AutomatedPaperBot(
        bot_id="PERSISTENT_LIMITS", broker=broker, db_path=db_path,
        risk_settings=BotRiskSettings(max_daily_trades=1),
    )
    bot.heartbeat_time = at
    bot._sync_daily_risk_counters()
    baseline = bot.daily_start_balance
    assert bot._claim_daily_order_slot() is True
    assert bot._claim_daily_order_slot() is False

    # Create a new bot instance pointing to the same SQLite — the cap and
    # baseline cannot reset just by restarting the local process.
    restarted = AutomatedPaperBot(
        bot_id="PERSISTENT_LIMITS", broker=broker, db_path=db_path,
        risk_settings=BotRiskSettings(max_daily_trades=1),
    )
    restarted.heartbeat_time = at
    restarted._sync_daily_risk_counters()
    assert restarted.today_trades_count == 1
    assert restarted.daily_start_balance == baseline
    assert restarted._claim_daily_order_slot() is False



def test_chart_navigation_cannot_change_paper_strategy_timeframe(monkeypatch) -> None:
    import app as application
    assert application.bot.engine is not application.engine
    assert application.bot.engine.current_timeframe == "5m"
    with monkeypatch.context() as context:
        context.setattr(application.engine, "current_timeframe", "1m")
        assert application.bot.engine.current_timeframe == "5m"
        context.setattr(application.engine, "current_timeframe", "15m")
        assert application.bot.engine.current_timeframe == "5m"
