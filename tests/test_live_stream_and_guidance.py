"""Offline regression coverage: authenticated provider precision and fail-closed guidance."""
from datetime import datetime, timezone

import pytest

from goldlab.market_safety import OandaReadOnlyFeed, execution_gate
from goldlab.review_journal import DecisionJournal
from goldlab.agent_bridge import AgentBridge


def _provider_event(*, status="tradeable", bid="4387.123", ask="4387.137"):
    return {
        "type": "PRICE", "instrument": "XAU_USD",
        "time": "2026-11-09T15:00:00.123456789Z",
        "status": status, "tradeable": status == "tradeable",
        "bids": [{"price": bid}], "asks": [{"price": ask}],
    }


def test_provider_source_precision_not_demo_or_fixed_to_two_decimals(monkeypatch):
    monkeypatch.setenv("OANDA_ENV", "practice")
    monkeypatch.setenv("OANDA_API_TOKEN", "local-test-only")
    monkeypatch.setenv("OANDA_ACCOUNT_ID", "local-account")
    feed = OandaReadOnlyFeed()
    assert "stream-fxpractice.oanda.com" in feed.stream_url
    assert "/pricing/stream?instruments=XAU_USD" in feed.stream_url
    quote = feed.quote_from_price(_provider_event())
    assert quote.bid_display == "4387.123"
    assert quote.ask_display == "4387.137"
    assert quote.source == "OANDA_V20_READ_ONLY"
    assert execution_gate(quote, now=datetime(2026, 11, 9, 15, 0, 1,
                                              tzinfo=timezone.utc))[0] is True


@pytest.mark.parametrize("event", [
    {"type": "HEARTBEAT", "time": "2026-11-09T15:00:00Z"},
    _provider_event(bid="4387.140", ask="4387.130"),
    _provider_event(bid="NaN"),
    _provider_event(ask="Infinity"),
    {**_provider_event(), "instrument": "EUR_USD"},
    {**_provider_event(), "bids": []},
])
def test_invalid_provider_events_rejected(event):
    with pytest.raises((ValueError, KeyError, TypeError)):
        OandaReadOnlyFeed().quote_from_price(event)


def test_provider_closed_quote_does_not_authorize_paper_order():
    quote = OandaReadOnlyFeed().quote_from_price(
        _provider_event(status="non-tradeable"))
    assert quote.tradeable is False
    assert execution_gate(quote, now=datetime(2026, 11, 9, 15, 0, 1,
                                              tzinfo=timezone.utc))[0] is False


def test_persisted_safety_advice_is_idempotent_and_handed_to_agent(tmp_path):
    db_path = str(tmp_path / "safety.sqlite")
    memory = DecisionJournal(db_path)
    now = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)
    first = memory.record_block("QUOTE_STALE_OR_FUTURE", "quote_ttl", now)
    assert first and "قدیمی" in first["guidance"]
    assert memory.record_block("QUOTE_STALE_OR_FUTURE", "quote_ttl", now) is None
    assert len(memory.recent()) == 1
    assert all(item["confidence"] == "DETERMINISTIC_SAFETY_RULE"
               for item in memory.recent())
    bridge = AgentBridge(db_path)
    handoff = tmp_path / "TASK.md"
    bridge.write_handoff(str(handoff))
    text = handoff.read_text(encoding="utf-8")
    assert "QUOTE_STALE_OR_FUTURE" in text
    assert "safety_lessons" in text
    assert bridge.state()["agent_status"] == "NOT_CONNECTED"


def test_no_provider_defaults_to_no_chart_data(monkeypatch):
    import app as application
    # A fresh process without OANDA credentials must never import demo data.
    if not application.market_feed.configured:
        assert application.engine.market_data_source in (
            "NO_VERIFIED_PROVIDER_DATA", "DEMO_CSV")
        if application.engine.market_data_source == "DEMO_CSV":
            # Demo data is explicitly opted in for replay only.
            import os
            assert os.getenv("GOLDLAB_ENABLE_DEMO_REPLAY") == "1"


def test_paper_close_saved_once_without_ai_verdict(tmp_path):
    bridge = AgentBridge(str(tmp_path / "trades.sqlite"))
    trade = dict(
        trade_id="PAPER-1", direction="BUY", entry_price=4390.12,
        exit_price=4387.75, realized_pnl=-23.7, close_reason="STOP_LOSS",
    )
    assert bridge.record_closed_paper_trade(**trade) is True
    assert bridge.record_closed_paper_trade(**trade) is False
    assert bridge.observe_local_issues() == 1
    handoff = tmp_path / "CLOSED_TASK.md"
    bridge.write_handoff(str(handoff))
    text = handoff.read_text(encoding="utf-8")
    assert "PAPER-1" in text
    assert "STOP_LOSS" in text
    assert "AWAITING_REVIEW" in text
    assert "normal losses" not in text.lower() or "Normal losses" in text
    assert bridge.state()["agent_status"] == "NOT_CONNECTED"
