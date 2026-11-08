"""
Central Research Engine for XAUUSD Session Research Lab.
Orchestrates data pipeline, market structure analysis, session levels,
modular setups, risk simulation, and reporting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from goldlab.calendar import MacroNewsCalendar
from goldlab.data import DataPipeline
from goldlab.market_structure import MarketStructureAnalyzer
from goldlab.metrics import MetricsCalculator
from goldlab.sessions import SessionManager
from goldlab.setups import SetupConfig, SetupEngine
from goldlab.simulator import ExecutionSimulator
from goldlab.types import (
    BacktestSummary,
    Candle,
    FairValueGap,
    OrderBlockProxy,
    SetupSignal,
    SwingPoint,
    TradeOrder,
)


class ResearchEngine:
    """Institutional-grade quant engine for XAUUSD session and market structure research."""

    def __init__(
        self,
        setup_config: Optional[SetupConfig] = None,
        db_path: str = "data/xauusd_lab.sqlite",
    ) -> None:
        self.session_mgr = SessionManager()
        self.structure = MarketStructureAnalyzer(left_bars=3, right_bars=3, atr_period=14)
        self.setups = SetupEngine(config=setup_config, structure=self.structure, session_mgr=self.session_mgr)
        self.simulator = ExecutionSimulator()
        self.data_pipeline = DataPipeline(db_path=db_path)
        self.calendar = MacroNewsCalendar()

        # State cache
        self.candles_1m: List[Candle] = []
        self.current_candles: List[Candle] = []
        self.current_timeframe: str = "5m"
        self.session_stats: Dict[str, Any] = {}
        self.swings: List[SwingPoint] = []
        self.fvgs: List[FairValueGap] = []
        self.obs: List[OrderBlockProxy] = []
        self.signals: List[SetupSignal] = []
        self.trades: List[TradeOrder] = []
        self.summary: BacktestSummary = BacktestSummary()
        self.feed_health: Dict[str, str] = {"status": "OFFLINE_EMPTY", "detail": "داده‌ای بارگذاری نشده است."}

    def load_candles(self, candles: List[Candle], timeframe: str = "5m") -> None:
        """Loads candle series directly and aggregates to specified timeframe."""
        self.candles_1m = candles
        self.current_timeframe = timeframe
        self.current_candles = self.data_pipeline.aggregate_candles(candles, timeframe)
        self.feed_health = self.data_pipeline.diagnostics.check_feed_status(self.current_candles)

    def load_from_csv(self, csv_path: Path, timeframe: str = "5m") -> None:
        """Parses CSV, stores in local SQLite, and aggregates."""
        raw_1m = self.data_pipeline.parse_csv(csv_path)
        self.data_pipeline.save_to_sqlite(raw_1m, source_label=csv_path.name)
        self.load_candles(raw_1m, timeframe=timeframe)

    def run_pipeline(self) -> BacktestSummary:
        """
        Executes end-to-end analytical workflow across current timeframe candles:
        1. Candle metric enrichment (ATR14, wicks, displacement)
        2. Session statistics and level calculation (PDH/PDL, Asia H/L, London H/L, NY H/L)
        3. Market structure analysis (Confirmed swings, EQH/EQL, FVG, OB proxies)
        4. Setup detection
        5. Simulation and metrics
        """
        if not self.current_candles:
            self.summary = BacktestSummary()
            return self.summary

        # 1. Enrich candle metrics
        self.structure.enrich_candle_metrics(self.current_candles)

        # 2. Calculate Session levels
        self.session_stats = self.session_mgr.calculate_session_stats(self.current_candles)

        # 3. Market structure
        self.swings = self.structure.find_swing_points(self.current_candles)
        self.fvgs = self.structure.find_fair_value_gaps(self.current_candles)
        self.obs = self.structure.detect_order_block_proxies(self.current_candles, self.swings)

        # 4. Evaluate setups
        self.signals = self.setups.evaluate_all(
            self.current_candles, self.swings, self.fvgs, self.obs, self.session_stats
        )

        # 5. Simulate execution
        self.trades = self.simulator.run_simulation(self.current_candles, self.signals)

        # 6. Performance metrics
        self.summary = MetricsCalculator.calculate_summary(self.trades)
        return self.summary

    def get_dashboard_payload(self) -> Dict[str, Any]:
        """Prepares comprehensive JSON payload for the web dashboard."""
        candle_data = [
            {
                "time": int(c.timestamp.timestamp()),
                "iso": c.timestamp.isoformat(),
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "atr": c.atr14,
                "sessions": [s.value for s in self.session_mgr.get_candle_sessions(c.timestamp)],
            }
            for c in self.current_candles
        ]

        signal_data = [
            {
                "setup_id": s.setup_id,
                "setup_name": s.setup_name,
                "direction": s.direction.value,
                "time": int(s.signal_time.timestamp()),
                "entry_time": int(self.current_candles[s.entry_index].timestamp.timestamp())
                if s.entry_index < len(self.current_candles)
                else None,
                "entry_price": s.entry_price,
                "sl": s.sl_price,
                "tp": s.tp_price,
                "risk_r": s.risk_r,
                "reason": s.reason,
            }
            for s in self.signals
        ]

        trade_data = [
            {
                "trade_id": t.trade_id,
                "direction": t.direction.value,
                "entry_time": t.entry_time.isoformat(),
                "entry_price": t.entry_price,
                "sl": t.sl_price,
                "tp": t.tp_price,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "exit_price": t.exit_price,
                "outcome": t.outcome.value,
                "realized_r": t.realized_r,
                "mae": t.mae_pips,
                "mfe": t.mfe_pips,
                "bars": t.bars_in_trade,
                "reason": t.exit_reason,
            }
            for t in self.trades
        ]

        # Bootstrap CI
        ci_lower, ci_upper = MetricsCalculator.bootstrap_expectancy_ci(self.trades)

        return {
            "feed_health": self.feed_health,
            "session_stats": self.session_stats,
            "candles": candle_data,
            "signals": signal_data,
            "trades": trade_data,
            "metrics": {
                "total_trades": self.summary.total_trades,
                "win_rate_pct": self.summary.win_rate_pct,
                "profit_factor": self.summary.profit_factor,
                "expectancy_r": self.summary.expectancy_r,
                "max_drawdown_r": self.summary.max_drawdown_r,
                "avg_mae": self.summary.avg_mae,
                "avg_mfe": self.summary.avg_mfe,
                "bootstrap_ci": [ci_lower, ci_upper],
                "distribution_by_day": self.summary.distribution_by_day,
            },
        }
