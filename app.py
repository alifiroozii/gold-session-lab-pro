"""
FastAPI Server & Application Controller for Gold Session Lab Pro.
Runs strictly locally on macOS at 127.0.0.1.
Coordinates real-time market data, paper broker, automated bot, and web dashboard.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from goldlab.backtester import BacktestingEngine
from goldlab.bot import AutomatedPaperBot, BotState
from goldlab.calendar import EconomicEvent, MacroNewsCalendar
from goldlab.engine import ResearchEngine
from goldlab.paper_broker import OrderDirection, OrderStatus, OrderType, PaperBroker

TZ_UTC = timezone.utc

app = FastAPI(
    title="Gold Session Lab Pro",
    description="XAUUSD Quantitative Market Structure Research & Internal Paper Broker",
    version="1.0.0",
)

# Restrict CORS to localhost only for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static and Templates
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
DATA_DIR = BASE_DIR / "data"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Core Systems
DB_PATH = str(DATA_DIR / "xauusd_lab.sqlite")
engine = ResearchEngine(db_path=DB_PATH)
broker = PaperBroker(db_path=DB_PATH)
bot = AutomatedPaperBot(account_id="ACC_DEFAULT", broker=broker, engine=engine, db_path=DB_PATH)
backtester = BacktestingEngine(db_path=DB_PATH)

# Setup initial events in Calendar
engine.calendar = MacroNewsCalendar(
    events=[
        EconomicEvent(
            name="US CPI (شاخص قیمت مصرف‌کننده)",
            release_time=datetime(2026, 11, 10, 13, 30, tzinfo=TZ_UTC),
            impact="HIGH",
        ),
        EconomicEvent(
            name="US NFP (گزارش اشتغال بخش غیرکشاورزی)",
            release_time=datetime(2026, 11, 6, 13, 30, tzinfo=TZ_UTC),
            impact="HIGH",
        ),
        EconomicEvent(
            name="FOMC Rate Decision (تصمیم نرخ بهره فدرال رزرو)",
            release_time=datetime(2026, 11, 18, 19, 0, tzinfo=TZ_UTC),
            impact="HIGH",
        ),
    ]
)

# Load demo dataset on startup
DEMO_CSV = DATA_DIR / "demo_xauusd_1m.csv"
if DEMO_CSV.exists():
    try:
        engine.load_from_csv(DEMO_CSV, timeframe="5m")
        engine.run_pipeline()
    except Exception as e:
        print(f"Notice: Initial data load: {e}")

# WebSocket connection manager
class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_json(self, message: dict) -> None:
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

# Background live simulator task
background_task: Optional[asyncio.Task] = None

async def market_heartbeat_loop() -> None:
    """Simulates live tick updates and dispatches them over WebSocket."""
    while True:
        try:
            await asyncio.sleep(2.0)
            if engine.current_candles:
                last_bar = engine.current_candles[-1]
                bid = last_bar.close
                ask = round(bid + 0.25, 2)
                broker.on_tick(bid, ask)

                await ws_manager.broadcast_json({
                    "type": "TICK",
                    "bid": bid,
                    "ask": ask,
                    "timestamp": datetime.now(TZ_UTC).isoformat()
                })
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Error in heartbeat loop: {e}")

@app.on_event("startup")
async def startup_event() -> None:
    global background_task
    background_task = asyncio.create_task(market_heartbeat_loop())

@app.on_event("shutdown")
async def shutdown_event() -> None:
    global background_task
    if background_task:
        background_task.cancel()

# --- Pydantic Request Models ---
class TimeframeRequest(BaseModel):
    timeframe: str

class OrderRequest(BaseModel):
    direction: str  # BUY / SELL
    order_type: str = "MARKET"  # MARKET / LIMIT / STOP
    quantity_lots: float = 0.10
    target_price: Optional[float] = None
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None

class FundRequest(BaseModel):
    amount: float

class BotStateRequest(BaseModel):
    state: str

class BotRiskRequest(BaseModel):
    risk_per_trade_pct: float
    max_daily_loss_pct: float
    max_open_positions: int
    max_daily_trades: int
    max_spread_pips: float

# --- Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request) -> Any:
    """Serves the primary Persian RTL Light-Theme Dashboard."""
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/api/market")
async def get_market_data(timeframe: Optional[str] = None) -> Dict[str, Any]:
    """Returns candle history, session levels, detected setups, and backtest summary."""
    if timeframe and timeframe != engine.current_timeframe and engine.candles_1m:
        engine.current_timeframe = timeframe
        engine.current_candles = engine.data_pipeline.aggregate_candles(engine.candles_1m, timeframe)
        engine.run_pipeline()
    return engine.get_dashboard_payload()

@app.post("/api/market/timeframe")
async def set_market_timeframe(req: TimeframeRequest) -> Dict[str, str]:
    if req.timeframe not in ["1m", "5m", "15m", "1h"]:
        raise HTTPException(status_code=400, detail="تایم‌فریم نامعتبر است.")
    if engine.candles_1m:
        engine.load_candles(engine.candles_1m, timeframe=req.timeframe)
        engine.run_pipeline()
    return {"status": "success", "timeframe": req.timeframe}

# --- Paper Broker Endpoints ---

@app.get("/api/broker/account")
async def get_account_info() -> Dict[str, Any]:
    acc = broker.accounts.get("ACC_DEFAULT")
    if not acc:
        raise HTTPException(status_code=404, detail="حساب پیش‌فرض یافت نشد.")
    broker.update_account_metrics("ACC_DEFAULT")
    return {
        "account_id": acc.account_id,
        "name": acc.name,
        "balance": acc.balance,
        "equity": acc.equity,
        "margin_used": acc.margin_used,
        "margin_free": acc.margin_free,
        "margin_level_pct": acc.margin_level_pct,
        "unrealized_pnl": acc.unrealized_pnl,
        "realized_pnl": acc.realized_pnl,
        "leverage": acc.leverage,
    }

@app.post("/api/broker/deposit")
async def deposit_funds(req: FundRequest) -> Dict[str, Any]:
    acc = broker.deposit("ACC_DEFAULT", req.amount, notes="واریز دستی وجه مجازی")
    return {"status": "success", "balance": acc.balance}

@app.post("/api/broker/withdraw")
async def withdraw_funds(req: FundRequest) -> Dict[str, Any]:
    try:
        acc = broker.withdraw("ACC_DEFAULT", req.amount, notes="برداشت دستی وجه مجازی")
        return {"status": "success", "balance": acc.balance}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/broker/reset")
async def reset_account() -> Dict[str, Any]:
    acc = broker.reset_account("ACC_DEFAULT", 10000.0)
    return {"status": "success", "balance": acc.balance}

@app.get("/api/broker/positions")
async def get_open_positions() -> List[Dict[str, Any]]:
    positions = [
        {
            "position_id": p.position_id,
            "symbol": p.symbol,
            "direction": p.direction.value,
            "quantity_lots": p.quantity_lots,
            "entry_price": p.entry_price,
            "current_price": p.current_price,
            "sl_price": p.sl_price,
            "tp_price": p.tp_price,
            "unrealized_pnl": p.unrealized_pnl,
            "entry_time": p.entry_time.isoformat(),
        }
        for p in broker.positions.values()
        if p.status.value == "OPEN"
    ]
    return positions

@app.post("/api/broker/positions/{pos_id}/close")
async def close_position_endpoint(pos_id: str) -> Dict[str, Any]:
    pos = broker.positions.get(pos_id)
    if not pos or pos.status.value != "OPEN":
        raise HTTPException(status_code=404, detail="موقعیت باز یافت نشد.")
    bid = engine.current_candles[-1].close if engine.current_candles else pos.entry_price
    ask = round(bid + 0.25, 2)
    exit_p = bid if pos.direction == OrderDirection.BUY else ask
    closed_pos = broker.close_position(pos_id, exit_p, reason="MANUAL_CLOSE")
    return {"status": "success", "realized_pnl": closed_pos.realized_pnl}

@app.get("/api/broker/orders")
async def get_orders() -> List[Dict[str, Any]]:
    return [
        {
            "order_id": o.order_id,
            "direction": o.direction.value,
            "order_type": o.order_type.value,
            "quantity_lots": o.quantity_lots,
            "target_price": o.target_price,
            "sl_price": o.sl_price,
            "tp_price": o.tp_price,
            "status": o.status.value,
            "created_time": o.created_time.isoformat(),
        }
        for o in broker.orders.values()
    ]

@app.post("/api/broker/order")
async def submit_order_endpoint(req: OrderRequest) -> Dict[str, Any]:
    direction = OrderDirection(req.direction.upper())
    order_type = OrderType(req.order_type.upper())

    bid = engine.current_candles[-1].close if engine.current_candles else 2650.0
    ask = round(bid + 0.25, 2)

    try:
        order = broker.submit_order(
            account_id="ACC_DEFAULT",
            direction=direction,
            order_type=order_type,
            quantity_lots=req.quantity_lots,
            target_price=req.target_price,
            sl_price=req.sl_price,
            tp_price=req.tp_price,
            current_bid=bid,
            current_ask=ask,
        )
        return {"status": "success", "order_id": order.order_id, "order_status": order.status.value}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/broker/orders/{order_id}/cancel")
async def cancel_order_endpoint(order_id: str) -> Dict[str, str]:
    order = broker.orders.get(order_id)
    if not order or order.status.value != "PENDING":
        raise HTTPException(status_code=404, detail="سفارش معلق یافت نشد.")
    order.status = OrderStatus.CANCELLED
    broker._save_order_db(order)
    return {"status": "success"}

@app.get("/api/broker/ledger")
async def get_ledger_history() -> List[Dict[str, Any]]:
    import sqlite3
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM wallet_ledger ORDER BY timestamp DESC LIMIT 50")
        return [dict(row) for row in cur.fetchall()]

# --- Bot Endpoints ---

@app.get("/api/bot/status")
async def get_bot_status() -> Dict[str, Any]:
    import sqlite3
    events = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM bot_events ORDER BY timestamp DESC LIMIT 25")
        events = [dict(r) for r in cur.fetchall()]
        events.reverse()

    return {
        "bot_id": bot.bot_id,
        "state": bot.state.value,
        "heartbeat": bot.heartbeat_time.isoformat(),
        "today_trades_count": bot.today_trades_count,
        "events": events,
        "risk_settings": {
            "risk_per_trade_pct": bot.risk.risk_per_trade_pct,
            "max_daily_loss_pct": bot.risk.max_daily_loss_pct,
            "max_open_positions": bot.risk.max_open_positions,
            "max_daily_trades": bot.risk.max_daily_trades,
            "max_spread_pips": bot.risk.max_spread_pips,
        },
    }

@app.post("/api/bot/state")
async def set_bot_state_endpoint(req: BotStateRequest) -> Dict[str, str]:
    try:
        new_state = BotState(req.state)
        bot.set_state(new_state)
        return {"status": "success", "new_state": bot.state.value}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/bot/risk")
async def set_bot_risk_endpoint(req: BotRiskRequest) -> Dict[str, str]:
    bot.risk.risk_per_trade_pct = req.risk_per_trade_pct
    bot.risk.max_daily_loss_pct = req.max_daily_loss_pct
    bot.risk.max_open_positions = req.max_open_positions
    bot.risk.max_daily_trades = req.max_daily_trades
    bot.risk.max_spread_pips = req.max_spread_pips
    bot.log_event("RISK_UPDATED", "تنظیمات مدیریت ریسک ربات به‌روزرسانی شد.")
    return {"status": "success"}

# --- Backtest Endpoints ---

@app.get("/api/backtest/compare")
async def get_strategy_comparison() -> Dict[str, Any]:
    """Runs all 8 strategies on the current dataset and returns comparison metrics."""
    if not engine.current_candles:
        raise HTTPException(status_code=400, detail="داده‌ای برای ارزیابی موجود نیست.")
    results = backtester.run_strategy_comparison(engine.current_candles)
    return {
        "results": [
            {
                "strategy_id": r.strategy_id,
                "strategy_name": r.strategy_name,
                "total_trades": r.total_trades,
                "win_rate_pct": r.win_rate_pct,
                "profit_factor": r.profit_factor,
                "expectancy_r": r.expectancy_r,
                "max_drawdown_r": r.max_drawdown_r,
                "evidence_status": r.evidence_status,
            }
            for r in results
        ]
    }

# --- Calendar Endpoints ---

@app.get("/api/calendar")
async def get_calendar_events() -> Dict[str, Any]:
    now = datetime.now(TZ_UTC)
    events_data = []
    for ev in engine.calendar.events:
        is_blocked, reason = engine.calendar.is_blackout(now)
        events_data.append({
            "name": ev.name,
            "release_time": ev.release_time.isoformat(),
            "impact": ev.impact,
            "status": "مسدود شده (Blackout Active)" if is_blocked else "عادی (Clear)",
            "is_blackout": is_blocked,
        })
    return {"events": events_data}

# --- WebSocket Endpoint ---

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
