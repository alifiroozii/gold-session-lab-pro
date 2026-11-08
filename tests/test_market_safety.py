"""Guards against paper trades on a closed market, stale/demo feeds and fabricated AI fixes."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from goldlab.agent_bridge import AgentBridge
from goldlab.market_safety import MarketQuote, execution_gate
from goldlab.sessions import SessionManager
from goldlab.types import Candle

UTC = timezone.utc


def quote(t: datetime, *, source: str = "OANDA_V20_READ_ONLY",
          tradeable: bool = True) -> MarketQuote:
    return MarketQuote(3000.1, 3000.3, t, source, tradeable=tradeable)


def test_sunday_market_closed_even_with_fresh_quote():
    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    assert execution_gate(quote(now), now)[0] is False


def test_weekday_market_open_only_with_verified_quote():
    now = datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
    assert execution_gate(quote(now), now)[0] is True
    assert execution_gate(quote(now, source="DEMO_CSV"), now)[0] is False
    assert execution_gate(quote(now, tradeable=False), now)[0] is False
    assert execution_gate(None, now)[0] is False


def test_stale_future_daily_break_and_wrong_market():
    mon = datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
    assert execution_gate(quote(mon - timedelta(minutes=5)), mon)[0] is False
    assert execution_gate(quote(mon + timedelta(seconds=40)), mon)[0] is False
    mon_break = datetime(2026, 11, 9, 22, 30, tzinfo=UTC)  # 17:30 New York
    assert execution_gate(quote(mon_break), mon_break)[0] is False


def test_order_endpoint_fail_closed_without_real_quote(monkeypatch):
    import app as application
    monkeypatch.setattr(application, "verified_quote", None)
    client = TestClient(application.app)
    response = client.post("/api/broker/order", json={
        "direction": "BUY", "order_type": "MARKET", "quantity_lots": 0.1,
    })
    assert response.status_code == 409
    status = client.get("/api/market/status")
    assert status.status_code == 200
    assert status.json()["paper_orders_allowed"] is False
    assert status.json()["historical_data_is_executable"] is False


def test_auto_bot_rejected_without_validation(monkeypatch):
    import app as application
    now = datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
    monkeypatch.setattr(application, "verified_quote", quote(now))
    client = TestClient(application.app)
    response = client.post("/api/bot/state", json={"state": "PAPER_AUTO"})
    assert response.status_code == 409
    assert "PAPER_AUTO_UNVERIFIED" in response.json()["detail"] or "blocked" in response.json()["detail"]


def test_session_boxes_have_true_window_and_price_extremes():
    mgr = SessionManager()
    times = [datetime(2026, 11, 4, hour, 0, tzinfo=UTC) for hour in [0, 1, 2, 10, 11, 14]]
    candles = [Candle(timestamp=ts, open=3000.0, high=3002.0 + idx,
                      low=2999.0 - idx, close=3001.0)
               for idx, ts in enumerate(times)]
    boxes = mgr.calculate_session_boxes(candles)
    asia = [b for b in boxes if b["session"] == "asia"]
    assert len(asia) == 1
    assert asia[0]["high"] == pytest.approx(3004.0)
    assert asia[0]["low"] == pytest.approx(2997.0)
    assert asia[0]["start"] == int(datetime(2026,11,4,0,0,tzinfo=UTC).timestamp())
    assert any(b["session"] == "overlap" for b in boxes)


def test_antigravity_events_need_evidence_for_verified_resolution(tmp_path):
    bridge = AgentBridge(str(tmp_path / "lab.sqlite"))
    assert bridge.state()["agent_status"] == "NOT_CONNECTED"
    with pytest.raises(ValueError):
        bridge.record("RESOLVED", "simulated fix", actor="ANTIGRAVITY",
                      evidence="", verified=True)
    with pytest.raises(ValueError):
        bridge.record("TESTS_PASSED", "simulated test", actor="ANTIGRAVITY",
                      evidence="no actual evidence", verified=False)
    bridge.record("PATCH_PROPOSED", "example candidate", actor="ANTIGRAVITY")
    assert bridge.state()["agent_status"] == "RECENT_ACTIVITY"
    assert bridge.state()["verified_fixes"] == 0


def test_agent_handoff_is_real_file_not_false_ai_execution(tmp_path):
    bridge = AgentBridge(str(tmp_path / "lab.sqlite"))
    dest = tmp_path / "REVIEW_TASK.md"
    bridge.observe_local_issues()
    assert dest.exists() is False
    path = bridge.write_handoff(str(dest))
    text = dest.read_text(encoding="utf-8")
    assert path == str(dest)
    assert "UNTRUSTED OBSERVATIONS" in text
    assert bridge.state()["agent_status"] == "NOT_CONNECTED"
