"""
Regression and Contract Tests for Master Prompt V5:
- 3 Primary Navigation Tabs
- Layer C Comparison Panel
- 10-State Causal State Machine
- 9 Verifiable Fields in 'ناظر هوشمند و گزارش اصلاحات'
- $1,000.00 Virtual Balance Baseline
"""
from pathlib import Path

from fastapi.testclient import TestClient

from app import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def test_three_primary_navigation_tabs_only():
    html = (ROOT / "templates/index.html").read_text(encoding="utf-8")

    # Navigation must contain exactly the 3 primary tabs
    assert 'data-tab="tab-chart"' in html
    assert 'data-tab="tab-positions"' in html
    assert 'data-tab="tab-ai-research"' in html

    # Secondary tabs must not be in top navigation buttons
    nav_section = html.split('<nav class="nav-tabs"', 1)[1].split('</nav>', 1)[0]
    assert 'data-tab="tab-strategies"' not in nav_section
    assert 'data-tab="tab-bot"' not in nav_section
    assert 'data-tab="tab-broker"' not in nav_section
    assert 'data-tab="tab-backtest"' not in nav_section
    assert 'data-tab="tab-calendar"' not in nav_section
    assert 'data-tab="tab-health"' not in nav_section


def test_supervisor_panel_has_nine_verifiable_fields():
    html = (ROOT / "templates/index.html").read_text(encoding="utf-8")

    expected_fields = [
        "auditLastInspection",
        "auditDiscoveredIssue",
        "auditProbableCause",
        "auditReproTest",
        "auditProposedPatch",
        "auditTestOutcome",
        "auditVerificationStatus",
        "auditGitRef",
        "auditStrategyResult",
    ]
    for field_id in expected_fields:
        assert f'id="{field_id}"' in html, f"Missing field ID: {field_id}"


def test_layer_c_comparison_table_and_delta_box():
    html = (ROOT / "templates/index.html").read_text(encoding="utf-8")
    assert 'id="marketComparisonTable"' in html
    assert 'id="priceDeltaBox"' in html
    assert 'id="priceDeltaAmount"' in html
    assert 'id="priceDeltaExplanation"' in html


def test_state_machine_badge_and_side_column():
    html = (ROOT / "templates/index.html").read_text(encoding="utf-8")
    assert 'id="stateMachineBadge"' in html
    assert 'id="sideAccBalance"' in html
    assert 'id="sideAccEquity"' in html
    assert 'id="sideLastSignal"' in html


def test_virtual_balance_baseline_is_one_thousand():
    html = (ROOT / "templates/index.html").read_text(encoding="utf-8")
    assert "$1,000.00" in html
    assert "$۱۰,۰۰۰" not in html
    assert "$10,000" not in html


def test_api_market_comparison_endpoint():
    res = client.get("/api/market/comparison")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert len(data["layers"]) == 2
    assert data["layers"][0]["source_layer"] == "لایه A (مرجع بصری)"
    assert data["layers"][1]["source_layer"] == "لایه B (مظنه اجرایی تأییدشده)"
    assert "difference_usd" in data["price_delta"]


def test_api_strategy_state_endpoint():
    res = client.get("/api/strategy/state")
    assert res.status_code == 200
    data = res.json()
    assert "current_state" in data
    assert "recent_transitions" in data
    assert "strategy_version" in data


def test_api_agent_supervisor_report_endpoint():
    res = client.get("/api/agent/supervisor-report")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "last_inspection" in data
    assert "discovered_issue" in data
    assert "probable_cause" in data
    assert "reproduction_test" in data
    assert "proposed_patch" in data
    assert "test_outcome" in data
    assert "verification_status" in data
    assert "inspected_git_ref" in data
    assert "strategy_audit_result" in data
