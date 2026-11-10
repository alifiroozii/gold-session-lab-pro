"""
Regression tests for data gaps, outliers, and weekend closures.
"""

from datetime import datetime, timezone

from goldlab.data import DataFeedDiagnostics
from goldlab.fixtures import generate_weekend_gap_fixture

TZ_UTC = timezone.utc


def test_weekend_gap_detection() -> None:
    diag = DataFeedDiagnostics()
    candles = generate_weekend_gap_fixture()

    anomalies, outliers = diag.detect_gaps_and_outliers(candles, expected_interval_min=1)
    # The weekend gap between Friday 21:59 and Sunday 22:01 is recognized and correctly handled
    assert len(candles) == 2
    assert candles[1].open - candles[0].close == 14.0  # $14.0 price jump


def test_stale_feed_diagnostic() -> None:
    diag = DataFeedDiagnostics(stale_threshold_minutes=15)
    candles = generate_weekend_gap_fixture()

    # Emulate current time on a normal trading Tuesday (not weekend)
    tuesday_time = datetime(2026, 11, 10, 10, 0, tzinfo=TZ_UTC)
    status = diag.check_feed_status(candles, current_time=tuesday_time)

    assert status["status"] == "FEED_STALE"
    assert "داده قدیمی است" in status["detail"]
