"""
XAUUSD Session Research Lab — Core Package.
"""

from goldlab.autofix import FixStatus, RiskLevel, SafeAutoFixEngine
from goldlab.backtester import BacktestingEngine, StrategyComparisonItem
from goldlab.bot import AutomatedPaperBot, BotRiskSettings, BotState
from goldlab.diagnostics import DiagnosticsEngine, IncidentCategory, IncidentSeverity
from goldlab.engine import ResearchEngine
from goldlab.guardian import IndependentRiskGuardian, RiskGuardianConfig
from goldlab.learning import AutopsyVerdict, HypothesisStatus, MistakeAnalyzerAndHypothesisRegistry
from goldlab.market_structure import MarketStructureAnalyzer
from goldlab.ml_model import MLTradeQualityModel
from goldlab.paper_broker import PaperAccount, PaperBroker, PaperOrder
from goldlab.promotion import ChampionChallengerManager, StrategyVersion
from goldlab.regime import MarketRegimeMonitor, MarketRegimeReport, MarketRegimeType
from goldlab.sessions import SessionConfig, SessionManager
from goldlab.setups import SetupConfig, SetupEngine
from goldlab.simulator import ExecutionSimulator, SimulatorConfig
from goldlab.supervisor import JobStatus, JobType, ResearchSupervisor
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
    "PaperBroker",
    "PaperAccount",
    "PaperOrder",
    "AutomatedPaperBot",
    "BotRiskSettings",
    "BotState",
    "BacktestingEngine",
    "StrategyComparisonItem",
    "IndependentRiskGuardian",
    "RiskGuardianConfig",
    "MarketRegimeMonitor",
    "MarketRegimeType",
    "MarketRegimeReport",
    "DiagnosticsEngine",
    "IncidentCategory",
    "IncidentSeverity",
    "SafeAutoFixEngine",
    "RiskLevel",
    "FixStatus",
    "MistakeAnalyzerAndHypothesisRegistry",
    "AutopsyVerdict",
    "HypothesisStatus",
    "MLTradeQualityModel",
    "ChampionChallengerManager",
    "StrategyVersion",
    "ResearchSupervisor",
    "JobType",
    "JobStatus",
]
