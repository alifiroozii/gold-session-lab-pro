import numpy as np

from research.replay_quotes import Quotes
from research.screen_candidates import Signal, simulate, summarize, trade_exit


def quotes():
    return Quotes(
        time=np.array([14*3_600_000, 14*3_600_000+60_000, 21*3_600_000]),
        bid_open=np.array([2710.0, 2709.5, 2710.0]),
        bid_high=np.array([2710.2, 2714.0, 2710.1]),
        bid_low=np.array([2709.9, 2707.5, 2709.9]),
        bid_close=np.array([2710.1, 2712.0, 2710.1]),
        ask_open=np.array([2710.1, 2709.6, 2710.1]),
        ask_high=np.array([2710.3, 2714.1, 2710.2]),
        ask_low=np.array([2710.0, 2707.6, 2710.0]),
        ask_close=np.array([2710.2, 2712.1, 2710.2]),
        is_tick=False,
    )


def test_both_brackets_in_same_minute_use_stop_and_exit_side():
    q = quotes()
    assert trade_exit(q, 0, 3, 1, 2708, 2713, 0.10) == (1, 2707.9, "stop")
    assert trade_exit(q, 0, 3, -1, 2713, 2708, 0.10) == (1, 2713.1, "stop")


def test_timed_exit_uses_first_available_exit_side_quote():
    q = quotes()
    assert trade_exit(q, 0, 3, 1, 2706, 2715, 0) == (2, 2710.0, "time")
    assert trade_exit(q, 0, 3, -1, 2715, 2706, 0) == (2, 2710.1, "time")


def test_single_position_sizing_and_cost():
    q = quotes()
    ready = Signal(int(q.time[0]), 0, 1, 2710, 2708, 2713, 2.0, "overlap")
    trades = simulate(q, [ready, ready], int(q.time[-1]+60_000), 0.05)
    assert len(trades) == 1
    assert trades[0]["entry"] == 2710.15
    assert trades[0]["exit"] == 2707.95
    assert trades[0]["lots"] == 0.06
    assert round(trades[0]["risk"],2) == 14.4
    assert summarize(trades)["net"] == -13.8
    assert summarize([])["profit_factor"] is None
