import pytest

from goldlab.promotion import ChampionChallengerManager


@pytest.fixture
def test_db_path(tmp_path):
    return str(tmp_path / "test_promotion.sqlite")


def test_baseline_champion_seeded(test_db_path):
    mgr = ChampionChallengerManager(db_path=test_db_path)
    champ = mgr.get_current_champion()
    assert champ is not None
    assert champ.is_champion is True
    assert champ.name == "Champion-Baseline-V1"
    assert champ.total_trades == 0
    assert champ.expectancy_r == 0


def test_challenger_promotion_evaluation_criteria(test_db_path):
    mgr = ChampionChallengerManager(db_path=test_db_path)

    # 1. Under-performing challenger (small sample size)
    challenger_weak = mgr.register_version(
        name="Challenger-SmallSample",
        is_champion=False,
        config={"param": 1},
        total_trades=10,  # Below 30
        expectancy_r=0.60,
        p_value=0.01,
    )
    eval_weak = mgr.evaluate_challenger_promotion(challenger_weak.version_id)
    assert eval_weak["eligible"] is False
    assert eval_weak["checks"]["sample_size_ok"] is False

    # 2. Even a strong-looking challenger cannot beat an unvalidated baseline.
    challenger_strong = mgr.register_version(
        name="Challenger-Alpha",
        is_champion=False,
        config={"param": 2},
        total_trades=55,
        win_rate=58.0,
        expectancy_r=0.62,  # Baseline is 0.42 -> Delta = +0.20 >= 0.15
        max_drawdown_pct=1.3,
        p_value=0.02,
    )
    eval_strong = mgr.evaluate_challenger_promotion(challenger_strong.version_id)
    assert eval_strong["eligible"] is False
    assert "validated" in eval_strong["reason"]


def test_promotion_requires_user_approval(test_db_path):
    mgr = ChampionChallengerManager(db_path=test_db_path)
    challenger = mgr.register_version(
        name="Challenger-Candidate",
        is_champion=False,
        config={},
        total_trades=40,
        expectancy_r=0.70,
        p_value=0.01,
    )

    # Must fail without user confirmation
    res_fail = mgr.promote_challenger(challenger.version_id, user_confirmed=False)
    assert res_fail["success"] is False

    # Explicit approval alone does not establish statistical evidence.
    res_ok = mgr.promote_challenger(challenger.version_id, user_confirmed=True)
    assert res_ok["success"] is False
    assert mgr.get_current_champion().version_id != challenger.version_id
