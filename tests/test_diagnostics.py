import pytest

from goldlab.autofix import FixStatus, RiskLevel, SafeAutoFixEngine
from goldlab.diagnostics import DiagnosticsEngine, IncidentCategory, IncidentSeverity


@pytest.fixture
def test_db_path(tmp_path):
    return str(tmp_path / "test_diag.sqlite")


def test_diagnostics_categorization_software_bug(test_db_path):
    engine = DiagnosticsEngine(db_path=test_db_path)
    try:
        _ = 1 / 0
    except ZeroDivisionError as e:
        inc = engine.categorize_exception(e)

    assert inc.category == IncidentCategory.SOFTWARE_BUG
    assert inc.error_type == "ZeroDivisionError"
    assert len(engine.get_recent_incidents()) == 1


def test_diagnostics_categorization_ledger_issue(test_db_path):
    engine = DiagnosticsEngine(db_path=test_db_path)
    exc = ValueError("Corrupt ledger balance mismatch detected")
    inc = engine.categorize_exception(exc)

    assert inc.category == IncidentCategory.PAPER_EXECUTION
    assert inc.severity == IncidentSeverity.CRITICAL


def test_diagnostics_record_market_loss(test_db_path):
    engine = DiagnosticsEngine(db_path=test_db_path)
    inc = engine.record_market_loss(
        trade_id="TR-001",
        loss_amount=50.0,
        r_multiple=-1.0,
        setup_id="S1_ASIA_SWEEP",
        reason="Hit SL after news spike",
    )
    assert inc.category == IncidentCategory.MARKET_LOSS
    assert inc.severity == IncidentSeverity.LOW
    assert inc.resolved is True


def test_safe_autofix_risk_classification(test_db_path):
    autofix = SafeAutoFixEngine(db_path=test_db_path)

    # High risk for guardian and broker
    risk_guard = autofix.classify_risk("goldlab/guardian.py", "update stop-loss limit")
    assert risk_guard == RiskLevel.HIGH

    # Medium risk for setups
    risk_setup = autofix.classify_risk("goldlab/setups.py", "adjust swing filter")
    assert risk_setup == RiskLevel.MEDIUM

    # Low risk for docs or formatting
    risk_low = autofix.classify_risk("docs/README.md", "fix typo")
    assert risk_low == RiskLevel.LOW


def test_autofix_proposal_approval_gate(test_db_path):
    autofix = SafeAutoFixEngine(db_path=test_db_path)
    prop = autofix.create_proposal(
        incident_id="INC-123",
        target_file="goldlab/guardian.py",
        title="Fix Daily Loss Boundary",
        diff_content="--- +++",
        explanation="Fixing strict threshold check",
        minimal_reproducer="def test_repro(): pass",
    )
    assert prop.requires_human_approval is True

    # Attempt to apply without user confirmation
    res_fail = autofix.approve_and_apply_fix(prop.proposal_id, user_confirmed=False)
    assert res_fail["success"] is False

    # Apply with user confirmation
    res_ok = autofix.approve_and_apply_fix(prop.proposal_id, user_confirmed=True)
    assert res_ok["success"] is True

    updated_prop = autofix.get_proposal(prop.proposal_id)
    assert updated_prop.status == FixStatus.APPLIED
