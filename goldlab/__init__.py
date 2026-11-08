"""
XAUUSD Session Research Lab — Core Package.
"""

from goldlab.engine import ResearchEngine
from goldlab.market_structure import MarketStructureAnalyzer
from goldlab.sessions import SessionConfig, SessionManager
from goldlab.setups import SetupConfig, SetupEngine
from goldlab.simulator import ExecutionSimulator, SimulatorConfig
from goldlab.types import (
    BacktestSummary,
    Candle,
    FairValueGap,
    OrderBlockProxy,
    SessionName,
    SessionWindow,
    SetupSignal,
    SignalDirection,
    SwingPoint,
    TradeOrder,
    TradeOutcome,
)

__all__ = [
    "ResearchEngine",
    "SessionManager",
    "SessionConfig",
    "MarketStructureAnalyzer",
    "SetupEngine",
    "SetupConfig",
    "ExecutionSimulator",
    "SimulatorConfig",
    "Candle",
    "SessionName",
    "SessionWindow",
    "SwingPoint",
    "FairValueGap",
    "OrderBlockProxy",
    "SetupSignal",
    "SignalDirection",
    "TradeOrder",
    "TradeOutcome",
    "BacktestSummary",
]
