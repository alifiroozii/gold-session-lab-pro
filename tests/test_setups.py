"""
Tests for Modular Setup detection.
Rigorously proves that for a pattern of Sweep + Reclaim + BOS + Retest,
the generated signal mandates ENTRY strictly on the NEXT CANDLE (index i + 1).
"""


from goldlab.fixtures import generate_sweep_reclaim_bos_retest_fixture
from goldlab.market_structure import MarketStructureAnalyzer
from goldlab.setups import SetupConfig, SetupEngine
from goldlab.types import SignalDirection


def test_sweep_reclaim_bos_retest_entry_on_next_candle() -> None:
    candles = generate_sweep_reclaim_bos_retest_fixture()
    analyzer = MarketStructureAnalyzer()
    analyzer.enrich_candle_metrics(candles)
    swings = analyzer.find_swing_points(candles)
    fvgs = analyzer.find_fair_value_gaps(candles)
    obs = analyzer.detect_order_block_proxies(candles, swings)

    # In the fixture, level was 2650.0 (simulating PDL or Asia Low)
    session_stats = {"asia": {"low": 2650.0, "high": 2670.0}}

    cfg = SetupConfig(enable_sweep_reclaim_bos=True)
    setup_engine = SetupEngine(config=cfg, structure=analyzer)

    signals = setup_engine.evaluate_all(candles, swings, fvgs, obs, session_stats)

    assert len(signals) >= 1
    sig = signals[0]
    assert sig.setup_id == "SETUP_2_SWEEP_RECLAIM_BOS"
    assert sig.direction == SignalDirection.BUY

    # Retest was finalized on candle index 7
    assert sig.signal_index == 7

    # PROOF OF ZERO LOOKAHEAD: Entry MUST be on candle index 8 (next candle open)!
    assert sig.entry_index == 8
    assert sig.entry_price == candles[8].open
    assert sig.sl_price < sig.entry_price
    assert sig.tp_price > sig.entry_price
