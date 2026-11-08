"""
Unit tests for Market Data Gateway (Layers A, B, C) - Master Prompt V5.
"""
from datetime import datetime, timedelta, timezone

from goldlab.market_gateway import (
    MarketDataGateway,
    TradingViewReferenceMetadata,
)
from goldlab.market_safety import MarketQuote

TZ_UTC = timezone.utc


def test_tradingview_reference_metadata():
    meta = TradingViewReferenceMetadata()
    assert meta.symbol == "OANDA:XAUUSD"
    assert meta.is_executable is False
    assert "تریدینگ‌ویو" in meta.notes
    assert "OANDA%3AXAUUSD" in meta.widget_url


def test_market_gateway_comparison_payload_unconfigured():
    gateway = MarketDataGateway()
    payload = gateway.get_comparison_payload(verified_quote=None)

    assert payload["status"] == "SUCCESS"
    assert len(payload["layers"]) == 2
    assert payload["layers"][0]["source_layer"] == "لایه A (مرجع بصری)"
    assert payload["layers"][0]["is_executable"] is False
    assert payload["layers"][1]["source_layer"] == "لایه B (مظنه اجرایی تأییدشده)"
    assert payload["execution_gate"]["allowed"] is False


def test_market_gateway_comparison_with_live_quotes():
    # Tuesday 14:00 UTC (Active trading hours)
    now = datetime(2026, 11, 10, 14, 0, 0, tzinfo=TZ_UTC)
    gateway = MarketDataGateway()

    # Feed Layer A TV Quote
    gateway.update_tv_reference_quote({
        "symbol": "OANDA:XAUUSD",
        "price": 2735.40,
        "bid": 2735.25,
        "ask": 2735.55,
        "time_iso": now.isoformat(),
    })

    # Feed Layer B Execution Quote
    live_quote = MarketQuote(
        timestamp=now - timedelta(seconds=2),
        bid=2735.30,
        ask=2735.60,
        instrument="XAU_USD",
        source="OANDA_V20_READ_ONLY",
        tradeable=True,
    )

    payload = gateway.get_comparison_payload(verified_quote=live_quote, now=now)

    assert payload["status"] == "SUCCESS"
    assert payload["price_delta"]["difference_usd"] == 0.05  # (2735.45 mid - 2735.40 tv)
    assert payload["execution_gate"]["allowed"] is True
    assert payload["layers"][1]["bid"] == 2735.30
    assert payload["layers"][1]["ask"] == 2735.60
    assert payload["layers"][1]["spread"] == 0.30
