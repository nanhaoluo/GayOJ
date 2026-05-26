from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from typing import Any

from ..models import Clarification, Contest, ContestAnnouncement, ContestPrintJob, JudgeNode, JudgeQueueJob, Submission
from ..store import Store, seed_data
from storage.database import StateDatabase, SqliteStateDatabase, create_state_database
from storage.database_config import DatabaseSettings


class SnapshotRepository(Store):
    """Repository adapter that stores the normalized app state through storage.database."""

    def __init__(self, database: StateDatabase, *, seed_path: Path | None = None) -> None:
        self.path = seed_path or Path("<database-state>")
        self.database = database
        self._lock = threading.RLock()
        self._cached_payload: str | None = None
        self._cached_data: dict[str, Any] | None = None
        self._ensure_seeded()

    @classmethod
    def from_settings(cls, settings: DatabaseSettings) -> "SnapshotRepository":
        return cls(create_state_database(settings), seed_path=settings.dev_db_json_path)

    @classmethod
    def sqlite(
        cls,
        path: Path,
        *,
        seed_path: Path | None = None,
        busy_timeout_ms: int = 5000,
        cache_enabled: bool = True,
    ) -> "SnapshotRepository":
        return cls(
            SqliteStateDatabase(
                path,
                busy_timeout_ms=busy_timeout_ms,
                cache_enabled=cache_enabled,
            ),
            seed_path=seed_path,
        )

    def _ensure_seeded(self) -> None:
        with self._lock:
            payload = self.database.read_payload()
            if payload is not None:
                data = self._parse_payload(payload)
                data, changed = self._normalize_data(data)
                if changed:
                    self._write(data)
                    self._replace_hot_collections(data)
                else:
                    self._cache_snapshot(payload, data)
                    self._replace_hot_collections(data)
                return
            data = self._load_seed_data()
            data, _changed = self._normalize_data(data)
            self._write(data)
            self._replace_hot_collections(data)

    def _load_seed_data(self) -> dict[str, Any]:
        if self.path.exists():
            raw = self.path.read_text(encoding="utf-8")
            if raw.strip():
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
        return seed_data()

    def _read(self) -> dict[str, Any]:
        with self._lock:
            payload = self.database.read_payload()
            if payload is None:
                data = self._load_seed_data()
                data, _changed = self._normalize_data(data)
                self._write(data)
                self._replace_hot_collections(data)
                return copy.deepcopy(data)
            if self._cached_data is not None and self._cached_payload == payload:
                return copy.deepcopy(self._cached_data)
            data = self._parse_payload(payload)
            data, changed = self._normalize_data(data)
            if changed:
                self._write(data)
                self._replace_hot_collections(data)
                return copy.deepcopy(data)
            self._cache_snapshot(payload, data)
            return copy.deepcopy(data)

    def _write(self, data: dict[str, Any]) -> None:
        with self._lock:
            payload = json.dumps(data, ensure_ascii=False, indent=2)
            self.database.write_payload(payload)
            self._cache_snapshot(payload, data)
            self._replace_hot_collections(data)

    def _cache_snapshot(self, payload: str, data: dict[str, Any]) -> None:
        self._cached_payload = payload
        self._cached_data = copy.deepcopy(data)

    def _parse_payload(self, payload: str) -> dict[str, Any]:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return seed_data()
        return data if isinstance(data, dict) else seed_data()

    def _replace_hot_collections(self, data: dict[str, Any], *collections: str) -> None:
        if not hasattr(self.database, "replace_hot_collection"):
            return
        try:
            if collections:
                for collection in collections:
                    items = data.get(collection, [])
                    self.database.replace_hot_collection(collection, items if isinstance(items, list) else [])
            else:
                self.database.replace_hot_collections(data)
        except Exception:
            return

    def _replace_cached_hot_collections(self, *collections: str) -> None:
        if self._cached_data is not None:
            self._replace_hot_collections(self._cached_data, *collections)

    def _list_hot(self, collection: str, *, contest_id: str | None = None, status: str | None = None) -> list[dict[str, Any]] | None:
        if not hasattr(self.database, "list_hot_items"):
            return None
        try:
            return self.database.list_hot_items(collection, contest_id=contest_id, status=status)
        except Exception:
            return None

    def _get_hot(self, collection: str, item_id: str) -> dict[str, Any] | None:
        if not hasattr(self.database, "get_hot_item"):
            return None
        try:
            return self.database.get_hot_item(collection, item_id)
        except Exception:
            return None

    def list_submissions(self) -> list[Submission]:
        items = self._list_hot("submissions")
        if items is None:
            return super().list_submissions()
        return [Submission(**item) for item in items]

    def get_submission(self, submission_id: str) -> Submission | None:
        item = self._get_hot("submissions", submission_id)
        if item is not None:
            return Submission(**item)
        return super().get_submission(submission_id)

    def add_submission(self, submission: Submission) -> Submission:
        result = super().add_submission(submission)
        self._replace_cached_hot_collections("submissions", "judge_queue_jobs")
        return result

    def update_submission(self, submission: Submission) -> Submission:
        result = super().update_submission(submission)
        self._replace_cached_hot_collections("submissions")
        return result

    def delete_submission(self, submission_id: str) -> None:
        super().delete_submission(submission_id)
        self._replace_cached_hot_collections("submissions")

    def list_judge_queue_jobs(self) -> list[JudgeQueueJob]:
        items = self._list_hot("judge_queue_jobs")
        if items is None:
            return super().list_judge_queue_jobs()
        return [JudgeQueueJob(**item) for item in items]

    def get_judge_queue_job(self, job_id: str) -> JudgeQueueJob | None:
        item = self._get_hot("judge_queue_jobs", job_id)
        if item is not None:
            return JudgeQueueJob(**item)
        return super().get_judge_queue_job(job_id)

    def add_judge_queue_job(self, job: JudgeQueueJob) -> JudgeQueueJob:
        result = super().add_judge_queue_job(job)
        self._replace_cached_hot_collections("judge_queue_jobs")
        return result

    def update_judge_queue_job(self, job: JudgeQueueJob) -> JudgeQueueJob:
        result = super().update_judge_queue_job(job)
        self._replace_cached_hot_collections("judge_queue_jobs")
        return result

    def delete_judge_queue_job(self, job_id: str) -> None:
        super().delete_judge_queue_job(job_id)
        self._replace_cached_hot_collections("judge_queue_jobs")

    def claim_next_judge_queue_job(self, *, node_id: str) -> tuple[JudgeQueueJob, Submission] | None:
        result = super().claim_next_judge_queue_job(node_id=node_id)
        if result is not None:
            self._replace_cached_hot_collections("judge_queue_jobs", "submissions", "judge_nodes")
        return result

    def claim_next_code_submission(self, *, worker_id: str, languages: list[str]) -> Submission | None:
        result = super().claim_next_code_submission(worker_id=worker_id, languages=languages)
        if result is not None:
            self._replace_cached_hot_collections("judge_queue_jobs", "submissions")
        return result

    def list_contests(self) -> list[Contest]:
        items = self._list_hot("contests")
        if items is None:
            return super().list_contests()
        return [Contest(**item) for item in items]

    def get_contest(self, contest_id: str) -> Contest | None:
        item = self._get_hot("contests", contest_id)
        if item is not None:
            return Contest(**item)
        return super().get_contest(contest_id)

    def add_contest(self, contest: Contest) -> Contest:
        result = super().add_contest(contest)
        self._replace_cached_hot_collections("contests")
        return result

    def update_contest(self, contest: Contest) -> Contest:
        result = super().update_contest(contest)
        self._replace_cached_hot_collections("contests")
        return result

    def list_clarifications(self) -> list[Clarification]:
        items = self._list_hot("clarifications")
        if items is None:
            return super().list_clarifications()
        return [Clarification(**item) for item in items]

    def get_clarification(self, clarification_id: str) -> Clarification | None:
        item = self._get_hot("clarifications", clarification_id)
        if item is not None:
            return Clarification(**item)
        return super().get_clarification(clarification_id)

    def add_clarification(self, clarification: Clarification) -> Clarification:
        result = super().add_clarification(clarification)
        self._replace_cached_hot_collections("clarifications")
        return result

    def update_clarification(self, clarification: Clarification) -> Clarification:
        result = super().update_clarification(clarification)
        self._replace_cached_hot_collections("clarifications")
        return result

    def list_contest_announcements(self, contest_id: str | None = None) -> list[ContestAnnouncement]:
        items = self._list_hot("contest_announcements", contest_id=contest_id)
        if items is None:
            return super().list_contest_announcements(contest_id)
        return [ContestAnnouncement(**item) for item in items]

    def add_contest_announcement(self, announcement: ContestAnnouncement) -> ContestAnnouncement:
        result = super().add_contest_announcement(announcement)
        self._replace_cached_hot_collections("contest_announcements")
        return result

    def list_contest_print_jobs(self, contest_id: str | None = None) -> list[ContestPrintJob]:
        items = self._list_hot("contest_print_jobs", contest_id=contest_id)
        if items is None:
            return super().list_contest_print_jobs(contest_id)
        return [ContestPrintJob(**item) for item in items]

    def get_contest_print_job(self, job_id: str) -> ContestPrintJob | None:
        item = self._get_hot("contest_print_jobs", job_id)
        if item is not None:
            return ContestPrintJob(**item)
        return super().get_contest_print_job(job_id)

    def add_contest_print_job(self, job: ContestPrintJob) -> ContestPrintJob:
        result = super().add_contest_print_job(job)
        self._replace_cached_hot_collections("contest_print_jobs")
        return result

    def update_contest_print_job(self, job: ContestPrintJob) -> ContestPrintJob:
        result = super().update_contest_print_job(job)
        self._replace_cached_hot_collections("contest_print_jobs")
        return result

    def list_contest_balloons(self, contest_id: str | None = None) -> list[dict[str, Any]]:
        items = self._list_hot("contest_balloons", contest_id=contest_id)
        if items is None:
            return super().list_contest_balloons(contest_id)
        return [dict(item) for item in items]

    def upsert_contest_balloon(self, balloon: dict[str, Any]) -> dict[str, Any]:
        result = super().upsert_contest_balloon(balloon)
        self._replace_cached_hot_collections("contest_balloons")
        return result

    def delete_contest_balloon(self, contest_id: str, user_id: str, problem_id: str) -> None:
        super().delete_contest_balloon(contest_id, user_id, problem_id)
        self._replace_cached_hot_collections("contest_balloons")

    def list_judge_nodes(self) -> list[JudgeNode]:
        data = self._read()
        if self._migrate_judge_nodes(data):
            self._write(data)
        return [JudgeNode(**item) for item in data["judge_nodes"]]

    def update_judge_node(self, judge_node: JudgeNode) -> JudgeNode:
        result = super().update_judge_node(judge_node)
        self._replace_cached_hot_collections("judge_nodes")
        return result


def create_snapshot_repository(settings: DatabaseSettings) -> SnapshotRepository:
    return SnapshotRepository.from_settings(settings)


__all__ = ["SnapshotRepository", "create_snapshot_repository"]
