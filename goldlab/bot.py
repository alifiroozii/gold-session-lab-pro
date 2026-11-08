"""
Automated Paper Trading Bot for XAUUSD.
Operates strictly in simulation/paper mode.
Supports state machine: OFF, ANALYSIS_ONLY, PAPER_AUTO, PAUSED, DATA_DISCONNECTED, ERROR, STOPPED.
Enforces institutional risk constraints: max daily loss, per-trade risk sizing, and consecutive loss cooldown.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional, Set, Tuple

from goldlab.engine import ResearchEngine
from goldlab.paper_broker import OrderDirection, OrderType, PaperBroker
from goldlab.types import Candle, SetupSignal, SignalDirection

TZ_UTC = timezone.utc


class BotState(str, Enum):
    OFF = "OFF"
    ANALYSIS_ONLY = "ANALYSIS_ONLY"
    PAPER_AUTO = "PAPER_AUTO"
    PAUSED = "PAUSED"
    DATA_DISCONNECTED = "DATA_DISCONNECTED"
    ERROR = "ERROR"
    STOPPED = "STOPPED"


@dataclass
class BotRiskSettings:
    risk_per_trade_pct: float = 0.50  # 0.5% risk per trade
    max_daily_loss_pct: float = 2.00  # 2.0% max daily drawdown
    max_open_positions: int = 2
    max_daily_trades: int = 4
    min_rr_ratio: float = 1.50
    consecutive_losses_limit: int = 2
    cooldown_bars: int = 6
    max_spread_pips: float = 0.50  # Block entry if spread > $0.50


class AutomatedPaperBot:
    """Manages autonomous paper order execution on live/replay candle arrival."""

    def __init__(
        self,
        bot_id: str = "BOT_XAU_ALPHA",
        account_id: str = "ACC_DEFAULT",
        broker: Optional[PaperBroker] = None,
        engine: Optional[ResearchEngine] = None,
        risk_settings: Optional[BotRiskSettings] = None,
        db_path: str = "data/xauusd_lab.sqlite",
    ) -> None:
        self.bot_id = bot_id
        self.account_id = account_id
        self.broker = broker or PaperBroker(db_path=db_path)
        self.engine = engine or ResearchEngine(db_path=db_path)
        self.risk = risk_settings or BotRiskSettings()
        self.db_path = Path(db_path)

        self.state: BotState = BotState.ANALYSIS_ONLY
        self.today_trades_count: int = 0
        self.consecutive_losses: int = 0
        self.cooldown_remaining_bars: int = 0
        self.daily_start_balance: float = 1000.0
        self.last_trade_date: Optional[str] = None
        self.dispatched_signals: Set[Tuple[str, str, int]] = set()
        self.last_evaluation_time: Optional[datetime] = None
        self.heartbeat_time: datetime = datetime.now(TZ_UTC)

        self._init_bot_db()

    def _init_bot_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    state TEXT NOT NULL,
                    message TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def log_event(self, event_type: str, message: str) -> None:
        now = datetime.now(TZ_UTC)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO bot_events (bot_id, timestamp, event_type, state, message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self.bot_id, now.isoformat(), event_type, self.state.value, message),
            )
            conn.commit()

    def set_state(self, new_state: BotState) -> None:
        old_state = self.state
        self.state = new_state
        self.log_event("STATE_CHANGE", f"وضعیت ربات از {old_state.value} به {new_state.value} تغییر یافت.")

    def emergency_stop(self, reason: str = "توقف اضطراری توسط اپراتور") -> None:
        """Immediately halts all automated trading and locks bot into STOPPED state."""
        self.set_state(BotState.STOPPED)
        self.log_event("EMERGENCY_STOP", reason)

    def resume_after_emergency_stop(self, target_state: BotState = BotState.ANALYSIS_ONLY) -> None:
        """Explicit operator-approved recovery after emergency stop."""
        if self.state == BotState.STOPPED:
            self.log_event("MANUAL_REACTIVATION", f"فعال‌سازی مجدد پس از توقف اضطراری به وضعیت {target_state.value}")
            self.set_state(target_state)

    def on_trade_closed(self, pnl: float) -> None:
        """Updates consecutive loss counter and activates cooldown if limit reached."""
        if pnl < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.risk.consecutive_losses_limit:
                self.cooldown_remaining_bars = self.risk.cooldown_bars
                self.log_event(
                    "COOLDOWN_ACTIVATED",
                    f"{self.consecutive_losses} زیان متوالی رخ داد. کول‌داون به مدت {self.risk.cooldown_bars} کندل فعال گردید.",
                )
        else:
            self.consecutive_losses = 0

    def on_candle_close(
        self,
        closed_candles: List[Candle],
        current_bid: float,
        current_ask: float,
        current_time: Optional[datetime] = None,
    ) -> List[SetupSignal]:
        """Triggered when a candle closes.

        1. Checks feed status and heartbeat
        2. Evaluates risk thresholds (daily loss limit, max open positions)
        3. Checks economic news blackout
        4. Runs research engine strategy pipeline
        5. If in PAPER_AUTO mode, sizes lots and dispatches paper orders
        """
        self.heartbeat_time = current_time or datetime.now(TZ_UTC)
        self.last_evaluation_time = self.heartbeat_time

        if self.state == BotState.STOPPED:
            return []

        # Reset daily counters at midnight UTC
        current_date_str = self.heartbeat_time.strftime("%Y-%m-%d")
        if self.last_trade_date != current_date_str:
            self.last_trade_date = current_date_str
            self.today_trades_count = 0
            acc_initial = self.broker.accounts.get(self.account_id)
            if acc_initial:
                self.daily_start_balance = acc_initial.equity

        if not closed_candles:
            return []

        last_candle = closed_candles[-1]

        # 1. Feed Health Check
        feed_health = self.engine.data_pipeline.diagnostics.check_feed_status(
            closed_candles, current_time=self.heartbeat_time
        )
        if feed_health["status"] in ["FEED_STALE", "MARKET_CLOSED", "OFFLINE_EMPTY"]:
            if self.state == BotState.PAPER_AUTO:
                self.set_state(BotState.DATA_DISCONNECTED)
            return []
        elif self.state == BotState.DATA_DISCONNECTED:
            # Fail closed. A recovered feed must NEVER silently re-arm
            # auto trading; operator must approve a validated strategy again.
            self.log_event("FEED_RECOVERED", "فید برگشت؛ ربات تا تأیید دستی در حالت توقف باقی می‌ماند.")
            self.set_state(BotState.PAUSED)

        # 2. Risk Pre-Checks
        acc = self.broker.accounts.get(self.account_id)
        if not acc:
            return []

        # Check daily drawdown limit
        daily_loss_dollars = self.daily_start_balance - acc.equity
        if daily_loss_dollars > (self.daily_start_balance * (self.risk.max_daily_loss_pct / 100.0)):
            if self.state == BotState.PAPER_AUTO:
                self.set_state(BotState.PAUSED)
                self.log_event("RISK_LIMIT", f"حداکثر زیان روزانه ({self.risk.max_daily_loss_pct}%) لمس شد. ربات متوقف گردید.")
            return []

        # Check consecutive loss cooldown
        in_cooldown = False
        if self.cooldown_remaining_bars > 0:
            self.cooldown_remaining_bars -= 1
            in_cooldown = True
            if self.state == BotState.PAPER_AUTO:
                self.log_event("COOLDOWN_BLOCK", f"کول‌داون پس از زیان فعال است ({self.cooldown_remaining_bars + 1} کندل باقی‌مانده).")

        # Check max open positions
        open_positions = [
            p for p in self.broker.positions.values() if p.account_id == self.account_id and p.status.value == "OPEN"
        ]
        if len(open_positions) >= self.risk.max_open_positions:
            return []

        # Check max daily trades
        if self.today_trades_count >= self.risk.max_daily_trades:
            if self.state == BotState.PAPER_AUTO:
                self.log_event("MAX_DAILY_TRADES", f"سقف معاملات روزانه ({self.risk.max_daily_trades}) تکمیل شد.")
            return []

        # 3. News Blackout Check
        is_blocked, news_reason = self.engine.calendar.is_blackout(last_candle.timestamp)
        if is_blocked and self.state == BotState.PAPER_AUTO:
            self.log_event("NEWS_BLOCK", f"معامله متوقف شد به دلیل: {news_reason}")
            return []

        # 4. Run Analysis Pipeline
        self.engine.load_candles(closed_candles, timeframe=self.engine.current_timeframe)
        self.engine.run_pipeline(allow_pending=True)

        new_signals = [s for s in self.engine.signals if s.signal_index == len(self.engine.current_candles) - 1]

        # 5. Paper Auto Dispatch
        if self.state == BotState.PAPER_AUTO and new_signals and not in_cooldown:
            spread = current_ask - current_bid
            if spread > self.risk.max_spread_pips:
                self.log_event("SPREAD_FILTER", f"اسپرد جاری (${spread:.2f}) بالاتر از سقف مجاز (${self.risk.max_spread_pips:.2f}) است.")
                return new_signals

            for sig in new_signals:
                if len(open_positions) >= self.risk.max_open_positions:
                    break
                if self.today_trades_count >= self.risk.max_daily_trades:
                    break

                # Prevent duplicate order for identical signal
                sig_key = (sig.setup_id, sig.direction.value, sig.signal_index)
                if sig_key in self.dispatched_signals:
                    continue

                # Position sizing based on 0.5% risk
                risk_dollars = acc.balance * (self.risk.risk_per_trade_pct / 100.0)
                sl_distance = abs(sig.entry_price - sig.sl_price)
                if sl_distance <= 0:
                    continue

                calculated_lots = risk_dollars / (sl_distance * acc.contract_size)
                # Clamp lots
                lots = round(max(0.01, min(5.0, calculated_lots)), 2)

                direction = OrderDirection.BUY if sig.direction == SignalDirection.BUY else OrderDirection.SELL

                order = self.broker.submit_order(
                    account_id=self.account_id,
                    direction=direction,
                    order_type=OrderType.MARKET,
                    quantity_lots=lots,
                    sl_price=sig.sl_price,
                    tp_price=sig.tp_price,
                    current_bid=current_bid,
                    current_ask=current_ask,
                )
                self.today_trades_count += 1
                self.dispatched_signals.add(sig_key)
                self.log_event(
                    "ORDER_DISPATCHED",
                    f"ارسال سفارش مجازی {direction.value} {lots} لات به استراتژی {sig.setup_name} (سفارش #{order.order_id})",
                )

        return new_signals

        return new_signals
