from datetime import date
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.parse_report import parse_report
from research.run_backtest import SPLITS, SYMBOL, import_result, months, prepare


@pytest.fixture
def config(tmp_path):
    broker = "LiteFinance-MT5-Live"
    cache = tmp_path / broker / "ticks" / SYMBOL
    cache.mkdir(parents=True)
    return SimpleNamespace(
        split="validation", broker=broker, tick_cache=cache, output=tmp_path / "output",
        strategy="breakout", mode="fast", reference="asia-utc",
        leverage=100, hypothesis="Fixture only", frozen_validation=None,
    )


def complete_fixture_cache(config):
    for month in months(*SPLITS[config.split]):
        (config.tick_cache / f"{month}.tkc").write_bytes(b"unit test placeholder")


def report_fixture(folder: Path, trades=4):
    values = {
        "Symbol": SYMBOL, "Period": "M5 (2025.11.01 - 2026.05.01)", "Initial Deposit": "1 000.00",
        "Total Trades": str(trades), "Profit Trades (% of total)": "3 (75.00%)" if trades else "0 (0.00%)",
        "Equity Drawdown Relative": "2.51% (25.10)", "Total Net Profit": "12.50",
        "Gross Loss": "-10.00" if trades else "0.00", "Profit Factor": "2.25" if trades else "0.00",
    }
    report = folder / "report.htm"
    cells = "".join(f"<td>{label}:</td><td><b>{value}</b></td>" for label, value in values.items())
    report.write_text(f"<table><tr>{cells}</tr></table>", encoding="utf-16")
    return report


def import_fixture(config, prepared):
    folder = config.output
    coverage = folder / "coverage.json"
    coverage.write_text(json.dumps(dict(
        symbol=SYMBOL, broker=config.broker, from_inclusive="2025-11-01", to_exclusive="2026-05-01",
        missing_trading_minutes=0, generated_ticks=0, visual=False, evidence="unit test placeholder",
        data_sha256=hashlib.sha256(b"fixture").hexdigest(),
    )))
    journal = folder / "journal.log"
    journal.write_text(
        "every tick based on real ticks\n"
        "GLAB|INIT|XAUUSD_o|CLOCK_LITEFINANCE_EU|REF_ASIA_UTC|STRATEGY_BREAKOUT|MODE_FAST|audit=0\n"
        "test passed\n",
        encoding="utf-16",
    )
    return SimpleNamespace(output=folder, experiment_id=prepared["id"], coverage=coverage, journal=journal,
                           report=report_fixture(folder))


def test_splits_use_exclusive_end():
    assert list(months(*SPLITS["training"])) == [
        "202411", "202412", *(f"2025{month:02}" for month in range(1, 11)),
    ]
    assert SPLITS["holdout"][1] == date(2026, 11, 1)
    assert SPLITS["training"][1] == SPLITS["validation"][0]
    assert SPLITS["validation"][1] == SPLITS["holdout"][0]


def test_preparation_reports_missing_ticks_and_deduplicates(config):
    first = prepare(config)
    assert first["status"] == "MISSING_TICKS"
    assert first["missing_months"] == ["202511", "202512", "202601", "202602", "202603", "202604"]
    config.hypothesis = "Different wording"
    assert prepare(config)["id"] == first["id"]
    ini_path = Path(first["folder"]) / "tester.ini"
    assert not ini_path.exists()
    complete_fixture_cache(config)
    assert prepare(config)["status"] == "COVERAGE_REVIEW_REQUIRED"
    ini = ini_path.read_text()
    assert "Model=4\n" in ini and "Visual=0\n" in ini and "AllowLiveTrading=0\n" in ini


def test_refuses_holdout_without_matching_validation(config):
    config.split = "holdout"
    with pytest.raises(ValueError, match="frozen"):
        prepare(config)


def test_import_checks_fallback_and_keeps_raw_evidence(config):
    complete_fixture_cache(config)
    prepared = prepare(config)
    args = import_fixture(config, prepared)
    good_journal = args.journal.read_bytes()
    args.journal.write_text("real ticks absent for 3 minute bars, every tick generation used", encoding="utf-16")
    with pytest.raises(ValueError, match="fallback"):
        import_result(args)
    args.journal.write_bytes(good_journal)
    result = import_result(args)
    assert result["status"] == "REVIEWABLE"
    assert result["summary"]["win_rate"] == 0.75
    assert (Path(prepared["folder"]) / "evidence/report.htm").read_bytes() == args.report.read_bytes()
    with pytest.raises(ValueError, match="required tick cache"):
        import_result(args)
    config.split = "holdout"
    config.frozen_validation = prepared["id"]
    assert prepare(config)["status"] == "MISSING_TICKS"
    config.mode = "standard"
    with pytest.raises(ValueError, match="differ"):
        prepare(config)


def test_empty_report_has_undefined_win_rate_and_profit_factor(tmp_path):
    summary = parse_report(report_fixture(tmp_path, trades=0))
    assert summary["trade_count"] == 0
    assert summary["win_rate"] is None and summary["profit_factor"] is None
