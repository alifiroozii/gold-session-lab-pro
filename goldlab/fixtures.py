"""
Standardized Synthetic Test Fixtures for Regression Testing and Boundary Validation.
Includes:
- Deterministic Liquidity Sweep + Reclaim + BOS + Retest pattern
- US & UK Daylight Saving Time (DST) Transition weeks (March, October, November)
- Friday market close and Sunday evening opening gap
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from goldlab.types import Candle

TZ_UTC = timezone.utc


def generate_sweep_reclaim_bos_retest_fixture() -> List[Candle]:
    """
    Generates a deterministic 15-candle sequence containing:
    - Candle 0-3: Range setup establishing level at 2650.00
    - Candle 4: Sweep of 2650.00 (Low dips to 2645.00)
    - Candle 5: Reclaim (Closes firmly back at 2652.00)
    - Candle 6: Break of Structure (BOS) closing at 2656.00
    - Candle 7: Retest dipping to 2650.50 with a strong lower wick rejection (Setup completed on close)
    - Candle 8: Next candle OPEN where entry MUST take place!
    - Candle 9-14: Continuation to target
    """
    start_time = datetime(2026, 11, 2, 8, 0, tzinfo=TZ_UTC)
    data = [
        # (O, H, L, C, Vol)
        (2652.0, 2654.0, 2650.0, 2651.0, 100),  # 0
        (2651.0, 2653.0, 2650.0, 2652.5, 110),  # 1: Level low 2650.0
        (2652.5, 2653.0, 2651.0, 2651.5, 95),   # 2
        (2651.5, 2652.0, 2650.0, 2650.5, 120),  # 3: Low 2650.0
        # 4: SWEEP low breaks 2650.0 to 2645.0
        (2650.5, 2651.0, 2645.0, 2648.0, 250),
        # 5: RECLAIM closes back above 2650.0
        (2648.0, 2653.0, 2647.5, 2652.0, 300),
        # 6: BOS breaks candle 5 high (2653.0)
        (2652.0, 2657.0, 2651.5, 2656.0, 320),
        # 7: RETEST touches 2650.50 with long lower wick and closes green
        (2656.0, 2656.5, 2650.5, 2654.5, 280),
        # 8: ENTRY BAR (Entry at Open = 2654.5)
        (2654.5, 2660.0, 2654.0, 2659.0, 220),
        # 9-14: Target expansion
        (2659.0, 2664.0, 2658.0, 2663.0, 210),
        (2663.0, 2668.0, 2662.0, 2667.5, 200),
        (2667.5, 2672.0, 2667.0, 2671.0, 190),
        (2671.0, 2675.0, 2670.0, 2674.5, 180),
        (2674.5, 2678.0, 2673.5, 2677.0, 170),
    ]

    candles: List[Candle] = []
    for idx, (o, h, low_val, c, v) in enumerate(data):
        candles.append(
            Candle(
                timestamp=start_time + timedelta(minutes=idx * 5),
                open=o,
                high=h,
                low=low_val,
                close=c,
                volume=v,
                is_closed=True,
            )
        )
    return candles


def generate_dst_transition_fixtures() -> dict[str, List[datetime]]:
    """
    Returns critical timestamps during US and UK Daylight Saving Time switches:
    - US Spring forward (2nd Sunday in March)
    - UK Spring forward (last Sunday in March)
    - UK Fall back (last Sunday in October)
    - US Fall back (1st Sunday in November)
    """
    return {
        "us_spring": [
            datetime(2026, 3, 8, 6, 0, tzinfo=TZ_UTC),
            datetime(2026, 3, 8, 7, 0, tzinfo=TZ_UTC),
            datetime(2026, 3, 9, 13, 0, tzinfo=TZ_UTC),  # NY Open after switch
        ],
        "uk_spring": [
            datetime(2026, 3, 29, 0, 0, tzinfo=TZ_UTC),
            datetime(2026, 3, 29, 1, 0, tzinfo=TZ_UTC),
            datetime(2026, 3, 30, 7, 0, tzinfo=TZ_UTC),  # London Open after switch
        ],
        "uk_fall": [
            datetime(2026, 10, 25, 0, 0, tzinfo=TZ_UTC),
            datetime(2026, 10, 25, 1, 0, tzinfo=TZ_UTC),
            datetime(2026, 10, 26, 8, 0, tzinfo=TZ_UTC),
        ],
        "us_fall": [
            datetime(2026, 11, 1, 5, 0, tzinfo=TZ_UTC),
            datetime(2026, 11, 1, 6, 0, tzinfo=TZ_UTC),
            datetime(2026, 11, 2, 14, 0, tzinfo=TZ_UTC),
        ],
    }


def generate_weekend_gap_fixture() -> List[Candle]:
    """
    Returns two candles spanning the Friday close (21:59 UTC) to Sunday reopen (22:01 UTC)
    with a noticeable price gap.
    """
    friday_close = datetime(2026, 11, 6, 21, 59, tzinfo=TZ_UTC)
    sunday_open = datetime(2026, 11, 8, 22, 1, tzinfo=TZ_UTC)

    return [
        Candle(
            timestamp=friday_close,
            open=2660.0,
            high=2662.0,
            low=2659.0,
            close=2661.0,
            volume=500,
            is_closed=True,
        ),
        Candle(
            timestamp=sunday_open,
            open=2675.0,  # $14.0 gap up
            high=2678.0,
            low=2674.0,
            close=2676.0,
            volume=450,
            is_closed=True,
        ),
    ]
