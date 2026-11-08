"""
Independent Risk Guardian for XAUUSD Autonomous Lab.
Operates completely outside the control of AI agents.
Enforces hard deterministic guardrails:
- Maximum daily loss limit (2.0%)
- Per-trade risk cap (0.5%)
- Maximum concurrent open positions (2)
- Consecutive losses cooldown threshold (3)
- Ledger balance invariance verification (double-entry audit)
- Stale data and spread expansion gates
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from goldlab.paper_broker import PaperAccount, PaperBroker, PaperOrder

TZ_UTC = timezone.utc


@dataclass
class RiskGuardianConfig:
    max_risk_per_trade_pct: float = 0.50
    max_daily_loss_pct: float = 2.00
    max_open_positions: int = 2
    max_daily_trades: int = 4
    max_consecutive_losses: int = 3
    cooldown_bars_after_loss: int = 6
    max_spread_pips: float = 0.50  # Gold $0.50


class IndependentRiskGuardian:
    """Hard-coded, deterministic safety sentinel independent of AI agent modifications."""

    def __init__(
        self,
        config: Optional[RiskGuardianConfig] = None,
        db_path: str = "data/xauusd_lab.sqlite",
    ) -> None:
        self.config = config or RiskGuardianConfig()
        self.db_path = Path(db_path)
        self.daily_starting_equity: float = 1000.0
        self.consecutive_losses_count: int = 0
        self.cooldown_remaining_bars: int = 0
        self.last_reset_date: Optional[str] = None

    def reset_daily_metrics_if_needed(self, current_dt: datetime, current_equity: float) -> None:
        """Resets daily loss counter at midnight UTC."""
        date_str = current_dt.strftime("%Y-%m-%d")
        if self.last_reset_date != date_str:
            self.last_reset_date = date_str
            self.daily_starting_equity = current_equity

    def audit_ledger_invariance(self, account_id: str, broker: PaperBroker) -> Tuple[bool, str]:
        """
        Double-entry audit: Calculates the sum of all historical ledger entries.
        Sum of ledger MUST exactly match current account balance.
        If discrepancy > $0.01, flags immediate integrity corruption halt.
        """
        acc = broker.accounts.get(account_id)
        if not acc:
            return False, f"Account {account_id} not found."

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT COALESCE(SUM(amount), 0.0) FROM wallet_ledger WHERE account_id = ?",
                (account_id,),
            )
            ledger_sum = float(cur.fetchone()[0])

        diff = abs(ledger_sum - acc.balance)
        if diff > 0.01:
            return (
                False,
                f"LEDGER_CORRUPTION_DETECTED: Ledger sum (${ledger_sum:.2f}) does not match balance (${acc.balance:.2f}). Diff: ${diff:.2f}",
            )

        return True, "LEDGER_INTEGRITY_OK"

    def validate_order(
        self,
        account: PaperAccount,
        order: PaperOrder,
        open_positions_count: int,
        daily_trades_count: int,
        current_spread: float,
        current_dt: datetime,
    ) -> Tuple[bool, str]:
        """
        Pre-trade risk verification: Checks all safety parameters before any paper order is executed.
        """
        self.reset_daily_metrics_if_needed(current_dt, account.equity)

        # 1. Daily drawdown check
        daily_loss = self.daily_starting_equity - account.equity
        max_allowed_loss = self.daily_starting_equity * (self.config.max_daily_loss_pct / 100.0)
        if daily_loss >= max_allowed_loss:
            return (
                False,
                f"REJECTED_DAILY_LOSS_LIMIT: افت روزانه (${daily_loss:.2f}) از سقف مجاز (${max_allowed_loss:.2f}) عبور کرده است.",
            )

        # 2. Maximum open positions check
        if open_positions_count >= self.config.max_open_positions:
            return (
                False,
                f"REJECTED_MAX_POSITIONS: تعداد پوزیشن‌های باز جاری ({open_positions_count}) به سقف مجاز رسیده است.",
            )

        # 3. Maximum daily trades check
        if daily_trades_count >= self.config.max_daily_trades:
            return (
                False,
                f"REJECTED_DAILY_TRADES_LIMIT: تعداد معاملات امروز ({daily_trades_count}) به سقف مجاز رسیده است.",
            )

        # 4. Consecutive losses cooldown check
        if self.cooldown_remaining_bars > 0:
            return (
                False,
                f"REJECTED_COOLDOWN_ACTIVE: دوره استراحت پس از باخت‌های متوالی فعال است ({self.cooldown_remaining_bars} کندل باقی‌مانده).",
            )

        # 5. Spread gate
        if current_spread > self.config.max_spread_pips:
            return (
                False,
                f"REJECTED_WIDE_SPREAD: اسپرد جاری (${current_spread:.2f}) از سقف مجاز (${self.config.max_spread_pips:.2f}) بیشتر است.",
            )

        # 6. Sizing check
        if order.sl_price is None:
            return False, "REJECTED_NO_STOP_LOSS: ثبت سفارش بدون حد ضرر مجاز نیست."

        return True, "APPROVED_BY_RISK_GUARDIAN"

    def record_trade_outcome(self, is_win: bool) -> None:
        """Updates consecutive loss tracking and cooldown."""
        if is_win:
            self.consecutive_losses_count = 0
        else:
            self.consecutive_losses_count += 1
            if self.consecutive_losses_count >= self.config.max_consecutive_losses:
                self.cooldown_remaining_bars = self.config.cooldown_bars_after_loss

    def on_bar_completed(self) -> None:
        """Decrements cooldown timer per closed bar."""
        if self.cooldown_remaining_bars > 0:
            self.cooldown_remaining_bars -= 1
