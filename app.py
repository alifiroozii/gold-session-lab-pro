"""
FastAPI Server & Application Controller for Gold Autonomous Trading Research Lab Pro.
Runs strictly locally on macOS at 127.0.0.1:8000.
Coordinates real-time market data, paper broker, automated bot,
independent risk guardian, market regime monitor, AI research supervisor,
diagnostics, learning autopsies, and Champion/Challenger promotion.
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

from goldlab.agent_bridge import AgentBridge
from goldlab.autofix import SafeAutoFixEngine
from goldlab.backtester import BacktestingEngine
from goldlab.bot import AutomatedPaperBot, BotState
from goldlab.calendar import EconomicEvent, MacroNewsCalendar
from goldlab.diagnostics import DiagnosticsEngine
from goldlab.engine import ResearchEngine
from goldlab.guardian import IndependentRiskGuardian
from goldlab.market_safety import OandaReadOnlyFeed, MarketQuote, execution_gate
from goldlab.learning import MistakeAnalyzerAndHypothesisRegistry
from goldlab.ml_model import MLTradeQualityModel
from goldlab.paper_broker import OrderDirection, OrderStatus, OrderType, PaperBroker
from goldlab.promotion import ChampionChallengerManager
from goldlab.regime import MarketRegimeMonitor
from goldlab.supervisor import JobType, ResearchSupervisor

TZ_UTC = timezone.utc

app = FastAPI(
    title="Gold Session Lab Pro — Autonomous Research Lab",
    description="XAUUSD Institutional Market Structure Research, Paper Broker & Autonomous AI Lab",
    version="3.0.0",
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
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Core Systems
DB_PATH = str(DATA_DIR / "xauusd_lab.sqlite")
engine = ResearchEngine(db_path=DB_PATH)
market_feed = OandaReadOnlyFeed()
verified_quote: Optional[MarketQuote] = None
market_block_reason = "NO_VERIFIED_LIVE_QUOTE"
engine.market_data_source = "DEMO_CSV"
broker = PaperBroker(db_path=DB_PATH)
bot = AutomatedPaperBot(account_id="ACC_DEFAULT", broker=broker, engine=engine, db_path=DB_PATH)
backtester = BacktestingEngine(db_path=DB_PATH)

# Autonomous Research & Safety Engines
guardian = IndependentRiskGuardian(db_path=DB_PATH)
regime_monitor = MarketRegimeMonitor()
diagnostics = DiagnosticsEngine(db_path=DB_PATH)
autofix = SafeAutoFixEngine(db_path=DB_PATH)
agent_bridge = AgentBridge(db_path=DB_PATH)
learning = MistakeAnalyzerAndHypothesisRegistry(db_path=DB_PATH)
ml_model = MLTradeQualityModel(db_path=DB_PATH, shadow_mode=True)
promotion = ChampionChallengerManager(db_path=DB_PATH)
supervisor = ResearchSupervisor(db_path=DB_PATH, reports_dir=str(REPORTS_DIR))

# Calendar initialization
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
if market_feed.configured:
    try:
        candles = market_feed.historical_m1()
        if candles:
            engine.load_candles(candles, timeframe="5m")
            engine.market_data_source = "OANDA_HISTORICAL_MID"
            engine.run_pipeline()
    except Exception:
        # Credential failures must not convert demo candles to a live quote.
        pass
if not engine.current_candles and DEMO_CSV.exists():
    try:
        engine.load_from_csv(DEMO_CSV, timeframe="5m")
        engine.market_data_source = "DEMO_CSV"
        engine.run_pipeline()
    except Exception as e:
        print(f"Notice: Initial demo load: {e}")


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

# Background live simulator & supervisor task
background_task: Optional[asyncio.Task] = None


async def market_heartbeat_loop() -> None:
    """Poll verified read-only OANDA prices; never replay old/demo data as live ticks."""
    global verified_quote, market_block_reason
    counter = 0
    while True:
        try:
            await asyncio.sleep(5.0)
            counter += 1
            new_quote = None
            if market_feed.configured:
                try:
                    new_quote = await asyncio.to_thread(market_feed.latest_quote)
                except Exception:
                    market_block_reason = "LIVE_FEED_UNAVAILABLE"
            ok, reason = execution_gate(new_quote)
            verified_quote = new_quote if ok else None
            market_block_reason = reason if new_quote is not None else (
                "LIVE_FEED_UNAVAILABLE" if market_feed.configured else "OANDA_NOT_CONFIGURED"
            )
            if verified_quote is not None:
                broker.on_tick(verified_quote.bid, verified_quote.ask,
                               timestamp=verified_quote.timestamp)
                # Refresh actual historical candles separately from authenticated quotes.
                if counter % 12 == 0:
                    try:
                        bars = await asyncio.to_thread(market_feed.historical_m1)
                        if bars:
                            engine.load_candles(bars, timeframe=engine.current_timeframe)
                            engine.market_data_source = "OANDA_HISTORICAL_MID"
                            engine.run_pipeline()
                    except Exception:
                        pass
                await ws_manager.broadcast_json({
                    "type": "TICK", "bid": verified_quote.bid, "ask": verified_quote.ask,
                    "source": verified_quote.source,
                    "timestamp": verified_quote.timestamp.isoformat(),
                    "verified": True,
                })
            else:
                # Closed market or unavailable source: do NOT send synthetic ticks.
                if bot.state == BotState.PAPER_AUTO:
                    bot.set_state(BotState.DATA_DISCONNECTED)
                await ws_manager.broadcast_json({
                    "type": "MARKET_STATUS", "status": market_block_reason,
                    "verified": False,
                    "timestamp": datetime.now(TZ_UTC).isoformat(),
                })
            if counter % 6 == 0:
                supervisor.run_health_loop(broker)
                guardian.audit_ledger_invariance("ACC_DEFAULT", broker)
        except asyncio.CancelledError:
            break
        except Exception as e:
            verified_quote = None
            market_block_reason = "LIVE_FEED_ERROR"
            diagnostics.categorize_exception(e, {"source": "market_heartbeat_loop"})


@app.on_event("startup")
async def startup_event() -> None:
    global background_task
    # Ensure research hypotheses and baseline champion are seeded
    supervisor.run_research_cycle()
    background_task = asyncio.create_task(market_heartbeat_loop())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    global background_task
    if background_task:
        background_task.cancel()


def get_execution_status() -> Dict[str, Any]:
    allowed, reason = execution_gate(verified_quote)
    return {
        "market_open": allowed,
        "paper_orders_allowed": allowed,
        "paper_auto_allowed": False,
        "reason": reason if not allowed else "VERIFIED_LIVE_PRICE",
        "quote_source": verified_quote.source if verified_quote else None,
        "quote_time": verified_quote.timestamp.isoformat() if verified_quote else None,
        "bid": verified_quote.bid if verified_quote else None,
        "ask": verified_quote.ask if verified_quote else None,
        "chart_source": engine.market_data_source,
        "provider_configured": market_feed.configured,
        "historical_data_is_executable": False,
    }


@app.get("/api/market/status")
async def get_market_status() -> Dict[str, Any]:
    return get_execution_status()


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


class HypothesisCreateRequest(BaseModel):
    title: str
    rationale: str
    target_metric: str


class AutoFixActionRequest(BaseModel):
    user_confirmed: bool = False
    reason: str = ""


class PromoteChallengerRequest(BaseModel):
    challenger_id: str
    user_confirmed: bool = False


# --- Core Web & Market Endpoints ---

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
    payload = engine.get_dashboard_payload()
    payload["data_source"] = engine.market_data_source
    payload["execution"] = get_execution_status()
    payload["session_boxes"] = engine.session_mgr.calculate_session_boxes(engine.current_candles)
    return payload


@app.post("/api/market/timeframe")
async def set_market_timeframe(req: TimeframeRequest) -> Dict[str, str]:
    if req.timeframe not in ["1m", "5m", "15m", "1h"]:
        raise HTTPException(status_code=400, detail="تایم‌فریم نامعتبر است.")
    if engine.candles_1m:
        engine.load_candles(engine.candles_1m, timeframe=req.timeframe)
        engine.run_pipeline()
    return {"status": "success", "timeframe": req.timeframe}


@app.get("/api/regime/current")
async def get_current_regime() -> Dict[str, Any]:
    """Returns real-time market regime, volatility ratio, trend slope, and trading favorability."""
    is_news, _ = engine.calendar.is_blackout(datetime.now(TZ_UTC))
    report = regime_monitor.analyze_regime(
        candles=engine.current_candles,
        current_spread=0.25,
        is_news_blackout=is_news,
    )
    return {
        "primary_regime": report.primary_regime.value,
        "secondary_regime": report.secondary_regime.value if report.secondary_regime else None,
        "atr_current": report.atr_current,
        "atr_baseline": report.atr_baseline,
        "volatility_ratio": report.volatility_ratio,
        "adx_trend_slope": report.adx_trend_slope,
        "false_breakout_rate": report.false_breakout_rate,
        "current_spread": report.current_spread,
        "is_favorable": report.is_favorable_for_trading,
        "description": report.description,
    }


# --- Paper Broker Endpoints ---

@app.get("/api/broker/account")
async def get_account_info() -> Dict[str, Any]:
    acc = broker.accounts.get("ACC_DEFAULT")
    if not acc:
        raise HTTPException(status_code=404, detail="حساب پیش‌فرض یافت نشد.")
    broker.update_account_metrics("ACC_DEFAULT")

    # Audit ledger invariance
    ok, audit_msg = guardian.audit_ledger_invariance("ACC_DEFAULT", broker)

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
        "ledger_invariance_ok": ok,
        "ledger_audit_msg": audit_msg,
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
    return [
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


@app.post("/api/broker/positions/{pos_id}/close")
async def close_position_endpoint(pos_id: str) -> Dict[str, Any]:
    pos = broker.positions.get(pos_id)
    if not pos or pos.status.value != "OPEN":
        raise HTTPException(status_code=404, detail="موقعیت باز یافت نشد.")
    allowed, reason = execution_gate(verified_quote)
    if not allowed:
        raise HTTPException(status_code=409, detail=f"Market close blocked: {reason}")
    assert verified_quote is not None
    exit_p = verified_quote.bid if pos.direction == OrderDirection.BUY else verified_quote.ask
    closed_pos = broker.close_position(pos_id, exit_p, reason="MANUAL_CLOSE")

    # Trigger post-trade autopsy
    r_val = 0.0
    if pos.sl_price and abs(pos.entry_price - pos.sl_price) > 0:
        risk_dist = abs(pos.entry_price - pos.sl_price)
        r_val = (closed_pos.realized_pnl / (risk_dist * pos.quantity_lots * 100.0))
    learning.perform_autopsy(
        trade_id=pos.position_id,
        setup_id="MANUAL",
        side=pos.direction.value,
        pnl=closed_pos.realized_pnl,
        r_multiple=r_val,
        entry_price=pos.entry_price,
        exit_price=exit_p,
        sl_price=pos.sl_price or (pos.entry_price - 2.0),
        tp_price=pos.tp_price or (pos.entry_price + 4.0),
    )

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

    allowed, reason = execution_gate(verified_quote)
    if not allowed:
        raise HTTPException(status_code=409, detail=f"Order blocked: {reason}")
    assert verified_quote is not None

    try:
        order = broker.submit_order(
            account_id="ACC_DEFAULT",
            direction=direction,
            order_type=order_type,
            quantity_lots=req.quantity_lots,
            target_price=req.target_price,
            sl_price=req.sl_price,
            tp_price=req.tp_price,
            current_bid=verified_quote.bid,
            current_ask=verified_quote.ask,
        )
        return {"status": "success", "order_id": order.order_id, "order_status": order.status.value}
    except Exception as e:
        diagnostics.categorize_exception(e, {"source": "submit_order", "req": req.dict()})
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
        if new_state == BotState.PAPER_AUTO:
            allowed, reason = execution_gate(verified_quote)
            if not allowed:
                raise HTTPException(status_code=409, detail=f"Paper auto blocked: {reason}")
            # No automatic entries until causal next-bar strategy execution is validated.
            raise HTTPException(status_code=409, detail="PAPER_AUTO_UNVERIFIED: strategy runtime has not passed execution tests.")
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
        is_blocked, _ = engine.calendar.is_blackout(now)
        events_data.append({
            "name": ev.name,
            "release_time": ev.release_time.isoformat(),
            "impact": ev.impact,
            "status": "مسدود شده (Blackout Active)" if is_blocked else "عادی (Clear)",
            "is_blackout": is_blocked,
        })
    return {"events": events_data}


# --- Antigravity transparent bridge (no invented live agent) ---
@app.get("/api/agent/status")
async def get_agent_status() -> Dict[str, Any]:
    return agent_bridge.state()


# --- AI Research Supervisor Endpoints ---

@app.get("/api/supervisor/status")
async def get_supervisor_status() -> Dict[str, Any]:
    """Returns state of research cycles, current champion, and recent job queue."""
    champ = promotion.get_current_champion()
    recent_jobs = supervisor.list_jobs(limit=10)
    return {
        "status": "LOCAL_SUPERVISOR_ONLY",
        "antigravity": agent_bridge.state()["agent_status"],
        "champion": {
            "name": champ.name if champ else "None",
            "expectancy_r": champ.expectancy_r if champ else 0.0,
            "win_rate": champ.win_rate if champ else 0.0,
            "trades": champ.total_trades if champ else 0,
        },
        "recent_jobs": recent_jobs,
        "timestamp": datetime.now(TZ_UTC).isoformat(),
    }


@app.post("/api/supervisor/trigger")
async def trigger_supervisor_cycle(cycle_type: str) -> Dict[str, Any]:
    """Manually triggers a specific research loop (HEALTH, DIAGNOSTICS, RESEARCH, NIGHTLY)."""
    try:
        jt = JobType(cycle_type.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"نوع چرخه نامعتبر است: {cycle_type}")

    job = supervisor.enqueue_job(jt)
    executed_job = supervisor.execute_next_pending_job(broker)
    return {
        "status": "success",
        "job_id": job.job_id,
        "result": executed_job.result if executed_job else {},
    }


# --- Diagnostics & Auto-Fix Endpoints ---

@app.get("/api/diagnostics/incidents")
async def get_diagnostic_incidents(limit: int = 50) -> List[Dict[str, Any]]:
    return diagnostics.get_recent_incidents(limit=limit)


@app.get("/api/diagnostics/summary")
async def get_diagnostic_summary() -> Dict[str, Any]:
    counts = diagnostics.get_category_counts()
    return {"category_counts": counts}


@app.get("/api/autofix/proposals")
async def get_autofix_proposals(limit: int = 50) -> List[Dict[str, Any]]:
    return autofix.list_proposals(limit=limit)


@app.post("/api/autofix/proposals/{proposal_id}/approve")
async def approve_autofix_proposal(proposal_id: str, req: AutoFixActionRequest) -> Dict[str, Any]:
    res = autofix.approve_and_apply_fix(proposal_id, user_confirmed=req.user_confirmed)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res


@app.post("/api/autofix/proposals/{proposal_id}/reject")
async def reject_autofix_proposal(proposal_id: str, req: AutoFixActionRequest) -> Dict[str, str]:
    autofix.reject_fix(proposal_id, reason=req.reason)
    return {"status": "success", "message": f"اصلاحیه {proposal_id} رد شد."}


# --- Learning & Hypothesis Registry Endpoints ---

@app.get("/api/learning/autopsies")
async def get_trade_autopsies(limit: int = 50) -> List[Dict[str, Any]]:
    return learning.list_autopsies(limit=limit)


@app.get("/api/learning/hypotheses")
async def get_hypotheses(limit: int = 50) -> List[Dict[str, Any]]:
    return learning.list_hypotheses(limit=limit)


@app.post("/api/learning/hypotheses")
async def create_hypothesis_endpoint(req: HypothesisCreateRequest) -> Dict[str, Any]:
    hyp = learning.register_hypothesis(
        title=req.title,
        rationale=req.rationale,
        target_metric=req.target_metric,
    )
    return {"status": "success", "hypothesis_id": hyp.hypothesis_id}


# --- ML Shadow Scores Endpoints ---

@app.get("/api/ml/scores")
async def get_ml_scores(limit: int = 50) -> List[Dict[str, Any]]:
    return ml_model.get_recent_scores(limit=limit)


# --- Champion / Challenger Promotion Endpoints ---

@app.get("/api/promotion/versions")
async def get_strategy_versions() -> List[Dict[str, Any]]:
    return promotion.list_versions()


@app.get("/api/promotion/evaluate/{challenger_id}")
async def evaluate_challenger(challenger_id: str) -> Dict[str, Any]:
    return promotion.evaluate_challenger_promotion(challenger_id)


@app.post("/api/promotion/promote")
async def promote_challenger_endpoint(req: PromoteChallengerRequest) -> Dict[str, Any]:
    res = promotion.promote_challenger(
        challenger_id=req.challenger_id,
        user_confirmed=req.user_confirmed,
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res


# --- Reports Endpoint ---

@app.get("/api/reports/latest")
async def get_latest_report() -> Dict[str, Any]:
    report_files = sorted(REPORTS_DIR.glob("DAILY_RESEARCH_REPORT_*.md"), reverse=True)
    if not report_files:
        # Trigger nightly report generation
        res = supervisor.run_nightly_evaluation(broker)
        report_files = [Path(res["report_path"])]

    latest_file = report_files[0]
    content = latest_file.read_text(encoding="utf-8")
    return {
        "filename": latest_file.name,
        "content": content,
    }


# --- WebSocket Endpoint ---

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
