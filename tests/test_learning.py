from datetime import datetime, timezone

import pytest

from goldlab.learning import (
    AutopsyVerdict,
    HypothesisStatus,
    MistakeAnalyzerAndHypothesisRegistry,
)
from goldlab.ml_model import MLTradeQualityModel
from goldlab.types import Candle, SetupSignal, SignalDirection

TZ_UTC = timezone.utc


@pytest.fixture
def test_db_path(tmp_path):
    return str(tmp_path / "test_learning.sqlite")


def test_trade_autopsy_verdict_good_loss(test_db_path):
    analyzer = MistakeAnalyzerAndHypothesisRegistry(db_path=test_db_path)
    autopsy = analyzer.perform_autopsy(
        trade_id="POS-101",
        setup_id="S1_ASIA_SWEEP",
        side="BUY",
        pnl=-50.0,
        r_multiple=-1.0,
        entry_price=2650.0,
        exit_price=2648.0,
        sl_price=2648.0,
        tp_price=2654.0,
        entry_regime="RANGING",
        entry_wick_ratio=0.25,
    )
    assert autopsy.verdict == AutopsyVerdict.GOOD_LOSS
    assert autopsy.r_multiple == -1.0


def test_trade_autopsy_chased_price(test_db_path):
    analyzer = MistakeAnalyzerAndHypothesisRegistry(db_path=test_db_path)
    autopsy = analyzer.perform_autopsy(
        trade_id="POS-102",
        setup_id="S1_ASIA_SWEEP",
        side="BUY",
        pnl=-50.0,
        r_multiple=-1.0,
        entry_price=2650.0,
        exit_price=2648.0,
        sl_price=2648.0,
        tp_price=2654.0,
        entry_regime="RANGING",
        entry_wick_ratio=0.65,  # High wick > 0.50 triggers CHASED_PRICE
    )
    assert autopsy.verdict == AutopsyVerdict.CHASED_PRICE


def test_hypothesis_lifecycle(test_db_path):
    registry = MistakeAnalyzerAndHypothesisRegistry(db_path=test_db_path)
    hyp = registry.register_hypothesis(
        title="فیلتر سشن آسیا",
        rationale="کاهش ضررهای ناشی از نقدینگی اندک",
        target_metric="Sharpe > 1.2",
    )
    assert hyp.status == HypothesisStatus.PROPOSED

    registry.update_hypothesis_status(
        hypothesis_id=hyp.hypothesis_id,
        status=HypothesisStatus.PROMISING,
        sample_size=45,
        p_value=0.03,
        evidence="Outperformed benchmark by 0.22R",
    )
    all_hyps = registry.list_hypotheses()
    assert len(all_hyps) == 1
    assert all_hyps[0]["status"] == "PROMISING"
    assert all_hyps[0]["sample_size"] == 45


def test_ml_model_scoring_and_shadow_mode(test_db_path):
    ml = MLTradeQualityModel(db_path=test_db_path, shadow_mode=True)
    c = Candle(
        timestamp=datetime(2026, 11, 8, 14, 0, tzinfo=TZ_UTC),
        open=2650.0,
        high=2652.0,
        low=2649.0,
        close=2651.5,
        volume=150.0,
        atr14=1.2,
        wick_ratio=0.35,
    )
    sig = SetupSignal(
        setup_id="S2_LONDON_EXPANSION",
        setup_name="London Expansion",
        direction=SignalDirection.BUY,
        signal_index=10,
        signal_time=c.timestamp,
        entry_index=11,
        entry_price=2651.5,
        sl_price=2649.0,
        tp_price=2656.5,
        risk_r=1.0,
        reason="London Expansion breakout",
        metrics={"session_id": "LONDON"},
    )
    score = ml.evaluate_signal(candles_history=[c], signal=sig, current_spread=0.25)

    assert 0.0 <= score.predicted_win_prob <= 1.0
    assert score.quality_grade in ["A+", "A", "B", "C"]
    assert score.shadow_mode is True
    assert "wick_sweep_strength" in score.feature_attributions
