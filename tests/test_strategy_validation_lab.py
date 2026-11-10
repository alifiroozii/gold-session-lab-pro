"""
Tests for StrategyValidationLab in Gold Session Lab Pro (V6).
Verifies walk-forward splitting, out-of-sample metrics, fail-closed handling,
and fail-closed authorization of PAPER_AUTO.
"""

from pathlib import Path

from goldlab.strategy_validation_lab import StrategyValidationLab


def test_strategy_validation_lab_on_demo_csv(tmp_path):
    reports_dir = tmp_path / "reports"
    lab = StrategyValidationLab(
        db_path=str(tmp_path / "test.sqlite"),
        reports_dir=str(reports_dir),
    )

    demo_csv = Path("data/demo_xauusd_1m.csv")
    if not demo_csv.exists():
        return

    report = lab.run_validation(csv_path=demo_csv, timeframe="5m")

    assert report.total_candles > 0
    assert report.train_candles > 0
    assert report.test_candles > 0
    # Demo CSV must NOT be certified as provenance verified
    assert report.data_provenance_verified is False
    assert report.authorizes_paper_auto is False
    assert (reports_dir / "STRATEGY_VALIDATION.json").exists()


def test_strategy_validation_lab_empty_candles(tmp_path):
    reports_dir = tmp_path / "reports"
    lab = StrategyValidationLab(
        db_path=str(tmp_path / "test.sqlite"),
        reports_dir=str(reports_dir),
    )
    report = lab.run_validation(candles=[])
    assert report.statistical_verdict == "INSUFFICIENT_DATA"
    assert report.authorizes_paper_auto is False
