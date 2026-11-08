"""Regression contracts for honest TV reference, dashboard and bounded paper risk."""
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]


def test_scanner_reference_cannot_spoof_executable_bid_ask() -> None:
    server = (ROOT / "app.py").read_text(encoding="utf-8")
    scanner = server.split("async def fetch_tradingview_quote_async()", 1)[1].split(
        '@app.get("/api/tradingview/quote")', 1
    )[0]
    assert "TRADINGVIEW_SCANNER_UNVERIFIED" in scanner
    assert '"verified_for_execution": False' in scanner
    assert '"data_role": "REFERENCE_ONLY"' in scanner
    assert '"bid":' not in scanner and '"ask":' not in scanner
    assert 'quote_age_seconds' in scanner
    assert 'received_at' in scanner


def test_dashboard_does_not_overwrite_broker_quotes_from_tv_close() -> None:
    js = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")
    handler = js.split("function handleTradingViewQuote(quote)", 1)[1].split(
        "// --- تابع جامع", 1
    )[0]
    assert 'quoteBidEl' not in handler
    assert 'quoteAskEl' not in handler
    assert 'updateLiveQuoteLine(' not in handler
    assert "مرجع غیررسمی" in handler


def test_chart_metrics_dont_crash_on_missing_optional_dom_nodes() -> None:
    js = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")
    html = (ROOT / "templates/index.html").read_text(encoding="utf-8")
    for node in ("stratWinRate", "stratPF", "stratExpectancy", "stratMaxDD"):
        if f'id="{node}"' not in html:
            assert f'if (document.getElementById("{node}"))' in js
    assert "fetchBotStatus();" not in js
    assert 'btnSaveRisk")?.addEventListener' in js


def test_backend_enforces_paper_risk_ceiling() -> None:
    from app import BotRiskRequest
    valid = {
        "risk_per_trade_pct": 0.5,
        "max_daily_loss_pct": 2.0,
        "max_open_positions": 2,
        "max_daily_trades": 4,
        "max_spread_pips": 0.5,
    }
    BotRiskRequest(**valid)
    for key, bad in (
        ("risk_per_trade_pct", 99.0),
        ("max_daily_loss_pct", 5.0),
        ("max_open_positions", 100),
        ("max_daily_trades", 100),
        ("max_spread_pips", float("nan")),
    ):
        with pytest.raises(ValidationError):
            BotRiskRequest(**{**valid, key: bad})


def test_pull_hook_requires_explicit_local_install() -> None:
    installer = (ROOT / "scripts/install-antigravity-hooks.sh").read_text(encoding="utf-8")
    assert "post-merge" in installer and "post-rewrite" in installer
    assert "Refusing to overwrite existing hook" in installer
    assert "run once" in installer.lower() or "Run once" in installer



def test_chart_requires_real_feed_without_hidden_demo_fallback() -> None:
    js = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")
    html = (ROOT / "templates/index.html").read_text(encoding="utf-8")
    handler = js.split("async function fetchMarketData()", 1)[1].split(
        "function renderMarketData(", 1
    )[0]
    assert "/api/market/load-demo" not in handler
    assert 'id="chartEmptyState"' in html
    assert 'lastQuoteTime' in html
    assert "chartHasFittedOnce" in js
    assert "setVisibleLogicalRange" in js
    assert "currentMarketData?.data_source" in js


def test_synthetic_replay_cannot_authorize_market_order(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app import app, engine
    with monkeypatch.context() as context:
        context.setattr(engine, "market_data_source", "DEMO_CSV")
        res = TestClient(app).post("/api/broker/order", json={
            "direction": "BUY", "order_type": "MARKET",
            "quantity_lots": 0.01,
        })
    assert res.status_code == 409
    assert "synthetic chart" in res.json()["detail"]
