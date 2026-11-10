"""Offline regressions for provider-to-shadow wiring and honest proposal gates."""
from datetime import datetime, timedelta, timezone

import pytest

from types import SimpleNamespace
from goldlab.market_safety import MarketQuote
from goldlab.state_machine import SessionTradingStateMachine
from goldlab.types import Candle, SetupSignal, SignalDirection

UTC = timezone.utc
AT = datetime(2026, 11, 9, 14, 0, tzinfo=UTC)


def proposal(sm, quote=None, calendar=None, reward=12):
    bar = Candle(timestamp=AT, open=100, high=101, low=99, close=100)
    sig = SetupSignal(setup_id="TEST", setup_name="TEST", direction=SignalDirection.BUY,
                      signal_index=0, signal_time=AT, entry_index=1, entry_price=100,
                      sl_price=94, tp_price=100 + reward, risk_r=6, reason="fixture")
    sm._record_shadow_proposal(sig, bar, quote, calendar)
    return sm.get_shadow_proposals()[0]


def test_missing_quote_cannot_invent_shadow_spread(tmp_path):
    sm = SessionTradingStateMachine(db_path=str(tmp_path / 'sm.sqlite'))
    row = proposal(sm)
    assert row['spread'] is None
    assert row['status'] == 'REJECTED_QUOTE'


def test_calendar_does_not_bypass_reward_filter(tmp_path):
    sm = SessionTradingStateMachine(db_path=str(tmp_path / 'sm.sqlite'))
    q = MarketQuote(100, 100.2, AT + timedelta(minutes=5), 'OANDA_V20_READ_ONLY', tradeable=True)
    assert proposal(sm, q, SimpleNamespace(is_blackout=lambda _: (False, "")), reward=1)['status'] == 'REJECTED_RISK'


@pytest.mark.parametrize('timeframe', ['1m', '15m', '1h'])
def test_shadow_receives_only_complete_5m_bars(monkeypatch, timeframe, tmp_path):
    import app as runtime
    from goldlab.engine import ResearchEngine
    monkeypatch.setattr(runtime, "engine", ResearchEngine(db_path=str(tmp_path / "chart.sqlite")))
    bars = [Candle(timestamp=AT + timedelta(minutes=i), open=100, high=101, low=99,
                   close=100, is_closed=True) for i in range(8)]
    received = []
    monkeypatch.setattr(runtime.engine, 'current_timeframe', timeframe)
    monkeypatch.setattr(runtime.engine, 'run_pipeline', lambda: None)
    monkeypatch.setattr(runtime.session_state_machine, 'process_completed_5m_candles',
                        lambda values, **kw: received.extend(values))
    runtime.process_provider_candles(bars)
    assert [b.timestamp for b in received] == [AT]
    assert runtime.engine.current_timeframe == timeframe


@pytest.mark.parametrize('quote', [
    MarketQuote(100, 100.2, AT - timedelta(hours=1), 'OANDA_V20_READ_ONLY', tradeable=True),
    MarketQuote(100, 100.2, AT + timedelta(minutes=5), 'UNVERIFIED', tradeable=True),
])
def test_shadow_rejects_stale_or_untrusted_quote(tmp_path, quote):
    sm = SessionTradingStateMachine(db_path=str(tmp_path / 'sm.sqlite'))
    assert proposal(sm, quote)['status'] == 'REJECTED_QUOTE'
