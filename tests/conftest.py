"""
Pytest configuration and shared fixtures for goldlab test suite.
"""

from datetime import datetime, timezone

import pytest

from goldlab.fixtures import (
    generate_dst_transition_fixtures,
    generate_sweep_reclaim_bos_retest_fixture,
    generate_weekend_gap_fixture,
)
from goldlab.types import Candle

TZ_UTC = timezone.utc


@pytest.fixture
def sweep_bos_fixture() -> list[Candle]:
    return generate_sweep_reclaim_bos_retest_fixture()


@pytest.fixture
def dst_fixtures() -> dict[str, list[datetime]]:
    return generate_dst_transition_fixtures()


@pytest.fixture
def weekend_gap_fixture() -> list[Candle]:
    return generate_weekend_gap_fixture()
