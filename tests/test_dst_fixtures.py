"""
Tests validating US and UK Daylight Saving Time (DST) switches and transitions.
"""

from datetime import timezone

from goldlab.fixtures import generate_dst_transition_fixtures
from goldlab.sessions import SessionManager
from goldlab.types import SessionName

TZ_UTC = timezone.utc


def test_dst_transitions() -> None:
    mgr = SessionManager()
    fixtures = generate_dst_transition_fixtures()

    # US Spring: NY Open after spring forward
    ny_spring_open = fixtures["us_spring"][2]  # 2026-03-09 13:00 UTC
    sessions = mgr.get_candle_sessions(ny_spring_open)
    assert SessionName.NEW_YORK in sessions

    # UK Spring: London Open after spring forward
    uk_spring_open = fixtures["uk_spring"][2]  # 2026-03-30 07:00 UTC
    sessions = mgr.get_candle_sessions(uk_spring_open)
    assert SessionName.LONDON in sessions

    # US Fall: NY Open after fall back
    us_fall_open = fixtures["us_fall"][2]  # 2026-11-02 14:00 UTC
    sessions = mgr.get_candle_sessions(us_fall_open)
    assert SessionName.NEW_YORK in sessions
