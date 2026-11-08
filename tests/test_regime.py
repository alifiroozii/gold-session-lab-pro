from datetime import datetime, timezone

from goldlab.regime import MarketRegimeMonitor, MarketRegimeType
from goldlab.types import Candle

TZ_UTC = timezone.utc


def make_dummy_candles(n=30, trend=0.0, atr=1.5):
    candles = []
    base_price = 2650.0
    for i in range(n):
        p = base_price + (i * trend)
        c = Candle(
            timestamp=datetime(2026, 11, 8, 10, i, tzinfo=TZ_UTC),
            open=p,
            high=p + 1.0,
            low=p - 1.0,
            close=p + 0.2,
            volume=100.0,
            atr14=atr,
            wick_ratio=0.3,
        )
        candles.append(c)
    return candles


def test_regime_unclassified_on_small_sample():
    monitor = MarketRegimeMonitor()
    report = monitor.analyze_regime(candles=make_dummy_candles(n=5))
    assert report.primary_regime == MarketRegimeType.UNCLASSIFIED


def test_regime_news_blackout():
    monitor = MarketRegimeMonitor()
    report = monitor.analyze_regime(candles=make_dummy_candles(n=25), is_news_blackout=True)
    assert report.primary_regime == MarketRegimeType.NEWS_DRIVEN
    assert report.is_favorable_for_trading is False


def test_regime_high_spread():
    monitor = MarketRegimeMonitor()
    report = monitor.analyze_regime(candles=make_dummy_candles(n=25), current_spread=0.60)
    assert report.primary_regime == MarketRegimeType.HIGH_SPREAD
    assert report.is_favorable_for_trading is False


def test_regime_trending_detection():
    monitor = MarketRegimeMonitor()
    # Strong upward trend
    candles = make_dummy_candles(n=30, trend=2.0, atr=1.0)
    report = monitor.analyze_regime(candles=candles)
    assert report.primary_regime == MarketRegimeType.TRENDING
