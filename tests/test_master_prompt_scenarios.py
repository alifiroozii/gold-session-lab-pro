"""Master Prompt Verification Suite — Scenarios 1 to 8.

Proves:
TEST 1: Market closed -> no new paper orders allowed.
TEST 2: Synthetic / unverified price -> order rejected.
TEST 3: Stale price -> order rejected.
TEST 4: Sweep happened but BOS not confirmed -> no entry signal.
TEST 5: All strategy conditions complete -> valid entry signal generated.
TEST 6: In Paper Auto mode with verified quote and valid risk controls -> virtual trade allowed.
TEST 7: Antigravity disconnected -> paper execution engine operates independently.
TEST 8: Challenger strategy performs worse than Champion -> Champion is preserved.
"""
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from goldlab.agent_bridge import AgentBridge
from goldlab.bot import AutomatedPaperBot, BotRiskSettings, BotState
from goldlab.fixtures import generate_sweep_reclaim_bos_retest_fixture
from goldlab.market_safety import MarketQuote, execution_gate
from goldlab.market_structure import MarketStructureAnalyzer
from goldlab.paper_broker import OrderDirection, OrderStatus, OrderType, PaperBroker
from goldlab.promotion import ChampionChallengerManager
from goldlab.setups import SetupConfig, SetupEngine
from goldlab.types import Candle, SignalDirection

UTC = timezone.utc
NY = ZoneInfo("America/New_York")


def test_scenario_1_market_closed_no_new_orders() -> None:
    """TEST 1: Market is closed (weekend) -> execution_gate blocks all orders."""
    # Saturday 12:00 NY time
    saturday_noon = datetime(2026, 11, 7, 12, 0, tzinfo=NY).astimezone(UTC)
    quote = MarketQuote(
        bid=2650.0,
        ask=2650.5,
        timestamp=saturday_noon,
        source="OANDA_V20_READ_ONLY",
        tradeable=True,
    )
    allowed, reason = execution_gate(quote, now=saturday_noon)
    assert not allowed, "Orders must be blocked when market is closed"
    assert reason == "WEEKEND_MARKET_CLOSED"


def test_scenario_2_synthetic_price_rejected() -> None:
    """TEST 2: Synthetic/demo price source -> rejected by execution_gate."""
    now = datetime(2026, 11, 4, 14, 0, tzinfo=UTC)  # Wednesday mid-market
    synthetic_quote = MarketQuote(
        bid=2650.0,
        ask=2650.5,
        timestamp=now,
        source="DEMO_CSV",  # Untrusted
        tradeable=True,
    )
    allowed, reason = execution_gate(synthetic_quote, now=now)
    assert not allowed, "Synthetic price must be rejected"
    assert reason == "UNTRUSTED_DATA_SOURCE"


def test_scenario_3_stale_price_rejected() -> None:
    """TEST 3: Stale quote (> 30s old) -> rejected by execution_gate."""
    now = datetime(2026, 11, 4, 14, 0, tzinfo=UTC)
    stale_timestamp = now - timedelta(seconds=45)
    stale_quote = MarketQuote(
        bid=2650.0,
        ask=2650.5,
        timestamp=stale_timestamp,
        source="OANDA_V20_READ_ONLY",
        tradeable=True,
    )
    allowed, reason = execution_gate(stale_quote, now=now, max_age_seconds=30)
    assert not allowed, "Stale price must be rejected"
    assert reason == "QUOTE_STALE_OR_FUTURE"


