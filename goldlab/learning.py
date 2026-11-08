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
    ) -> TradeAutopsy:
        """Evaluates trade execution quality and determines the precise learning verdict."""
        is_long = side.upper() == "BUY"

        # Calculate MAE / MFE
        if is_long:
            mae = abs(entry_price - (max_adverse_price if max_adverse_price else min(entry_price, exit_price)))
            mfe = abs((max_favorable_price if max_favorable_price else max(entry_price, exit_price)) - entry_price)
        else:
            mae = abs((max_adverse_price if max_adverse_price else max(entry_price, exit_price)) - entry_price)
            mfe = abs(entry_price - (max_favorable_price if max_favorable_price else min(entry_price, exit_price)))

        # Verdict heuristic
        if pnl > 0:
            if entry_regime in ("HIGH_SPREAD", "NEWS_DRIVEN"):
                verdict = AutopsyVerdict.LUCK_WIN
                takeaway = "سود تصادفی در شرایط پرریسک و اخبار نامساعد؛ لزوم پایبندی به بلک‌اوت خبری."
            else:
                verdict = AutopsyVerdict.GOOD_WIN
                takeaway = f"معامله ساختاریافته عالی با برآیند مثبت R={r_multiple:.2f}."
        else:
            if entry_regime == "TRENDING" and setup_id in ("S1_ASIA_SWEEP", "S4_NEW_YORK_REVERSAL"):
                verdict = AutopsyVerdict.ADVERSE_REGIME
                takeaway = "ورود معکوس در جهت خلاف روند پرقدرت روزانه؛ نیازمند فیلتر تایید مومنتوم."
            elif entry_wick_ratio > 0.50:
                verdict = AutopsyVerdict.CHASED_PRICE
                takeaway = "ورود روی سایه بلند (تله نقدینگی) قبل از تکمیل بسته شدن بدنه کندل."
            elif abs(entry_price - sl_price) < 0.80:
                verdict = AutopsyVerdict.TIGHT_STOP
                takeaway = "حد ضرر فشرده‌تر از نوسان ذاتی طلا؛ حد ضرر باید به پشت سویینگ پایدار منتقل شود."
            else:
                verdict = AutopsyVerdict.GOOD_LOSS
                takeaway = "ضرر طبیعی و سیستماتیک در چارچوب لبه آماری؛ مدیریت ریسک کاملاً رعایت شد."

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
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trade_autopsies
                (autopsy_id, trade_id, setup_id, side, pnl, r_multiple, mae_dollars, mfe_dollars, entry_regime, wick_ratio_at_entry, verdict, takeaway_persian, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    autopsy.created_at,
                ),
            )
            conn.commit()

        return autopsy

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
