"""
Causal Event-Driven Session Trading State Machine for XAUUSD (Master Prompt V6).
Enforces a strict 10-state progression with zero lookahead, deterministic SQLite logging,
Shadow Mode proposal evaluation, and fail-closed risk management:
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
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from goldlab.calendar import MacroNewsCalendar
from goldlab.market_safety import MarketQuote, execution_gate
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
    bars_in_state: int = 0


@dataclass
class ShadowProposal:
    proposal_id: str
    candle_id: str
    timestamp: str
    direction: str
    setup_name: str
    target_level: str
    target_price: float
    entry_price: float
    sl_price: float
    tp_price: float
    risk_r: float
    spread: Optional[float]
    status: str  # "ELIGIBLE_SHADOW", "REJECTED_SPREAD", "REJECTED_NEWS", "REJECTED_RISK"
    rejection_reason: str


class SessionTradingStateMachine:
    """
    Evaluates market candles sequentially and causally.
    Transitions through 10 formal states, records all state changes and shadow proposals
    into SQLite, and enforces restart recovery.
    """

    def __init__(
        self,
        strategy_version: str = "v6.0.0-causal",
        source_data: str = "OANDA_V20",
        db_path: str = "data/xauusd_lab.sqlite",
        session_mgr: Optional[SessionManager] = None,
        retest_tolerance_pips: float = 0.50,
        min_wick_ratio: float = 0.35,
        risk_reward_ratio: float = 2.0,
        atr_multiplier: float = 1.0,
        shadow_mode: bool = True,
        max_spread: float = 0.50,
    ) -> None:
        self.strategy_version = strategy_version
        self.source_data = source_data
        self.db_path = Path(db_path)
        self.session_mgr = session_mgr or SessionManager()
        self.retest_tolerance = retest_tolerance_pips
        self.min_wick_ratio = min_wick_ratio
        self.risk_reward_ratio = risk_reward_ratio
        self.atr_multiplier = atr_multiplier
        self.max_spread = max_spread

        self.shadow_mode = shadow_mode
        self.live_execution_enabled: bool = False
        self.current_state: SessionStrategyState = SessionStrategyState.WAITING_FOR_SESSION
        self.current_trade_date: Optional[str] = None
        self.ref_high: Optional[float] = None
        self.ref_low: Optional[float] = None
        self.active_setup: Optional[ActiveSetupContext] = None
        self.last_transition_reason: str = "Initialized"
        self.last_candle_id: str = ""
        self.processed_candles_count: int = 0

        self._init_db()
        self._restore_state_from_db()

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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state_machine_processed_candles (
                    candle_id TEXT PRIMARY KEY,
                    processed_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shadow_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    candle_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    setup_name TEXT NOT NULL,
                    target_level TEXT NOT NULL,
                    target_price REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    sl_price REAL NOT NULL,
                    tp_price REAL NOT NULL,
                    risk_r REAL NOT NULL,
                    spread REAL,
                    status TEXT NOT NULL,
                    rejection_reason TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _restore_state_from_db(self) -> None:
        """Restores the latest valid state from SQLite if available."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                last_row = conn.execute(
                    """
                    SELECT to_state, trade_date, ref_high, ref_low,
                           transition_reason, candle_id
                    FROM strategy_state_transitions
                    ORDER BY transition_id DESC
                    LIMIT 1
                    """
                ).fetchone()
                if last_row:
                    try:
                        self.current_state = SessionStrategyState(last_row["to_state"])
                        self.current_trade_date = last_row["trade_date"]
                        self.ref_high = last_row["ref_high"]
                        self.ref_low = last_row["ref_low"]
                        self.last_transition_reason = last_row["transition_reason"]
                        self.last_candle_id = last_row["candle_id"]
                    except ValueError:
                        pass
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM state_machine_processed_candles"
                ).fetchone()[0]
                self.processed_candles_count = cnt
        except Exception:
            pass

    def is_candle_processed(self, candle_id: str) -> bool:
        """Checks if a candle was already processed."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM state_machine_processed_candles WHERE candle_id = ?",
                (candle_id,),
            ).fetchone()
            return row is not None

    def mark_candle_processed(self, candle_id: str) -> None:
        """Marks a candle as processed in SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO state_machine_processed_candles (candle_id, processed_at) VALUES (?, ?)",
                (candle_id, datetime.now(TZ_UTC).isoformat()),
            )
            conn.commit()
        self.processed_candles_count += 1

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
        if self.active_setup:
            self.active_setup.bars_in_state = 0

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
            # Never include the first bar after 00:00 NY in the completed
            # 20:00–00:00 NY reference range; its extrema are future data
            # relative to the finalized reference for London/NY setups.
            if SessionName.ASIA_REFERENCE in sessions:
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

            self.active_setup.bars_in_state += 1
            level = self.active_setup.target_level_val

            # Invalidation Timeout: 8 bars without reclaim
            if self.active_setup.bars_in_state >= 8:
                self._log_transition(
                    SessionStrategyState.CLOSED,
                    candle,
                    primary_session,
                    "ابطال ستاپ: گذشت بیش از ۸ کندل بدون تأیید بازپس‌گیری سطح (Reclaim Timeout)",
                    {},
                    {"timeout_bars": self.active_setup.bars_in_state},
                )
                self.active_setup = None
                return None

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
                    self.active_setup = None
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
                    self.active_setup = None
            return None

        # State 5: RECLAIM_CONFIRMED
        elif self.current_state == SessionStrategyState.RECLAIM_CONFIRMED:
            if not self.active_setup:
                self.current_state = SessionStrategyState.RANGE_FINALIZED
                return None

            self.active_setup.bars_in_state += 1

            # Invalidation Timeout: 8 bars without BOS
            if self.active_setup.bars_in_state >= 8:
                self._log_transition(
                    SessionStrategyState.CLOSED,
                    candle,
                    primary_session,
                    "ابطال ستاپ: عدم شکست ساختار در ۸ کندل پس از بازپس‌گیری (BOS Timeout)",
                    {},
                    {"timeout_bars": self.active_setup.bars_in_state},
                )
                self.active_setup = None
                return None

            if self.active_setup.direction == SignalDirection.BUY:
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

            self.active_setup.bars_in_state += 1

            # Invalidation Timeout: 12 bars without retest
            if self.active_setup.bars_in_state >= 12:
                self._log_transition(
                    SessionStrategyState.CLOSED,
                    candle,
                    primary_session,
                    "ابطال ستاپ: عدم پولبک و ریجکشن شدو در ۱۲ کندل پس از شکست ساختار (Retest Timeout)",
                    {},
                    {"timeout_bars": self.active_setup.bars_in_state},
                )
                self.active_setup = None
                return None

            level = self.active_setup.target_level_val
            if self.active_setup.direction == SignalDirection.BUY:
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
            if self.active_setup:
                self.active_setup.bars_in_state += 1
                if self.active_setup.bars_in_state >= 3:
                    self._log_transition(
                        SessionStrategyState.CLOSED,
                        candle,
                        primary_session,
                        "پایان پنجره مجاز ورود سیگنال (Entry Window Expired)",
                        {},
                        {"expired_bars": self.active_setup.bars_in_state},
                    )
                    self.active_setup = None
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

    def process_completed_5m_candles(
        self,
        candles: List[Candle],
        live_quote: Optional[MarketQuote] = None,
        calendar: Optional[MacroNewsCalendar] = None,
    ) -> List[SetupSignal]:
        """
        Feeds a batch of completed 5m candles sequentially and causally.
        Deduplicates each candle in SQLite to ensure exact-once processing.
        In Shadow Mode: evaluates filtering rules and records shadow proposals.
        """
        if not candles:
            return []

        stats_series = self.session_mgr.calculate_as_of_session_stats_series(candles)
        signals: List[SetupSignal] = []

        for i, candle in enumerate(candles):
            cid = candle.timestamp.isoformat()
            if self.is_candle_processed(cid):
                continue

            stat_i = stats_series[i] if i < len(stats_series) else None
            sig = self.process_candle(candle, candles[:i], session_stats=stat_i)

            if sig:
                signals.append(sig)
                self._record_shadow_proposal(sig, candle, live_quote, calendar)

            self.mark_candle_processed(cid)

        return signals

    def _record_shadow_proposal(
        self,
        sig: SetupSignal,
        candle: Candle,
        live_quote: Optional[MarketQuote],
        calendar: Optional[MacroNewsCalendar],
    ) -> None:
        """Evaluates filters and stores a shadow entry proposal in SQLite."""
        pid = f"PROP_{candle.timestamp.strftime('%Y%m%d_%H%M%S')}_{sig.direction.value}"
        spread = live_quote.spread if live_quote else None

        # Evaluate risk/filtering conditions
        status = "ELIGIBLE_SHADOW"
        reason = "واجد شرایط کامل در حالت سایه (Shadow Mode - بدون سفارش زنده)"

        is_blackout, news_reason = calendar.is_blackout(candle.timestamp) if calendar else (False, "")
        quote_ok, quote_reason = execution_gate(
            live_quote, now=candle.timestamp + timedelta(minutes=5),
        )
        if is_blackout:
            status = "REJECTED_NEWS"
            reason = f"توقف به دلیل انتشار خبر اقتصادی حساس ({news_reason})"
        elif spread is not None and spread > self.max_spread:
            status = "REJECTED_SPREAD"
            reason = f"اسپرد جاری ({spread:.2f}$) بالاتر از سقف مجاز است."
        elif not quote_ok:
            status = "REJECTED_QUOTE"
            reason = "مظنه معتبر در زمان بسته‌شدن کندل موجود نیست: " + quote_reason
        elif sig.risk_r <= 0 or (abs(sig.tp_price - sig.entry_price) / sig.risk_r) < self.risk_reward_ratio:
            status = "REJECTED_RISK"
            reason = f"نسبت ریوارد به ریسک کمتر از سقف مجاز ({self.risk_reward_ratio}R) است."

        prop = ShadowProposal(
            proposal_id=pid,
            candle_id=candle.timestamp.isoformat(),
            timestamp=candle.timestamp.isoformat(),
            direction=sig.direction.value,
            setup_name=sig.setup_name,
            target_level=sig.metrics.get("level", ""),
            target_price=sig.metrics.get("level_val", 0.0),
            entry_price=sig.entry_price,
            sl_price=sig.sl_price,
            tp_price=sig.tp_price,
            risk_r=sig.risk_r,
            spread=spread,
            status=status,
            rejection_reason=reason,
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO shadow_proposals (
                    proposal_id, candle_id, timestamp, direction, setup_name,
                    target_level, target_price, entry_price, sl_price, tp_price,
                    risk_r, spread, status, rejection_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prop.proposal_id,
                    prop.candle_id,
                    prop.timestamp,
                    prop.direction,
                    prop.setup_name,
                    prop.target_level,
                    prop.target_price,
                    prop.entry_price,
                    prop.sl_price,
                    prop.tp_price,
                    prop.risk_r,
                    prop.spread,
                    prop.status,
                    prop.rejection_reason,
                ),
            )
            conn.commit()

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

    def on_position_opened(self, position_id: str, candle: Candle | MarketQuote) -> None:
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

    def on_position_closed(self, candle: Candle | MarketQuote, close_reason: str) -> None:
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
        self.active_setup = None

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

            prop_rows = conn.execute(
                """
                SELECT proposal_id, candle_id, timestamp, direction, setup_name,
                       target_level, target_price, entry_price, sl_price, tp_price,
                       risk_r, spread, status, rejection_reason
                FROM shadow_proposals
                ORDER BY timestamp DESC
                LIMIT 10
                """
            ).fetchall()

            processed_count = conn.execute(
                "SELECT COUNT(*) FROM state_machine_processed_candles"
            ).fetchone()[0]

        history = [dict(r) for r in rows]
        proposals = [dict(p) for p in prop_rows]

        # Explicit truth: If not yet fed any closed candle, mark NOT_WIRED_TO_LIVE_CANDLE_LOOP.
        # Once candles are fed, report SHADOW_MODE.
        runtime_status = (
            "SHADOW_MODE"
            if processed_count > 0 or self.processed_candles_count > 0
            else "NOT_WIRED_TO_LIVE_CANDLE_LOOP"
        )

        return {
            "current_state": self.current_state.value,
            "runtime_status": runtime_status,
            "shadow_mode": self.shadow_mode,
            "enabled_for_auto_trading": self.live_execution_enabled,
            "trade_date": self.current_trade_date,
            "ref_high": self.ref_high,
            "ref_low": self.ref_low,
            "last_reason": self.last_transition_reason,
            "last_candle_id": self.last_candle_id,
            "strategy_version": self.strategy_version,
            "active_setup": asdict(self.active_setup) if self.active_setup else None,
            "processed_candles_count": processed_count,
            "recent_transitions": history,
            "recent_proposals": proposals,
        }

    def get_shadow_proposals(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns recent shadow proposals from SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT proposal_id, candle_id, timestamp, direction, setup_name,
                       target_level, target_price, entry_price, sl_price, tp_price,
                       risk_r, spread, status, rejection_reason
                FROM shadow_proposals
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