def test_scenario_4_sweep_without_bos_no_entry() -> None:
    """TEST 4: Sweep happened but BOS was never confirmed -> no entry signal."""
    # Build candle sequence where candle sweeps but reclaim fails to break structure (no BOS)
    start = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)
    candles = [
        Candle(timestamp=start, open=2652.0, high=2654.0, low=2650.0, close=2651.0),
        Candle(timestamp=start + timedelta(minutes=5), open=2651.0, high=2653.0, low=2650.0, close=2652.0),
        Candle(timestamp=start + timedelta(minutes=10), open=2652.0, high=2653.0, low=2650.5, close=2651.5),
        Candle(timestamp=start + timedelta(minutes=15), open=2651.5, high=2652.0, low=2650.0, close=2650.5),
        # Sweep below 2650.0
        Candle(timestamp=start + timedelta(minutes=20), open=2650.5, high=2651.0, low=2645.0, close=2648.0),
        # Reclaim closes inside range (2651.0)
        Candle(timestamp=start + timedelta(minutes=25), open=2648.0, high=2652.0, low=2647.0, close=2651.0),
        # Fails BOS: bar stays flat, does not break candle 5 high (2652.0)
        Candle(timestamp=start + timedelta(minutes=30), open=2651.0, high=2651.5, low=2650.2, close=2650.8),
        # Retest attempt without prior BOS
        Candle(timestamp=start + timedelta(minutes=35), open=2650.8, high=2651.0, low=2650.1, close=2650.9),
    ]

    analyzer = MarketStructureAnalyzer()
    analyzer.enrich_candle_metrics(candles)
    swings = analyzer.find_swing_points(candles)
    fvgs = analyzer.find_fair_value_gaps(candles)
    obs = analyzer.detect_order_block_proxies(candles, swings)
    session_stats = {"asia": {"low": 2650.0, "high": 2670.0}}

    cfg = SetupConfig(enable_sweep_reclaim_bos=True)
    engine = SetupEngine(config=cfg, structure=analyzer)

    signals = engine.evaluate_all(candles, swings, fvgs, obs, session_stats, allow_pending=True)
    sweep_signals = [s for s in signals if s.setup_id == "SETUP_2_SWEEP_RECLAIM_BOS"]
    assert len(sweep_signals) == 0, "No entry signal may be generated without confirmed BOS"


def test_scenario_5_all_conditions_complete_valid_signal() -> None:
    """TEST 5: All strategy conditions complete (Sweep -> Reclaim -> BOS -> Retest)

    -> Valid Setup 2 signal generated.
    """
    candles = generate_sweep_reclaim_bos_retest_fixture()[:8]
    analyzer = MarketStructureAnalyzer()
    analyzer.enrich_candle_metrics(candles)
    swings = analyzer.find_swing_points(candles)
    fvgs = analyzer.find_fair_value_gaps(candles)
    obs = analyzer.detect_order_block_proxies(candles, swings)
    session_stats = {"asia": {"low": 2650.0, "high": 2670.0}}

    cfg = SetupConfig(enable_sweep_reclaim_bos=True)
    engine = SetupEngine(config=cfg, structure=analyzer)

    signals = engine.evaluate_all(candles, swings, fvgs, obs, session_stats, allow_pending=True)
    sweep_signals = [s for s in signals if s.setup_id == "SETUP_2_SWEEP_RECLAIM_BOS"]
    assert len(sweep_signals) == 1
    sig = sweep_signals[0]
    assert sig.direction == SignalDirection.BUY
    assert sig.signal_index == 7
    assert sig.entry_index == 8
    assert sig.sl_price < sig.entry_price < sig.tp_price


