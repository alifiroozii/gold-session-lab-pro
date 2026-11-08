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
    assert res.status_code == 200
    results = res.json()["results"]
    assert len(results) == 8  # S1 to S8
