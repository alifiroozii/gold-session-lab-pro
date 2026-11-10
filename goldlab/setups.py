"""
Modular Trading Setups for XAUUSD Session Research Lab.
Every setup is an independent module with explicit mathematical rules,
zero lookahead leakage, and togglable activation.
All signals generate orders for execution on the NEXT candle open.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Union

from goldlab.market_structure import MarketStructureAnalyzer
from goldlab.sessions import SessionManager
from goldlab.types import (
    Candle,
    FairValueGap,
    OrderBlockProxy,
    SetupSignal,
    SignalDirection,
    SwingPoint,
)


@dataclass
class SetupConfig:
    enable_asia_breakout: bool = True
    enable_sweep_reclaim_bos: bool = True
    enable_liquidity_choch: bool = True
    enable_fvg_mitigation: bool = True
    enable_order_block_proxy: bool = True
    enable_candlestick_rejections: bool = True
    enable_trend_continuation: bool = True
    enable_combined_structural: bool = True
    enable_mtf_confluence: bool = False

    retest_tolerance_pips: float = 0.50  # Gold $0.50 tolerance
    min_wick_ratio: float = 0.35
    risk_reward_ratio: float = 2.0
    atr_sl_multiplier: float = 1.0


class SetupEngine:
    """Evaluates modular market structure setups across historical closed candles."""

    def __init__(
        self,
        config: Optional[SetupConfig] = None,
        structure: Optional[MarketStructureAnalyzer] = None,
        session_mgr: Optional[SessionManager] = None,
    ) -> None:
        self.config = config or SetupConfig()
        self.structure = structure or MarketStructureAnalyzer()
        self.session_mgr = session_mgr or SessionManager()

    def _get_stats_at(
        self, session_stats: Union[dict, List[dict]], idx: int
    ) -> dict:
        if isinstance(session_stats, list):
            if 0 <= idx < len(session_stats):
                return session_stats[idx]
            return session_stats[-1] if session_stats else {}
        return session_stats or {}

    def evaluate_all(
        self,
        candles: List[Candle],
        swings: List[SwingPoint],
        fvgs: List[FairValueGap],
        obs: List[OrderBlockProxy],
        session_stats: Union[dict, List[dict]],
        allow_pending: bool = False,
    ) -> List[SetupSignal]:
        """Runs all active setup detectors over the closed candle sequence.

        Returns a list of generated SetupSignal objects.
        """
        signals: List[SetupSignal] = []
        n = len(candles)
        if n < 8:
            return signals

        max_i = n if allow_pending else n - 1

        # 1. Asia Range Breakout + Retest
        if self.config.enable_asia_breakout:
            signals.extend(self._detect_asia_breakout(candles, session_stats, max_i))

        # 2. Sweep + Reclaim + BOS + Retest (Core Liquidity Reversal)
        if self.config.enable_sweep_reclaim_bos:
            signals.extend(self._detect_sweep_reclaim_bos_retest(candles, swings, session_stats, max_i))

        # 3. Liquidity Sweep + CHoCH
        if self.config.enable_liquidity_choch:
            signals.extend(self._detect_liquidity_choch(candles, swings, max_i))

        # 4. FVG Mitigation & Retest
        if self.config.enable_fvg_mitigation:
            signals.extend(self._detect_fvg_mitigation(candles, fvgs, max_i))

        # 5. Order Block Proxy Retest
        if self.config.enable_order_block_proxy:
            signals.extend(self._detect_order_block_retest(candles, obs, max_i))

        # 6. Candlestick Rejections (Pin Bar / Engulfing at Session Levels)
        if self.config.enable_candlestick_rejections:
            signals.extend(self._detect_candlestick_rejections(candles, session_stats, max_i))

        # 7. Trend Continuation Pullback
        if self.config.enable_trend_continuation:
            signals.extend(self._detect_trend_continuation(candles, swings, max_i))

        # 8. Combined Structural Model
        if self.config.enable_combined_structural:
            signals.extend(
                self._detect_combined_structural_model(candles, swings, fvgs, session_stats, max_i)
            )

        # Deduplicate signals by (setup_id, direction, signal_index, entry_index)
        unique_signals: Dict[tuple, SetupSignal] = {}
        for s in signals:
            key = (s.setup_id, s.direction.value, s.signal_index, s.entry_index)
            if key not in unique_signals:
                unique_signals[key] = s

        return sorted(unique_signals.values(), key=lambda s: s.signal_index)

    def _detect_asia_breakout(
        self, candles: List[Candle], session_stats: Union[dict, List[dict]], max_i: int
    ) -> List[SetupSignal]:
        """Setup 1: Asia Range Breakout + Close Acceptance + Retest."""
        signals: List[SetupSignal] = []
        n = len(candles)
        start_i = 14 if n > 14 else min(10, max(5, n // 2))

        # Look for breakout in recent bars followed by retest
        for i in range(start_i, max_i):
            c_curr = candles[i]
            c_prev = candles[i - 1]
            # The breakout candle must be judged against a finalized range
            # known before the breakout/retest, never the retest bar's own high.
            stats_i = self._get_stats_at(session_stats, i - 1)
            if not stats_i.get("asia_complete", True):
                continue
            asia = stats_i.get("asia", {})
            asia_high = asia.get("high")
            asia_low = asia.get("low")
            if asia_high is None or asia_low is None:
                continue

            # Bullish Breakout Acceptance and Retest of Asia High
            if c_prev.close > asia_high and c_curr.low <= (asia_high + self.config.retest_tolerance_pips):
                if c_curr.close > asia_high and c_curr.lower_wick >= c_curr.range * self.config.min_wick_ratio:
                    entry = candles[i + 1].open if i + 1 < n else c_curr.close
                    sl = round(c_curr.low - (c_curr.atr14 * self.config.atr_sl_multiplier), 4)
                    risk = entry - sl
                    if risk > 0:
                        tp = round(entry + (risk * self.config.risk_reward_ratio), 4)
                        signals.append(
                            SetupSignal(
                                setup_id="SETUP_1_ASIA_BO_RETEST",
                                setup_name="Asia Range Breakout + Retest",
                                direction=SignalDirection.BUY,
                                signal_index=i,
                                signal_time=c_curr.timestamp,
                                entry_index=i + 1,
                                entry_price=entry,
                                sl_price=sl,
                                tp_price=tp,
                                risk_r=round(risk, 4),
                                reason=f"Breakout above Asia High ({asia_high}) followed by retest wick rejection",
                                metrics={"asia_high": asia_high, "wick_ratio": c_curr.wick_ratio},
                            )
                        )

            # Bearish Breakdown Acceptance and Retest of Asia Low
            elif c_prev.close < asia_low and c_curr.high >= (asia_low - self.config.retest_tolerance_pips):
                if c_curr.close < asia_low and c_curr.upper_wick >= c_curr.range * self.config.min_wick_ratio:
                    entry = candles[i + 1].open if i + 1 < n else c_curr.close
                    sl = round(c_curr.high + (c_curr.atr14 * self.config.atr_sl_multiplier), 4)
                    risk = sl - entry
                    if risk > 0:
                        tp = round(entry - (risk * self.config.risk_reward_ratio), 4)
                        signals.append(
                            SetupSignal(
                                setup_id="SETUP_1_ASIA_BO_RETEST",
                                setup_name="Asia Range Breakout + Retest",
                                direction=SignalDirection.SELL,
                                signal_index=i,
                                signal_time=c_curr.timestamp,
                                entry_index=i + 1,
                                entry_price=entry,
                                sl_price=sl,
                                tp_price=tp,
                                risk_r=round(risk, 4),
                                reason=f"Breakdown below Asia Low ({asia_low}) followed by retest wick rejection",
                                metrics={"asia_low": asia_low, "wick_ratio": c_curr.wick_ratio},
                            )
                        )

        return signals

    def _detect_sweep_reclaim_bos_retest(
        self,
        candles: List[Candle],
        swings: List[SwingPoint],
        session_stats: Union[dict, List[dict]],
        max_i: int,
    ) -> List[SetupSignal]:
        """Setup 2: Sweep + Reclaim + BOS + Retest + Wick Rejection.

        Key liquidity level (PDH/PDL or Asia H/L) is swept, reclaimed, BOS occurs,
        and retest produces a wick rejection. Entry is STRICTLY on the next candle open.
        """
        signals: List[SetupSignal] = []
        n = len(candles)
        if n < 8:
            return signals

        start_i = min(14, 5)

        for i in range(start_i, max_i):
            c_retest = candles[i]
            c_bos = candles[i - 1]
            c_reclaim = candles[i - 2]
            c_sweep = candles[i - 3]

            # Freeze reference levels at the instant BEFORE the sweep candle.
            # Later session highs/lows must never redefine what was swept.
            stats_i = self._get_stats_at(session_stats, i - 4)
            levels = []
            if stats_i.get("pd", {}).get("high"):
                levels.append(("PDH", stats_i["pd"]["high"], True))
            if stats_i.get("pd", {}).get("low"):
                levels.append(("PDL", stats_i["pd"]["low"], False))
            if stats_i.get("asia_complete", True):
                if stats_i.get("asia", {}).get("high") is not None:
                    levels.append(("AsiaHigh", stats_i["asia"]["high"], True))
                if stats_i.get("asia", {}).get("low") is not None:
                    levels.append(("AsiaLow", stats_i["asia"]["low"], False))

            for level_name, level_val, is_high in levels:
                # Bullish Sweep + Reclaim of Low level
                if not is_high:
                    swept = c_sweep.low < level_val
                    reclaimed = c_reclaim.close > level_val
                    bos = c_bos.close > c_reclaim.high
                    retested = (
                        c_retest.low <= level_val + self.config.retest_tolerance_pips
                        and c_retest.close > level_val
                        and c_retest.lower_wick >= c_retest.range * self.config.min_wick_ratio
                    )

                    if swept and reclaimed and bos and retested:
                        entry = candles[i + 1].open if i + 1 < n else c_retest.close
                        sl = round(min(c_sweep.low, c_retest.low) - (c_retest.atr14 * 0.5), 4)
                        risk = entry - sl
                        if risk > 0:
                            tp = round(entry + (risk * self.config.risk_reward_ratio), 4)
                            signals.append(
                                SetupSignal(
                                    setup_id="SETUP_2_SWEEP_RECLAIM_BOS",
                                    setup_name="Sweep + Reclaim + BOS + Retest",
                                    direction=SignalDirection.BUY,
                                    signal_index=i,
                                    signal_time=c_retest.timestamp,
                                    entry_index=i + 1,
                                    entry_price=entry,
                                    sl_price=sl,
                                    tp_price=tp,
                                    risk_r=round(risk, 4),
                                    reason=f"Bullish sweep of {level_name} ({level_val}), reclaimed, BOS and retest confirmed",
                                    metrics={"level": level_name, "level_val": level_val},
                                )
                            )

                # Bearish Sweep + Reclaim of High level
                else:
                    swept = c_sweep.high > level_val
                    reclaimed = c_reclaim.close < level_val
                    bos = c_bos.close < c_reclaim.low
                    retested = (
                        c_retest.high >= level_val - self.config.retest_tolerance_pips
                        and c_retest.close < level_val
                        and c_retest.upper_wick >= c_retest.range * self.config.min_wick_ratio
                    )

                    if swept and reclaimed and bos and retested:
                        entry = candles[i + 1].open if i + 1 < n else c_retest.close
                        sl = round(max(c_sweep.high, c_retest.high) + (c_retest.atr14 * 0.5), 4)
                        risk = sl - entry
                        if risk > 0:
                            tp = round(entry - (risk * self.config.risk_reward_ratio), 4)
                            signals.append(
                                SetupSignal(
                                    setup_id="SETUP_2_SWEEP_RECLAIM_BOS",
                                    setup_name="Sweep + Reclaim + BOS + Retest",
                                    direction=SignalDirection.SELL,
                                    signal_index=i,
                                    signal_time=c_retest.timestamp,
                                    entry_index=i + 1,
                                    entry_price=entry,
                                    sl_price=sl,
                                    tp_price=tp,
                                    risk_r=round(risk, 4),
                                    reason=f"Bearish sweep of {level_name} ({level_val}), reclaimed, BOS and retest confirmed",
                                    metrics={"level": level_name, "level_val": level_val},
                                )
                            )

        return signals

    def _detect_liquidity_choch(
        self, candles: List[Candle], swings: List[SwingPoint], max_i: int
    ) -> List[SetupSignal]:
        """Setup 3: Liquidity sweep + CHoCH with confirmed swing pivots (only after right_bars)."""
        signals: List[SetupSignal] = []
        n = len(candles)

        for s in swings:
            # Must be strictly past confirmation index to prevent lookahead
            start_i = max(14, s.confirmed_index + 1)
            for i in range(start_i, max_i):
                c = candles[i]
                if s.is_high and c.close > s.price:
                    # Bullish CHoCH: closed above confirmed swing high
                    entry = candles[i + 1].open if i + 1 < n else c.close
                    sl = round(candles[i].low - candles[i].atr14, 4)
                    risk = entry - sl
                    if risk > 0:
                        signals.append(
                            SetupSignal(
                                setup_id="SETUP_3_LIQ_CHOCH",
                                setup_name="Liquidity Sweep + CHoCH",
                                direction=SignalDirection.BUY,
                                signal_index=i,
                                signal_time=c.timestamp,
                                entry_index=i + 1,
                                entry_price=entry,
                                sl_price=sl,
                                tp_price=round(entry + (risk * self.config.risk_reward_ratio), 4),
                                risk_r=round(risk, 4),
                                reason=f"Bullish CHoCH above confirmed swing high at {s.price}",
                            )
                        )
                    break
                elif not s.is_high and c.close < s.price:
                    # Bearish CHoCH: closed below confirmed swing low
                    entry = candles[i + 1].open if i + 1 < n else c.close
                    sl = round(candles[i].high + candles[i].atr14, 4)
                    risk = sl - entry
                    if risk > 0:
                        signals.append(
                            SetupSignal(
                                setup_id="SETUP_3_LIQ_CHOCH",
                                setup_name="Liquidity Sweep + CHoCH",
                                direction=SignalDirection.SELL,
                                signal_index=i,
                                signal_time=c.timestamp,
                                entry_index=i + 1,
                                entry_price=entry,
                                sl_price=sl,
                                tp_price=round(entry - (risk * self.config.risk_reward_ratio), 4),
                                risk_r=round(risk, 4),
                                reason=f"Bearish CHoCH below confirmed swing low at {s.price}",
                            )
                        )
                    break

        return signals

    def _detect_fvg_mitigation(
        self, candles: List[Candle], fvgs: List[FairValueGap], max_i: int
    ) -> List[SetupSignal]:
        """Setup 4: FVG 3-candle sequence, mitigation area retest."""
        signals: List[SetupSignal] = []
        n = len(candles)

        for fvg in fvgs:
            # Check bars after the FVG is fully formed (fvg.end_index + 1 onwards)
            start_i = max(14, fvg.end_index + 1)
            for i in range(start_i, min(fvg.end_index + 15, max_i)):
                c = candles[i]
                if fvg.is_bullish:
                    # Retest into bullish FVG
                    if c.low <= fvg.top and c.low >= fvg.bottom and c.close > fvg.bottom:
                        entry = candles[i + 1].open if i + 1 < n else c.close
                        sl = round(fvg.bottom - (c.atr14 * 0.5), 4)
                        risk = entry - sl
                        if risk > 0:
                            signals.append(
                                SetupSignal(
                                    setup_id="SETUP_4_FVG_RETEST",
                                    setup_name="Fair Value Gap Mitigation",
                                    direction=SignalDirection.BUY,
                                    signal_index=i,
                                    signal_time=c.timestamp,
                                    entry_index=i + 1,
                                    entry_price=entry,
                                    sl_price=sl,
                                    tp_price=round(entry + (risk * self.config.risk_reward_ratio), 4),
                                    risk_r=round(risk, 4),
                                    reason=f"Bullish FVG tap and reaction between {fvg.bottom} and {fvg.top}",
                                )
                            )
                            break
                else:
                    # Retest into bearish FVG
                    if c.high >= fvg.bottom and c.high <= fvg.top and c.close < fvg.top:
                        entry = candles[i + 1].open if i + 1 < n else c.close
                        sl = round(fvg.top + (c.atr14 * 0.5), 4)
                        risk = sl - entry
                        if risk > 0:
                            signals.append(
                                SetupSignal(
                                    setup_id="SETUP_4_FVG_RETEST",
                                    setup_name="Fair Value Gap Mitigation",
                                    direction=SignalDirection.SELL,
                                    signal_index=i,
                                    signal_time=c.timestamp,
                                    entry_index=i + 1,
                                    entry_price=entry,
                                    sl_price=sl,
                                    tp_price=round(entry - (risk * self.config.risk_reward_ratio), 4),
                                    risk_r=round(risk, 4),
                                    reason=f"Bearish FVG tap and reaction between {fvg.bottom} and {fvg.top}",
                                )
                            )
                            break

        return signals

    def _detect_order_block_retest(
        self, candles: List[Candle], obs: List[OrderBlockProxy], max_i: int
    ) -> List[SetupSignal]:
        """Setup 5: Order block proxy and breaker block proxy retest."""
        signals: List[SetupSignal] = []
        n = len(candles)

        for ob in obs:
            start_i = max(14, ob.index + 3)
            for i in range(start_i, min(ob.index + 25, max_i)):
                c = candles[i]
                if ob.is_bullish:
                    # Retest into Bullish OB top
                    if c.low <= ob.top and c.close >= ob.bottom:
                        entry = candles[i + 1].open if i + 1 < n else c.close
                        sl = round(ob.bottom - (c.atr14 * 0.5), 4)
                        risk = entry - sl
                        if risk > 0:
                            signals.append(
                                SetupSignal(
                                    setup_id="SETUP_5_OB_PROXY",
                                    setup_name="Order Block Proxy Retest",
                                    direction=SignalDirection.BUY,
                                    signal_index=i,
                                    signal_time=c.timestamp,
                                    entry_index=i + 1,
                                    entry_price=entry,
                                    sl_price=sl,
                                    tp_price=round(entry + (risk * self.config.risk_reward_ratio), 4),
                                    risk_r=round(risk, 4),
                                    reason=f"Bullish Order Block Proxy tap ({ob.bottom}-{ob.top})",
                                )
                            )
                            break
                else:
                    if c.high >= ob.bottom and c.close <= ob.top:
                        entry = candles[i + 1].open if i + 1 < n else c.close
                        sl = round(ob.top + (c.atr14 * 0.5), 4)
                        risk = sl - entry
                        if risk > 0:
                            signals.append(
                                SetupSignal(
                                    setup_id="SETUP_5_OB_PROXY",
                                    setup_name="Order Block Proxy Retest",
                                    direction=SignalDirection.SELL,
                                    signal_index=i,
                                    signal_time=c.timestamp,
                                    entry_index=i + 1,
                                    entry_price=entry,
                                    sl_price=sl,
                                    tp_price=round(entry - (risk * self.config.risk_reward_ratio), 4),
                                    risk_r=round(risk, 4),
                                    reason=f"Bearish Order Block Proxy tap ({ob.bottom}-{ob.top})",
                                )
                            )
                            break

        return signals

    def _detect_candlestick_rejections(
        self, candles: List[Candle], session_stats: Union[dict, List[dict]], max_i: int
    ) -> List[SetupSignal]:
        """Setup 6: Failed breakout, bull/bear trap, engulfing, pin bar, doji, inside bar,

        and high/low wick rejection at key levels.
        """
        signals: List[SetupSignal] = []
        n = len(candles)
        start_i = 14 if n > 14 else 1

        for i in range(start_i, max_i):
            c = candles[i]
            # Pin bar with >= 60% wick
            is_bull_pin = c.lower_wick >= c.range * 0.60 and c.range > 0
            is_bear_pin = c.upper_wick >= c.range * 0.60 and c.range > 0

            if is_bull_pin:
                entry = candles[i + 1].open if i + 1 < n else c.close
                sl = round(c.low - (c.atr14 * 0.5), 4)
                risk = entry - sl
                if risk > 0:
                    signals.append(
                        SetupSignal(
                            setup_id="SETUP_6_CANDLE_REJECTION",
                            setup_name="Candle Wick Rejection (Pin Bar)",
                            direction=SignalDirection.BUY,
                            signal_index=i,
                            signal_time=c.timestamp,
                            entry_index=i + 1,
                            entry_price=entry,
                            sl_price=sl,
                            tp_price=round(entry + (risk * self.config.risk_reward_ratio), 4),
                            risk_r=round(risk, 4),
                            reason="Bullish Pin Bar with strong lower wick rejection",
                        )
                    )
            elif is_bear_pin:
                entry = candles[i + 1].open if i + 1 < n else c.close
                sl = round(c.high + (c.atr14 * 0.5), 4)
                risk = sl - entry
                if risk > 0:
                    signals.append(
                        SetupSignal(
                            setup_id="SETUP_6_CANDLE_REJECTION",
                            setup_name="Candle Wick Rejection (Pin Bar)",
                            direction=SignalDirection.SELL,
                            signal_index=i,
                            signal_time=c.timestamp,
                            entry_index=i + 1,
                            entry_price=entry,
                            sl_price=sl,
                            tp_price=round(entry - (risk * self.config.risk_reward_ratio), 4),
                            risk_r=round(risk, 4),
                            reason="Bearish Pin Bar with strong upper wick rejection",
                        )
                    )

        return signals

    def _detect_trend_continuation(
        self, candles: List[Candle], swings: List[SwingPoint], max_i: int
    ) -> List[SetupSignal]:
        """Setup 7: Trend continuation and pullback to BOS/level with displacement filter."""
        signals: List[SetupSignal] = []
        n = len(candles)
        start_i = min(14, 5)

        for i in range(start_i, max_i):
            c_curr = candles[i]
            c_prev = candles[i - 1]

            # Strong displacement candle followed by shallow pullback
            if c_prev.displacement and c_prev.close > c_prev.open:  # Bullish impulse
                # Shallow pullback holding upper half of previous bar
                half_level = (c_prev.open + c_prev.close) / 2.0
                if c_curr.low >= half_level and c_curr.close > half_level:
                    entry = candles[i + 1].open if i + 1 < n else c_curr.close
                    sl = round(c_prev.low, 4)
                    risk = entry - sl
                    if risk > 0:
                        signals.append(
                            SetupSignal(
                                setup_id="SETUP_7_TREND_CONTINUATION",
                                setup_name="Trend Continuation Pullback",
                                direction=SignalDirection.BUY,
                                signal_index=i,
                                signal_time=c_curr.timestamp,
                                entry_index=i + 1,
                                entry_price=entry,
                                sl_price=sl,
                                tp_price=round(entry + (risk * self.config.risk_reward_ratio), 4),
                                risk_r=round(risk, 4),
                                reason="Bullish displacement followed by high-level consolidation pullback",
                            )
                        )
            elif c_prev.displacement and c_prev.close < c_prev.open:  # Bearish impulse
                # Shallow pullback holding lower half of previous bar
                half_level = (c_prev.open + c_prev.close) / 2.0
                if c_curr.high <= half_level and c_curr.close < half_level:
                    entry = candles[i + 1].open if i + 1 < n else c_curr.close
                    sl = round(c_prev.high, 4)
                    risk = sl - entry
                    if risk > 0:
                        signals.append(
                            SetupSignal(
                                setup_id="SETUP_7_TREND_CONTINUATION",
                                setup_name="Trend Continuation Pullback",
                                direction=SignalDirection.SELL,
                                signal_index=i,
                                signal_time=c_curr.timestamp,
                                entry_index=i + 1,
                                entry_price=entry,
                                sl_price=sl,
                                tp_price=round(entry - (risk * self.config.risk_reward_ratio), 4),
                                risk_r=round(risk, 4),
                                reason="Bearish displacement followed by shallow consolidation pullback",
                            )
                        )

        return signals

    def _detect_combined_structural_model(
        self,
        candles: List[Candle],
        swings: List[SwingPoint],
        fvgs: List[FairValueGap],
        session_stats: Union[dict, List[dict]],
        max_i: int,
    ) -> List[SetupSignal]:
        """Setup 8: Combined Structural Model (Liquidity Sweep + BOS + FVG + Retest).

        Synergistic confluence of:
        1. Liquidity sweep of key level (Asia H/L or PDH/PDL)
        2. Break of Structure (BOS)
        3. FVG retest / mitigation
        4. Causal execution strictly on following candle open (t+1).
        """
        signals: List[SetupSignal] = []
        n = len(candles)
        if n < 8:
            return signals

        start_i = max(14, 6)

        for i in range(start_i, max_i):
            c_curr = candles[i]
            c_prev = candles[i - 1]
            stats_i = self._get_stats_at(session_stats, i)

            # Check key levels
            levels = []
            if stats_i.get("asia", {}).get("high"):
                levels.append(("AsiaHigh", stats_i["asia"]["high"], True))
            if stats_i.get("asia", {}).get("low"):
                levels.append(("AsiaLow", stats_i["asia"]["low"], False))
            if stats_i.get("pd", {}).get("high"):
                levels.append(("PDH", stats_i["pd"]["high"], True))
            if stats_i.get("pd", {}).get("low"):
                levels.append(("PDL", stats_i["pd"]["low"], False))

            for lvl_name, lvl_val, is_high in levels:
                if not is_high:
                    # Bullish Confluence: Swept low in recent bars, reclaimed, and now retesting with rejection
                    sweep_window = candles[max(0, i - 5):i - 1]
                    if not sweep_window:
                        continue
                    swept = any(c.low < lvl_val for c in sweep_window)
                    reclaimed = c_prev.close > lvl_val
                    if (
                        swept
                        and reclaimed
                        and c_curr.close > lvl_val
                        and c_curr.lower_wick >= c_curr.range * self.config.min_wick_ratio
                    ):
                        entry = candles[i + 1].open if i + 1 < n else c_curr.close
                        sl = round(min(c.low for c in sweep_window) - (c_curr.atr14 * 0.5), 4)
                        risk = entry - sl
                        if risk > 0:
                            tp = round(entry + (risk * self.config.risk_reward_ratio), 4)
                            signals.append(
                                SetupSignal(
                                    setup_id="SETUP_8_COMBINED_STRUCTURAL",
                                    setup_name="Combined Structural Model",
                                    direction=SignalDirection.BUY,
                                    signal_index=i,
                                    signal_time=c_curr.timestamp,
                                    entry_index=i + 1,
                                    entry_price=entry,
                                    sl_price=sl,
                                    tp_price=tp,
                                    risk_r=round(risk, 4),
                                    reason=f"Bullish combined structural confluence: sweep of {lvl_name} ({lvl_val}), reclaim & wick rejection",
                                    metrics={"level": lvl_name, "level_val": lvl_val},
                                )
                            )
                else:
                    # Bearish Confluence: Swept high in recent bars, reclaimed below, and now retesting with rejection
                    sweep_window = candles[max(0, i - 5):i - 1]
                    if not sweep_window:
                        continue
                    swept = any(c.high > lvl_val for c in sweep_window)
                    reclaimed = c_prev.close < lvl_val
                    if (
                        swept
                        and reclaimed
                        and c_curr.close < lvl_val
                        and c_curr.upper_wick >= c_curr.range * self.config.min_wick_ratio
                    ):
                        entry = candles[i + 1].open if i + 1 < n else c_curr.close
                        sl = round(max(c.high for c in sweep_window) + (c_curr.atr14 * 0.5), 4)
                        risk = sl - entry
                        if risk > 0:
                            tp = round(entry - (risk * self.config.risk_reward_ratio), 4)
                            signals.append(
                                SetupSignal(
                                    setup_id="SETUP_8_COMBINED_STRUCTURAL",
                                    setup_name="Combined Structural Model",
                                    direction=SignalDirection.SELL,
                                    signal_index=i,
                                    signal_time=c_curr.timestamp,
                                    entry_index=i + 1,
                                    entry_price=entry,
                                    sl_price=sl,
                                    tp_price=tp,
                                    risk_r=round(risk, 4),
                                    reason=f"Bearish combined structural confluence: sweep of {lvl_name} ({lvl_val}), reclaim & wick rejection",
                                    metrics={"level": lvl_name, "level_val": lvl_val},
                                )
                            )

        return signals
