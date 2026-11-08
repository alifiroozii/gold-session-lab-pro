"""
Learning, Mistake Analysis & Hypothesis Registry for Gold Autonomous Trading Research Lab.
Performs post-trade autopsies (MAE, MFE, Regime, Wick dynamics) and maintains
the quantitative Hypothesis Registry to prevent repeating trading mistakes.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

TZ_UTC = timezone.utc


class AutopsyVerdict(str, Enum):
    GOOD_LOSS = "GOOD_LOSS"              # Followed rules, valid edge, normal statistical loss
    CHASED_PRICE = "CHASED_PRICE"        # Entered after excessive extension without clean retest
    TIGHT_STOP = "TIGHT_STOP"            # SL within normal market noise (< 1.0 ATR)
    ADVERSE_REGIME = "ADVERSE_REGIME"    # Traded mean-reversion in strong trend or during high spread
    GOOD_WIN = "GOOD_WIN"                # High quality setup, respected structure, clean TP
    LUCK_WIN = "LUCK_WIN"                # Violated rules or entered in adverse regime, but market bailed out


class FailureCategory(str, Enum):
    NORMAL_STATISTICAL_LOSS = "NORMAL_STATISTICAL_LOSS"  # A: Valid strategy executions that lost money
    EXECUTION_DEFECT = "EXECUTION_DEFECT"                # B: Incorrect fills, duplicate orders, wrong sizing
    STRATEGY_WEAKNESS = "STRATEGY_WEAKNESS"              # C: Hypotheses supported by sufficient evidence
    DATA_FAILURE = "DATA_FAILURE"                        # D: Invalid, unavailable or stale market information
    PROFITABLE_TRADE = "PROFITABLE_TRADE"                # Trade ended with positive P&L


class HypothesisStatus(str, Enum):
    PROPOSED = "PROPOSED"
    TESTING = "TESTING"
    INCONCLUSIVE = "INCONCLUSIVE"
    REJECTED = "REJECTED"
    PROMISING = "PROMISING"
    APPROVED = "APPROVED"
    ARCHIVED = "ARCHIVED"


@dataclass
class TradeAutopsy:
    autopsy_id: str
    trade_id: str
    setup_id: str
    side: str
    pnl: float
    r_multiple: float
    mae_dollars: float
    mfe_dollars: float
    entry_regime: str
    wick_ratio_at_entry: float
    verdict: AutopsyVerdict
    takeaway_persian: str
    strategy_version: str = "Champion-Baseline-V1"
    signal_time: str = ""
    entry_time: str = ""
    exit_time: str = ""
    entry_bid: float = 0.0
    entry_ask: float = 0.0
    exit_bid: float = 0.0
    exit_ask: float = 0.0
    lot_size: float = 0.1
    exposure_dollars: float = 0.0
    sl_price: float = 0.0
    tp_price: float = 0.0
    spread_at_entry: float = 0.0
    slippage_dollars: float = 0.0
    commission_dollars: float = 0.0
    trading_session: str = "LONDON_NY_OVERLAP"
    entry_rationale: str = ""
    exit_reason: str = ""
    risk_violations: str = ""
    followed_approved_strategy: bool = True
    failure_category: FailureCategory = FailureCategory.NORMAL_STATISTICAL_LOSS
    what_went_wrong: str = ""
    what_not_to_repeat: str = ""
    pre_trade_checklist: str = ""
    gating_rule: str = ""
    confidence: str = "VERIFIED"
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(TZ_UTC).isoformat()


@dataclass
class QuantitativeHypothesis:
    hypothesis_id: str
    title: str
    rationale: str
    target_metric: str
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    sample_size: int = 0
    p_value: float = 1.0
    evidence_summary: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = datetime.now(TZ_UTC).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


class MistakeAnalyzerAndHypothesisRegistry:
    """Performs deep autopsies on closed trades and systematically tracks research hypotheses."""

    def __init__(self, db_path: str = "data/xauusd_lab.sqlite") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_autopsies (
                    autopsy_id TEXT PRIMARY KEY,
                    trade_id TEXT NOT NULL,
                    setup_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    pnl REAL NOT NULL,
                    r_multiple REAL NOT NULL,
                    mae_dollars REAL NOT NULL,
                    mfe_dollars REAL NOT NULL,
                    entry_regime TEXT NOT NULL,
                    wick_ratio_at_entry REAL NOT NULL,
                    verdict TEXT NOT NULL,
                    takeaway_persian TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            # Safe schema migration for rich Phase 5 autopsy metadata
            cursor = conn.execute("PRAGMA table_info(trade_autopsies);")
            existing_cols = {row[1] for row in cursor.fetchall()}
            extra_cols = [
                ("strategy_version", "TEXT DEFAULT 'Champion-Baseline-V1'"),
                ("signal_time", "TEXT DEFAULT ''"),
                ("entry_time", "TEXT DEFAULT ''"),
                ("exit_time", "TEXT DEFAULT ''"),
                ("entry_bid", "REAL DEFAULT 0.0"),
                ("entry_ask", "REAL DEFAULT 0.0"),
                ("exit_bid", "REAL DEFAULT 0.0"),
                ("exit_ask", "REAL DEFAULT 0.0"),
                ("lot_size", "REAL DEFAULT 0.1"),
                ("exposure_dollars", "REAL DEFAULT 0.0"),
                ("sl_price", "REAL DEFAULT 0.0"),
                ("tp_price", "REAL DEFAULT 0.0"),
                ("spread_at_entry", "REAL DEFAULT 0.0"),
                ("slippage_dollars", "REAL DEFAULT 0.0"),
                ("commission_dollars", "REAL DEFAULT 0.0"),
                ("trading_session", "TEXT DEFAULT ''"),
                ("entry_rationale", "TEXT DEFAULT ''"),
                ("exit_reason", "TEXT DEFAULT ''"),
                ("risk_violations", "TEXT DEFAULT ''"),
                ("followed_approved_strategy", "INTEGER DEFAULT 1"),
                ("failure_category", "TEXT DEFAULT 'NORMAL_STATISTICAL_LOSS'"),
                ("what_went_wrong", "TEXT DEFAULT ''"),
                ("what_not_to_repeat", "TEXT DEFAULT ''"),
                ("pre_trade_checklist", "TEXT DEFAULT ''"),
                ("gating_rule", "TEXT DEFAULT ''"),
                ("confidence", "TEXT DEFAULT 'VERIFIED'"),
            ]
            for col_name, col_type in extra_cols:
                if col_name not in existing_cols:
                    conn.execute(f"ALTER TABLE trade_autopsies ADD COLUMN {col_name} {col_type};")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hypotheses (
                    hypothesis_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    target_metric TEXT NOT NULL,
                    status TEXT NOT NULL,
                    sample_size INTEGER NOT NULL DEFAULT 0,
                    p_value REAL NOT NULL DEFAULT 1.0,
                    evidence_summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def perform_autopsy(
        self,
        trade_id: str,
        setup_id: str,
        side: str,
        pnl: float,
        r_multiple: float,
        entry_price: float,
        exit_price: float,
        sl_price: float,
        tp_price: float,
        entry_regime: str = "RANGING",
        entry_wick_ratio: float = 0.20,
        max_adverse_price: Optional[float] = None,
        max_favorable_price: Optional[float] = None,
        strategy_version: str = "Champion-Baseline-V1",
        signal_time: str = "",
        entry_time: str = "",
        exit_time: str = "",
        entry_bid: float = 0.0,
        entry_ask: float = 0.0,
        exit_bid: float = 0.0,
        exit_ask: float = 0.0,
        lot_size: float = 0.1,
        exposure_dollars: float = 0.0,
        spread_at_entry: float = 0.0,
        slippage_dollars: float = 0.0,
        commission_dollars: float = 0.0,
        trading_session: str = "LONDON_NY_OVERLAP",
        entry_rationale: str = "",
        exit_reason: str = "",
        risk_violations: str = "",
        followed_approved_strategy: bool = True,
    ) -> TradeAutopsy:
        """Evaluates trade execution quality, categorizes failure into 4 classes, and generates actionable Persian guidance."""
        is_long = side.upper() == "BUY"

        # Calculate MAE / MFE
        if is_long:
            mae = abs(entry_price - (max_adverse_price if max_adverse_price else min(entry_price, exit_price)))
            mfe = abs((max_favorable_price if max_favorable_price else max(entry_price, exit_price)) - entry_price)
        else:
            mae = abs((max_adverse_price if max_adverse_price else max(entry_price, exit_price)) - entry_price)
            mfe = abs(entry_price - (max_favorable_price if max_favorable_price else min(entry_price, exit_price)))

        # Verdict heuristic and 4-class failure categorization
        if pnl > 0:
            if entry_regime in ("HIGH_SPREAD", "NEWS_DRIVEN"):
                verdict = AutopsyVerdict.LUCK_WIN
                takeaway = "سود تصادفی در شرایط پرریسک و اخبار نامساعد؛ لزوم پایبندی به بلک‌اوت خبری."
            else:
                verdict = AutopsyVerdict.GOOD_WIN
                takeaway = f"معامله ساختاریافته عالی با برآیند مثبت R={r_multiple:.2f}."
            failure_category = FailureCategory.PROFITABLE_TRADE
            what_went_wrong = "معامله طبق قوانین با سود بسته شد."
            what_not_to_repeat = "از خروج شتابزده یا دستکاری حد سود پیش از تارگت اجتناب شود."
            pre_trade_checklist = "بررسی ساختار تاییدشده، تطابق سشن و عدم وجود رویدادهای قرمز خبری."
            gating_rule = "STRATEGY_EDGE_VALIDATED"
            confidence = "VERIFIED"
        else:
            if spread_at_entry > 0.50 or "STALE" in risk_violations or "DISCONNECTED" in risk_violations:
                verdict = AutopsyVerdict.ADVERSE_REGIME
                takeaway = "نوسان اسپرد بیش از حد مجاز یا داده نامعتبر فید قیمت."
                failure_category = FailureCategory.DATA_FAILURE
                what_went_wrong = "ورود در شرایط اختلال فید قیمت یا اسپرد غیرعادی."
                what_not_to_repeat = "معامله در زمان قطعی فید یا اسپرد فراتر از ۰.۵۰ دلار."
                pre_trade_checklist = "اعتبارسنجی تازگی مظنه (< ۳۰ ثانیه) و وضعیت بازار پیش از ورود."
                gating_rule = "FEED_HEALTH_GATE"
                confidence = "VERIFIED"
            elif risk_violations or not followed_approved_strategy or lot_size > 2.0:
                verdict = AutopsyVerdict.CHASED_PRICE
                takeaway = f"تخطی از قوانین ریسک یا نقص در اجرای سفارش ({risk_violations or 'حجم نامتعارف'})."
                failure_category = FailureCategory.EXECUTION_DEFECT
                what_went_wrong = "نقص در مدیریت ریسک، اندازه معامله یا اجرای غیرسیستمی سفارش."
                what_not_to_repeat = "ورود بدون رعایت فرمول حجم ۰.۵٪ یا جابجایی حد ضرر اولیه."
                pre_trade_checklist = "اعتبارسنجی محاسبه حجم، مارجین آزاد و تایید حد ضرر در بروکر."
                gating_rule = "INDEPENDENT_RISK_GUARDIAN"
                confidence = "VERIFIED"
            elif entry_regime == "TRENDING" and setup_id in ("SETUP_1_ASIA_BO_RETEST", "SETUP_2_SWEEP_RECLAIM_BOS") or entry_wick_ratio > 0.50:
                verdict = AutopsyVerdict.ADVERSE_REGIME if entry_regime == "TRENDING" else AutopsyVerdict.CHASED_PRICE
                takeaway = "ورود خلاف روند قدرتمند یا ورود روی سایه کندل پیش از تثبیت کلوز."
                failure_category = FailureCategory.STRATEGY_WEAKNESS
                what_went_wrong = "نقص در تطابق با رژیم بازار یا ورود شتابزده پیش از تایید شکست ساختار."
                what_not_to_repeat = "معامله ستاپ بازگشتی در جهت خلاف روند پرقدرت روزانه."
                pre_trade_checklist = "تایید ساختار چندزمانه و رصد مومنتوم با اندیکاتورهای ساختاری."
                gating_rule = "REGIME_MOMENTUM_FILTER"
                confidence = "PROVISIONAL"
            else:
                verdict = AutopsyVerdict.GOOD_LOSS
                takeaway = "ضرر طبیعی و سیستماتیک در چارچوب لبه آماری؛ مدیریت ریسک کاملاً رعایت شد."
                failure_category = FailureCategory.NORMAL_STATISTICAL_LOSS
                what_went_wrong = "ضرر عادی در چارچوب واریانس آماری استراتژی؛ کلیه قواعد رعایت شدند."
                what_not_to_repeat = "افزایش حجم احساسی جهت انتقام‌گیری از بازار (Revenge Trading)."
                pre_trade_checklist = "پایبندی ۱۰۰٪ به قوانین ستاپ، پذیرش زیان به عنوان هزینه معامله‌گری."
                gating_rule = "ACCEPTABLE_STATISTICAL_VARIANCE"
                confidence = "VERIFIED"

        autopsy = TradeAutopsy(
            autopsy_id=f"AUT-{uuid.uuid4().hex[:8].upper()}",
            trade_id=trade_id,
            setup_id=setup_id,
            side=side,
            pnl=round(pnl, 2),
            r_multiple=round(r_multiple, 2),
            mae_dollars=round(mae, 2),
            mfe_dollars=round(mfe, 2),
            entry_regime=entry_regime,
            wick_ratio_at_entry=round(entry_wick_ratio, 2),
            verdict=verdict,
            takeaway_persian=takeaway,
            strategy_version=strategy_version,
            signal_time=signal_time,
            entry_time=entry_time,
            exit_time=exit_time,
            entry_bid=entry_bid,
            entry_ask=entry_ask,
            exit_bid=exit_bid,
            exit_ask=exit_ask,
            lot_size=lot_size,
            exposure_dollars=exposure_dollars,
            sl_price=sl_price,
            tp_price=tp_price,
            spread_at_entry=spread_at_entry,
            slippage_dollars=slippage_dollars,
            commission_dollars=commission_dollars,
            trading_session=trading_session,
            entry_rationale=entry_rationale,
            exit_reason=exit_reason,
            risk_violations=risk_violations,
            followed_approved_strategy=followed_approved_strategy,
            failure_category=failure_category,
            what_went_wrong=what_went_wrong,
            what_not_to_repeat=what_not_to_repeat,
            pre_trade_checklist=pre_trade_checklist,
            gating_rule=gating_rule,
            confidence=confidence,
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trade_autopsies
                (autopsy_id, trade_id, setup_id, side, pnl, r_multiple, mae_dollars, mfe_dollars,
                 entry_regime, wick_ratio_at_entry, verdict, takeaway_persian, strategy_version,
                 signal_time, entry_time, exit_time, entry_bid, entry_ask, exit_bid, exit_ask,
                 lot_size, exposure_dollars, sl_price, tp_price, spread_at_entry, slippage_dollars,
                 commission_dollars, trading_session, entry_rationale, exit_reason, risk_violations,
                 followed_approved_strategy, failure_category, what_went_wrong, what_not_to_repeat,
                 pre_trade_checklist, gating_rule, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    autopsy.autopsy_id,
                    autopsy.trade_id,
                    autopsy.setup_id,
                    autopsy.side,
                    autopsy.pnl,
                    autopsy.r_multiple,
                    autopsy.mae_dollars,
                    autopsy.mfe_dollars,
                    autopsy.entry_regime,
                    autopsy.wick_ratio_at_entry,
                    autopsy.verdict.value,
                    autopsy.takeaway_persian,
                    autopsy.strategy_version,
                    autopsy.signal_time,
                    autopsy.entry_time,
                    autopsy.exit_time,
                    autopsy.entry_bid,
                    autopsy.entry_ask,
                    autopsy.exit_bid,
                    autopsy.exit_ask,
                    autopsy.lot_size,
                    autopsy.exposure_dollars,
                    autopsy.sl_price,
                    autopsy.tp_price,
                    autopsy.spread_at_entry,
                    autopsy.slippage_dollars,
                    autopsy.commission_dollars,
                    autopsy.trading_session,
                    autopsy.entry_rationale,
                    autopsy.exit_reason,
                    autopsy.risk_violations,
                    1 if autopsy.followed_approved_strategy else 0,
                    autopsy.failure_category.value,
                    autopsy.what_went_wrong,
                    autopsy.what_not_to_repeat,
                    autopsy.pre_trade_checklist,
                    autopsy.gating_rule,
                    autopsy.confidence,
                    autopsy.created_at,
                ),
            )
            conn.commit()

        return autopsy

    def get_next_time_guidance(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Returns actionable Next-Time Guidance extracted from post-trade autopsies."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT autopsy_id, trade_id, setup_id, side, pnl, verdict, failure_category,
                       what_went_wrong, what_not_to_repeat, pre_trade_checklist, gating_rule,
                       confidence, takeaway_persian, created_at
                FROM trade_autopsies
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def register_hypothesis(
        self,
        title: str,
        rationale: str,
        target_metric: str,
    ) -> QuantitativeHypothesis:
        """Adds a quantitative thesis into the research backlog."""
        hyp = QuantitativeHypothesis(
            hypothesis_id=f"HYP-{uuid.uuid4().hex[:6].upper()}",
            title=title,
            rationale=rationale,
            target_metric=target_metric,
            status=HypothesisStatus.PROPOSED,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO hypotheses
                (hypothesis_id, title, rationale, target_metric, status, sample_size, p_value, evidence_summary, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hyp.hypothesis_id,
                    hyp.title,
                    hyp.rationale,
                    hyp.target_metric,
                    hyp.status.value,
                    hyp.sample_size,
                    hyp.p_value,
                    hyp.evidence_summary,
                    hyp.created_at,
                    hyp.updated_at,
                ),
            )
            conn.commit()
        return hyp

    def update_hypothesis_status(
        self,
        hypothesis_id: str,
        status: HypothesisStatus,
        sample_size: int,
        p_value: float,
        evidence: str,
    ) -> None:
        now = datetime.now(TZ_UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE hypotheses
                SET status = ?, sample_size = ?, p_value = ?, evidence_summary = ?, updated_at = ?
                WHERE hypothesis_id = ?
                """,
                (status.value, sample_size, p_value, evidence, now, hypothesis_id),
            )
            conn.commit()

    def list_autopsies(self, limit: int = 50) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM trade_autopsies ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def list_hypotheses(self, limit: int = 50) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM hypotheses ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
