from pathlib import Path

import pytest

from goldlab.paper_broker import PaperBroker
from goldlab.supervisor import JobStatus, JobType, ResearchSupervisor


@pytest.fixture
def test_supervisor_env(tmp_path):
    db_path = str(tmp_path / "test_supervisor.sqlite")
    reports_dir = str(tmp_path / "reports")
    return db_path, reports_dir


def test_supervisor_job_queue_enqueue_and_execute(test_supervisor_env):
    db_path, reports_dir = test_supervisor_env
    supervisor = ResearchSupervisor(db_path=db_path, reports_dir=reports_dir)
    broker = PaperBroker(db_path=db_path)

    # 1. Enqueue Health Check
    job = supervisor.enqueue_job(JobType.HEALTH_CHECK)
    assert job.status == JobStatus.PENDING

    # 2. Execute Pending Job
    completed_job = supervisor.execute_next_pending_job(broker)
    assert completed_job is not None
    assert completed_job.status == JobStatus.COMPLETED
    assert completed_job.result["status"] == "HEALTHY"


def test_supervisor_nightly_evaluation_report_generation(test_supervisor_env):
    db_path, reports_dir = test_supervisor_env
    supervisor = ResearchSupervisor(db_path=db_path, reports_dir=reports_dir)
    broker = PaperBroker(db_path=db_path)

    res = supervisor.run_nightly_evaluation(broker)
    report_path = Path(res["report_path"])

    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "گزارش جامع روزانه آزمایشگاه خودکار طلا" in content
    assert "Double-Entry Invariance" in content
    assert "Ledger Invariance OK" in content
