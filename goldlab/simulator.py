"""
Execution Simulator and Risk Engine for XAUUSD.
Strictly decoupled from signal generation.
- Decision taken on closed candle index i.
- Entry executed strictly on candle index i + 1 OPEN.
- Conservative resolution: If both TP and SL are touched in the same candle,
  the simulator resolves to the WORST CASE (Stop Loss hit).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from goldlab.types import (
    Candle,
    SetupSignal,
    SignalDirection,
    TradeOrder,
    TradeOutcome,
)


@dataclass
class SimulatorConfig:
    spread_pips: float = 0.25  # Typical gold spread $0.25
    slippage_pips: float = 0.10  # Conservative execution slippage $0.10
    commission_per_lot: float = 5.0  # $5 round turn per standard lot
    contract_size: float = 100.0  # 100 oz per standard lot
    lot_size: float = 0.10  # 10 oz mini-lot
    conservative_dual_touch: bool = True  # Always assume worst-case (SL) if both touched


class ExecutionSimulator:
    """Simulates realistic execution without lookahead leakage."""

    def __init__(self, config: Optional[SimulatorConfig] = None) -> None:
        self.config = config or SimulatorConfig()

    def run_simulation(
        self, candles: List[Candle], signals: List[SetupSignal]
    ) -> List[TradeOrder]:
        """
        Simulates execution of generated signals across the historical candle series.
        """
        trades: List[TradeOrder] = []
        n = len(candles)
        if n == 0 or not signals:
            return trades

        # Track active trade index to avoid multiple overlapping entries if desired
        for sig in signals:
            entry_idx = sig.entry_index
            if entry_idx >= n:
                continue  # Cannot enter beyond available data

            entry_candle = candles[entry_idx]
            # Entry at open + slippage / spread adjustment
            if sig.direction == SignalDirection.BUY:
                actual_entry = entry_candle.open + (self.config.spread_pips + self.config.slippage_pips)
            else:
                actual_entry = entry_candle.open - (self.config.spread_pips + self.config.slippage_pips)

            trade = TradeOrder(
                trade_id=f"TRD_{entry_idx}_{sig.setup_id}",
                setup_id=sig.setup_id,
                direction=sig.direction,
                entry_index=entry_idx,
                entry_time=entry_candle.timestamp,
                entry_price=round(actual_entry, 4),
                sl_price=sig.sl_price,
                tp_price=sig.tp_price,
            )

            # Step through subsequent candles to evaluate outcome
            initial_risk = abs(actual_entry - sig.sl_price)
            if initial_risk <= 0:
                continue  # Invalid risk profile

            max_adverse = 0.0
            max_favorable = 0.0

            for bar_idx in range(entry_idx, n):
                bar = candles[bar_idx]
                trade.bars_in_trade += 1

                if trade.direction == SignalDirection.BUY:
                    # Excursion tracking
                    adverse = actual_entry - bar.low
                    favorable = bar.high - actual_entry
                    max_adverse = max(max_adverse, adverse)
                    max_favorable = max(max_favorable, favorable)

                    sl_hit = bar.low <= trade.sl_price
                    tp_hit = bar.high >= trade.tp_price

                    if sl_hit and tp_hit:
                        # Dual touch: Enforce worst-case conservative rule
                        trade.exit_index = bar_idx
                        trade.exit_time = bar.timestamp
                        trade.exit_price = trade.sl_price
                        trade.outcome = TradeOutcome.LOSS
                        trade.realized_r = -1.0
                        trade.exit_reason = "WORST_CASE_DUAL_TOUCH_SL"
                        break
                    elif sl_hit:
                        trade.exit_index = bar_idx
                        trade.exit_time = bar.timestamp
                        trade.exit_price = trade.sl_price
                        trade.outcome = TradeOutcome.LOSS
                        trade.realized_r = -1.0
                        trade.exit_reason = "STOP_LOSS_HIT"
                        break
                    elif tp_hit:
                        trade.exit_index = bar_idx
                        trade.exit_time = bar.timestamp
                        trade.exit_price = trade.tp_price
                        trade.outcome = TradeOutcome.WIN
                        trade.realized_r = round((trade.tp_price - actual_entry) / initial_risk, 2)
                        trade.exit_reason = "TAKE_PROFIT_HIT"
                        break

                else:  # SELL
                    adverse = bar.high - actual_entry
                    favorable = actual_entry - bar.low
                    max_adverse = max(max_adverse, adverse)
                    max_favorable = max(max_favorable, favorable)

                    sl_hit = bar.high >= trade.sl_price
                    tp_hit = bar.low <= trade.tp_price

                    if sl_hit and tp_hit:
                        trade.exit_index = bar_idx
                        trade.exit_time = bar.timestamp
                        trade.exit_price = trade.sl_price
                        trade.outcome = TradeOutcome.LOSS
                        trade.realized_r = -1.0
                        trade.exit_reason = "WORST_CASE_DUAL_TOUCH_SL"
                        break
                    elif sl_hit:
                        trade.exit_index = bar_idx
                        trade.exit_time = bar.timestamp
                        trade.exit_price = trade.sl_price
                        trade.outcome = TradeOutcome.LOSS
                        trade.realized_r = -1.0
                        trade.exit_reason = "STOP_LOSS_HIT"
                        break
                    elif tp_hit:
                        trade.exit_index = bar_idx
                        trade.exit_time = bar.timestamp
                        trade.exit_price = trade.tp_price
                        trade.outcome = TradeOutcome.WIN
                        trade.realized_r = round((actual_entry - trade.tp_price) / initial_risk, 2)
                        trade.exit_reason = "TAKE_PROFIT_HIT"
                        break

            trade.mae_pips = round(max_adverse, 2)
            trade.mfe_pips = round(max_favorable, 2)
            trades.append(trade)

        return trades
