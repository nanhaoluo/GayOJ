from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

from .config import JUDGE_QUEUE_BACKEND, JUDGE_QUEUE_TOPIC, KAFKA_BOOTSTRAP_SERVERS, REDIS_URL
from .db.repository import Repository
from .models import JudgeQueueBackend, JudgeQueueJob, JudgeQueueSummary, Problem, Submission


SUPPORTED_BACKENDS = {"json", "redis", "kafka"}


class QueueBackendUnavailable(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def make_queue_job_id() -> str:
    return f"JQ-{uuid4().hex[:12]}"


def build_code_queue_job(
    submission: Submission,
    problem: Problem,
    judge_config: dict,
    *,
    backend: JudgeQueueBackend,
) -> JudgeQueueJob:
    source = submission.source_code or ""
    testdata_ref = judge_config.get("testdata_ref") or judge_config.get("dataset_ref")
    return JudgeQueueJob(
        id=submission.queue_job_id or make_queue_job_id(),
        submission_id=submission.id,
        problem_id=problem.id,
        user_id=submission.user_id,
        contest_id=submission.contest_id,
        language=submission.language or "",
        source_ref=f"submission:{submission.id}:source_code",
        source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        limits={
            "time_limit_ms": problem.time_limit_ms,
            "memory_limit_mb": problem.memory_limit_mb,
        },
        testdata_ref=str(testdata_ref or f"problem:{problem.id}:testdata"),
        priority=10 if submission.contest_id else 0,
        status="pending",
        backend=backend,
        created_at=submission.queued_at or utc_now(),
    )


class JsonJudgeQueue:
    backend: JudgeQueueBackend = "json"

    def __init__(self, repository: Repository, topic: str = JUDGE_QUEUE_TOPIC):
        self.repository = repository
        self.topic = topic

    def enqueue_code_submission(
        self,
        submission: Submission,
        job: JudgeQueueJob,
        *,
        previous_submission: Submission | None = None,
    ) -> JudgeQueueJob:
        if self.repository.get_submission(submission.id):
            self.repository.update_submission(submission)
        else:
            self.repository.add_submission(submission)
        return self.repository.add_judge_queue_job(job)

    def rollback_code_submission(
        self,
        submission_id: str,
        job_id: str | None = None,
        *,
        previous_submission: Submission | None = None,
    ) -> None:
        if job_id:
            self.repository.delete_judge_queue_job(job_id)
        if previous_submission is None:
            self.repository.delete_submission(submission_id)
            return
        if self.repository.get_submission(previous_submission.id):
            self.repository.update_submission(previous_submission)
        else:
            self.repository.add_submission(previous_submission)

    def summary(self, limit: int = 10) -> JudgeQueueSummary:
        jobs = self.repository.list_judge_queue_jobs()
        pending = sum(1 for job in jobs if job.status == "pending")
        leased = sum(1 for job in jobs if job.status == "leased")
        last_jobs = sorted(jobs, key=lambda job: job.created_at, reverse=True)[:limit]
        return JudgeQueueSummary(
            backend=self.backend,
            topic=self.topic,
            depth=pending + leased,
            pending=pending,
            leased=leased,
            last_jobs=last_jobs,
        )


class RedisJudgeQueue(JsonJudgeQueue):
    backend: JudgeQueueBackend = "redis"

    def enqueue_code_submission(
        self,
        submission: Submission,
        job: JudgeQueueJob,
        *,
        previous_submission: Submission | None = None,
    ) -> JudgeQueueJob:
        stored = super().enqueue_code_submission(submission, job, previous_submission=previous_submission)
        if not REDIS_URL:
            self.rollback_code_submission(submission.id, stored.id, previous_submission=previous_submission)
            raise QueueBackendUnavailable("GAYOJ_REDIS_URL is required for the Redis judge queue backend")
        try:
            import redis  # type: ignore[import-not-found]
        except ImportError as exc:
            self.rollback_code_submission(submission.id, stored.id, previous_submission=previous_submission)
            raise QueueBackendUnavailable("Install the optional redis package to use GAYOJ_JUDGE_QUEUE_BACKEND=redis") from exc
        client = redis.Redis.from_url(REDIS_URL)
        try:
            client.rpush(self.topic, stored.model_dump_json())
        except Exception as exc:
            self.rollback_code_submission(submission.id, stored.id, previous_submission=previous_submission)
            raise QueueBackendUnavailable(f"Failed to publish judge queue job to Redis topic {self.topic}") from exc
        return stored


class KafkaJudgeQueue(JsonJudgeQueue):
    backend: JudgeQueueBackend = "kafka"

    def enqueue_code_submission(
        self,
        submission: Submission,
        job: JudgeQueueJob,
        *,
        previous_submission: Submission | None = None,
    ) -> JudgeQueueJob:
        stored = super().enqueue_code_submission(submission, job, previous_submission=previous_submission)
        if not KAFKA_BOOTSTRAP_SERVERS:
            self.rollback_code_submission(submission.id, stored.id, previous_submission=previous_submission)
            raise QueueBackendUnavailable(
                "GAYOJ_KAFKA_BOOTSTRAP_SERVERS is required for the Kafka judge queue backend"
            )
        try:
            from kafka import KafkaProducer  # type: ignore[import-not-found]
        except ImportError as exc:
            self.rollback_code_submission(submission.id, stored.id, previous_submission=previous_submission)
            raise QueueBackendUnavailable(
                "Install the optional kafka-python package to use GAYOJ_JUDGE_QUEUE_BACKEND=kafka"
            ) from exc
        producer = KafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","))
        try:
            future = producer.send(self.topic, stored.model_dump_json().encode("utf-8"))
            future.get(timeout=10)
            producer.flush(timeout=10)
        except Exception as exc:
            self.rollback_code_submission(submission.id, stored.id, previous_submission=previous_submission)
            raise QueueBackendUnavailable(f"Failed to publish judge queue job to Kafka topic {self.topic}") from exc
        finally:
            producer.close(timeout=10)
        return stored


def get_judge_queue(repository: Repository) -> JsonJudgeQueue:
    backend = JUDGE_QUEUE_BACKEND
    if backend not in SUPPORTED_BACKENDS:
        raise QueueBackendUnavailable(f"Unsupported GAYOJ_JUDGE_QUEUE_BACKEND: {backend}")
    if backend == "redis":
        return RedisJudgeQueue(repository)
    if backend == "kafka":
        return KafkaJudgeQueue(repository)
    return JsonJudgeQueue(repository)


__all__ = [
    "QueueBackendUnavailable",
    "build_code_queue_job",
    "get_judge_queue",
    "make_queue_job_id",
]
