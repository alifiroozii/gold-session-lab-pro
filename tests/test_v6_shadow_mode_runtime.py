"""
Master Prompt V6 Integration Tests — Shadow Mode Runtime, Timeouts & Validation Lab.
Verifies causal event loop, shadow proposals, timeout invalidations,
spread/news filters, restart recovery, and API endpoints.
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import app
from goldlab.calendar import EconomicEvent, MacroNewsCalendar
from goldlab.market_safety import MarketQuote
from goldlab.state_machine import SessionStrategyState, SessionTradingStateMachine
from goldlab.types import Candle

TZ_UTC = timezone.utc
client = TestClient(app)


def _make_candles(count: int, start_dt: datetime, base_p: float = 2700.0) -> list[Candle]:
    candles = []
    for i in range(count):
        t = start_dt + timedelta(minutes=5 * i)
        candles.append(
            Candle(
                timestamp=t,
                open=base_p,
                high=base_p + 1.0,
                low=base_p - 1.0,
                close=base_p + 0.2,
                volume=100.0,
                is_closed=True,
            )
        )
    return candles


def test_shadow_proposals_recorded_in_sqlite(tmp_path):
    db_file = str(tmp_path / "test_shadow.sqlite")
    sm = SessionTradingStateMachine(db_path=db_file, shadow_mode=True)

    # Simulate Asia session candles: 2026-11-08 20:00 to 00:00 NY (01:00 to 05:00 UTC)
    start_time = datetime(2026, 11, 9, 1, 0, tzinfo=TZ_UTC)
    candles = _make_candles(48, start_time, base_p=2700.0)

    # Process candles
    sm.process_completed_5m_candles(candles)

    summary = sm.get_state_summary()
    assert summary["processed_candles_count"] == 48
    assert summary["shadow_mode"] is True
    assert summary["enabled_for_auto_trading"] is False

    # Check recovery from DB
    sm2 = SessionTradingStateMachine(db_path=db_file, shadow_mode=True)
    summary2 = sm2.get_state_summary()
    assert summary2["processed_candles_count"] == 48


def test_shadow_proposal_spread_filter(tmp_path):
    db_file = str(tmp_path / "test_spread.sqlite")
    sm = SessionTradingStateMachine(db_path=db_file, max_spread=0.50)

    # Asia session to finalize range
    start_time = datetime(2026, 11, 9, 1, 0, tzinfo=TZ_UTC)
    candles = _make_candles(48, start_time, base_p=2700.0)
    # High = 2701.0, Low = 2699.0
    sm.process_completed_5m_candles(candles)

    # Transition bar right after Asia closes (05:05 UTC)
    post_asia_bar = Candle(
        timestamp=datetime(2026, 11, 9, 5, 5, tzinfo=TZ_UTC),
        open=2700.0,
        high=2700.5,
        low=2699.5,
        close=2700.2,
        volume=100.0,
        is_closed=True,
    )
    sm.process_completed_5m_candles([post_asia_bar])
    assert sm.current_state == SessionStrategyState.RANGE_FINALIZED
    assert sm.ref_high is not None and sm.ref_low is not None

    # London session: sweep high
    t_sweep = datetime(2026, 11, 9, 8, 5, tzinfo=TZ_UTC)
    sweep_bar = Candle(
        timestamp=t_sweep,
        open=2700.5,
        high=2703.5,  # sweep above 2701.0
        low=2700.0,
        close=2702.5,
        volume=150.0,
        is_closed=True,
    )
    sm.process_completed_5m_candles([sweep_bar])
    assert sm.current_state == SessionStrategyState.SWEEP_DETECTED

    # Reclaim bar
    t_reclaim = datetime(2026, 11, 9, 8, 10, tzinfo=TZ_UTC)
    reclaim_bar = Candle(
        timestamp=t_reclaim,
        open=2702.0,
        high=2702.2,
        low=2698.5,
        close=2699.5,  # closed back below 2701.0
        volume=200.0,
        is_closed=True,
    )
    sm.process_completed_5m_candles([reclaim_bar])
    assert sm.current_state == SessionStrategyState.RECLAIM_CONFIRMED

    # Structure break (BOS)
    t_bos = datetime(2026, 11, 9, 8, 15, tzinfo=TZ_UTC)
    bos_bar = Candle(
        timestamp=t_bos,
        open=2699.5,
        high=2699.8,
        low=2696.0,
        close=2697.0,
        volume=250.0,
        is_closed=True,
    )
    sm.process_completed_5m_candles([bos_bar])
    assert sm.current_state == SessionStrategyState.STRUCTURE_CONFIRMED

    # Retest bar
    t_retest = datetime(2026, 11, 9, 8, 20, tzinfo=TZ_UTC)
    retest_bar = Candle(
        timestamp=t_retest,
        open=2697.0,
        high=2701.2,  # retests 2701.0
        low=2696.5,
        close=2698.0,
        volume=220.0,
        is_closed=True,
    )
    sm.process_completed_5m_candles([retest_bar])
    assert sm.current_state == SessionStrategyState.RETEST_CONFIRMED

    # Next bar triggers entry formulation -> ENTRY_ELIGIBLE
    t_entry = datetime(2026, 11, 9, 8, 25, tzinfo=TZ_UTC)
    entry_bar = Candle(
        timestamp=t_entry,
        open=2698.0,
        high=2699.0,
        low=2697.5,
        close=2698.5,
        volume=180.0,
        is_closed=True,
    )
    signals = sm.process_completed_5m_candles([entry_bar])
    assert sm.current_state == SessionStrategyState.ENTRY_ELIGIBLE

    # Provide a wide spread quote ($1.20 > $0.50)
    wide_quote = MarketQuote(
        bid=2697.0,
        ask=2698.2,
        timestamp=t_retest,
        source="OANDA_V20_READ_ONLY",
    )
    assert len(signals) > 0
    sig = signals[0]
    sm._record_shadow_proposal(
        sig,
        entry_bar,
        live_quote=wide_quote,
        calendar=None,
    )

    proposals = sm.get_shadow_proposals()
    assert len(proposals) > 0
    prop = proposals[0]
    assert prop["status"] == "REJECTED_SPREAD"
    assert "اسپرد" in prop["rejection_reason"]


def test_shadow_proposal_macro_news_filter(tmp_path):
    db_file = str(tmp_path / "test_news.sqlite")
    sm = SessionTradingStateMachine(db_path=db_file)

    t_retest = datetime(2026, 11, 9, 13, 30, tzinfo=TZ_UTC)
    bar = Candle(
        timestamp=t_retest,
        open=2697.0,
        high=2701.0,
        low=2696.0,
        close=2698.0,
        volume=200.0,
        is_closed=True,
    )
    from goldlab.types import SetupSignal, SignalDirection

    sig = SetupSignal(
        setup_id="S1_SWEEP_ASIA_HIGH",
        setup_name="Liquidity Sweep High",
        direction=SignalDirection.SELL,
        signal_index=10,
        signal_time=t_retest,
        entry_index=11,
        entry_price=2698.0,
        sl_price=2704.0,
        tp_price=2686.0,
        risk_r=2.0,
        reason="Test",
        metrics={"level": "Asia_High", "level_val": 2701.0},
    )

    calendar = MacroNewsCalendar(
        events=[
            EconomicEvent(
                name="US CPI",
                release_time=datetime(2026, 11, 9, 13, 30, tzinfo=TZ_UTC),
                impact="HIGH",
            )
        ]
    )

    sm._record_shadow_proposal(sig, bar, live_quote=None, calendar=calendar)
    props = sm.get_shadow_proposals()
    assert len(props) > 0
    assert props[0]["status"] == "REJECTED_NEWS"
    assert "رویداد کلان" in props[0]["rejection_reason"]


def test_api_shadow_proposals_endpoint():
    res = client.get("/api/strategy/shadow-proposals")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_api_validation_report_endpoint():
    res = client.get("/api/strategy/validation-report")
    assert res.status_code == 200
    data = res.json()
    assert "statistical_verdict" in data or "outcome" in data
    assert data["authorizes_paper_auto"] is False
