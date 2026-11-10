"""
Market Regime Monitor for XAUUSD.
Quantifies market volatility regimes, trend state, spread stress, and false breakout prevalence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import numpy as np

from goldlab.types import Candle


class MarketRegimeType(str, Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    HIGH_SPREAD = "HIGH_SPREAD"
    NEWS_DRIVEN = "NEWS_DRIVEN"
    DATA_UNRELIABLE = "DATA_UNRELIABLE"
    UNCLASSIFIED = "UNCLASSIFIED"


@dataclass
class MarketRegimeReport:
    primary_regime: MarketRegimeType
    secondary_regime: Optional[MarketRegimeType]
    atr_current: float
    atr_baseline: float
    volatility_ratio: float  # atr_current / atr_baseline
    adx_trend_slope: float
    false_breakout_rate: float
    current_spread: float
    is_favorable_for_trading: bool
    description: str


class MarketRegimeMonitor:
    """Classifies current market behavior to prevent trading strategies in hostile regimes."""

    def __init__(self, baseline_lookback: int = 50) -> None:
        self.baseline_lookback = baseline_lookback

    def analyze_regime(
        self,
        candles: List[Candle],
        current_spread: float = 0.25,
        is_news_blackout: bool = False,
    ) -> MarketRegimeReport:
        n = len(candles)
        if n < 15:
            return MarketRegimeReport(
                primary_regime=MarketRegimeType.UNCLASSIFIED,
                secondary_regime=None,
                atr_current=1.0,
                atr_baseline=1.0,
                volatility_ratio=1.0,
                adx_trend_slope=0.0,
                false_breakout_rate=0.0,
                current_spread=current_spread,
                is_favorable_for_trading=True,
                description="حجم نمونه اندک برای تعیین رژیم نوسانی",
            )

        # 1. Volatility Ratio
        atrs = [c.atr14 for c in candles if c.atr14 > 0]
        curr_atr = candles[-1].atr14 if candles[-1].atr14 > 0 else 1.0
        baseline_atr = float(np.mean(atrs[-self.baseline_lookback :])) if atrs else curr_atr
        vol_ratio = round(curr_atr / baseline_atr, 2) if baseline_atr > 0 else 1.0

        # 2. Trend Slope (Linear regression over last 20 close prices)
        recent_closes = [c.close for c in candles[-20:]]
        x = np.arange(len(recent_closes))
        slope, _ = np.polyfit(x, recent_closes, 1)
        normalized_slope = round(float(slope / curr_atr), 3) if curr_atr > 0 else 0.0

        # 3. False Breakout Rate
        # Measures fraction of bars with long wicks relative to body
        wick_dominant_bars = sum(1 for c in candles[-20:] if c.wick_ratio >= 0.40)
        false_breakout_rate = round(wick_dominant_bars / 20.0, 2)

        # 4. Regime Determination
        if is_news_blackout:
            primary = MarketRegimeType.NEWS_DRIVEN
            desc = "رژیم خبری پرنوسان ناشی از انتشار آمار کلان اقتصادی"
            favorable = False
        elif current_spread > 0.45:
            primary = MarketRegimeType.HIGH_SPREAD
            desc = f"اسپرد غیرعادی و بالاتر از میانگین (${current_spread:.2f})"
            favorable = False
        elif vol_ratio >= 1.6:
            primary = MarketRegimeType.HIGH_VOLATILITY
            desc = f"نوسان شدید بازار طلا (ATR نسبت به میانگین: {vol_ratio}x)"
            favorable = True
        elif vol_ratio <= 0.65:
            primary = MarketRegimeType.LOW_VOLATILITY
            desc = "فشردگی نوسانات و رکود حرکتی قیمت"
            favorable = False
        elif abs(normalized_slope) >= 0.40:
            primary = MarketRegimeType.TRENDING
            desc = f"روند جهت‌دار قدرتمند ({'صعودی' if slope > 0 else 'نزولی'})"
            favorable = True
        else:
            primary = MarketRegimeType.RANGING
            desc = "نوسان افقی در محدوده رنج و مستعد شکار نقدینگی"
            favorable = True

        secondary = None
        if primary != MarketRegimeType.RANGING and false_breakout_rate >= 0.50:
            secondary = MarketRegimeType.RANGING

        return MarketRegimeReport(
            primary_regime=primary,
            secondary_regime=secondary,
            atr_current=round(curr_atr, 2),
            atr_baseline=round(baseline_atr, 2),
            volatility_ratio=vol_ratio,
            adx_trend_slope=normalized_slope,
            false_breakout_rate=false_breakout_rate,
            current_spread=round(current_spread, 2),
            is_favorable_for_trading=favorable,
            description=desc,
        )
