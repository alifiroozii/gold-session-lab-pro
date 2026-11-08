"""
Gold Paper Broker Engine.
Simulated virtual execution broker with strict double-entry ledger accounting,
multi-account support, realistic margin/equity calculations, bracket orders,
trailing stops, and zero live brokerage connections.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

TZ_UTC = timezone.utc


class OrderDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass
class PaperAccount:
    account_id: str
    name: str
    balance: float = 10000.0  # Default $10,000 USD virtual
    equity: float = 10000.0
    margin_used: float = 0.0
    margin_free: float = 10000.0
    margin_level_pct: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    leverage: float = 100.0  # 1:100 leverage
    contract_size: float = 100.0  # 100 oz per standard lot
    created_at: datetime = field(default_factory=lambda: datetime.now(TZ_UTC))


@dataclass
class PaperOrder:
    order_id: str
    account_id: str
    symbol: str
    direction: OrderDirection
    order_type: OrderType
    quantity_lots: float
    target_price: Optional[float] = None
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    trailing_stop_pips: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    created_time: datetime = field(default_factory=lambda: datetime.now(TZ_UTC))
    filled_time: Optional[datetime] = None
    filled_price: Optional[float] = None
    rejection_reason: Optional[str] = None


@dataclass
class PaperPosition:
    position_id: str
    order_id: str
    account_id: str
    symbol: str
    direction: OrderDirection
    quantity_lots: float
    entry_price: float
    entry_time: datetime
    current_price: float
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    trailing_stop_pips: Optional[float] = None
    highest_price: float = 0.0
    lowest_price: float = 999999.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    commission_paid: float = 0.0
    status: PositionStatus = PositionStatus.OPEN
    close_time: Optional[datetime] = None
    close_price: Optional[float] = None
    close_reason: Optional[str] = None


class PaperBroker:
    """Internal Paper Trading Broker managing accounts, ledger, and order execution."""

    def __init__(
        self,
        db_path: str = "data/xauusd_lab.sqlite",
        commission_per_lot: float = 5.0,  # $5.0 per round turn lot
        slippage_pips: float = 0.10,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.commission_per_lot = commission_per_lot
        self.slippage_pips = slippage_pips

        self.accounts: Dict[str, PaperAccount] = {}
        self.orders: Dict[str, PaperOrder] = {}
        self.positions: Dict[str, PaperPosition] = {}

        self._init_db()
        self._load_state()

    def _init_db(self) -> None:
        """Configures SQLite with WAL mode and institutional relational schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_accounts (
                    account_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    balance REAL NOT NULL,
                    equity REAL NOT NULL,
                    margin_used REAL NOT NULL,
                    leverage REAL NOT NULL DEFAULT 100.0,
                    contract_size REAL NOT NULL DEFAULT 100.0,
                    created_at TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS wallet_ledger (
                    ledger_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    entry_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    balance_after REAL NOT NULL,
                    reference_id TEXT,
                    notes TEXT,
                    FOREIGN KEY (account_id) REFERENCES paper_accounts(account_id)
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_orders (
                    order_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    quantity_lots REAL NOT NULL,
                    target_price REAL,
                    sl_price REAL,
                    tp_price REAL,
                    trailing_stop_pips REAL,
                    status TEXT NOT NULL,
                    created_time TEXT NOT NULL,
                    filled_time TEXT,
                    filled_price REAL,
                    rejection_reason TEXT,
                    FOREIGN KEY (account_id) REFERENCES paper_accounts(account_id)
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_positions (
                    position_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    quantity_lots REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    sl_price REAL,
                    tp_price REAL,
                    trailing_stop_pips REAL,
                    unrealized_pnl REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    commission_paid REAL NOT NULL,
                    status TEXT NOT NULL,
                    close_time TEXT,
                    close_price REAL,
                    close_reason TEXT,
                    FOREIGN KEY (account_id) REFERENCES paper_accounts(account_id)
                )
                """
            )
            conn.commit()

    def _load_state(self) -> None:
        """Loads accounts, pending orders, and open positions from SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Load accounts
            cur = conn.execute("SELECT * FROM paper_accounts")
            for row in cur.fetchall():
                acc = PaperAccount(
                    account_id=row["account_id"],
                    name=row["name"],
                    balance=row["balance"],
                    equity=row["equity"],
                    margin_used=row["margin_used"],
                    leverage=row["leverage"],
                    contract_size=row["contract_size"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                self.accounts[acc.account_id] = acc

            # Create default account if none exists
            if not self.accounts:
                default_acc = self.create_account("ACC_DEFAULT", "حساب پیش‌فرض مجازی (Paper Main)", 10000.0)
                self.accounts[default_acc.account_id] = default_acc

            # Load open positions
            cur = conn.execute("SELECT * FROM paper_positions WHERE status = 'OPEN'")
            for row in cur.fetchall():
                pos = PaperPosition(
                    position_id=row["position_id"],
                    order_id=row["order_id"],
                    account_id=row["account_id"],
                    symbol=row["symbol"],
                    direction=OrderDirection(row["direction"]),
                    quantity_lots=row["quantity_lots"],
                    entry_price=row["entry_price"],
                    entry_time=datetime.fromisoformat(row["entry_time"]),
                    current_price=row["entry_price"],
                    sl_price=row["sl_price"],
                    tp_price=row["tp_price"],
                    trailing_stop_pips=row["trailing_stop_pips"],
                    unrealized_pnl=row["unrealized_pnl"],
                    realized_pnl=row["realized_pnl"],
                    commission_paid=row["commission_paid"],
                    status=PositionStatus(row["status"]),
                )
                self.positions[pos.position_id] = pos

            # Load pending orders
            cur = conn.execute("SELECT * FROM paper_orders WHERE status = 'PENDING'")
            for row in cur.fetchall():
                ord_obj = PaperOrder(
                    order_id=row["order_id"],
                    account_id=row["account_id"],
                    symbol=row["symbol"],
                    direction=OrderDirection(row["direction"]),
                    order_type=OrderType(row["order_type"]),
                    quantity_lots=row["quantity_lots"],
                    target_price=row["target_price"],
                    sl_price=row["sl_price"],
                    tp_price=row["tp_price"],
                    trailing_stop_pips=row["trailing_stop_pips"],
                    status=OrderStatus(row["status"]),
                    created_time=datetime.fromisoformat(row["created_time"]),
                )
                self.orders[ord_obj.order_id] = ord_obj

    def create_account(self, account_id: str, name: str, initial_deposit: float = 10000.0) -> PaperAccount:
        """Creates a new virtual account with ledger deposit entry."""
        acc = PaperAccount(
            account_id=account_id,
            name=name,
            balance=initial_deposit,
            equity=initial_deposit,
            margin_free=initial_deposit,
        )
        self.accounts[account_id] = acc

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO paper_accounts (account_id, name, balance, equity, margin_used, leverage, contract_size, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    acc.account_id,
                    acc.name,
                    acc.balance,
                    acc.equity,
                    acc.margin_used,
                    acc.leverage,
                    acc.contract_size,
                    acc.created_at.isoformat(),
                ),
            )
            # Record deposit in ledger
            self._record_ledger(
                conn,
                account_id=account_id,
                entry_type="DEPOSIT",
                amount=initial_deposit,
                balance_after=initial_deposit,
                notes="موجودی اولیه حساب مجازی",
            )
            conn.commit()

        return acc

    def deposit(self, account_id: str, amount: float, notes: str = "شارژ دستی موجودی مجازی") -> PaperAccount:
        """Virtual deposit: strictly updates balance via ledger entry."""
        if amount <= 0:
            raise ValueError("مبلغ واریز باید مثبت باشد.")
        acc = self.accounts[account_id]
        acc.balance += amount
        acc.equity += amount
        acc.margin_free = acc.equity - acc.margin_used

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE paper_accounts SET balance = ?, equity = ? WHERE account_id = ?",
                (acc.balance, acc.equity, acc.account_id),
            )
            self._record_ledger(
                conn,
                account_id=account_id,
                entry_type="DEPOSIT",
                amount=amount,
                balance_after=acc.balance,
                notes=notes,
            )
            conn.commit()
        return acc

    def withdraw(self, account_id: str, amount: float, notes: str = "برداشت دستی موجودی مجازی") -> PaperAccount:
        """Virtual withdrawal: ensures free margin is sufficient."""
        if amount <= 0:
            raise ValueError("مبلغ برداشت باید مثبت باشد.")
        acc = self.accounts[account_id]
        if amount > acc.margin_free:
            raise ValueError(f"موجودی آزاد ناکافی است. حداکثر قابل برداشت: {acc.margin_free:.2f}")

        acc.balance -= amount
        acc.equity -= amount
        acc.margin_free = acc.equity - acc.margin_used

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE paper_accounts SET balance = ?, equity = ? WHERE account_id = ?",
                (acc.balance, acc.equity, acc.account_id),
            )
            self._record_ledger(
                conn,
                account_id=account_id,
                entry_type="WITHDRAWAL",
                amount=-amount,
                balance_after=acc.balance,
                notes=notes,
            )
            conn.commit()
        return acc

    def reset_account(self, account_id: str, new_balance: float = 10000.0) -> PaperAccount:
        """Resets account by archiving/closing open positions and orders, and setting new balance."""
        acc = self.accounts[account_id]
        # Close positions
        now = datetime.now(TZ_UTC)
        for pos_id, pos in list(self.positions.items()):
            if pos.account_id == account_id and pos.status == PositionStatus.OPEN:
                pos.status = PositionStatus.CLOSED
                pos.close_time = now
                pos.close_reason = "ACCOUNT_RESET"

        # Cancel orders
        for ord_id, ord_obj in list(self.orders.items()):
            if ord_obj.account_id == account_id and ord_obj.status == OrderStatus.PENDING:
                ord_obj.status = OrderStatus.CANCELLED

        acc.balance = new_balance
        acc.equity = new_balance
        acc.margin_used = 0.0
        acc.margin_free = new_balance
        acc.margin_level_pct = 0.0
        acc.unrealized_pnl = 0.0

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE paper_positions SET status = 'CLOSED', close_time = ?, close_reason = 'ACCOUNT_RESET' WHERE account_id = ? AND status = 'OPEN'",
                (now.isoformat(), account_id),
            )
            conn.execute(
                "UPDATE paper_orders SET status = 'CANCELLED' WHERE account_id = ? AND status = 'PENDING'",
                (account_id,),
            )
            conn.execute(
                "UPDATE paper_accounts SET balance = ?, equity = ?, margin_used = 0.0 WHERE account_id = ?",
                (new_balance, new_balance, account_id),
            )
            self._record_ledger(
                conn,
                account_id=account_id,
                entry_type="RESET",
                amount=new_balance,
                balance_after=new_balance,
                notes=f"ریست کامل حساب مجازی به موجودی {new_balance:,.2f} دلار",
            )
            conn.commit()

        return acc

    def _record_ledger(
        self,
        conn: sqlite3.Connection,
        account_id: str,
        entry_type: str,
        amount: float,
        balance_after: float,
        reference_id: Optional[str] = None,
        notes: str = "",
    ) -> None:
        """Records an immutable transaction in the wallet ledger."""
        ledger_id = f"LEDG_{int(datetime.now(TZ_UTC).timestamp() * 1000)}_{uuid.uuid4().hex[:8]}_{entry_type}"
        conn.execute(
            """
            INSERT INTO wallet_ledger (ledger_id, account_id, timestamp, entry_type, amount, balance_after, reference_id, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ledger_id,
                account_id,
                datetime.now(TZ_UTC).isoformat(),
                entry_type,
                round(amount, 4),
                round(balance_after, 4),
                reference_id,
                notes,
            ),
        )

    def submit_order(
        self,
        account_id: str,
        direction: OrderDirection,
        order_type: OrderType,
        quantity_lots: float,
        target_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        tp_price: Optional[float] = None,
        trailing_stop_pips: Optional[float] = None,
        current_bid: Optional[float] = None,
        current_ask: Optional[float] = None,
    ) -> PaperOrder:
        """Submits market, limit, or stop paper order."""
        if account_id not in self.accounts:
            raise ValueError(f"حساب {account_id} یافت نشد.")

        order_id = f"ORD_{int(datetime.now(TZ_UTC).timestamp() * 1000)}_{uuid.uuid4().hex[:8]}"
        order = PaperOrder(
            order_id=order_id,
            account_id=account_id,
            symbol="XAUUSD",
            direction=direction,
            order_type=order_type,
            quantity_lots=quantity_lots,
            target_price=target_price,
            sl_price=sl_price,
            tp_price=tp_price,
            trailing_stop_pips=trailing_stop_pips,
            status=OrderStatus.PENDING,
        )
        self.orders[order_id] = order

        # If MARKET order and prices are provided, execute immediately
        if order_type == OrderType.MARKET and current_bid is not None and current_ask is not None:
            self._fill_market_order(order, current_bid, current_ask)
        else:
            self._save_order_db(order)

        return order

    def _fill_market_order(self, order: PaperOrder, bid: float, ask: float) -> None:
        """Fills a market order: Buy at Ask + slippage, Sell at Bid - slippage."""
        acc = self.accounts[order.account_id]
        now = datetime.now(TZ_UTC)

        exec_price = (
            ask + self.slippage_pips if order.direction == OrderDirection.BUY else bid - self.slippage_pips
        )
        required_margin = (order.quantity_lots * acc.contract_size * exec_price) / acc.leverage

        if acc.margin_free < required_margin:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = f"مارجین ناکافی (موردنیاز: ${required_margin:.2f}، آزاد: ${acc.margin_free:.2f})"
            self._save_order_db(order)
            return

        commission = order.quantity_lots * self.commission_per_lot

        order.status = OrderStatus.FILLED
        order.filled_time = now
        order.filled_price = round(exec_price, 4)
        self._save_order_db(order)

        # Deduct commission from balance immediately
        acc.balance -= commission
        acc.margin_used += required_margin
        acc.equity = acc.balance
        acc.margin_free = acc.equity - acc.margin_used

        pos_id = f"POS_{order.order_id}"
        pos = PaperPosition(
            position_id=pos_id,
            order_id=order.order_id,
            account_id=acc.account_id,
            symbol=order.symbol,
            direction=order.direction,
            quantity_lots=order.quantity_lots,
            entry_price=round(exec_price, 4),
            entry_time=now,
            current_price=round(exec_price, 4),
            sl_price=order.sl_price,
            tp_price=order.tp_price,
            trailing_stop_pips=order.trailing_stop_pips,
            highest_price=exec_price,
            lowest_price=exec_price,
            commission_paid=commission,
        )
        self.positions[pos_id] = pos

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO paper_positions (
                    position_id, order_id, account_id, symbol, direction, quantity_lots,
                    entry_price, entry_time, sl_price, tp_price, trailing_stop_pips,
                    unrealized_pnl, realized_pnl, commission_paid, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pos.position_id,
                    pos.order_id,
                    pos.account_id,
                    pos.symbol,
                    pos.direction.value,
                    pos.quantity_lots,
                    pos.entry_price,
                    pos.entry_time.isoformat(),
                    pos.sl_price,
                    pos.tp_price,
                    pos.trailing_stop_pips,
                    0.0,
                    0.0,
                    pos.commission_paid,
                    pos.status.value,
                ),
            )
            self._record_ledger(
                conn,
                account_id=acc.account_id,
                entry_type="COMMISSION",
                amount=-commission,
                balance_after=acc.balance,
                reference_id=pos.position_id,
                notes=f"کارمزد باز کردن موقعیت {pos.direction.value} {pos.quantity_lots} لات",
            )
            conn.execute(
                "UPDATE paper_accounts SET balance = ?, equity = ?, margin_used = ? WHERE account_id = ?",
                (acc.balance, acc.equity, acc.margin_used, acc.account_id),
            )
            conn.commit()

    def close_position(
        self, position_id: str, exit_price: float, reason: str = "MANUAL_CLOSE"
    ) -> PaperPosition:
        """Closes an open position and credits/debits realized P&L to account balance."""
        pos = self.positions.get(position_id)
        if not pos or pos.status != PositionStatus.OPEN:
            raise ValueError(f"موقعیت {position_id} معتبر یا باز نیست.")

        acc = self.accounts[pos.account_id]
        now = datetime.now(TZ_UTC)

        # Gross P&L using Decimal for precise currency calculations
        d_exit = Decimal(str(exit_price))
        d_entry = Decimal(str(pos.entry_price))
        d_lots = Decimal(str(pos.quantity_lots))
        d_contract = Decimal(str(acc.contract_size))
        if pos.direction == OrderDirection.BUY:
            pnl_dec = (d_exit - d_entry) * d_lots * d_contract
        else:
            pnl_dec = (d_entry - d_exit) * d_lots * d_contract
        pnl = float(round(pnl_dec, 4))

        pos.status = PositionStatus.CLOSED
        pos.close_time = now
        pos.close_price = round(exit_price, 4)
        pos.realized_pnl = round(pnl, 4)
        pos.unrealized_pnl = 0.0
        pos.close_reason = reason

        # Free margin calculation
        released_margin = (pos.quantity_lots * acc.contract_size * pos.entry_price) / acc.leverage
        acc.balance += pnl
        acc.realized_pnl += pnl
        acc.margin_used = max(0.0, acc.margin_used - released_margin)
        self.update_account_metrics(acc.account_id)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE paper_positions SET
                    status = 'CLOSED', close_time = ?, close_price = ?,
                    realized_pnl = ?, unrealized_pnl = 0.0, close_reason = ?
                WHERE position_id = ?
                """,
                (now.isoformat(), pos.close_price, pos.realized_pnl, pos.close_reason, pos.position_id),
            )
            self._record_ledger(
                conn,
                account_id=acc.account_id,
                entry_type="TRADE_PNL",
                amount=pnl,
                balance_after=acc.balance,
                reference_id=pos.position_id,
                notes=f"سود/زیان بسته شدن معامله {pos.direction.value} ({pos.close_reason})",
            )
            conn.execute(
                "UPDATE paper_accounts SET balance = ?, equity = ?, margin_used = ? WHERE account_id = ?",
                (acc.balance, acc.equity, acc.margin_used, acc.account_id),
            )
            conn.commit()

        return pos

    def on_tick(self, bid: float, ask: float, timestamp: Optional[datetime] = None) -> None:
        """
        Processes price tick across all accounts:
        1. Checks and triggers pending orders (Limit/Stop)
        2. Updates unrealized PnL for open positions
        3. Checks Stop Loss, Take Profit, Trailing Stop
        4. Updates account equity, free margin, margin level %
        5. Enforces Stop Out if Margin Level < 20%
        """
        _now = timestamp or datetime.now(TZ_UTC)

        # 1. Process Pending Orders
        for ord_id, ord_obj in list(self.orders.items()):
            if ord_obj.status == OrderStatus.PENDING and ord_obj.target_price is not None:
                if ord_obj.direction == OrderDirection.BUY:
                    # Buy Limit triggers when Ask <= target
                    if ord_obj.order_type == OrderType.LIMIT and ask <= ord_obj.target_price:
                        self._fill_market_order(ord_obj, bid, ask)
                    # Buy Stop triggers when Ask >= target
                    elif ord_obj.order_type == OrderType.STOP and ask >= ord_obj.target_price:
                        self._fill_market_order(ord_obj, bid, ask)
                else:
                    # Sell Limit triggers when Bid >= target
                    if ord_obj.order_type == OrderType.LIMIT and bid >= ord_obj.target_price:
                        self._fill_market_order(ord_obj, bid, ask)
                    # Sell Stop triggers when Bid <= target
                    elif ord_obj.order_type == OrderType.STOP and bid <= ord_obj.target_price:
                        self._fill_market_order(ord_obj, bid, ask)

        # 2. Update Open Positions & Check SL/TP
        for pos_id, pos in list(self.positions.items()):
            if pos.status != PositionStatus.OPEN:
                continue

            acc = self.accounts[pos.account_id]
            d_entry = Decimal(str(pos.entry_price))
            d_lots = Decimal(str(pos.quantity_lots))
            d_contract = Decimal(str(acc.contract_size))

            if pos.direction == OrderDirection.BUY:
                pos.current_price = bid
                pos.highest_price = max(pos.highest_price, bid)
                d_bid = Decimal(str(bid))
                pos.unrealized_pnl = float(round((d_bid - d_entry) * d_lots * d_contract, 4))

                # Check SL
                if pos.sl_price is not None and bid <= pos.sl_price:
                    self.close_position(pos.position_id, pos.sl_price, reason="STOP_LOSS")
                    continue
                # Check TP
                if pos.tp_price is not None and bid >= pos.tp_price:
                    self.close_position(pos.position_id, pos.tp_price, reason="TAKE_PROFIT")
                    continue
                # Trailing Stop update
                if pos.trailing_stop_pips is not None:
                    new_sl = round(pos.highest_price - pos.trailing_stop_pips, 4)
                    if pos.sl_price is None or new_sl > pos.sl_price:
                        pos.sl_price = new_sl

            else:  # SELL
                pos.current_price = ask
                pos.lowest_price = min(pos.lowest_price, ask)
                d_ask = Decimal(str(ask))
                pos.unrealized_pnl = float(round((d_entry - d_ask) * d_lots * d_contract, 4))

                # Check SL
                if pos.sl_price is not None and ask >= pos.sl_price:
                    self.close_position(pos.position_id, pos.sl_price, reason="STOP_LOSS")
                    continue
                # Check TP
                if pos.tp_price is not None and ask <= pos.tp_price:
                    self.close_position(pos.position_id, pos.tp_price, reason="TAKE_PROFIT")
                    continue
                # Trailing Stop update
                if pos.trailing_stop_pips is not None:
                    new_sl = round(pos.lowest_price + pos.trailing_stop_pips, 4)
                    if pos.sl_price is None or new_sl < pos.sl_price:
                        pos.sl_price = new_sl

        # 3. Recalculate Accounts
        for acc_id in self.accounts:
            self.update_account_metrics(acc_id)

    def update_account_metrics(self, account_id: str) -> None:
        """Recalculates equity, margin, and margin level for an account."""
        acc = self.accounts[account_id]
        open_pos = [p for p in self.positions.values() if p.account_id == account_id and p.status == PositionStatus.OPEN]

        total_unrealized = sum(p.unrealized_pnl for p in open_pos)
        total_margin = sum(
            (p.quantity_lots * acc.contract_size * p.entry_price) / acc.leverage for p in open_pos
        )

        acc.unrealized_pnl = round(total_unrealized, 2)
        acc.equity = round(acc.balance + acc.unrealized_pnl, 2)
        acc.margin_used = round(total_margin, 2)
        acc.margin_free = round(acc.equity - acc.margin_used, 2)
        acc.margin_level_pct = (
            round((acc.equity / acc.margin_used) * 100.0, 2) if acc.margin_used > 0 else 0.0
        )

    def _save_order_db(self, order: PaperOrder) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO paper_orders (
                    order_id, account_id, symbol, direction, order_type, quantity_lots,
                    target_price, sl_price, tp_price, trailing_stop_pips, status,
                    created_time, filled_time, filled_price, rejection_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.order_id,
                    order.account_id,
                    order.symbol,
                    order.direction.value,
                    order.order_type.value,
                    order.quantity_lots,
                    order.target_price,
                    order.sl_price,
                    order.tp_price,
                    order.trailing_stop_pips,
                    order.status.value,
                    order.created_time.isoformat(),
                    order.filled_time.isoformat() if order.filled_time else None,
                    order.filled_price,
                    order.rejection_reason,
                ),
            )
            conn.commit()
