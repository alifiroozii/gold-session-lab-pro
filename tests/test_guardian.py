from datetime import datetime, timezone

import pytest

from goldlab.guardian import IndependentRiskGuardian, RiskGuardianConfig
from goldlab.paper_broker import OrderDirection, OrderType, PaperAccount, PaperBroker, PaperOrder

TZ_UTC = timezone.utc


@pytest.fixture
def test_db_path(tmp_path):
    return str(tmp_path / "test_guardian.sqlite")


def test_ledger_invariance_audit_success(test_db_path):
    broker = PaperBroker(db_path=test_db_path)
    guardian = IndependentRiskGuardian(db_path=test_db_path)

    # ACC_DEFAULT is initialized with $10,000 deposit in ledger
    ok, msg = guardian.audit_ledger_invariance("ACC_DEFAULT", broker)
    assert ok is True
    assert msg == "LEDGER_INTEGRITY_OK"


def test_ledger_invariance_audit_detects_corruption(test_db_path):
    broker = PaperBroker(db_path=test_db_path)
    guardian = IndependentRiskGuardian(db_path=test_db_path)

    # Artificially tamper with balance without recording in wallet_ledger
    broker.accounts["ACC_DEFAULT"].balance += 500.0

    ok, msg = guardian.audit_ledger_invariance("ACC_DEFAULT", broker)
    assert ok is False
    assert "LEDGER_CORRUPTION_DETECTED" in msg


def test_guardian_order_validation_rules(test_db_path):
    guardian = IndependentRiskGuardian(
        config=RiskGuardianConfig(
            max_daily_loss_pct=2.0,
            max_open_positions=1,
            max_daily_trades=2,
            max_spread_pips=0.40,
        ),
        db_path=test_db_path,
    )
    acc = PaperAccount(
        account_id="ACC1",
        name="Test",
        balance=10000.0,
        equity=10000.0,
        margin_used=0.0,
        margin_free=10000.0,
        margin_level_pct=0.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        leverage=100.0,
        created_at=datetime.now(TZ_UTC),
    )

    valid_order = PaperOrder(
        order_id="ORD1",
        account_id="ACC1",
        symbol="XAUUSD",
        direction=OrderDirection.BUY,
        order_type=OrderType.MARKET,
        quantity_lots=0.10,
        target_price=2650.0,
        sl_price=2648.0,
        tp_price=2654.0,
    )

    now = datetime(2026, 11, 8, 12, 0, tzinfo=TZ_UTC)

    # 1. Normal valid order
    ok, msg = guardian.validate_order(acc, valid_order, open_positions_count=0, daily_trades_count=0, current_spread=0.25, current_dt=now)
    assert ok is True

    # 2. Max open positions reached
    ok, msg = guardian.validate_order(acc, valid_order, open_positions_count=1, daily_trades_count=0, current_spread=0.25, current_dt=now)
    assert ok is False
    assert "REJECTED_MAX_POSITIONS" in msg

    # 3. Wide spread
    ok, msg = guardian.validate_order(acc, valid_order, open_positions_count=0, daily_trades_count=0, current_spread=0.55, current_dt=now)
    assert ok is False
    assert "REJECTED_WIDE_SPREAD" in msg

    # 4. Daily drawdown breach
    acc.equity = 9700.0  # $300 loss > 2% ($200)
    ok, msg = guardian.validate_order(acc, valid_order, open_positions_count=0, daily_trades_count=0, current_spread=0.25, current_dt=now)
    assert ok is False
    assert "REJECTED_DAILY_LOSS_LIMIT" in msg
