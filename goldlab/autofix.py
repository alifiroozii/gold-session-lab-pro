"""
Safe Auto-Fix Pipeline for Gold Autonomous Trading Research Lab.
Implements a 9-step rigorous verification protocol with 3-tier risk classification:
- LOW: Non-critical parameter tuning, log formatting, documentation (auto-verifiable)
- MEDIUM: Helper logic, resampler fixes, UI components (requires test pass)
- HIGH: Core execution, Risk Guardian, Ledger balance, Broker engine (MANDATORY human approval gate)
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


class RiskLevel(str, Enum):
    LOW = "LOW"          # Parameter adjustment, logging, cache clean, documentation
    MEDIUM = "MEDIUM"    # Data parsing, indicator formula, non-critical UI/API
    HIGH = "HIGH"        # Risk Guardian, Paper Broker, Ledger, Order Execution


class FixStatus(str, Enum):
    PROPOSED = "PROPOSED"
    VERIFIED = "VERIFIED"
    APPLIED = "APPLIED"  # Legacy; no new change can claim this without a verified commit
    APPROVED_FOR_REVIEW = "APPROVED_FOR_REVIEW"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass
class AutoFixProposal:
    proposal_id: str
    incident_id: str
    risk_level: RiskLevel
    title: str
    target_file: str
    diff_content: str
    explanation: str
    minimal_reproducer: str
    status: FixStatus = FixStatus.PROPOSED
    requires_human_approval: bool = True
    test_results: str = ""
    created_at: str = ""
    applied_at: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(TZ_UTC).isoformat()
        # High and Medium risk strictly require human user approval
        self.requires_human_approval = self.risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM)


class SafeAutoFixEngine:
    """Manages the creation, isolated testing, and approval gate of code/parameter fixes."""

    def __init__(self, db_path: str = "data/xauusd_lab.sqlite") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS autofix_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    title TEXT NOT NULL,
                    target_file TEXT NOT NULL,
                    diff_content TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    minimal_reproducer TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requires_human_approval INTEGER NOT NULL,
                    test_results TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    applied_at TEXT
                );
                """
            )
            conn.commit()

    def classify_risk(self, target_file: str, changes_summary: str) -> RiskLevel:
        """Classifies modification risk according to institutional safety boundaries."""
        high_risk_files = ["guardian.py", "paper_broker.py", "bot.py"]
        medium_risk_files = ["setups.py", "market_structure.py", "data.py", "simulator.py"]

        for hf in high_risk_files:
            if hf in target_file:
                return RiskLevel.HIGH

        for mf in medium_risk_files:
            if mf in target_file:
                return RiskLevel.MEDIUM

        if any(w in changes_summary.lower() for w in ["risk", "capital", "lot", "stop_loss", "ledger"]):
            return RiskLevel.HIGH

        return RiskLevel.LOW

    def create_proposal(
        self,
        incident_id: str,
        target_file: str,
        title: str,
        diff_content: str,
        explanation: str,
        minimal_reproducer: str,
    ) -> AutoFixProposal:
        """Generates a structured fix proposal with automatic risk classification."""
        risk = self.classify_risk(target_file, explanation)
        proposal = AutoFixProposal(
            proposal_id=f"FIX-{uuid.uuid4().hex[:8].upper()}",
            incident_id=incident_id,
            risk_level=risk,
            title=title,
            target_file=target_file,
            diff_content=diff_content,
            explanation=explanation,
            minimal_reproducer=minimal_reproducer,
            status=FixStatus.PROPOSED,
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO autofix_proposals
                (proposal_id, incident_id, risk_level, title, target_file, diff_content, explanation, minimal_reproducer, status, requires_human_approval, test_results, created_at, applied_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.proposal_id,
                    proposal.incident_id,
                    proposal.risk_level.value,
                    proposal.title,
                    proposal.target_file,
                    proposal.diff_content,
                    proposal.explanation,
                    proposal.minimal_reproducer,
                    proposal.status.value,
                    1 if proposal.requires_human_approval else 0,
                    proposal.test_results,
                    proposal.created_at,
                    proposal.applied_at,
                ),
            )
            conn.commit()

        return proposal

    def record_verification_result(self, proposal_id: str, success: bool, test_output: str) -> None:
        new_status = FixStatus.VERIFIED if success else FixStatus.FAILED
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE autofix_proposals
                SET status = ?, test_results = ?
                WHERE proposal_id = ?
                """,
                (new_status.value, test_output, proposal_id),
            )
            conn.commit()

    def approve_and_apply_fix(self, proposal_id: str, user_confirmed: bool = False) -> Dict[str, Any]:
        """
        Enforces human approval gate for HIGH and MEDIUM risk fixes.
        Low risk fixes can be verified and applied autonomously.
        """
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            return {"success": False, "message": f"Proposal {proposal_id} not found."}

        if proposal.requires_human_approval and not user_confirmed:
            return {
                "success": False,
                "message": f"تغییر با سطح ریسک {proposal.risk_level.value} نیازمند تأیید صریح کاربر است.",
                "proposal": proposal,
            }

        # A database approval does NOT apply a Git patch or run tests.
        # The external Antigravity agent must create a candidate commit, run
        # regression tests and request a separate human-reviewed merge.
        if proposal.status != FixStatus.VERIFIED:
            return {
                "success": False,
                "message": "تست معتبر ثبت نشده است؛ ابتدا در Worktree جداگانه آزمایش کنید.",
            }
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE autofix_proposals SET status = ? WHERE proposal_id = ?",
                (FixStatus.APPROVED_FOR_REVIEW.value, proposal_id),
            )
            conn.commit()
        return {
            "success": True,
            "message": "اصلاحیه فقط برای بازبینی کد تأیید شد؛ هنوز روی کد فعال اعمال نشده است.",
            "proposal_id": proposal_id,
            "applied": False,
        }

    def reject_fix(self, proposal_id: str, reason: str = "") -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE autofix_proposals
                SET status = ?, test_results = test_results || ?
                WHERE proposal_id = ?
                """,
                (FixStatus.REJECTED.value, f" [REJECTED: {reason}]", proposal_id),
            )
            conn.commit()

    def get_proposal(self, proposal_id: str) -> Optional[AutoFixProposal]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM autofix_proposals WHERE proposal_id = ?", (proposal_id,)
            ).fetchone()
        if not row:
            return None
        return AutoFixProposal(
            proposal_id=row["proposal_id"],
            incident_id=row["incident_id"],
            risk_level=RiskLevel(row["risk_level"]),
            title=row["title"],
            target_file=row["target_file"],
            diff_content=row["diff_content"],
            explanation=row["explanation"],
            minimal_reproducer=row["minimal_reproducer"],
            status=FixStatus(row["status"]),
            requires_human_approval=bool(row["requires_human_approval"]),
            test_results=row["test_results"],
            created_at=row["created_at"],
            applied_at=row["applied_at"],
        )

    def list_proposals(self, status: Optional[FixStatus] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    "SELECT * FROM autofix_proposals WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status.value, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM autofix_proposals ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(r) for r in rows]
