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


def test_worker_creates_pending_balloon_for_accepted_contest_code_submission(store) -> None:
    from app.db import now
    from app.main import enqueue_code_submission_job
    from app.models import Submission
    from app.services import make_submission_id

    problem = store.get_problem("P1001")
    contest = store.get_contest("C1001")
    assert problem is not None and contest is not None

    submission = Submission(
        id=make_submission_id(),
        user_id="u-student",
        problem_id=problem.id,
        problem_title=problem.title,
        problem_type=problem.type,
        contest_id=contest.id,
        language="python",
        source_code="print('contest ac')\n",
        status="queued",
        score=0,
        max_score=100,
        details=[],
        message="queued",
        created_at=now(),
    )
    enqueue_code_submission_job(store, submission, problem, message="queued for contest")

    result = judge_submission(store, submission.id, FakePointExecutor())
    assert result.status == "accepted"

    balloons = store.list_contest_balloons(contest.id)
    matching = [item for item in balloons if item.get("submission_id") == submission.id]
    assert len(matching) == 1
    assert matching[0]["eligible"] is True
    assert matching[0]["released"] is False


def test_balloon_reconciles_when_first_ac_is_rejudged_away(store) -> None:
    from datetime import timedelta

    from app.db import now
    from app.models import Submission
    from app.services import make_submission_id, refresh_contest_balloon_for_submission

    contest = store.get_contest("C1001")
    problem = store.get_problem("P1001")
    assert contest is not None and problem is not None
    first_time = now()
    second_time = first_time + timedelta(minutes=1)

    first = Submission(
        id=make_submission_id(),
        user_id="u-student",
        problem_id=problem.id,
        problem_title=problem.title,
        problem_type=problem.type,
        contest_id=contest.id,
        language="python",
        source_code="print('first')\n",
        status="accepted",
        score=100,
        max_score=100,
        details=[],
        message="accepted",
        created_at=first_time,
        judged_at=first_time,
    )
    second = Submission(
        id=make_submission_id(),
        user_id="u-student",
        problem_id=problem.id,
        problem_title=problem.title,
        problem_type=problem.type,
        contest_id=contest.id,
        language="python",
        source_code="print('second')\n",
        status="accepted",
        score=100,
        max_score=100,
        details=[],
        message="accepted",
        created_at=second_time,
        judged_at=second_time,
    )
    store.add_submission(first)
    store.add_submission(second)

    initial = refresh_contest_balloon_for_submission(store, first)
    assert initial is not None
    assert initial.submission_id == first.id
    assert initial.first_ac is True

    first.status = "wrong_answer"
    first.score = 0
    store.update_submission(first)

    reconciled = refresh_contest_balloon_for_submission(store, first)
    assert reconciled is not None
    assert reconciled.submission_id == second.id
    assert reconciled.first_ac is True

    balloons = store.list_contest_balloons(contest.id)
    assert len(balloons) == 1
    assert balloons[0]["submission_id"] == second.id


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
