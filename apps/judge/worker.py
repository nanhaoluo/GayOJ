from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.db.json_repository import JsonRepository, now  # noqa: E402
from app.db.repository import Repository  # noqa: E402
from app.models import JudgeNode, JudgeQueueJob, Problem, Submission  # noqa: E402


DEFAULT_LANGUAGES = ("cpp", "c", "java", "python")


@dataclass(frozen=True)
class JudgeTask:
    submission_id: str
    problem_id: str
    language: str
    source_ref: str
    limits: dict[str, int | None]
    testdata_ref: str
    judge_mode: str


def parse_languages(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return list(DEFAULT_LANGUAGES)
    if isinstance(value, str):
        candidates = value.replace(";", ",").split(",")
    else:
        candidates = value
    languages: list[str] = []
    for item in candidates:
        language = str(item).strip().lower()
        if language and language not in languages:
            languages.append(language)
    return languages or list(DEFAULT_LANGUAGES)


def build_task(
    submission: Submission,
    problem: Problem,
    judge_config: dict[str, Any],
    queue_job: JudgeQueueJob | None = None,
) -> JudgeTask:
    if submission.problem_type != "code" or problem.type != "code":
        raise ValueError("Judge worker can only build tasks for code submissions")
    if not submission.language:
        raise ValueError("Code submission is missing language")

    configured_testdata = queue_job.testdata_ref if queue_job else judge_config.get("testdata_ref")
    if configured_testdata is None and "tests" in judge_config:
        configured_testdata = f"problem:{problem.id}:tests:{judge_config['tests']}"
    testdata_ref = str(configured_testdata or f"problem:{problem.id}:testdata")
    limits = queue_job.limits if queue_job else {
        "time_limit_ms": problem.time_limit_ms,
        "memory_limit_mb": problem.memory_limit_mb,
    }

    return JudgeTask(
        submission_id=submission.id,
        problem_id=problem.id,
        language=submission.language,
        source_ref=queue_job.source_ref if queue_job else f"submission:{submission.id}:source_code",
        limits=limits,
        testdata_ref=testdata_ref,
        judge_mode=str(judge_config.get("mode", "standard")),
    )


def public_task_payload(task: JudgeTask) -> dict[str, Any]:
    payload = asdict(task)
    payload["source_ref"] = f"submission:{task.submission_id}:source"
    return payload


class JudgeWorker:
    def __init__(
        self,
        repository: Repository,
        *,
        worker_id: str,
        name: str,
        languages: Sequence[str],
    ) -> None:
        self.repository = repository
        self.worker_id = worker_id
        self.name = name
        self.languages = parse_languages(languages)

    def queue_depth(self) -> int:
        supported = set(self.languages)
        return sum(
            1
            for submission in self.repository.list_submissions()
            if submission.problem_type == "code"
            and submission.status == "queued"
            and (not supported or submission.language in supported)
        )

    def heartbeat(self, *, status: str = "online", load: float = 0.0) -> JudgeNode:
        node = JudgeNode(
            id=self.worker_id,
            name=self.name,
            status=status,
            languages=list(self.languages),
            queue_depth=self.queue_depth(),
            load=max(0.0, min(load, 1.0)),
            last_heartbeat=now(),
        )
        return self.repository.update_judge_node(node)

    def claim_once(self) -> JudgeTask | None:
        self.heartbeat(load=0.0)
        claimed = self.repository.claim_next_judge_queue_job(node_id=self.worker_id)
        if claimed is None:
            self.heartbeat(load=0.0)
            return None
        queue_job, submission = claimed

        problem = self.repository.get_problem(submission.problem_id)
        if problem is None:
            raise RuntimeError(f"Problem {submission.problem_id} for submission {submission.id} was not found")
        judge_config = self.repository.get_problem_judge_config(problem.id)
        task = build_task(submission, problem, judge_config, queue_job)
        self.heartbeat(load=1.0)
        return task

    def _queue_job_for_submission(self, submission: Submission) -> JudgeQueueJob | None:
        if submission.queue_job_id:
            job = self.repository.get_judge_queue_job(submission.queue_job_id)
            if job:
                return job
        return next(
            (
                job
                for job in self.repository.list_judge_queue_jobs()
                if job.submission_id == submission.id
            ),
            None,
        )

    def poll_once(self) -> dict[str, Any]:
        task = self.claim_once()
        if task is None:
            return {
                "event": "idle",
                "worker_id": self.worker_id,
                "queue_depth": self.queue_depth(),
                "boundary": "claim_only_no_execution",
            }
        return {
            "event": "claimed",
            "worker_id": self.worker_id,
            "task": public_task_payload(task),
            "boundary": "claim_only_no_execution",
        }


def default_worker_id() -> str:
    host = socket.gethostname().replace(" ", "-").lower() or "local"
    return f"judge-{host}"


def print_event(event: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(event, ensure_ascii=False, sort_keys=True))
        return
    if event["event"] == "claimed":
        task = event["task"]
        print(
            f"claimed {task['submission_id']} for problem {task['problem_id']} "
            f"({task['language']}); code execution is deferred to sandbox stage"
        )
    else:
        print(f"idle; queue_depth={event['queue_depth']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="gayoj judge worker. P4-02 claims queued code submissions but does not execute user code.",
    )
    parser.add_argument(
        "--storage",
        type=Path,
        default=ROOT / "apps" / "api" / "storage" / "dev-db.json",
        help="Path to the JSON development store used by this worker.",
    )
    parser.add_argument("--worker-id", default=default_worker_id(), help="Stable judge node id.")
    parser.add_argument("--name", default="", help="Human-readable judge node name.")
    parser.add_argument(
        "--languages",
        default=",".join(DEFAULT_LANGUAGES),
        help="Comma-separated languages this worker can claim.",
    )
    parser.add_argument("--once", action="store_true", help="Run a single poll and exit.")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Seconds between polls in loop mode.")
    parser.add_argument("--max-iterations", type=int, default=0, help="Optional loop iteration limit.")
    parser.add_argument("--json", action="store_true", help="Print one JSON event per poll.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = JsonRepository(args.storage)
    worker = JudgeWorker(
        repository,
        worker_id=args.worker_id,
        name=args.name or args.worker_id,
        languages=parse_languages(args.languages),
    )

    iterations = 1 if args.once else args.max_iterations
    completed = 0
    while True:
        event = worker.poll_once()
        print_event(event, json_output=args.json)
        completed += 1
        if iterations and completed >= iterations:
            break
        if args.once:
            break
        time.sleep(max(args.poll_interval, 0.1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

