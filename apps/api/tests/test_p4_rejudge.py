from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import now


def submit_code(client: TestClient, auth_headers, source: str = "raise SystemExit('must not run in API')\n") -> dict:
    response = client.post(
        "/api/v1/problems/P1001/submit-code",
        headers=auth_headers("alice"),
        json={"language": "python", "source_code": source},
    )
    assert response.status_code == 200, response.text
    return response.json()


def submit_objective(client: TestClient, auth_headers) -> dict:
    response = client.post(
        "/api/v1/problems/P1003/submit-objective",
        headers=auth_headers("alice"),
        json={"answers": {"choice": "B"}},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_manual_rejudge_requires_override_permission_and_requeues_code_submission(
    client: TestClient,
    auth_headers,
    store,
) -> None:
    queued = submit_code(client, auth_headers)
    original_job_id = queued["queue_job_id"]

    forbidden = client.post(
        f"/api/v1/judge/submissions/{queued['id']}/rejudge",
        headers=auth_headers("alice"),
        json={"reason": "student should not rejudge"},
    )
    assert forbidden.status_code == 403

    submission = store.get_submission(queued["id"])
    assert submission is not None
    submission.status = "accepted"
    submission.score = 100
    submission.details = [{"case_id": "sample-1", "status": "accepted"}]
    submission.message = "Accepted before rejudge"
    submission.judged_at = now()
    store.update_submission(submission)

    response = client.post(
        f"/api/v1/judge/submissions/{queued['id']}/rejudge",
        headers=auth_headers("judge"),
        json={"reason": "testdata changed"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["score"] == 0
    assert payload["details"] == []
    assert payload["judged_at"] is None
    assert payload["queue_job_id"]
    assert payload["queue_job_id"] != original_job_id
    assert "重新进入在线评测队列" in payload["message"]

    job = store.get_judge_queue_job(payload["queue_job_id"])
    assert job is not None
    assert job.status == "pending"
    assert job.submission_id == queued["id"]
    assert job.source_ref == f"submission:{queued['id']}:source_code"
    assert "source_code" not in job.model_dump()

    public_detail = client.get("/api/v1/problems/P1001", headers=auth_headers("alice"))
    assert public_detail.status_code == 200
    assert "judge_config" not in public_detail.json()

    logs, total = store.list_audit_logs(action="submission.rejudge")
    assert total == 1
    assert logs[0].metadata["reason"] == "testdata changed"


def test_batch_rejudge_requeues_code_and_skips_non_code_or_missing_submissions(
    client: TestClient,
    auth_headers,
    store,
) -> None:
    code_submission = submit_code(client, auth_headers)
    objective_submission = submit_objective(client, auth_headers)

    response = client.post(
        "/api/v1/judge/submissions/rejudge",
        headers=auth_headers("admin"),
        json={
            "submission_ids": [code_submission["id"], objective_submission["id"], "S-MISSING"],
            "reason": "batch smoke",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["requeued_count"] == 1
    assert payload["requeued"][0]["id"] == code_submission["id"]
    assert payload["requeued"][0]["status"] == "queued"
    assert payload["skipped_count"] == 2
    skipped = {item["submission_id"]: item["reason"] for item in payload["skipped"]}
    assert "Only code submissions can be rejudged" in skipped[objective_submission["id"]]
    assert skipped["S-MISSING"] == "Submission not found"

    monitor = client.get("/api/v1/judge/monitor", headers=auth_headers("judge"))
    assert monitor.status_code == 200, monitor.text
    monitor_payload = monitor.json()
    assert monitor_payload["queue_depth"] >= 1
    assert monitor_payload["queue"]["pending"] >= 1
    assert monitor_payload["queue"]["last_jobs"][0]["source_ref"].startswith("submission:")


def test_batch_rejudge_can_filter_by_problem_and_status(
    client: TestClient,
    auth_headers,
    store,
) -> None:
    first = submit_code(client, auth_headers, "print('first queued only')\n")
    second = submit_code(client, auth_headers, "print('second queued only')\n")

    second_submission = store.get_submission(second["id"])
    assert second_submission is not None
    second_submission.status = "accepted"
    second_submission.score = 100
    second_submission.judged_at = now()
    store.update_submission(second_submission)

    response = client.post(
        "/api/v1/judge/submissions/rejudge",
        headers=auth_headers("admin"),
        json={"problem_id": "P1001", "statuses": ["accepted"], "reason": "accepted-only"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert {item["id"] for item in payload["requeued"]} == {second["id"]}
    assert all(item["submission_id"] != first["id"] for item in payload["skipped"])
