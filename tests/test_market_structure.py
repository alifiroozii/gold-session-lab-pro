"""
Unit tests for Market Structure Engine: swing pivots, zero-leakage right_bars,
Equal Highs/Lows (EQH/EQL), and Fair Value Gaps (FVG).
"""

from datetime import datetime, timedelta, timezone

from goldlab.market_structure import MarketStructureAnalyzer
from goldlab.types import Candle

TZ_UTC = timezone.utc


def test_swing_points_confirmation_zero_lookahead() -> None:
    analyzer = MarketStructureAnalyzer(left_bars=2, right_bars=2)
    start_t = datetime(2026, 11, 2, 8, 0, tzinfo=TZ_UTC)

    # 5 candles with high at index 2 (price 2660.0)
    prices = [2650.0, 2655.0, 2660.0, 2654.0, 2652.0]
    candles = [
        Candle(
            timestamp=start_t + timedelta(minutes=i * 5),
            open=p - 1.0,
            high=p,
            low=p - 2.0,
            close=p - 0.5,
            is_closed=True,
        )
        for i, p in enumerate(prices)
    ]

    swings = analyzer.find_swing_points(candles)
    assert len(swings) == 1
    s = swings[0]
    assert s.is_high is True
    assert s.index == 2
    assert s.price == 2660.0
    # Crucial guarantee: Swing at index 2 is ONLY confirmed at index 4 (2 + right_bars)
    assert s.confirmed_index == 4


def test_fair_value_gap_detection_and_mitigation() -> None:
    analyzer = MarketStructureAnalyzer()
    start_t = datetime(2026, 11, 2, 9, 0, tzinfo=TZ_UTC)

    # 4 candles creating Bullish FVG between candle 0 high and candle 2 low
    # Candle 0: H=2650.0
    # Candle 1: Strong impulse bar (O=2649.0, H=2665.0, L=2649.0, C=2664.0)
    # Candle 2: L=2654.0 -> Gap between 2650.0 and 2654.0 ($4.0 FVG)
    # Candle 3: Retests into gap (L=2652.0) -> Mitigated!
    candles = [
        Candle(timestamp=start_t, open=2648.0, high=2650.0, low=2647.0, close=2649.0),
        Candle(timestamp=start_t + timedelta(minutes=5), open=2649.0, high=2665.0, low=2649.0, close=2664.0),
        Candle(timestamp=start_t + timedelta(minutes=10), open=2664.0, high=2670.0, low=2654.0, close=2668.0),
        Candle(timestamp=start_t + timedelta(minutes=15), open=2668.0, high=2669.0, low=2650.0, close=2660.0),
    ]

    fvgs = analyzer.find_fair_value_gaps(candles)
    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg.is_bullish is True
    assert fvg.bottom == 2650.0
    assert fvg.top == 2654.0
    assert fvg.mitigated is True
    assert fvg.mitigated_index == 3
