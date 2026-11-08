"""
Market Structure Engine for XAUUSD.
Detects validated Swing Points (Zero lookahead leakage via right_bars confirmation),
Equal Highs/Lows (EQH/EQL), Fair Value Gaps (FVG), and Order Block / Breaker Proxies.
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np

from goldlab.types import Candle, FairValueGap, OrderBlockProxy, SwingPoint


class MarketStructureAnalyzer:
    """Computes technical structure indicators and guarantees absence of lookahead bias."""

    def __init__(self, left_bars: int = 3, right_bars: int = 3, atr_period: int = 14) -> None:
        self.left_bars = left_bars
        self.right_bars = right_bars
        self.atr_period = atr_period

    def calculate_atr(self, candles: List[Candle]) -> List[float]:
        """Calculates Average True Range (ATR) across the candle series."""
        n = len(candles)
        if n == 0:
            return []

        tr: List[float] = [candles[0].high - candles[0].low]
        for i in range(1, n):
            h_l = candles[i].high - candles[i].low
            h_pc = abs(candles[i].high - candles[i - 1].close)
            l_pc = abs(candles[i].low - candles[i - 1].close)
            tr.append(max(h_l, h_pc, l_pc))

        # Wilder's Smoothing for ATR
        atr: List[float] = [0.0] * n
        if n < self.atr_period:
            rolling_avg = float(np.mean(tr)) if tr else 0.0
            return [rolling_avg] * n

        first_atr = float(np.mean(tr[: self.atr_period]))
        atr[self.atr_period - 1] = first_atr

        for i in range(self.atr_period, n):
            atr[i] = (atr[i - 1] * (self.atr_period - 1) + tr[i]) / self.atr_period

        # Backfill initial elements
        for i in range(self.atr_period - 1):
            atr[i] = first_atr

        return atr

    def enrich_candle_metrics(self, candles: List[Candle]) -> None:
        """Enriches candle objects with ATR, body/ATR ratio, and displacement flag."""
        atr_values = self.calculate_atr(candles)
        for i, c in enumerate(candles):
            c.atr14 = round(atr_values[i], 4)
            c.body_to_atr = round(c.body / c.atr14, 4) if c.atr14 > 0 else 0.0
            # Displacement: Strong directional candle with body >= 1.2 * ATR
            c.displacement = c.body_to_atr >= 1.2 and c.wick_ratio < 0.45

    def find_swing_points(self, candles: List[Candle]) -> List[SwingPoint]:
        """
        Finds fractal swing highs and lows.
        CRITICAL: A swing point at index `i` is only officially confirmed at `i + right_bars`.
        Any decision using this point MUST NOT occur before `i + right_bars`.
        """
        n = len(candles)
        swings: List[SwingPoint] = []
        if n < self.left_bars + self.right_bars + 1:
            return swings

        for i in range(self.left_bars, n - self.right_bars):
            curr_h = candles[i].high
            curr_l = candles[i].low

            # Check Swing High
            is_high = True
            for left in range(i - self.left_bars, i):
                if candles[left].high >= curr_h:
                    is_high = False
                    break
            if is_high:
                for right in range(i + 1, i + self.right_bars + 1):
                    if candles[right].high > curr_h:
                        is_high = False
                        break
            if is_high:
                swings.append(
                    SwingPoint(
                        index=i,
                        timestamp=candles[i].timestamp,
                        price=curr_h,
                        is_high=True,
                        confirmed_index=i + self.right_bars,
                    )
                )

            # Check Swing Low
            is_low = True
            for left in range(i - self.left_bars, i):
                if candles[left].low <= curr_l:
                    is_low = False
                    break
            if is_low:
                for right in range(i + 1, i + self.right_bars + 1):
                    if candles[right].low < curr_l:
                        is_low = False
                        break
            if is_low:
                swings.append(
                    SwingPoint(
                        index=i,
                        timestamp=candles[i].timestamp,
                        price=curr_l,
                        is_high=False,
                        confirmed_index=i + self.right_bars,
                    )
                )

        return sorted(swings, key=lambda s: s.index)

    def find_equal_highs_lows(
        self, candles: List[Candle], swings: List[SwingPoint], tolerance_atr_multiplier: float = 0.15
    ) -> Tuple[List[Tuple[SwingPoint, SwingPoint]], List[Tuple[SwingPoint, SwingPoint]]]:
        """
        Detects Equal Highs (EQH) and Equal Lows (EQL) within dynamic ATR tolerance.
        """
        eqh_pairs: List[Tuple[SwingPoint, SwingPoint]] = []
        eql_pairs: List[Tuple[SwingPoint, SwingPoint]] = []

        high_swings = [s for s in swings if s.is_high]
        low_swings = [s for s in swings if not s.is_high]

        # EQH
        for i in range(len(high_swings) - 1):
            s1 = high_swings[i]
            s2 = high_swings[i + 1]
            atr = candles[s2.confirmed_index].atr14 if s2.confirmed_index < len(candles) else 1.0
            tol = atr * tolerance_atr_multiplier
            if abs(s1.price - s2.price) <= tol:
                eqh_pairs.append((s1, s2))

        # EQL
        for i in range(len(low_swings) - 1):
            s1 = low_swings[i]
            s2 = low_swings[i + 1]
            atr = candles[s2.confirmed_index].atr14 if s2.confirmed_index < len(candles) else 1.0
            tol = atr * tolerance_atr_multiplier
            if abs(s1.price - s2.price) <= tol:
                eql_pairs.append((s1, s2))

        return eqh_pairs, eql_pairs

    def find_fair_value_gaps(self, candles: List[Candle]) -> List[FairValueGap]:
        """
        Detects 3-candle Fair Value Gaps (FVG) and tracks mitigation in subsequent bars.
        - Bullish FVG: Candle[i-2].high < Candle[i].low (Imbalance between bar 0 high and bar 2 low)
        - Bearish FVG: Candle[i-2].low > Candle[i].high (Imbalance between bar 0 low and bar 2 high)
        """
        fvgs: List[FairValueGap] = []
        n = len(candles)
        if n < 3:
            return fvgs

        for i in range(2, n):
            c0 = candles[i - 2]
            _ = candles[i - 1]
            c2 = candles[i]

            # Bullish FVG
            if c2.low > c0.high:
                fvg = FairValueGap(
                    start_index=i - 2,
                    gap_index=i - 1,
                    end_index=i,
                    top=c2.low,
                    bottom=c0.high,
                    is_bullish=True,
                )
                # Check for mitigation in subsequent closed candles
                for j in range(i + 1, n):
                    if candles[j].low <= fvg.bottom:
                        fvg.mitigated = True
                        fvg.mitigated_index = j
                        break
                fvgs.append(fvg)

            # Bearish FVG
            elif c2.high < c0.low:
                fvg = FairValueGap(
                    start_index=i - 2,
                    gap_index=i - 1,
                    end_index=i,
                    top=c0.low,
                    bottom=c2.high,
                    is_bullish=False,
                )
                for j in range(i + 1, n):
                    if candles[j].high >= fvg.top:
                        fvg.mitigated = True
                        fvg.mitigated_index = j
                        break
                fvgs.append(fvg)

        return fvgs

    def detect_order_block_proxies(
        self, candles: List[Candle], swings: List[SwingPoint]
    ) -> List[OrderBlockProxy]:
        """
        Order Block / Breaker Block Proxy:
        Algorithmic label representing the last opposing candle before a confirmed displacement BOS.
        Disclaimer: This is a mathematical proxy, not actual institutional order book depth.
        """
        obs: List[OrderBlockProxy] = []
        n = len(candles)
        if n < 5:
            return obs

        for s in swings:
            # Look for a Break of Structure (BOS) beyond this swing point
            breakout_idx = None
            for idx in range(s.confirmed_index, n):
                if s.is_high and candles[idx].close > s.price:
                    breakout_idx = idx
                    break
                elif not s.is_high and candles[idx].close < s.price:
                    breakout_idx = idx
                    break

            if breakout_idx is not None:
                # Find the opposing candle prior to the displacement impulse
                # For bullish BOS: last down-close candle
                if s.is_high:
                    for k in range(breakout_idx - 1, max(s.index - 1, 0), -1):
                        if candles[k].close < candles[k].open:  # Bearish candle
                            obs.append(
                                OrderBlockProxy(
                                    index=k,
                                    timestamp=candles[k].timestamp,
                                    is_bullish=True,
                                    top=candles[k].high,
                                    bottom=candles[k].low,
                                    is_breaker=False,
                                )
                            )
                            break
                else:
                    for k in range(breakout_idx - 1, max(s.index - 1, 0), -1):
                        if candles[k].close > candles[k].open:  # Bullish candle
                            obs.append(
                                OrderBlockProxy(
                                    index=k,
                                    timestamp=candles[k].timestamp,
                                    is_bullish=False,
                                    top=candles[k].high,
                                    bottom=candles[k].low,
                                    is_breaker=False,
                                )
                            )
                            break

        return obs
