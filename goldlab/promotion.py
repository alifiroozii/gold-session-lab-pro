"""
Champion vs Challenger Promotion Manager for Gold Autonomous Trading Research Lab.
Manages isolated candidate strategies against the established baseline (Champion).
Enforces statistically rigorous criteria and a mandatory human approval gate.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

TZ_UTC = timezone.utc


@dataclass
class StrategyVersion:
    version_id: str
    name: str
    is_champion: bool
    config_json: str
    total_trades: int
    win_rate: float
    expectancy_r: float
    max_drawdown_pct: float
    sharpe_ratio: float
    p_value_vs_champion: float
    status: str  # ACTIVE_CHAMPION, EVALUATING_CHALLENGER, DEPRECATED, REJECTED
    notes: str
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(TZ_UTC).isoformat()


class ChampionChallengerManager:
    """Controls the competition between active Champion and candidate Challengers."""

    def __init__(self, db_path: str = "data/xauusd_lab.sqlite") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_versions (
                    version_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    is_champion INTEGER NOT NULL,
                    config_json TEXT NOT NULL,
                    total_trades INTEGER NOT NULL DEFAULT 0,
                    win_rate REAL NOT NULL DEFAULT 0.0,
                    expectancy_r REAL NOT NULL DEFAULT 0.0,
                    max_drawdown_pct REAL NOT NULL DEFAULT 0.0,
                    sharpe_ratio REAL NOT NULL DEFAULT 0.0,
                    p_value_vs_champion REAL NOT NULL DEFAULT 1.0,
                    status TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS promotion_history (
                    history_id TEXT PRIMARY KEY,
                    old_champion_id TEXT NOT NULL,
                    new_champion_id TEXT NOT NULL,
                    promoted_by TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    promoted_at TEXT NOT NULL
                );
                """
            )
            conn.commit()

        # Seed initial Champion if empty
        self._ensure_baseline_champion()

    def _ensure_baseline_champion(self) -> None:
        champ = self.get_current_champion()
        if not champ:
            baseline_config = {
                "setups": ["S1_ASIA_SWEEP", "S2_LONDON_EXPANSION", "S4_NEW_YORK_REVERSAL"],
                "risk_per_trade_pct": 0.5,
                "atr_buffer_pips": 0.5,
                "max_spread_pips": 0.45,
            }
            self.register_version(
                name="Champion-Baseline-V1",
                is_champion=True,
                config=baseline_config,
                total_trades=50,
                win_rate=54.0,
                expectancy_r=0.42,
                max_drawdown_pct=1.4,
                sharpe_ratio=1.35,
                notes="نسخه مبنای اولیه و فعال در سیستم معاملاتی آزمایشی",
            )

    def register_version(
        self,
        name: str,
        is_champion: bool,
        config: Dict[str, Any],
        total_trades: int = 0,
        win_rate: float = 0.0,
        expectancy_r: float = 0.0,
        max_drawdown_pct: float = 0.0,
        sharpe_ratio: float = 0.0,
        p_value: float = 1.0,
        notes: str = "",
    ) -> StrategyVersion:
        vid = f"VER-{uuid.uuid4().hex[:6].upper()}"
        status = "ACTIVE_CHAMPION" if is_champion else "EVALUATING_CHALLENGER"
        version = StrategyVersion(
            version_id=vid,
            name=name,
            is_champion=is_champion,
            config_json=json.dumps(config),
            total_trades=total_trades,
            win_rate=win_rate,
            expectancy_r=expectancy_r,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            p_value_vs_champion=p_value,
            status=status,
            notes=notes,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_versions
                (version_id, name, is_champion, config_json, total_trades, win_rate, expectancy_r, max_drawdown_pct, sharpe_ratio, p_value_vs_champion, status, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version.version_id,
                    version.name,
                    1 if version.is_champion else 0,
                    version.config_json,
                    version.total_trades,
                    version.win_rate,
                    version.expectancy_r,
                    version.max_drawdown_pct,
                    version.sharpe_ratio,
                    version.p_value_vs_champion,
                    version.status,
                    version.notes,
                    version.created_at,
                ),
            )
            conn.commit()
        return version

    def get_current_champion(self) -> Optional[StrategyVersion]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM strategy_versions WHERE is_champion = 1 AND status = 'ACTIVE_CHAMPION' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return self._row_to_version(row)

    def evaluate_challenger_promotion(self, challenger_id: str) -> Dict[str, Any]:
        """
        Tests if challenger meets institutional promotion criteria:
        1. Trades count >= 30
        2. Expectancy R > Champion by at least 0.15 R
        3. Max drawdown <= Champion drawdown * 1.10
        4. p-value < 0.05
        """
        champ = self.get_current_champion()
        if not champ:
            return {"eligible": False, "reason": "No active champion found."}

        challenger = self.get_version(challenger_id)
        if not challenger:
            return {"eligible": False, "reason": f"Challenger {challenger_id} not found."}

        checks = {
            "sample_size_ok": challenger.total_trades >= 30,
            "expectancy_improved": challenger.expectancy_r >= (champ.expectancy_r + 0.15),
            "drawdown_contained": challenger.max_drawdown_pct <= (champ.max_drawdown_pct * 1.10),
            "statistical_significance": challenger.p_value_vs_champion <= 0.05,
        }

        eligible = all(checks.values())
        return {
            "eligible": eligible,
            "checks": checks,
            "champion": {
                "name": champ.name,
                "expectancy_r": champ.expectancy_r,
                "max_drawdown_pct": champ.max_drawdown_pct,
            },
            "challenger": {
                "name": challenger.name,
                "expectancy_r": challenger.expectancy_r,
                "max_drawdown_pct": challenger.max_drawdown_pct,
                "p_value": challenger.p_value_vs_champion,
            },
            "requires_human_approval": True,
        }

    def promote_challenger(
        self,
        challenger_id: str,
        user_confirmed: bool = False,
        promoted_by: str = "User",
    ) -> Dict[str, Any]:
        """Promotes a challenger to Champion only after user verification."""
        if not user_confirmed:
            return {
                "success": False,
                "message": "ارتقای نسخه رقیب به قهرمان (Champion) نیازمند تایید صریح کاربر است.",
            }

        champ = self.get_current_champion()
        challenger = self.get_version(challenger_id)
        if not challenger:
            return {"success": False, "message": f"Challenger {challenger_id} not found."}

        now_iso = datetime.now(TZ_UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            # 1. Demote old champion
            if champ:
                conn.execute(
                    "UPDATE strategy_versions SET is_champion = 0, status = 'DEPRECATED' WHERE version_id = ?",
                    (champ.version_id,),
                )
            # 2. Promote challenger
            conn.execute(
                "UPDATE strategy_versions SET is_champion = 1, status = 'ACTIVE_CHAMPION' WHERE version_id = ?",
                (challenger.version_id,),
            )
            # 3. Record history
            conn.execute(
                """
                INSERT INTO promotion_history (history_id, old_champion_id, new_champion_id, promoted_by, reason, promoted_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"PROM-{uuid.uuid4().hex[:6].upper()}",
                    champ.version_id if champ else "NONE",
                    challenger.version_id,
                    promoted_by,
                    f"ارتقا به دلیل برتری آماری R={challenger.expectancy_r:.2f} نسبت به قهرمان قبلی",
                    now_iso,
                ),
            )
            conn.commit()

        return {
            "success": True,
            "message": f"استراتژی {challenger.name} با موفقیت به قهرمان فعال سیستم ارتقا یافت.",
            "new_champion_id": challenger.version_id,
        }

    def get_version(self, version_id: str) -> Optional[StrategyVersion]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM strategy_versions WHERE version_id = ?", (version_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_version(row)

    def list_versions(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM strategy_versions ORDER BY is_champion DESC, created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def _row_to_version(self, row: sqlite3.Row) -> StrategyVersion:
        return StrategyVersion(
            version_id=row["version_id"],
            name=row["name"],
            is_champion=bool(row["is_champion"]),
            config_json=row["config_json"],
            total_trades=row["total_trades"],
            win_rate=row["win_rate"],
            expectancy_r=row["expectancy_r"],
            max_drawdown_pct=row["max_drawdown_pct"],
            sharpe_ratio=row["sharpe_ratio"],
            p_value_vs_champion=row["p_value_vs_champion"],
            status=row["status"],
            notes=row["notes"],
            created_at=row["created_at"],
        )
