"""Regression tests for the strategy-verification gate (not a profit test)."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from goldlab.engine import ResearchEngine
from goldlab.strategy_verification import audit_point_in_time, verify_signal_contract
from goldlab.types import Candle, SetupSignal, SignalDirection


def _inputs():
    start = datetime(2026, 11, 9, 13, 0, tzinfo=timezone.utc)
    candles = [
        Candle(timestamp=start + timedelta(minutes=i * 5),
               open=3000.0 + i, high=3002.0 + i,
               low=2999.0 + i, close=3001.0 + i)
        for i in range(3)
    ]
    signal = SetupSignal(
        setup_id="TEST_SESSION_RULE",
        setup_name="Test Only",
        direction=SignalDirection.BUY,
        signal_index=1,
        signal_time=candles[1].timestamp,
        entry_index=2,
        entry_price=candles[2].open,
        sl_price=2999.0,
        tp_price=3008.0,
        risk_r=3.0,
        reason="Closed-bar test fixture",
    )
    return candles, signal


def test_valid_signal_contract_is_not_paper_auto_certification():
    candles, signal = _inputs()
    report = verify_signal_contract(candles, [signal])
    assert report["status"] == "PASS"
    assert report["checked_signals"] == 1
    assert report["authorizes_paper_auto"] is False


def test_invalid_next_bar_and_wrong_bracket_are_rejected():
    candles, signal = _inputs()
    signal.entry_index = 1
    result = verify_signal_contract(candles, [signal])
    assert result["status"] == "FAIL"
    assert any(f["code"] == "INVALID_NEXT_BAR_ENTRY" for f in result["findings"])

    signal.entry_index = 2
    signal.sl_price = 3100.0
    result = verify_signal_contract(candles, [signal])
    assert any(f["code"] == "INVALID_RISK_BRACKET" for f in result["findings"])


def test_future_entry_price_or_time_is_detected():
    candles, signal = _inputs()
    signal.entry_price = 3111.0
    signal.signal_time = candles[0].timestamp
    result = verify_signal_contract(candles, [signal])
    codes = {f["code"] for f in result["findings"]}
    assert "ENTRY_PRICE_MISMATCH" in codes
    assert "SIGNAL_TIME_MISMATCH" in codes


def test_duplicate_signal_is_rejected():
    candles, signal = _inputs()
    result = verify_signal_contract(candles, [signal, signal])
    assert any(f["code"] == "DUPLICATE_SIGNAL" for f in result["findings"])


def test_no_historical_signals_never_counts_as_evidence(tmp_path: Path):
    engine = ResearchEngine(db_path=str(tmp_path / "test.sqlite"))
    assert audit_point_in_time(engine)["status"] == "INSUFFICIENT_EVIDENCE"
    assert audit_point_in_time(engine)["authorizes_paper_auto"] is False