def test_scenario_6_paper_auto_with_verified_quote_executes(tmp_path: Path) -> None:
    """TEST 6: In Paper Auto mode with verified quote and risk controls passed

    -> virtual paper order executes successfully.
    """
    db_file = str(tmp_path / "paper_auto.sqlite")
    broker = PaperBroker(db_path=db_file)
    bot = AutomatedPaperBot(
        bot_id="BOT_TEST_AUTO",
        broker=broker,
        db_path=db_file,
        risk_settings=BotRiskSettings(risk_per_trade_pct=0.50, max_spread_pips=1.0),
    )
    bot.state = BotState.PAPER_AUTO

    # Feed healthy candles
    candles = generate_sweep_reclaim_bos_retest_fixture()[:8]
    bot.engine.calendar.is_blackout = lambda ts: (False, "")
    bot.engine.session_mgr.calculate_as_of_session_stats_series = lambda c: [
        {"asia": {"low": 2650.0, "high": 2670.0}} for _ in c
    ]

    # Explicitly fund the fake account so the minimum 0.01 lot fits
    # within 0.5% of account balance (no forced size-up is permitted).
    broker.deposit("ACC_DEFAULT", 5000.0, notes="test-only virtual funding")
    open_positions_before = len(broker.positions)
    bid, ask = 2654.0, 2654.5  # Spread $0.50 within limit

    signals = bot.on_candle_close(
        candles,
        current_bid=bid,
        current_ask=ask,
        current_time=candles[-1].timestamp,
    )
    assert len(signals) >= 1
    assert len(broker.positions) >= open_positions_before + 1

    # Verify order was submitted to broker
    open_orders = list(broker.orders.values())
    assert len(open_orders) >= 1
    last_order = open_orders[-1]
    assert last_order.direction == OrderDirection.BUY
    assert last_order.status == OrderStatus.FILLED

    # Verify filled position has entry price at ask + slippage
    open_positions = list(broker.positions.values())
    expected_entry = round(ask + broker.slippage_pips, 4)
    assert any(
        p.direction == OrderDirection.BUY and math.isclose(p.entry_price, expected_entry, abs_tol=1e-4)
        for p in open_positions
    )


def test_scenario_7_antigravity_disconnected_paper_engine_independent(tmp_path: Path) -> None:
    """TEST 7: Antigravity disconnected -> paper execution engine continues operating

    independently without halting.
    """
    db_file = str(tmp_path / "independent.sqlite")
    bridge = AgentBridge(db_path=db_file)
    status = bridge.state()
    assert status["agent_status"] == "NOT_CONNECTED"

    # Paper broker and bot remain fully operational
    broker = PaperBroker(db_path=db_file)
    account = broker.accounts.get("ACC_DEFAULT")
    assert account is not None
    assert account.balance == 1000.0

    # Broker submits orders independently of AI status
    order = broker.submit_order(
        account_id="ACC_DEFAULT",
        direction=OrderDirection.BUY,
        order_type=OrderType.MARKET,
        quantity_lots=0.1,
        current_bid=2650.0,
        current_ask=2650.5,
    )
    assert order.status == OrderStatus.FILLED


def test_scenario_8_worse_challenger_preserves_champion(tmp_path: Path) -> None:
    """TEST 8: Challenger strategy with worse performance does NOT replace Champion."""
    db_file = str(tmp_path / "promotion.sqlite")
    mgr = ChampionChallengerManager(db_path=db_file)

    champion = mgr.get_current_champion()
    assert champion is not None
    initial_champion_id = champion.version_id

    # Register an inferior challenger (Win rate 30%, negative expectancy)
    worse_challenger = mgr.register_version(
        name="Inferior Challenger",
        is_champion=False,
        config={"setups": ["S1_ASIA_SWEEP"]},
        total_trades=100,
        win_rate=30.0,
        expectancy_r=-0.35,
        max_drawdown_pct=15.0,
        sharpe_ratio=0.20,
        p_value=0.85,
        notes="Inferior challenger with poor metrics",
    )

    # Evaluate promotion - must not be eligible
    decision = mgr.evaluate_challenger_promotion(worse_challenger.version_id)
    assert decision["eligible"] is False

    # Attempt promotion - must fail and keep Champion intact
    promo_result = mgr.promote_challenger(worse_challenger.version_id, user_confirmed=True)
    assert promo_result["success"] is False

    # Champion must remain unchanged
    active_champion = mgr.get_current_champion()
    assert active_champion is not None
    assert active_champion.version_id == initial_champion_id
