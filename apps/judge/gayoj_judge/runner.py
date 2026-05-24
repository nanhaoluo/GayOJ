from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol
from uuid import uuid4


JudgeStatus = Literal[
    "accepted",
    "wrong_answer",
    "time_limit_exceeded",
    "memory_limit_exceeded",
    "runtime_error",
    "compile_error",
    "output_limit_exceeded",
    "system_error",
]

RunStatus = Literal[
    "accepted",
    "compile_error",
    "time_limit_exceeded",
    "memory_limit_exceeded",
    "runtime_error",
    "output_limit_exceeded",
    "system_error",
]


@dataclass(frozen=True)
class CodeTestCase:
    id: str
    input: str
    expected_output: str
    score: int = 1
    time_limit_ms: int | None = None
    memory_limit_mb: int | None = None
    output_limit_bytes: int | None = None


@dataclass(frozen=True)
class CodeJudgeTask:
    submission_id: str
    problem_id: str
    language: str
    source_code: str
    time_limit_ms: int
    memory_limit_mb: int
    test_cases: list[CodeTestCase] = field(default_factory=list)


@dataclass(frozen=True)
class CompileOutcome:
    ok: bool
    artifact: Any = None
    message: str = ""
    time_ms: int = 0


@dataclass(frozen=True)
class RunOutcome:
    status: RunStatus
    stdout: str = ""
    stderr: str = ""
    message: str = ""
    exit_code: int | None = None
    time_ms: int = 0
    memory_kb: int = 0


class SandboxExecutor(Protocol):
    """Worker-side sandbox adapter.

    Implementations must run outside the API/Web/CLI process and enforce the
    sandbox contract: temporary work directory, no network, and resource limits.
    """

    def compile(self, task: CodeJudgeTask) -> CompileOutcome: ...

    def run(self, task: CodeJudgeTask, artifact: Any, test_case: CodeTestCase) -> RunOutcome: ...

    def cleanup(self, artifact: Any) -> None: ...


