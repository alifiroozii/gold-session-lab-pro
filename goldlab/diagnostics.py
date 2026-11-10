"""
Diagnostics & Error Categorization Engine for Gold Autonomous Trading Research Lab.
Categorizes system errors, distinguishes normal market losses from bugs,
and logs structured incidents into SQLite.
"""

from __future__ import annotations

import sqlite3
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

TZ_UTC = timezone.utc


class IncidentCategory(str, Enum):
    SOFTWARE_BUG = "SOFTWARE_BUG"              # Syntax, type error, null pointer, unhandled exception
    TRADING_LOGIC = "TRADING_LOGIC"            # Lookahead bias, invalid setup trigger, SL/TP anomaly
    PAPER_EXECUTION = "PAPER_EXECUTION"        # Slippage mismatch, ledger imbalance, rejected order
    RESEARCH_ERROR = "RESEARCH_ERROR"          # Overfitting, data leakage, sample size too small
    MARKET_LOSS = "MARKET_LOSS"                # Normal statistical drawdown within strategy expectancy


class IncidentSeverity(str, Enum):
    CRITICAL = "CRITICAL"    # System halting (ledger corruption, infinite loop, process crash)
    HIGH = "HIGH"            # Component failure (feed disconnected, broker reject, risk breach)
    MEDIUM = "MEDIUM"        # Degraded operation (stale candle, missing optional field, retry)
    LOW = "LOW"              # Minor anomaly (slow response, non-critical warning, UI glitch)


@dataclass
class DiagnosticIncident:
    incident_id: str
    category: IncidentCategory
    severity: IncidentSeverity
    title: str
    description: str
    error_type: str
    stack_trace: str
    context_data: Dict[str, Any]
    suggested_fix: str
    resolved: bool = False
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(TZ_UTC).isoformat()


class DiagnosticsEngine:
    """Monitors, categorizes, and persists runtime incidents and system anomalies."""

    def __init__(self, db_path: str = "data/xauusd_lab.sqlite") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS diagnostics_incidents (
                    incident_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    stack_trace TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    suggested_fix TEXT NOT NULL,
                    resolved INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def categorize_exception(
        self,
        exc: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> DiagnosticIncident:
        """Analyzes an unhandled exception and generates a categorized diagnostic incident."""
        ctx = context or {}
        exc_type = type(exc).__name__
        tb = traceback.format_exc()
        msg = str(exc)

        # 1. Check for Paper Execution / Ledger issues
        if "ledger" in msg.lower() or "balance" in msg.lower() or "margin" in msg.lower():
            cat = IncidentCategory.PAPER_EXECUTION
            sev = IncidentSeverity.CRITICAL if "corrupt" in msg.lower() else IncidentSeverity.HIGH
            title = f"خطای اجرای بروکر مجازی: {exc_type}"
            fix = "بررسی دفتر کل دوطرفه و تراز مالی حساب در paper_broker.py"

        # 2. Check for Trading Logic issues (Lookahead, Setup, Sl/TP)
        elif any(k in msg.lower() for k in ["lookahead", "bias", "setup", "sl_price", "tp_price"]):
            cat = IncidentCategory.TRADING_LOGIC
            sev = IncidentSeverity.HIGH
            title = f"خطای منطق معاملاتی یا ساختار بازار: {exc_type}"
            fix = "اعتبارسنجی کندل سیگنال و محاسبه پیوت در market_structure.py / setups.py"

        # 3. Check for Research / Data issues
        elif any(k in msg.lower() for k in ["leakage", "split", "resample", "stale"]):
            cat = IncidentCategory.RESEARCH_ERROR
            sev = IncidentSeverity.MEDIUM
            fix = "بازبینی تفکیک نمونه داخل/خارج و بازنمونه‌گیری کندل‌ها در data.py"
            title = f"خطای پایپلاین داده و پژوهش: {exc_type}"

        # 4. Standard Software Bug
        else:
            cat = IncidentCategory.SOFTWARE_BUG
            sev = IncidentSeverity.CRITICAL if isinstance(exc, (SystemError, MemoryError)) else IncidentSeverity.MEDIUM
            title = f"باگ نرم‌افزاری پایتون: {exc_type} - {msg[:60]}"
            fix = "بررسی لاگ خطا، تصحیح نوع داده یا مدیریت استثنا در کد"

        incident = DiagnosticIncident(
            incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
            category=cat,
            severity=sev,
            title=title,
            description=msg,
            error_type=exc_type,
            stack_trace=tb,
            context_data=ctx,
            suggested_fix=fix,
        )
        self.record_incident(incident)
        return incident

    def record_market_loss(
        self,
        trade_id: str,
        loss_amount: float,
        r_multiple: float,
        setup_id: str,
        reason: str,
    ) -> DiagnosticIncident:
        """
        Explicitly records a market loss to distinguish expected statistical variance
        from system bugs or execution errors.
        """
        incident = DiagnosticIncident(
            incident_id=f"LOSS-{uuid.uuid4().hex[:8].upper()}",
            category=IncidentCategory.MARKET_LOSS,
            severity=IncidentSeverity.LOW,
            title=f"ضرر طبیعی بازار در معامله {trade_id} ({setup_id})",
            description=f"معامله با R={r_multiple:.2f} و مبلغ ${loss_amount:.2f} با حد ضرر بسته شد: {reason}",
            error_type="MarketStopLoss",
            stack_trace="",
            context_data={"trade_id": trade_id, "loss": loss_amount, "r": r_multiple, "setup": setup_id},
            suggested_fix="بررسی رژیم نوسانی بازار و کالبدشکافی معامله در ماژول learning.py",
            resolved=True,
        )
        self.record_incident(incident)
        return incident

    def record_incident(self, incident: DiagnosticIncident) -> None:
        import json

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO diagnostics_incidents
                (incident_id, category, severity, title, description, error_type, stack_trace, context_json, suggested_fix, resolved, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident.incident_id,
                    incident.category.value,
                    incident.severity.value,
                    incident.title,
                    incident.description,
                    incident.error_type,
                    incident.stack_trace,
                    json.dumps(incident.context_data, ensure_ascii=False),
                    incident.suggested_fix,
                    1 if incident.resolved else 0,
                    incident.created_at,
                ),
            )
            conn.commit()

    def get_recent_incidents(self, limit: int = 50) -> List[Dict[str, Any]]:
        import json

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT incident_id, category, severity, title, description, error_type, stack_trace, context_json, suggested_fix, resolved, created_at
                FROM diagnostics_incidents
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        results = []
        for r in rows:
            d = dict(r)
            try:
                d["context"] = json.loads(d.pop("context_json"))
            except Exception:
                d["context"] = {}
            results.append(d)
        return results

    def get_category_counts(self) -> Dict[str, int]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT category, COUNT(*) FROM diagnostics_incidents GROUP BY category"
            ).fetchall()
        counts = {c.value: 0 for c in IncidentCategory}
        for cat, cnt in rows:
            counts[cat] = cnt
        return counts
