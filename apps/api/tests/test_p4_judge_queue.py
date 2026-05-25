from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

import app.judge_queue as judge_queue
from app.db import SnapshotRepository, now, seed_data


def test_code_submit_creates_queue_job_metadata_without_copying_source(
    client: TestClient,
    auth_headers,
    store,
) -> None:
    source = "print('queued but not executed by API')\n"
    response = client.post(
        "/api/v1/problems/P1001/submit-code",
        headers=auth_headers("alice"),
        json={"language": "python", "source_code": source},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["queue_job_id"]
    assert payload["queued_at"]
    assert payload["judged_at"] is None

    job = store.get_judge_queue_job(payload["queue_job_id"])
    assert job is not None
    assert job.submission_id == payload["id"]
    assert job.status == "pending"
    assert job.source_ref == f"submission:{payload['id']}:source_code"
    assert job.source_sha256 == hashlib.sha256(source.encode("utf-8")).hexdigest()
    assert job.testdata_ref == "problem:P1001:testdata"
    assert job.limits == {"time_limit_ms": 1000, "memory_limit_mb": 128}
    assert "source_code" not in job.model_dump()
    assert source not in job.model_dump_json()

    monitor = client.get("/api/v1/judge/monitor", headers=auth_headers("judge"))
    assert monitor.status_code == 200, monitor.text
    queue = monitor.json()["queue"]
    assert queue["backend"] == "json"
    assert queue["pending"] >= 1
    assert queue["last_jobs"][0]["source_ref"].startswith("submission:")
    assert "queued but not executed by API" not in json.dumps(queue, ensure_ascii=False)


def test_sqlite_store_migrates_legacy_queued_code_submissions_into_queue_jobs(tmp_path: Path) -> None:
    data = seed_data()
    data.pop("judge_queue_jobs", None)
    data["submissions"].append(
        {
            "id": "S-LEGACY",
            "user_id": "u-student",
            "problem_id": "P1001",
            "problem_title": "A+B Problem",
            "problem_type": "code",
            "language": "python",
            "source_code": "print('legacy source stays on submission')\n",
            "status": "queued",
            "score": 0,
            "max_score": 100,
            "details": [],
            "message": "legacy queued submission",
            "created_at": now().isoformat(),
        }
    )
    target = tmp_path / "legacy-dev-db.json"
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    repository = SnapshotRepository.sqlite(tmp_path / "legacy.sqlite3", seed_path=target)
    jobs = repository.list_judge_queue_jobs()

    job = next(item for item in jobs if item.submission_id == "S-LEGACY")
    assert job.id == "JQ-S-LEGACY"
    assert job.status == "pending"
    assert job.source_ref == "submission:S-LEGACY:source_code"
    assert job.source_sha256

    migrated = json.loads(repository.database.read_payload())
    migrated_submission = next(item for item in migrated["submissions"] if item["id"] == "S-LEGACY")
    assert migrated_submission["queue_job_id"] == job.id
    assert migrated_submission["queued_at"]
    migrated_job = next(item for item in migrated["judge_queue_jobs"] if item["submission_id"] == "S-LEGACY")
    assert "source_code" not in migrated_job


def test_external_queue_config_failure_rolls_back_new_code_submission(
    client: TestClient,
    auth_headers,
    store,
    monkeypatch,
) -> None:
    monkeypatch.setattr(judge_queue, "JUDGE_QUEUE_BACKEND", "redis")
    monkeypatch.setattr(judge_queue, "REDIS_URL", "")

    response = client.post(
        "/api/v1/problems/P1001/submit-code",
        headers=auth_headers("alice"),
        json={"language": "python", "source_code": "print('must only enqueue')\n"},
    )

    assert response.status_code == 503
    assert "GAYOJ_REDIS_URL" in response.json()["detail"]
    assert store.list_submissions() == []
    assert store.list_judge_queue_jobs() == []


def test_external_queue_config_failure_restores_rejudge_submission(
    client: TestClient,
    auth_headers,
    store,
    monkeypatch,
) -> None:
    queued = client.post(
        "/api/v1/problems/P1001/submit-code",
        headers=auth_headers("alice"),
        json={"language": "python", "source_code": "print('queued once')\n"},
    )
    assert queued.status_code == 200, queued.text
    original_job_id = queued.json()["queue_job_id"]

    submission = store.get_submission(queued.json()["id"])
    assert submission is not None
    submission.status = "accepted"
    submission.score = 100
    submission.details = [{"case_id": "sample-1", "status": "accepted"}]
    submission.message = "Accepted before failed rejudge"
    submission.judged_at = now()
    store.update_submission(submission)
    expected = submission.model_dump(mode="json")

    monkeypatch.setattr(judge_queue, "JUDGE_QUEUE_BACKEND", "redis")
    monkeypatch.setattr(judge_queue, "REDIS_URL", "")

    response = client.post(
        f"/api/v1/judge/submissions/{submission.id}/rejudge",
        headers=auth_headers("judge"),
        json={"reason": "queue backend unavailable"},
    )

    assert response.status_code == 503
    restored = store.get_submission(submission.id)
    assert restored is not None
    assert restored.model_dump(mode="json") == expected
    assert store.get_judge_queue_job(original_job_id) is not None
    assert [job.id for job in store.list_judge_queue_jobs()] == [original_job_id]