class DockerSandboxPointExecutor:
    """Adapter from the Docker sandbox smoke executor to the P4-05 runner.

    The current Docker executor owns temporary-directory cleanup internally and
    executes one test point per call. This adapter keeps the API/Web/CLI boundary
    intact while letting the worker aggregate test-point details.
    """

    def __init__(self, sandbox: Any | None = None) -> None:
        if sandbox is None:
            from .sandbox import DockerSandboxExecutor

            sandbox = DockerSandboxExecutor()
        self.sandbox = sandbox

    def compile(self, task: CodeJudgeTask) -> CompileOutcome:
        return CompileOutcome(ok=True, artifact={"language": task.language}, message="Compilation is sandboxed per test point.")

    def run(self, task: CodeJudgeTask, artifact: Any, test_case: CodeTestCase) -> RunOutcome:
        from .sandbox import SandboxLimits

        result = self.sandbox.execute(
            language=task.language,
            source_code=task.source_code,
            stdin=test_case.input,
            limits=SandboxLimits(
                time_limit_ms=test_case.time_limit_ms or task.time_limit_ms,
                memory_limit_mb=test_case.memory_limit_mb or task.memory_limit_mb,
                output_limit_bytes=test_case.output_limit_bytes or 1_048_576,
            ),
        )
        status = _sandbox_verdict_to_status(result.verdict)
        return RunOutcome(
            status=status,
            stdout=result.stdout,
            stderr=result.stderr,
            message=result.message,
            exit_code=result.exit_code,
            time_ms=result.duration_ms,
            memory_kb=0,
        )

    def cleanup(self, artifact: Any) -> None:
        return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_output(value: str) -> list[str]:
    lines = [line.rstrip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def _preview(value: str, limit: int = 400) -> str:
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"


def _sandbox_verdict_to_status(verdict: str) -> RunStatus:
    return {
        "ok": "accepted",
        "compile_error": "compile_error",
        "time_limit_exceeded": "time_limit_exceeded",
        "memory_limit_exceeded": "memory_limit_exceeded",
        "output_limit_exceeded": "output_limit_exceeded",
        "runtime_error": "runtime_error",
        "unsupported_language": "compile_error",
        "sandbox_error": "system_error",
    }.get(verdict, "system_error")


def _case_from_dict(index: int, item: dict[str, Any], defaults: dict[str, int]) -> CodeTestCase:
    return CodeTestCase(
        id=str(item.get("id") or item.get("name") or f"case-{index + 1}"),
        input=str(item.get("input", "")),
        expected_output=str(item.get("expected_output", item.get("output", ""))),
        score=max(0, int(item.get("score", defaults.get("score", 1)))),
        time_limit_ms=int(item["time_limit_ms"]) if item.get("time_limit_ms") is not None else defaults.get("time_limit_ms"),
        memory_limit_mb=int(item["memory_limit_mb"]) if item.get("memory_limit_mb") is not None else defaults.get("memory_limit_mb"),
        output_limit_bytes=(
            int(item["output_limit_bytes"]) if item.get("output_limit_bytes") is not None else defaults.get("output_limit_bytes")
        ),
    )


def _cases_from_problem(problem: Any, judge_config: dict[str, Any]) -> list[CodeTestCase]:
    defaults = {
        "score": int(judge_config.get("default_score", 1)),
        "time_limit_ms": int(judge_config.get("time_limit_ms") or getattr(problem, "time_limit_ms", None) or 1000),
        "memory_limit_mb": int(judge_config.get("memory_limit_mb") or getattr(problem, "memory_limit_mb", None) or 128),
    }
    if judge_config.get("output_limit_bytes") is not None:
        defaults["output_limit_bytes"] = int(judge_config["output_limit_bytes"])

    raw_cases = judge_config.get("test_cases") or judge_config.get("tests")
    if isinstance(raw_cases, list):
        return [
            _case_from_dict(index, item, defaults)
            for index, item in enumerate(raw_cases)
            if isinstance(item, dict)
        ]

    samples = getattr(problem, "samples", []) or []
    sample_count = len([sample for sample in samples if isinstance(sample, dict)])
    base_score = 100 // sample_count if sample_count else defaults["score"]
    remainder = 100 % sample_count if sample_count else 0
    return [
        _case_from_dict(
            index,
            {
                "id": f"sample-{index + 1}",
                "input": sample.get("input", ""),
                "expected_output": sample.get("output", ""),
                "score": base_score + (1 if index < remainder else 0),
            },
            defaults,
        )
        for index, sample in enumerate(samples)
        if isinstance(sample, dict)
    ]


def build_task(submission: Any, problem: Any, judge_config: dict[str, Any]) -> CodeJudgeTask:
    if getattr(submission, "problem_type", None) != "code":
        raise ValueError("Only code submissions can be judged by the code worker")
    if getattr(problem, "type", None) != "code":
        raise ValueError("Only code problems can be judged by the code worker")
    source_code = getattr(submission, "source_code", None)
    language = getattr(submission, "language", None)
    if not source_code or not language:
        raise ValueError("Code submission must include language and source_code")

    task = CodeJudgeTask(
        submission_id=submission.id,
        problem_id=problem.id,
        language=language,
        source_code=source_code,
        time_limit_ms=int(judge_config.get("time_limit_ms") or getattr(problem, "time_limit_ms", None) or 1000),
        memory_limit_mb=int(judge_config.get("memory_limit_mb") or getattr(problem, "memory_limit_mb", None) or 128),
        test_cases=_cases_from_problem(problem, judge_config),
    )
    if not task.test_cases:
        raise ValueError("Code judge task must include at least one test case")
    return task


def run_test_points(task: CodeJudgeTask, executor: SandboxExecutor) -> dict[str, Any]:
    max_score = sum(test_case.score for test_case in task.test_cases)
    try:
        compile_result = executor.compile(task)
    except Exception:  # noqa: BLE001 - worker must convert sandbox setup failures into judge results.
        return {
            "status": "system_error",
            "score": 0,
            "max_score": max_score,
            "message": "Sandbox executor failed before running test points.",
            "details": [
                {
                    "phase": "compile",
                    "status": "system_error",
                    "score": 0,
                    "max_score": max_score,
                    "time_ms": 0,
                    "message": "Sandbox executor failed before running test points.",
                }
            ],
        }
    artifact = compile_result.artifact
    if not compile_result.ok:
        if artifact is not None:
            executor.cleanup(artifact)
        return {
            "status": "compile_error",
            "score": 0,
            "max_score": max_score,
            "message": compile_result.message or "Compile Error",
            "details": [
                {
                    "phase": "compile",
                    "status": "compile_error",
                    "score": 0,
                    "max_score": max_score,
                    "time_ms": compile_result.time_ms,
                    "message": compile_result.message,
                }
            ],
        }

    score = 0
    details: list[dict[str, Any]] = []
    final_status: JudgeStatus = "accepted"
    final_message = "Accepted"

    try:
        for index, test_case in enumerate(task.test_cases, start=1):
            try:
                outcome = executor.run(task, artifact, test_case)
            except Exception:  # noqa: BLE001 - worker must convert sandbox failures into judge results.
                status = "system_error"
                message = "Sandbox executor failed while running a test point."
                if final_status == "accepted":
                    final_status = status
                    final_message = message
                details.append(
                    {
                        "case_id": test_case.id,
                        "index": index,
                        "status": status,
                        "score": 0,
                        "max_score": test_case.score,
                        "time_ms": 0,
                        "memory_kb": 0,
                        "exit_code": None,
                        "message": message,
                        "actual_preview": "",
                        "stderr_preview": "",
                    }
                )
                break
            status: JudgeStatus = outcome.status
            case_score = 0
            message = outcome.message
            if outcome.status == "accepted":
                if _normalize_output(outcome.stdout) == _normalize_output(test_case.expected_output):
                    status = "accepted"
                    case_score = test_case.score
                    message = message or "Accepted"
                else:
                    status = "wrong_answer"
                    message = message or "Wrong Answer"

            if status != "accepted" and final_status == "accepted":
                final_status = status
                final_message = message or status

            score += case_score
            details.append(
                {
                    "case_id": test_case.id,
                    "index": index,
                    "status": status,
                    "score": case_score,
                    "max_score": test_case.score,
                    "time_ms": outcome.time_ms,
                    "memory_kb": outcome.memory_kb,
                    "exit_code": outcome.exit_code,
                    "message": message,
                    "actual_preview": _preview(outcome.stdout),
                    "stderr_preview": _preview(outcome.stderr),
                }
            )
    finally:
        executor.cleanup(artifact)

    return {
        "status": final_status,
        "score": score,
        "max_score": max_score,
        "message": final_message if final_status != "accepted" else "Accepted",
        "details": details,
    }


def judge_submission(store: Any, submission_id: str, executor: SandboxExecutor) -> Any:
    submission = store.get_submission(submission_id)
    if not submission:
        raise ValueError(f"Submission not found: {submission_id}")
    if submission.problem_type != "code":
        raise ValueError("Only code submissions can be judged by the code worker")
    if submission.status not in {"queued", "judging"}:
        raise ValueError(f"Submission is not pending code judging: {submission.status}")

    problem = store.get_problem(submission.problem_id)
    if not problem:
        raise ValueError(f"Problem not found: {submission.problem_id}")
    judge_config = store.get_problem_judge_config(problem.id)
    task = build_task(submission, problem, judge_config)

    submission.status = "judging"
    submission.message = "Judge worker is running test points."
    store.update_submission(submission)

    result = run_test_points(task, executor)
    submission.status = result["status"]
    submission.score = int(result["score"])
    submission.max_score = int(result["max_score"])
    submission.details = result["details"]
    submission.message = str(result["message"])
    submission.judged_at = _utcnow()
    store.update_submission(submission)

    job_id = getattr(submission, "queue_job_id", None)
    if job_id:
        _complete_queue_job(store, job_id, submission.status, submission.message)
    store.add_audit(
        None,
        "submission.code.judged",
        f"submission:{submission.id}",
        {"problem_id": submission.problem_id, "status": submission.status, "score": submission.score},
    )
    store.add_notification(
        _notification(
            user_id=submission.user_id,
            title="代码评测完成",
            content=f"{submission.problem_title}：{submission.status}，得分 {submission.score}/{submission.max_score}",
        )
    )
    return submission


def _complete_queue_job(store: Any, job_id: str, status: str, message: str) -> None:
    get_job = getattr(store, "get_judge_queue_job", None)
    update_job = getattr(store, "update_judge_queue_job", None)
    if not callable(get_job) or not callable(update_job):
        return
    job = get_job(job_id)
    if not job:
        return
    job.status = "failed" if status == "system_error" else "completed"
    job.completed_at = _utcnow()
    job.last_error = message if job.status == "failed" else ""
    update_job(job)


def _notification(user_id: str, title: str, content: str) -> Any:
    from app.models import Notification

    return Notification(
        id=f"N{uuid4().hex[:10].upper()}",
        user_id=user_id,
        title=title,
        content=content,
        type="judge",
        created_at=_utcnow(),
    )
