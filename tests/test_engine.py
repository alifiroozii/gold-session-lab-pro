"""
Integration tests for ResearchEngine.
"""

from pathlib import Path

from goldlab.engine import ResearchEngine
from goldlab.fixtures import generate_sweep_reclaim_bos_retest_fixture


def test_research_engine_pipeline_execution(tmp_path: Path) -> None:
    db = str(tmp_path / "test_engine.sqlite")
    engine = ResearchEngine(db_path=db)
    candles = generate_sweep_reclaim_bos_retest_fixture()

    engine.load_candles(candles, timeframe="5m")
    summary = engine.run_pipeline()

    assert summary is not None
    payload = engine.get_dashboard_payload()

    assert "candles" in payload
    assert "signals" in payload
    assert "metrics" in payload
    assert "session_stats" in payload
    assert len(payload["candles"]) == len(candles)
