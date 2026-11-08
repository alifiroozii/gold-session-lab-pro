"""
Integration tests for FastAPI endpoints and WebSocket.
"""

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def test_dashboard_html_served() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Gold Session Lab Pro" in response.text
    assert "Paper Trading" in response.text


def test_api_market_data() -> None:
    response = client.get("/api/market?timeframe=5m")
    assert response.status_code == 200
    data = response.json()
    assert "candles" in data
    assert "session_stats" in data
    assert "signals" in data
    assert "metrics" in data


def test_broker_account_and_funds() -> None:
    # 1. Get Account
    res = client.get("/api/broker/account")
    assert res.status_code == 200
    acc = res.json()
    assert acc["account_id"] == "ACC_DEFAULT"
    assert acc["balance"] >= 0.0

    # 2. Deposit
    dep_res = client.post("/api/broker/deposit", json={"amount": 500.0})
    assert dep_res.status_code == 200
    new_bal = dep_res.json()["balance"]

    # 3. Withdraw
    with_res = client.post("/api/broker/withdraw", json={"amount": 200.0})
    assert with_res.status_code == 200
    assert with_res.json()["balance"] == new_bal - 200.0


def test_bot_status_and_state_switch() -> None:
    res = client.get("/api/bot/status")
    assert res.status_code == 200
    data = res.json()
    assert "state" in data

    # Switch to ANALYSIS_ONLY
    switch_res = client.post("/api/bot/state", json={"state": "ANALYSIS_ONLY"})
    assert switch_res.status_code == 200
    assert switch_res.json()["new_state"] == "ANALYSIS_ONLY"


def test_calendar_endpoint() -> None:
    res = client.get("/api/calendar")
    assert res.status_code == 200
    events = res.json()["events"]
    assert len(events) >= 1
    assert any("CPI" in e["name"] for e in events)


def test_strategy_comparison_endpoint() -> None:
    res = client.get("/api/backtest/compare")
    if res.status_code == 400:
        # No authenticated real history is configured in CI.
        # Refusing to present fabricated comparisons is the correct behavior.
        market = client.get("/api/market").json()
        assert market["data_source"] == "NO_VERIFIED_PROVIDER_DATA"
        assert not market["candles"]
    else:
        assert res.status_code == 200
        results = res.json()["results"]
        assert len(results) == 8  # S1 to S8


def test_tradingview_quote_endpoint() -> None:
    res = client.get("/api/tradingview/quote")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("SUCCESS", "UNAVAILABLE")
    if data["status"] == "SUCCESS":
        q = data["quote"]
        assert q["symbol"] == "XAU/USD"
        assert q["price"] > 0
        assert q["bid"] > 0
        assert q["ask"] >= q["bid"]
        assert "source" in q


def test_load_demo_endpoint() -> None:
    res = client.post("/api/market/load-demo")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert data["count"] > 0
    assert data["session_boxes"] > 0
    # Reset engine state for subsequent isolation tests
    from app import engine
    engine.current_candles = []
    engine.candles_1m = []
    engine.market_data_source = "NO_VERIFIED_PROVIDER_DATA"
