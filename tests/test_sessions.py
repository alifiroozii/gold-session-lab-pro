"""
Unit tests for session boundaries, DST transitions, and weekend market closure.
"""

from datetime import datetime, timezone

from goldlab.sessions import SessionManager
from goldlab.types import SessionName

TZ_UTC = timezone.utc


def test_session_detection_london_ny_overlap() -> None:
    mgr = SessionManager()
    # 14:00 UTC is London afternoon and New York morning (Overlap)
    dt = datetime(2026, 11, 4, 14, 0, tzinfo=TZ_UTC)
    sessions = mgr.get_candle_sessions(dt)

    assert SessionName.LONDON in sessions
    assert SessionName.NEW_YORK in sessions
    assert SessionName.LONDON_NY_OVERLAP in sessions


def test_asia_reference_range_config() -> None:
    mgr = SessionManager()
    # 21:00 NY time is within Asia Reference Range (20:00 - 00:00 NY)
    # 21:00 NY in winter (EST, UTC-5) is 02:00 UTC next day
    dt = datetime(2026, 11, 4, 2, 0, tzinfo=TZ_UTC)
    sessions = mgr.get_candle_sessions(dt)

    assert SessionName.ASIA_REFERENCE in sessions


def test_market_closure_weekend() -> None:
    mgr = SessionManager()
    # Friday 23:00 UTC (Closed)
    fri_night = datetime(2026, 11, 6, 23, 0, tzinfo=TZ_UTC)
    assert mgr.is_market_closed(fri_night) is True

    # Saturday 12:00 UTC (Closed)
    sat_noon = datetime(2026, 11, 7, 12, 0, tzinfo=TZ_UTC)
    assert mgr.is_market_closed(sat_noon) is True

    # Sunday 20:00 UTC (Closed)
    sun_pre = datetime(2026, 11, 8, 20, 0, tzinfo=TZ_UTC)
    assert mgr.is_market_closed(sun_pre) is True

    # On Nov 8 NY is on EST (UTC-5); Sunday 22:30 UTC is only
    # 17:30 New York, BEFORE the 18:00 local market reopening.
    sun_pre_open = datetime(2026, 11, 8, 22, 30, tzinfo=TZ_UTC)
    assert mgr.is_market_closed(sun_pre_open) is True

    sun_open = datetime(2026, 11, 8, 23, 30, tzinfo=TZ_UTC)
    assert mgr.is_market_closed(sun_open) is False

    # Tuesday 10:00 UTC (Open)
    tue_open = datetime(2026, 11, 3, 10, 0, tzinfo=TZ_UTC)
    assert mgr.is_market_closed(tue_open) is False
