"""
Causal Event-Driven Session Trading State Machine for XAUUSD (Master Prompt V5).
Enforces a strict 10-state progression with zero lookahead, deterministic SQLite logging,
and fail-closed risk management:
- WAITING_FOR_SESSION
- BUILDING_RANGE
- RANGE_FINALIZED
- SWEEP_DETECTED
- RECLAIM_CONFIRMED
- STRUCTURE_CONFIRMED
- RETEST_CONFIRMED
- ENTRY_ELIGIBLE
- PAPER_ORDER
- POSITION_MANAGEMENT
- CLOSED
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from goldlab.sessions import SessionManager
from goldlab.types import Candle, SessionName, SetupSignal, SignalDirection

TZ_UTC = timezone.utc


class SessionStrategyState(str, Enum):
    WAITING_FOR_SESSION = "WAITING_FOR_SESSION"
    BUILDING_RANGE = "BUILDING_RANGE"
    RANGE_FINALIZED = "RANGE_FINALIZED"
    SWEEP_DETECTED = "SWEEP_DETECTED"
    RECLAIM_CONFIRMED = "RECLAIM_CONFIRMED"
    STRUCTURE_CONFIRMED = "STRUCTURE_CONFIRMED"
    RETEST_CONFIRMED = "RETEST_CONFIRMED"
    ENTRY_ELIGIBLE = "ENTRY_ELIGIBLE"
    PAPER_ORDER = "PAPER_ORDER"
    POSITION_MANAGEMENT = "POSITION_MANAGEMENT"
    CLOSED = "CLOSED"


@dataclass
class StateTransitionRecord:
    timestamp: str
    candle_id: str
    session: str
    trade_date: str
    source_data: str
    from_state: str
    to_state: str
    ref_high: Optional[float]
    ref_low: Optional[float]
    confirmation_conditions: str
    invalidating_conditions: str
    transition_reason: str
    strategy_version: str
    transition_id: Optional[int] = None


@dataclass
class ActiveSetupContext:
    direction: SignalDirection = SignalDirection.BUY
    target_level_name: str = ""
    target_level_val: float = 0.0
    sweep_candle_time: str = ""
    sweep_candle_price: float = 0.0
    reclaim_candle_time: str = ""
    reclaim_candle_high: float = 0.0
    reclaim_candle_low: float = 0.0
    bos_candle_time: str = ""
    retest_candle_time: str = ""
    entry_price: float = 0.0
    sl_price: float = 0.0
    tp_price: float = 0.0
    risk_r: float = 0.0
    order_id: Optional[str] = None
    position_id: Optional[str] = None


class SessionTradingStateMachine:
    """
    Evaluates market candles sequentially and causally.
    Transitions through 10 formal states and logs all state changes into SQLite.
    """

    def __init__(
        self,
        strategy_version: str = "v5.0.0-causal",
        source_data: str = "OANDA_V20",
        db_path: str = "data/xauusd_lab.sqlite",
        session_mgr: Optional[SessionManager] = None,
        retest_tolerance_pips: float = 0.50,
        min_wick_ratio: float = 0.35,
        risk_reward_ratio: float = 2.0,
        atr_multiplier: float = 1.0,
    ) -> None:
        self.strategy_version = strategy_version
        self.source_data = source_data
        self.db_path = Path(db_path)
        self.session_mgr = session_mgr or SessionManager()
        self.retest_tolerance = retest_tolerance_pips
        self.min_wick_ratio = min_wick_ratio
        self.risk_reward_ratio = risk_reward_ratio
        self.atr_multiplier = atr_multiplier

        self.current_state: SessionStrategyState = SessionStrategyState.WAITING_FOR_SESSION
        self.current_trade_date: Optional[str] = None
        self.ref_high: Optional[float] = None
        self.ref_low: Optional[float] = None
        self.active_setup: Optional[ActiveSetupContext] = None
        self.last_transition_reason: str = "Initialized"
        self.last_candle_id: str = ""

        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_state_transitions (
                    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    candle_id TEXT NOT NULL,
                    session TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    source_data TEXT NOT NULL,
                    from_state TEXT NOT NULL,
                    to_state TEXT NOT NULL,
                    ref_high REAL,
                    ref_low REAL,
                    confirmation_conditions TEXT NOT NULL,
                    invalidating_conditions TEXT NOT NULL,
                    transition_reason TEXT NOT NULL,
                    strategy_version TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _log_transition(
        self,
        to_state: SessionStrategyState,
        candle: Candle,
        session_name: str,
        reason: str,
        confirmations: Dict[str, Any],
        invalidations: Dict[str, Any],
    ) -> None:
        from_state_str = self.current_state.value
        to_state_str = to_state.value
        t_now = candle.timestamp.isoformat()
        t_day = self.current_trade_date or self.session_mgr.get_trading_day(candle.timestamp)

        rec = StateTransitionRecord(
            timestamp=t_now,
            candle_id=candle.timestamp.isoformat(),
            session=session_name,
            trade_date=t_day,
            source_data=self.source_data,
            from_state=from_state_str,
            to_state=to_state_str,
            ref_high=self.ref_high,
            ref_low=self.ref_low,
            confirmation_conditions=json.dumps(confirmations, ensure_ascii=False),
            invalidating_conditions=json.dumps(invalidations, ensure_ascii=False),
            transition_reason=reason,
            strategy_version=self.strategy_version,
        )

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO strategy_state_transitions (
                    timestamp, candle_id, session, trade_date, source_data,
                    from_state, to_state, ref_high, ref_low,
                    confirmation_conditions, invalidating_conditions,
                    transition_reason, strategy_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.timestamp,
                    rec.candle_id,
                    rec.session,
                    rec.trade_date,
                    rec.source_data,
                    rec.from_state,
                    rec.to_state,
                    rec.ref_high,
                    rec.ref_low,
                    rec.confirmation_conditions,
                    rec.invalidating_conditions,
                    rec.transition_reason,
                    rec.strategy_version,
                ),
            )
            rec.transition_id = cur.lastrowid
            conn.commit()

        self.current_state = to_state
        self.last_transition_reason = reason
        self.last_candle_id = candle.timestamp.isoformat()

    def process_candle(
        self,
        candle: Candle,
        prior_candles: List[Candle],
        session_stats: Optional[Dict[str, Any]] = None,
    ) -> Optional[SetupSignal]:
        """
        Processes a single closed candle causally and transitions states.
        If transition reaches ENTRY_ELIGIBLE, returns a valid SetupSignal.
        """
        t_day = self.session_mgr.get_trading_day(candle.timestamp)
        sessions = self.session_mgr.get_candle_sessions(candle.timestamp)
        primary_session = sessions[0].value if sessions else "OFF_HOURS"

        # Trading day rollover: reset reference levels if new day
        if self.current_trade_date != t_day:
            self.current_trade_date = t_day
            if self.current_state not in (
                SessionStrategyState.PAPER_ORDER,
                SessionStrategyState.POSITION_MANAGEMENT,
            ):
                self._log_transition(
                    SessionStrategyState.WAITING_FOR_SESSION,
                    candle,
                    primary_session,
                    f"شروع روز معاملاتی جدید {t_day}",
                    {"new_day": t_day},
                    {},
                )
                self.ref_high = None
                self.ref_low = None
                self.active_setup = None

        # State 1: WAITING_FOR_SESSION
        if self.current_state == SessionStrategyState.WAITING_FOR_SESSION:
            if SessionName.ASIA_REFERENCE in sessions:
                self.ref_high = candle.high
                self.ref_low = candle.low
                self._log_transition(
                    SessionStrategyState.BUILDING_RANGE,
                    candle,
                    primary_session,
                    "ورود به بازه مرجع آسیا (20:00 تا 00:00 نیویورک) و آغاز ثبت سطوح",
                    {"bar_high": candle.high, "bar_low": candle.low},
                    {},
                )
            return None

        # State 2: BUILDING_RANGE
        elif self.current_state == SessionStrategyState.BUILDING_RANGE:
            if self.ref_high is None or candle.high > self.ref_high:
                self.ref_high = candle.high
            if self.ref_low is None or candle.low < self.ref_low:
                self.ref_low = candle.low

            is_asia_complete = (
                session_stats.get("asia_complete", False)
                if session_stats
                else (SessionName.ASIA_REFERENCE not in sessions)
            )

            if is_asia_complete:
                self._log_transition(
                    SessionStrategyState.RANGE_FINALIZED,
                    candle,
                    primary_session,
                    f"پایان بازه آسیا در ساعت 00:00 نیویورک؛ تثبیت سطوح آسیا (High: {self.ref_high}, Low: {self.ref_low})",
                    {"final_high": self.ref_high, "final_low": self.ref_low},
                    {},
                )
            return None

        # State 3: RANGE_FINALIZED
        elif self.current_state == SessionStrategyState.RANGE_FINALIZED:
            if self.ref_high is None or self.ref_low is None:
                return None

            # Check for liquidity sweeps during London or New York sessions
            if SessionName.LONDON in sessions or SessionName.NEW_YORK in sessions:
                # Bullish Sweep of Asia Low
                if candle.low < self.ref_low:
                    self.active_setup = ActiveSetupContext(
                        direction=SignalDirection.BUY,
                        target_level_name="AsiaLow",
                        target_level_val=self.ref_low,
                        sweep_candle_time=candle.timestamp.isoformat(),
                        sweep_candle_price=candle.low,
                    )
                    self._log_transition(
                        SessionStrategyState.SWEEP_DETECTED,
                        candle,
                        primary_session,
                        f"نفوذ نقدینگی (Sweep) کف آسیا: قیمت {candle.low} زیر سطح {self.ref_low}",
                        {"level": "AsiaLow", "level_val": self.ref_low, "sweep_low": candle.low},
                        {"invalidation": f"شکست قطعی بدون بازگشت زیر {self.ref_low - 10.0}"},
                    )
                # Bearish Sweep of Asia High
                elif candle.high > self.ref_high:
                    self.active_setup = ActiveSetupContext(
                        direction=SignalDirection.SELL,
                        target_level_name="AsiaHigh",
                        target_level_val=self.ref_high,
                        sweep_candle_time=candle.timestamp.isoformat(),
                        sweep_candle_price=candle.high,
                    )
                    self._log_transition(
                        SessionStrategyState.SWEEP_DETECTED,
                        candle,
                        primary_session,
                        f"نفوذ نقدینگی (Sweep) سقف آسیا: قیمت {candle.high} بالای سطح {self.ref_high}",
                        {"level": "AsiaHigh", "level_val": self.ref_high, "sweep_high": candle.high},
                        {"invalidation": f"شکست قطعی بدون بازگشت بالای {self.ref_high + 10.0}"},
                    )
            return None

        # State 4: SWEEP_DETECTED
        elif self.current_state == SessionStrategyState.SWEEP_DETECTED:
            if not self.active_setup:
                self.current_state = SessionStrategyState.RANGE_FINALIZED
                return None

            level = self.active_setup.target_level_val
            if self.active_setup.direction == SignalDirection.BUY:
                if candle.close > level:
                    self.active_setup.reclaim_candle_time = candle.timestamp.isoformat()
                    self.active_setup.reclaim_candle_high = candle.high
                    self.active_setup.reclaim_candle_low = candle.low
                    self._log_transition(
                        SessionStrategyState.RECLAIM_CONFIRMED,
                        candle,
                        primary_session,
                        f"تأیید بازپس‌گیری (Reclaim): کلوز کندل {candle.close} بالای سطح {level}",
                        {"reclaim_close": candle.close, "level": level},
                        {"invalidation": f"کلوز مجدد زیر {level}"},
                    )
                elif candle.low < level - 15.0:  # Excessive blowout
                    self._log_transition(
                        SessionStrategyState.CLOSED,
                        candle,
                        primary_session,
                        f"ابطال سناریو: فرار شدید قیمت از سطح کف ({candle.low})",
                        {},
                        {"excessive_drop": candle.low},
                    )
            else:  # SELL
                if candle.close < level:
                    self.active_setup.reclaim_candle_time = candle.timestamp.isoformat()
                    self.active_setup.reclaim_candle_high = candle.high
                    self.active_setup.reclaim_candle_low = candle.low
                    self._log_transition(
                        SessionStrategyState.RECLAIM_CONFIRMED,
                        candle,
                        primary_session,
                        f"تأیید بازپس‌گیری (Reclaim): کلوز کندل {candle.close} زیر سطح {level}",
                        {"reclaim_close": candle.close, "level": level},
                        {"invalidation": f"کلوز مجدد بالای {level}"},
                    )
                elif candle.high > level + 15.0:
                    self._log_transition(
                        SessionStrategyState.CLOSED,
                        candle,
                        primary_session,
                        f"ابطال سناریو: فرار شدید قیمت از سطح سقف ({candle.high})",
                        {},
                        {"excessive_rise": candle.high},
                    )
            return None

        # State 5: RECLAIM_CONFIRMED
        elif self.current_state == SessionStrategyState.RECLAIM_CONFIRMED:
            if not self.active_setup:
                self.current_state = SessionStrategyState.RANGE_FINALIZED
                return None

            if self.active_setup.direction == SignalDirection.BUY:
                # BOS occurs when candle closes above reclaim candle high
                if candle.close > self.active_setup.reclaim_candle_high:
                    self.active_setup.bos_candle_time = candle.timestamp.isoformat()
                    self._log_transition(
                        SessionStrategyState.STRUCTURE_CONFIRMED,
                        candle,
                        primary_session,
                        f"شکست ساختار (BOS): کلوز {candle.close} بالاتر از سقف کندل بازپس‌گیری ({self.active_setup.reclaim_candle_high})",
                        {"bos_close": candle.close, "break_above": self.active_setup.reclaim_candle_high},
                        {"invalidation": f"کلوز زیر {self.active_setup.target_level_val}"},
                    )
            else:  # SELL
                if candle.close < self.active_setup.reclaim_candle_low:
                    self.active_setup.bos_candle_time = candle.timestamp.isoformat()
                    self._log_transition(
                        SessionStrategyState.STRUCTURE_CONFIRMED,
                        candle,
                        primary_session,
                        f"شکست ساختار (BOS): کلوز {candle.close} پایین‌تر از کف کندل بازپس‌گیری ({self.active_setup.reclaim_candle_low})",
                        {"bos_close": candle.close, "break_below": self.active_setup.reclaim_candle_low},
                        {"invalidation": f"کلوز بالای {self.active_setup.target_level_val}"},
                    )
            return None

        # State 6: STRUCTURE_CONFIRMED
        elif self.current_state == SessionStrategyState.STRUCTURE_CONFIRMED:
            if not self.active_setup:
                self.current_state = SessionStrategyState.RANGE_FINALIZED
                return None

            level = self.active_setup.target_level_val
            if self.active_setup.direction == SignalDirection.BUY:
                # Retest within tolerance + Wick rejection
                retested = (
                    candle.low <= level + self.retest_tolerance
                    and candle.close > level
                    and candle.lower_wick >= candle.range * self.min_wick_ratio
                )
                if retested:
                    self.active_setup.retest_candle_time = candle.timestamp.isoformat()
                    self._log_transition(
                        SessionStrategyState.RETEST_CONFIRMED,
                        candle,
                        primary_session,
                        f"تست مجدد سطح (Retest) و ریجکشن شدو (Wick {round(candle.lower_wick, 2)} >= {round(candle.range * self.min_wick_ratio, 2)})",
                        {"retest_low": candle.low, "retest_close": candle.close, "wick_ratio": candle.wick_ratio},
                        {"invalidation": "نقض حد ضرر"},
                    )
            else:  # SELL
                retested = (
                    candle.high >= level - self.retest_tolerance
                    and candle.close < level
                    and candle.upper_wick >= candle.range * self.min_wick_ratio
                )
                if retested:
                    self.active_setup.retest_candle_time = candle.timestamp.isoformat()
                    self._log_transition(
                        SessionStrategyState.RETEST_CONFIRMED,
                        candle,
                        primary_session,
                        f"تست مجدد سطح (Retest) و ریجکشن شدو (Wick {round(candle.upper_wick, 2)} >= {round(candle.range * self.min_wick_ratio, 2)})",
                        {"retest_high": candle.high, "retest_close": candle.close, "wick_ratio": candle.wick_ratio},
                        {"invalidation": "نقض حد ضرر"},
                    )
            return None

        # State 7: RETEST_CONFIRMED -> Formulate entry and move to ENTRY_ELIGIBLE
        elif self.current_state == SessionStrategyState.RETEST_CONFIRMED:
            if not self.active_setup:
                self.current_state = SessionStrategyState.RANGE_FINALIZED
                return None

            entry_price = candle.close
            if self.active_setup.direction == SignalDirection.BUY:
                sl = round(min(self.active_setup.sweep_candle_price, candle.low) - (candle.atr14 * self.atr_multiplier), 2)
                risk = round(entry_price - sl, 2)
                if risk > 0:
                    tp = round(entry_price + (risk * self.risk_reward_ratio), 2)
                    self.active_setup.entry_price = entry_price
                    self.active_setup.sl_price = sl
                    self.active_setup.tp_price = tp
                    self.active_setup.risk_r = risk

                    self._log_transition(
                        SessionStrategyState.ENTRY_ELIGIBLE,
                        candle,
                        primary_session,
                        f"سیگنال واجد شرایط معامله آزمایشی خرید: ورود={entry_price}، حد ضرر={sl}، حد سود={tp}، ریسک={risk}$",
                        {"entry": entry_price, "sl": sl, "tp": tp, "rr": self.risk_reward_ratio},
                        {"spread_limit": 0.50},
                    )

                    return SetupSignal(
                        setup_id="SETUP_V5_SWEEP_RECLAIM_CAUSAL",
                        setup_name="جلسه معاملاتی: Sweep + Reclaim + BOS + Retest",
                        direction=SignalDirection.BUY,
                        signal_index=len(prior_candles),
                        signal_time=candle.timestamp,
                        entry_index=len(prior_candles) + 1,
                        entry_price=entry_price,
                        sl_price=sl,
                        tp_price=tp,
                        risk_r=risk,
                        reason=f"تأیید چرخه کامل نقدینگی و بازپس‌گیری کف آسیا ({self.active_setup.target_level_val})",
                        metrics={"level": self.active_setup.target_level_name, "level_val": self.active_setup.target_level_val},
                    )
            else:  # SELL
                sl = round(max(self.active_setup.sweep_candle_price, candle.high) + (candle.atr14 * self.atr_multiplier), 2)
                risk = round(sl - entry_price, 2)
                if risk > 0:
                    tp = round(entry_price - (risk * self.risk_reward_ratio), 2)
                    self.active_setup.entry_price = entry_price
                    self.active_setup.sl_price = sl
                    self.active_setup.tp_price = tp
                    self.active_setup.risk_r = risk

                    self._log_transition(
                        SessionStrategyState.ENTRY_ELIGIBLE,
                        candle,
                        primary_session,
                        f"سیگنال واجد شرایط معامله آزمایشی فروش: ورود={entry_price}، حد ضرر={sl}، حد سود={tp}، ریسک={risk}$",
                        {"entry": entry_price, "sl": sl, "tp": tp, "rr": self.risk_reward_ratio},
                        {"spread_limit": 0.50},
                    )

                    return SetupSignal(
                        setup_id="SETUP_V5_SWEEP_RECLAIM_CAUSAL",
                        setup_name="جلسه معاملاتی: Sweep + Reclaim + BOS + Retest",
                        direction=SignalDirection.SELL,
                        signal_index=len(prior_candles),
                        signal_time=candle.timestamp,
                        entry_index=len(prior_candles) + 1,
                        entry_price=entry_price,
                        sl_price=sl,
                        tp_price=tp,
                        risk_r=risk,
                        reason=f"تأیید چرخه کامل نقدینگی و بازپس‌گیری سقف آسیا ({self.active_setup.target_level_val})",
                        metrics={"level": self.active_setup.target_level_name, "level_val": self.active_setup.target_level_val},
                    )
            return None

        # State 8: ENTRY_ELIGIBLE -> Waiting for order placement
        elif self.current_state == SessionStrategyState.ENTRY_ELIGIBLE:
            # If candle violates SL or moves away before fill
            return None

        # State 9: PAPER_ORDER -> Dispatched
        elif self.current_state == SessionStrategyState.PAPER_ORDER:
            return None

        # State 10: POSITION_MANAGEMENT -> Live position
        elif self.current_state == SessionStrategyState.POSITION_MANAGEMENT:
            return None

        # State 11: CLOSED
        elif self.current_state == SessionStrategyState.CLOSED:
            return None

        return None

    def on_order_dispatched(self, order_id: str, candle: Candle) -> None:
        """Transitions state machine to PAPER_ORDER."""
        if self.active_setup:
            self.active_setup.order_id = order_id
        sessions = self.session_mgr.get_candle_sessions(candle.timestamp)
        sess = sessions[0].value if sessions else "OFF_HOURS"
        self._log_transition(
            SessionStrategyState.PAPER_ORDER,
            candle,
            sess,
            f"ارسال سفارش مجازی {order_id} به بروکر شبیه‌ساز",
            {"order_id": order_id},
            {},
        )

    def on_position_opened(self, position_id: str, candle: Candle) -> None:
        """Transitions state machine to POSITION_MANAGEMENT."""
        if self.active_setup:
            self.active_setup.position_id = position_id
        sessions = self.session_mgr.get_candle_sessions(candle.timestamp)
        sess = sessions[0].value if sessions else "OFF_HOURS"
        self._log_transition(
            SessionStrategyState.POSITION_MANAGEMENT,
            candle,
            sess,
            f"اجرای سفارش و گشایش پوزیشن مجازی {position_id}؛ آغاز مدیریت حد ضرر و حد سود",
            {"position_id": position_id},
            {},
        )

    def on_position_closed(self, candle: Candle, close_reason: str) -> None:
        """Transitions state machine to CLOSED."""
        sessions = self.session_mgr.get_candle_sessions(candle.timestamp)
        sess = sessions[0].value if sessions else "OFF_HOURS"
        self._log_transition(
            SessionStrategyState.CLOSED,
            candle,
            sess,
            f"بسته شدن موقعیت معاملاتی به دلیل: {close_reason}",
            {"close_reason": close_reason},
            {},
        )

    def get_state_summary(self) -> Dict[str, Any]:
        """Returns snapshot of current state machine context for UI/API."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT transition_id, timestamp, candle_id, session, trade_date,
                       source_data, from_state, to_state, ref_high, ref_low,
                       confirmation_conditions, invalidating_conditions,
                       transition_reason, strategy_version
                FROM strategy_state_transitions
                ORDER BY transition_id DESC
                LIMIT 15
                """
            ).fetchall()

        history = [dict(r) for r in rows]

        return {
            "current_state": self.current_state.value,
            "trade_date": self.current_trade_date,
            "ref_high": self.ref_high,
            "ref_low": self.ref_low,
            "last_reason": self.last_transition_reason,
            "last_candle_id": self.last_candle_id,
            "strategy_version": self.strategy_version,
            "active_setup": asdict(self.active_setup) if self.active_setup else None,
            "recent_transitions": history,
        }
