"""
Advanced Event-Driven Backtesting and Strategy Comparison Engine for XAUUSD.
Features:
- Walk-Forward & Temporal Out-of-Sample validation
- Side-by-side comparative matrix of 8 independent market structure strategies
- Parameter stability & sensitivity heatmaps (Wick ratio vs ATR buffer)
- Cost modeling: spread, slippage, and commissions
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from goldlab.engine import ResearchEngine
from goldlab.setups import SetupConfig
from goldlab.simulator import SimulatorConfig
from goldlab.types import BacktestSummary, Candle


@dataclass
class StrategyComparisonItem:
    strategy_id: str
    strategy_name: str
    total_trades: int
    win_rate_pct: float
    profit_factor: float
    expectancy_r: float
    max_drawdown_r: float
    evidence_status: str  # "SUFFICIENT_EVIDENCE" / "INSUFFICIENT_EVIDENCE"


class BacktestingEngine:
    """Orchestrates comprehensive multi-strategy backtesting, OOS validation, and comparison."""

    def __init__(self, db_path: str = "data/xauusd_lab.sqlite") -> None:
        self.db_path = db_path

    def run_strategy_comparison(
        self, candles: List[Candle], sim_config: Optional[SimulatorConfig] = None
    ) -> List[StrategyComparisonItem]:
        """
        Runs and compares all 8 strategies independently on the identical candle dataset.
        """
        strategies = [
            ("S1", "S1 — Asia Range Breakout", {"enable_asia_breakout": True}),
            ("S2", "S2 — Sweep + Reclaim + BOS + Retest", {"enable_sweep_reclaim_bos": True}),
            ("S3", "S3 — Liquidity Sweep + CHoCH", {"enable_liquidity_choch": True}),
            ("S4", "S4 — Fair Value Gap Mitigation", {"enable_fvg_mitigation": True}),
            ("S5", "S5 — Order Block Proxy Retest", {"enable_order_block_proxy": True}),
            ("S6", "S6 — Candlestick Wick Rejection", {"enable_candlestick_rejections": True}),
            ("S7", "S7 — Trend Continuation Pullback", {"enable_trend_continuation": True}),
            ("S8", "S8 — Combined Structural Model", {
                "enable_asia_breakout": True,
                "enable_sweep_reclaim_bos": True,
                "enable_liquidity_choch": True,
                "enable_fvg_mitigation": True,
                "enable_order_block_proxy": True,
            }),
        ]

        comparison_results: List[StrategyComparisonItem] = []

        for strat_id, strat_name, flags in strategies:
            # Build exclusive config where only this strategy is enabled
            cfg_kwargs = {
                "enable_asia_breakout": False,
                "enable_sweep_reclaim_bos": False,
                "enable_liquidity_choch": False,
                "enable_fvg_mitigation": False,
                "enable_order_block_proxy": False,
                "enable_candlestick_rejections": False,
                "enable_trend_continuation": False,
            }
            cfg_kwargs.update(flags)
            setup_cfg = SetupConfig(**cfg_kwargs)

            engine = ResearchEngine(setup_config=setup_cfg, db_path=self.db_path)
            if sim_config:
                engine.simulator.config = sim_config

            engine.load_candles(candles, timeframe="5m")
            summary = engine.run_pipeline()

            evidence = "SUFFICIENT_EVIDENCE" if summary.total_trades >= 30 else "INSUFFICIENT_EVIDENCE (حجم نمونه اندک)"

            comparison_results.append(
                StrategyComparisonItem(
                    strategy_id=strat_id,
                    strategy_name=strat_name,
                    total_trades=summary.total_trades,
                    win_rate_pct=summary.win_rate_pct,
                    profit_factor=summary.profit_factor,
                    expectancy_r=summary.expectancy_r,
                    max_drawdown_r=summary.max_drawdown_r,
                    evidence_status=evidence,
                )
            )

        return comparison_results

    def run_walk_forward_splits(
        self, candles: List[Candle], train_ratio: float = 0.60, val_ratio: float = 0.20
    ) -> Dict[str, BacktestSummary]:
        """
        Splits dataset temporally into Train (In-Sample), Validation, and Test (Out-of-Sample).
        Strict chronological splitting without random shuffling.
        """
        n = len(candles)
        if n < 50:
            return {}

        train_end = int(n * train_ratio)
        val_end = int(n * (train_ratio + val_ratio))

        train_candles = candles[:train_end]
        val_candles = candles[train_end:val_end]
        test_candles = candles[val_end:]

        engine = ResearchEngine(db_path=self.db_path)

        # 1. Train
        engine.load_candles(train_candles)
        train_sum = engine.run_pipeline()

        # 2. Validation
        engine.load_candles(val_candles)
        val_sum = engine.run_pipeline()

        # 3. Out-of-Sample Test
        engine.load_candles(test_candles)
        test_sum = engine.run_pipeline()

        return {
            "in_sample_train": train_sum,
            "validation": val_sum,
            "out_of_sample_test": test_sum,
        }

    def generate_parameter_sensitivity_matrix(
        self,
        candles: List[Candle],
        wick_ratios: List[float] = [0.20, 0.30, 0.40, 0.50, 0.60],
        atr_multipliers: List[float] = [0.5, 1.0, 1.5, 2.0],
    ) -> List[Dict[str, Any]]:
        """
        Builds a parameter heatmap matrix testing combinations of Wick Ratio vs ATR Buffer.
        Ensures strategy resilience across parameter neighborhoods.
        """
        matrix: List[Dict[str, Any]] = []

        for wr in wick_ratios:
            for atr_m in atr_multipliers:
                cfg = SetupConfig(min_wick_ratio=wr, atr_sl_multiplier=atr_m)
                engine = ResearchEngine(setup_config=cfg, db_path=self.db_path)
                engine.load_candles(candles, timeframe="5m")
                summary = engine.run_pipeline()

                matrix.append(
                    {
                        "wick_ratio": wr,
                        "atr_multiplier": atr_m,
                        "total_trades": summary.total_trades,
                        "win_rate_pct": summary.win_rate_pct,
                        "profit_factor": summary.profit_factor,
                        "expectancy_r": summary.expectancy_r,
                    }
                )

        return matrix
