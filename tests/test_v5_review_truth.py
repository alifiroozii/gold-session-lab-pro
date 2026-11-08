"""The new V5 dashboard must not falsely claim that an AI agent is live."""
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_strategy_state_api_explicitly_discloses_unwired_execution():
    response = client.get("/api/strategy/state")
    assert response.status_code == 200
    state = response.json()
    assert state["runtime_status"] == "NOT_WIRED_TO_LIVE_CANDLE_LOOP"
    assert state["enabled_for_auto_trading"] is False


def test_supervisor_report_never_invents_branch_test_counts_or_agent_connection():
    response = client.get("/api/agent/supervisor-report")
    assert response.status_code == 200
    report = response.json()
    assert "104" not in str(report) and "۱۰۴" not in str(report)
    assert "candidate/v5-session-lab-recovery" not in str(report)
    assert "agent_status" in report
    if report["agent_status"] == "NOT_CONNECTED":
        assert report["last_inspection"] is None
        assert "متصل نیست" in report["verification_status"]


def test_broker_auto_remains_prohibited_even_with_state_machine_module():
    result = client.post("/api/bot/state", json={"state": "PAPER_AUTO"})
    assert result.status_code == 409
