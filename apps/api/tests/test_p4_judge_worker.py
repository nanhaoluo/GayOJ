from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import JsonRepository, now
from app.models import Submission
from app.services import make_submission_id


ROOT = Path(__file__).resolve().parents[3]
JUDGE_ROOT = ROOT / "apps" / "judge"
if str(JUDGE_ROOT) not in sys.path:
    sys.path.insert(0, str(JUDGE_ROOT))

from worker import JudgeWorker  # noqa: E402
from gayoj_judge import CodeJudgeTask, CodeTestCase, CompileOutcome, RunOutcome  # noqa: E402


class FakeWorkerExecutor:
    def __init__(self) -> None:
        self.compiled = False
        self.runs: list[str] = []
        self.cleaned = False

    def compile(self, task: CodeJudgeTask) -> CompileOutcome:
        self.compiled = True
        return CompileOutcome(ok=True, artifact={"submission_id": task.submission_id})

    def run(self, task: CodeJudgeTask, artifact: object, test_case: CodeTestCase) -> RunOutcome:
        self.runs.append(test_case.id)
        return RunOutcome(status="accepted", stdout=test_case.expected_output, time_ms=8, memory_kb=1024)

    def cleanup(self, artifact: object) -> None:
        self.cleaned = True


def submit_code(client: TestClient, auth_headers, language: str = "python") -> dict[str, object]:
    response = client.post(
        "/api/v1/problems/P1001/submit-code",
        headers=auth_headers("alice"),
        json={
            "language": language,
            "source_code": "print('this source is queued as data only')\n",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_worker_claims_code_submission_without_executing_or_leaking_config(
    client: TestClient,
    auth_headers,
    store,
) -> None:
    queued = submit_code(client, auth_headers, "python")

    worker = JudgeWorker(
        store,
        worker_id="pytest-worker",
        name="pytest worker",
        languages=["python"],
    )
    task = worker.claim_once()

    assert task is not None
    assert task.submission_id == queued["id"]
    assert task.problem_id == "P1001"
    assert task.language == "python"
    assert task.source_ref == f"submission:{queued['id']}:source_code"
    assert "source_code" not in asdict(task)
    assert task.testdata_ref == "problem:P1001:testdata"
    assert task.limits == {"time_limit_ms": 1000, "memory_limit_mb": 128}

    stored = store.get_submission(str(queued["id"]))
    assert stored is not None
    assert stored.status == "judging"
    assert stored.score == 0
    assert stored.judged_at is None
    assert stored.details == []
    assert "评测节点 pytest-worker" in stored.message
    assert stored.queue_job_id
    job = store.get_judge_queue_job(stored.queue_job_id)
    assert job is not None
    assert job.status == "leased"
    assert job.assigned_node_id == "pytest-worker"
    assert job.attempts == 1

    public_detail = client.get("/api/v1/problems/P1001", headers=auth_headers("alice"))
    assert public_detail.status_code == 200
    assert "judge_config" not in public_detail.json()

    node = next(item for item in store.list_judge_nodes() if item.id == "pytest-worker")
    assert node.status == "online"
    assert node.languages == ["python"]


def test_worker_respects_language_filter(client: TestClient, auth_headers, store) -> None:
    queued = submit_code(client, auth_headers, "cpp")

    python_worker = JudgeWorker(
        store,
        worker_id="python-worker",
        name="python worker",
        languages=["python"],
    )
    assert python_worker.claim_once() is None
    assert store.get_submission(str(queued["id"])).status == "queued"

    cpp_worker = JudgeWorker(
        store,
        worker_id="cpp-worker",
        name="cpp worker",
        languages=["cpp"],
    )
    task = cpp_worker.claim_once()
    assert task is not None
    assert task.submission_id == queued["id"]
    assert store.get_submission(str(queued["id"])).status == "judging"


def test_worker_execute_once_runs_sandbox_contract_and_writes_back_result(
    client: TestClient,
    auth_headers,
    store,
) -> None:
    queued = submit_code(client, auth_headers, "python")
    executor = FakeWorkerExecutor()
    worker = JudgeWorker(
        store,
        worker_id="execute-worker",
        name="execute worker",
        languages=["python"],
    )

    event = worker.execute_once(executor)

    assert event["event"] == "judged"
    assert event["worker_id"] == "execute-worker"
    assert event["boundary"] == "worker_sandbox_execution"
    assert event["task"]["submission_id"] == queued["id"]
    assert event["task"]["source_ref"] == f"submission:{queued['id']}:source"
    assert event["submission"]["status"] == "accepted"
    assert executor.compiled is True
    assert executor.runs == ["sample-1", "sample-2"]
    assert executor.cleaned is True

    stored = store.get_submission(str(queued["id"]))
    assert stored is not None
    assert stored.status == "accepted"
    assert stored.score == stored.max_score == 100
    assert stored.judged_at is not None
    assert [item["status"] for item in stored.details] == ["accepted", "accepted"]
    assert all("input_preview" not in item for item in stored.details)
    assert all("expected_preview" not in item for item in stored.details)
    job = store.get_judge_queue_job(str(stored.queue_job_id))
    assert job is not None
    assert job.status == "completed"
    node = next(item for item in store.list_judge_nodes() if item.id == "execute-worker")
    assert node.load == 0.0


def test_worker_execute_once_marks_claimed_job_failed_when_task_cannot_be_built(
    client: TestClient,
    auth_headers,
    store,
) -> None:
    queued = submit_code(client, auth_headers, "python")
    problem = store.get_problem("P1001")
    assert problem is not None
    problem.samples = []
    store.update_problem(problem)
    worker = JudgeWorker(
        store,
        worker_id="broken-worker",
        name="broken worker",
        languages=["python"],
    )

    event = worker.execute_once(FakeWorkerExecutor())

    assert event["event"] == "failed"
    assert event["submission"]["status"] == "system_error"
    stored = store.get_submission(str(queued["id"]))
    assert stored is not None
    assert stored.status == "system_error"
    assert stored.score == 0
    assert stored.judged_at is not None
    assert stored.message == "Judge worker failed before completing the sandbox run."
    job = store.get_judge_queue_job(str(stored.queue_job_id))
    assert job is not None
    assert job.status == "failed"
    assert job.completed_at is not None
    assert job.last_error == stored.message


def test_worker_poll_once_marks_claimed_job_failed_when_problem_metadata_is_invalid(
    client: TestClient,
    auth_headers,
    store,
) -> None:
    queued = submit_code(client, auth_headers, "python")
    problem = store.get_problem("P1001")
    assert problem is not None
    problem.type = "blank"  # type: ignore[assignment]
    store.update_problem(problem)
    worker = JudgeWorker(
        store,
        worker_id="poll-failure-worker",
        name="poll failure worker",
        languages=["python"],
    )

    event = worker.poll_once()

    assert event["event"] == "failed"
    assert event["boundary"] == "claim_only_no_execution"
    assert event["submission"]["id"] == queued["id"]
    stored = store.get_submission(str(queued["id"]))
    assert stored is not None
    assert stored.status == "system_error"
    job = store.get_judge_queue_job(str(stored.queue_job_id))
    assert job is not None
    assert job.status == "failed"


def test_worker_cli_claims_task_from_json_store(tmp_path: Path) -> None:
    db_path = tmp_path / "dev-db.json"
    repository = JsonRepository(db_path)
    submission = Submission(
        id=make_submission_id(),
        user_id="u-student",
        problem_id="P1001",
        problem_title="A+B Problem",
        problem_type="code",
        language="python",
        source_code="raise SystemExit('worker smoke should not execute source')\n",
        status="queued",
        score=0,
        max_score=100,
        details=[],
        message="queued for worker smoke",
        created_at=now(),
    )
    repository.add_submission(submission)

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "apps" / "judge" / "worker.py"),
            "--storage",
            str(db_path),
            "--worker-id",
            "cli-worker",
            "--languages",
            "python",
            "--once",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    event = json.loads(completed.stdout.strip())
    assert event["event"] == "claimed"
    assert event["task"]["submission_id"] == submission.id
    assert event["boundary"] == "claim_only_no_execution"
    assert "worker smoke should not execute source" not in completed.stdout

    stored = repository.get_submission(submission.id)
    assert stored is not None
    assert stored.status == "judging"
    assert stored.judged_at is None
    assert stored.details == []
