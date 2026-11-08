"""
Data structures and core types for XAUUSD Session Research Lab.
All timestamps are strictly timezone-aware UTC datetime instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class SignalDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeOutcome(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    BREAK_EVEN = "BREAK_EVEN"
    OPEN = "OPEN"


class SessionName(str, Enum):
    TOKYO = "Tokyo"
    LONDON = "London"
    NEW_YORK = "New_York"
    ASIA_REFERENCE = "Asia_Reference"
    LONDON_NY_OVERLAP = "London_NY_Overlap"


@dataclass
class Candle:
    timestamp: datetime  # UTC aware
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0  # Explicitly Tick Volume
    is_closed: bool = True

    # Computed metrics
    range: float = 0.0
    body: float = 0.0
    upper_wick: float = 0.0
    lower_wick: float = 0.0
    wick_ratio: float = 0.0
    atr14: float = 0.0
    body_to_atr: float = 0.0
    displacement: bool = False
    ambiguous_touch_flag: bool = False  # Set if high and low breached opposite levels in the same bar

    def __post_init__(self) -> None:
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError(f"Invalid candle geometry: O={self.open}, H={self.high}, L={self.low}, C={self.close}")
        self.range = round(self.high - self.low, 4)
        self.body = round(abs(self.close - self.open), 4)
        self.upper_wick = round(self.high - max(self.open, self.close), 4)
        self.lower_wick = round(min(self.open, self.close) - self.low, 4)
        max_wick = max(self.upper_wick, self.lower_wick)
        self.wick_ratio = round(max_wick / self.range, 4) if self.range > 0 else 0.0


@dataclass
class SessionWindow:
    name: SessionName
    start_utc: datetime
    end_utc: datetime
    high: Optional[float] = None
    low: Optional[float] = None
    midline: Optional[float] = None
    prior_close: Optional[float] = None
    prior_open: Optional[float] = None
    candle_indices: List[int] = field(default_factory=list)


@dataclass
class SwingPoint:
    index: int
    timestamp: datetime
    price: float
    is_high: bool  # True for Swing High, False for Swing Low
    confirmed_index: int  # index + right_bars (Strict zero-leakage guarantee)


@dataclass
class FairValueGap:
    start_index: int  # Candle 0 in the 3-candle sequence
    gap_index: int    # Candle 1 (the middle candle)
    end_index: int    # Candle 2 (when FVG becomes defined upon close)
    top: float
    bottom: float
    is_bullish: bool
    mitigated: bool = False
    mitigated_index: Optional[int] = None


@dataclass
class OrderBlockProxy:
    index: int
    timestamp: datetime
    is_bullish: bool
    top: float
    bottom: float
    is_breaker: bool = False
    mitigated: bool = False


@dataclass
class SetupSignal:
    setup_id: str
    setup_name: str
    direction: SignalDirection
    signal_index: int  # Index of candle where setup completed (closed)
    signal_time: datetime
    entry_index: int   # signal_index + 1 (Entry strictly on next bar open)
    entry_price: float
    sl_price: float
    tp_price: float
    risk_r: float
    reason: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    ambiguous: bool = False


@dataclass
class TradeOrder:
    trade_id: str
    setup_id: str
    direction: SignalDirection
    entry_index: int
    entry_time: datetime
    entry_price: float
    sl_price: float
    tp_price: float
    exit_index: Optional[int] = None
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    outcome: TradeOutcome = TradeOutcome.OPEN
    realized_r: float = 0.0
    mae_pips: float = 0.0
    mfe_pips: float = 0.0
    bars_in_trade: int = 0
    exit_reason: str = "OPEN"


@dataclass
class BacktestSummary:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    break_even_trades: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    expectancy_r: float = 0.0
    max_drawdown_r: float = 0.0
    avg_mae: float = 0.0
    avg_mfe: float = 0.0
    trades: List[TradeOrder] = field(default_factory=list)
    distribution_by_session: Dict[str, int] = field(default_factory=dict)
    distribution_by_day: Dict[str, int] = field(default_factory=dict)
