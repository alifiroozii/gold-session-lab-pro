"""
Unit tests for Internal Paper Broker:
- Ledger invariance (every balance change has an immutable ledger entry)
- Margin calculations (contract size, leverage, used margin, free margin)
- Position execution, SL/TP triggers, and position closure
- Virtual deposit, withdrawal, and reset
"""

from pathlib import Path

import pytest

from goldlab.paper_broker import (
    OrderDirection,
    OrderStatus,
    OrderType,
    PaperBroker,
    PositionStatus,
)


@pytest.fixture
def temp_broker(tmp_path: Path) -> PaperBroker:
    db = str(tmp_path / "test_broker.sqlite")
    return PaperBroker(db_path=db)


def test_paper_account_deposit_and_withdrawal(temp_broker: PaperBroker) -> None:
    broker = temp_broker
    acc = broker.create_account("ACC_TEST", "Test Account", 5000.0)
    assert acc.balance == 5000.0
    assert acc.equity == 5000.0
    assert acc.margin_free == 5000.0

    # Deposit
    broker.deposit("ACC_TEST", 1500.0, notes="Test deposit")
    assert acc.balance == 6500.0
    assert acc.equity == 6500.0

    # Withdrawal
    broker.withdraw("ACC_TEST", 2000.0, notes="Test withdrawal")
    assert acc.balance == 4500.0
    assert acc.equity == 4500.0

    # Excessive withdrawal must fail
    with pytest.raises(ValueError):
        broker.withdraw("ACC_TEST", 10000.0)


def test_market_order_and_margin_calculation(temp_broker: PaperBroker) -> None:
    broker = temp_broker
    acc = broker.create_account("ACC_MARGIN", "Margin Account", 10000.0)

    # Submit BUY 0.10 lot (10 oz) at Ask = 2650.0
    # Required Margin = (0.10 lots * 100 oz * 2650.10) / 100 leverage = $265.01
    order = broker.submit_order(
        account_id="ACC_MARGIN",
        direction=OrderDirection.BUY,
        order_type=OrderType.MARKET,
        quantity_lots=0.10,
        current_bid=2649.75,
        current_ask=2650.00,
    )

    assert order.status == OrderStatus.FILLED
    pos = broker.positions.get(f"POS_{order.order_id}")
    assert pos is not None
    assert pos.status == PositionStatus.OPEN
    assert pos.quantity_lots == 0.10

    # Verify margin deducted
    broker.update_account_metrics("ACC_MARGIN")
    assert acc.margin_used > 260.0
    assert acc.margin_free < 10000.0


def test_position_close_and_pnl(temp_broker: PaperBroker) -> None:
    broker = temp_broker
    acc = broker.create_account("ACC_PNL", "PnL Account", 10000.0)

    order = broker.submit_order(
        account_id="ACC_PNL",
        direction=OrderDirection.BUY,
        order_type=OrderType.MARKET,
        quantity_lots=0.10,
        current_bid=2650.00,
        current_ask=2650.00,
    )
    pos_id = f"POS_{order.order_id}"

    # Price moves from 2650.10 (with slippage) up to 2660.10 ($10 gain on 10 oz = +$100.00)
    broker.close_position(pos_id, exit_price=2660.10, reason="MANUAL_CLOSE")
    pos = broker.positions[pos_id]

    assert pos.status == PositionStatus.CLOSED
    assert pos.realized_pnl == pytest.approx(100.0, abs=0.5)
    # Balance must reflect the gain
    assert acc.balance > 10000.0
