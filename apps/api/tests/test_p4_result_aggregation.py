from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[3]
JUDGE_ROOT = ROOT / "apps" / "judge"
if str(JUDGE_ROOT) not in sys.path:
    sys.path.insert(0, str(JUDGE_ROOT))

from gayoj_judge import CodeJudgeTask, CodeTestCase, CompileOutcome, RunOutcome, judge_submission, run_test_points  # noqa: E402


class FakePointExecutor:
    def __init__(
        self,
        *,
        compile_ok: bool = True,
        compile_message: str = "",
        outputs: dict[str, str] | None = None,
        statuses: dict[str, str] | None = None,
    ) -> None:
        self.compile_ok = compile_ok
        self.compile_message = compile_message
        self.outputs = outputs or {}
        self.statuses = statuses or {}
        self.runs: list[str] = []
        self.cleaned = False

    def compile(self, task: CodeJudgeTask) -> CompileOutcome:
        return CompileOutcome(ok=self.compile_ok, artifact={"submission_id": task.submission_id}, message=self.compile_message)

    def run(self, task: CodeJudgeTask, artifact: Any, test_case: CodeTestCase) -> RunOutcome:
        self.runs.append(test_case.id)
        status = self.statuses.get(test_case.id, "accepted")
        return RunOutcome(
            status=status,  # type: ignore[arg-type]
            stdout=self.outputs.get(test_case.id, test_case.expected_output),
            message=status if status != "accepted" else "",
            time_ms=12,
            memory_kb=2048,
        )

    def cleanup(self, artifact: Any) -> None:
        self.cleaned = True


def submit_code(client: TestClient, auth_headers, source_code: str = "print('ok')\n") -> dict[str, Any]:
    response = client.post(
        "/api/v1/problems/P1001/submit-code",
        headers=auth_headers("alice"),
        json={"language": "python", "source_code": source_code},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_worker_aggregates_accepted_result_and_completes_queue_job(client: TestClient, auth_headers, store) -> None:
    queued = submit_code(client, auth_headers)
    assert queued["status"] == "queued"
    assert queued["judged_at"] is None
    assert queued["details"] == []
    assert queued["queue_job_id"]

    result = judge_submission(store, queued["id"], FakePointExecutor())

    assert result.status == "accepted"
    assert result.score == result.max_score == 100
    assert result.judged_at is not None
    assert [item["status"] for item in result.details] == ["accepted", "accepted"]
    job = store.get_judge_queue_job(queued["queue_job_id"])
    assert job is not None
    assert job.status == "completed"
    assert job.completed_at is not None

    logs, _total = store.list_audit_logs(action="submission.code.judged")
    assert any(log.resource == f"submission:{queued['id']}" for log in logs)
    assert any(notification.title == "代码评测完成" for notification in store.list_notifications("u-student"))


def test_worker_reports_wrong_answer_from_output_mismatch() -> None:
    task = CodeJudgeTask(
        submission_id="S1",
        problem_id="P1",
        language="python",
        source_code="print(1)\n",
        time_limit_ms=1000,
        memory_limit_mb=128,
        test_cases=[
            CodeTestCase(id="case-1", input="1 2\n", expected_output="3\n", score=50),
            CodeTestCase(id="case-2", input="2 2\n", expected_output="4\n", score=50),
        ],
    )

    result = run_test_points(task, FakePointExecutor(outputs={"case-2": "5\n"}))

    assert result["status"] == "wrong_answer"
    assert result["score"] == 50
    assert result["max_score"] == 100
    assert result["details"][1]["status"] == "wrong_answer"
    assert "input_preview" not in result["details"][1]
    assert "expected_preview" not in result["details"][1]
    assert result["details"][1]["actual_preview"] == "5\n"


def test_worker_reports_compile_error_without_running_tests() -> None:
    task = CodeJudgeTask(
        submission_id="S1",
        problem_id="P1",
        language="cpp",
        source_code="int main(",
        time_limit_ms=1000,
        memory_limit_mb=128,
        test_cases=[CodeTestCase(id="case-1", input="", expected_output="", score=100)],
    )
    executor = FakePointExecutor(compile_ok=False, compile_message="expected ')' before end of input")

    result = run_test_points(task, executor)

    assert result["status"] == "compile_error"
    assert result["score"] == 0
    assert result["details"][0]["phase"] == "compile"
    assert executor.runs == []


def test_worker_maps_runtime_limit_statuses() -> None:
    task = CodeJudgeTask(
        submission_id="S1",
        problem_id="P1",
        language="python",
        source_code="print(1)\n",
        time_limit_ms=1000,
        memory_limit_mb=128,
        test_cases=[
            CodeTestCase(id="case-1", input="", expected_output="", score=25),
            CodeTestCase(id="case-2", input="", expected_output="", score=25),
            CodeTestCase(id="case-3", input="", expected_output="", score=25),
            CodeTestCase(id="case-4", input="", expected_output="", score=25),
        ],
    )
    executor = FakePointExecutor(
        statuses={
            "case-1": "time_limit_exceeded",
            "case-2": "memory_limit_exceeded",
            "case-3": "runtime_error",
            "case-4": "accepted",
        }
    )

    result = run_test_points(task, executor)

    assert result["status"] == "time_limit_exceeded"
    assert result["score"] == 25
    assert [item["status"] for item in result["details"]] == [
        "time_limit_exceeded",
        "memory_limit_exceeded",
        "runtime_error",
        "accepted",
    ]
    assert executor.cleaned is True


def test_worker_marks_queue_job_failed_on_system_error(client: TestClient, auth_headers, store) -> None:
    queued = submit_code(client, auth_headers)

    result = judge_submission(
        store,
        queued["id"],
        FakePointExecutor(statuses={"sample-1": "system_error"}),
    )

    assert result.status == "system_error"
    job = store.get_judge_queue_job(queued["queue_job_id"])
    assert job is not None
    assert job.status == "failed"
    assert job.last_error == "system_error"


def test_worker_converts_compile_executor_exception_to_system_error() -> None:
    class BrokenExecutor(FakePointExecutor):
        def compile(self, task: CodeJudgeTask) -> CompileOutcome:
            raise RuntimeError("docker daemon unavailable")

    task = CodeJudgeTask(
        submission_id="S1",
        problem_id="P1",
        language="python",
        source_code="print(1)\n",
        time_limit_ms=1000,
        memory_limit_mb=128,
        test_cases=[CodeTestCase(id="case-1", input="hidden", expected_output="hidden", score=100)],
    )

    result = run_test_points(task, BrokenExecutor())

    assert result["status"] == "system_error"
    assert result["score"] == 0
    assert result["details"][0]["status"] == "system_error"
    assert "docker daemon unavailable" not in result["message"]


def test_worker_converts_run_executor_exception_without_leaking_internal_error() -> None:
    class BrokenRunExecutor(FakePointExecutor):
        def run(self, task: CodeJudgeTask, artifact: Any, test_case: CodeTestCase) -> RunOutcome:
            raise RuntimeError("C:/secret/host/path leaked")

    task = CodeJudgeTask(
        submission_id="S1",
        problem_id="P1",
        language="python",
        source_code="print(1)\n",
        time_limit_ms=1000,
        memory_limit_mb=128,
        test_cases=[CodeTestCase(id="case-1", input="hidden", expected_output="hidden", score=100)],
    )

    result = run_test_points(task, BrokenRunExecutor())

    assert result["status"] == "system_error"
    assert result["details"][0]["status"] == "system_error"
    assert result["details"][0]["message"] == "Sandbox executor failed while running a test point."
    assert "C:/secret/host/path" not in result["details"][0]["message"]
