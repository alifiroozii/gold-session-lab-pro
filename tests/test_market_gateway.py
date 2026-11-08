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
        "symbol": "XAU/USD",
        "ticker": "OANDA:XAUUSD",
        "source": "TRADINGVIEW_SCANNER_UNVERIFIED",
        "data_role": "REFERENCE_ONLY",
        "verified_for_execution": False,
        "price": 2735.40,
        "time_iso": now.isoformat(),
        # Even if a caller supplies these fields, the scanner cannot
        # vouch for an executable bid/ask quote or a broker spread.
        "bid": 2735.25,
        "ask": 2735.55,
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



def test_gateway_adapter_calls_existing_read_only_latest_quote_method():
    from unittest.mock import Mock

    from goldlab.market_gateway import OandaProviderAdapter
    adapter = OandaProviderAdapter(feed=Mock(configured=True))
    adapter.get_latest_quote()
    adapter.feed.latest_quote.assert_called_once_with()
    assert not adapter.feed.poll_quote.called


def test_unverified_tradingview_reference_is_not_used_even_for_comparison():
    now = datetime(2026, 11, 10, 14, tzinfo=TZ_UTC)
    gateway = MarketDataGateway()
    gateway.update_tv_reference_quote({
        "ticker": "OANDA:XAUUSD", "source": "SCANNER_UNKNOWN",
        "data_role": "REFERENCE_ONLY", "verified_for_execution": False,
        "price": 4100, "time_iso": now.isoformat(),
    })
    assert gateway.get_comparison_payload(None, now=now)["layers"][0]["mid"] is None


def test_scanner_reference_expires_with_source_timestamp():
    now = datetime(2026, 11, 10, 14, tzinfo=TZ_UTC)
    gateway = MarketDataGateway()
    gateway.update_tv_reference_quote({
        "ticker": "OANDA:XAUUSD",
        "source": "TRADINGVIEW_SCANNER_UNVERIFIED",
        "data_role": "REFERENCE_ONLY",
        "verified_for_execution": False,
        "price": 4300,
        "time_iso": (now - timedelta(seconds=60)).isoformat(),
    })
    p = gateway.get_comparison_payload(None, now=now)
    assert p["layers"][0]["mid"] is None
    assert p["price_delta"]["difference_usd"] is None


def test_tv_scanner_does_not_create_false_bid_ask_or_spread():
    now = datetime(2026, 11, 10, 14, tzinfo=TZ_UTC)
    gateway = MarketDataGateway()
    gateway.update_tv_reference_quote({
        "ticker": "OANDA:XAUUSD",
        "source": "TRADINGVIEW_SCANNER_UNVERIFIED",
        "data_role": "REFERENCE_ONLY",
        "verified_for_execution": False,
        "price": 4300, "time_iso": now.isoformat(),
        "bid": 4290, "ask": 4310,
    })
    ref = gateway.get_comparison_payload(None, now=now)["layers"][0]
    assert ref["bid"] is None and ref["ask"] is None
    assert ref["spread"] is None and ref["mid"] == 4300
    assert "< 1" not in ref["latency_estimate"]
