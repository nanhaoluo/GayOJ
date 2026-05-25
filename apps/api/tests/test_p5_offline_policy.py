from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db import SnapshotRepository, seed_data


def pack_problem_ids(client: TestClient, auth_headers, path: str = "/api/v1/problem-sets/PS1001/offline-package") -> list[str]:
    response = client.get(path, headers=auth_headers("alice"))
    assert response.status_code == 200, response.text
    return [problem["id"] for problem in response.json()["payload"]["problems"]]


def test_public_problem_detail_hides_offline_policy_and_judge_config(client: TestClient) -> None:
    response = client.get("/api/v1/problems/P1002")

    assert response.status_code == 200, response.text
    body = response.json()
    assert "judge_config" not in body
    assert "offline_policy" not in body
    assert "offline_enabled" not in body


def test_problem_offline_policy_filters_authorized_pack(client: TestClient, auth_headers) -> None:
    assert pack_problem_ids(client, auth_headers) == ["P1002", "P1003"]

    response = client.patch(
        "/api/v1/admin/problems/P1003/offline-policy",
        headers=auth_headers("coach"),
        json={"offline_enabled": False, "offline_policy": {"answer_visibility": "full", "sync_mode": "allow"}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["offline_enabled"] is False
    assert body["offline_policy"]["answer_visibility"] == "full"

    assert pack_problem_ids(client, auth_headers) == ["P1002"]


def test_answer_visibility_none_excludes_problem_from_pack(client: TestClient, auth_headers) -> None:
    response = client.patch(
        "/api/v1/admin/problems/P1002/offline-policy",
        headers=auth_headers("coach"),
        json={"offline_enabled": True, "offline_policy": {"answer_visibility": "none", "sync_mode": "allow"}},
    )
    assert response.status_code == 200, response.text

    assert pack_problem_ids(client, auth_headers) == ["P1003"]


def test_problem_policy_ttl_controls_pack_expiry(client: TestClient, auth_headers) -> None:
    updated = client.patch(
        "/api/v1/admin/problems/P1002/offline-policy",
        headers=auth_headers("coach"),
        json={
            "offline_enabled": True,
            "offline_policy": {"ttl_hours": 2, "answer_visibility": "full", "sync_mode": "allow"},
        },
    )
    assert updated.status_code == 200, updated.text

    response = client.get("/api/v1/training/offline-pack", headers=auth_headers("alice"))
    assert response.status_code == 200, response.text
    payload = response.json()["payload"]
    generated_at = datetime.fromisoformat(payload["generated_at"]).astimezone(timezone.utc)
    expires_at = datetime.fromisoformat(payload["expires_at"]).astimezone(timezone.utc)
    assert 7190 <= (expires_at - generated_at).total_seconds() <= 7210


def test_problem_set_offline_policy_can_reject_download(client: TestClient, auth_headers) -> None:
    updated = client.patch(
        "/api/v1/problem-sets/PS1001/offline-policy",
        headers=auth_headers("coach"),
        json={"offline_enabled": False, "offline_policy": {"answer_visibility": "full", "sync_mode": "allow"}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["offline_enabled"] is False

    response = client.get("/api/v1/problem-sets/PS1001/offline-package", headers=auth_headers("alice"))
    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"]


def test_code_problem_creation_cannot_enable_offline_pack(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/api/v1/admin/problems",
        headers=auth_headers("admin"),
        json={
            "title": "Code offline boundary",
            "type": "code",
            "difficulty": "基础",
            "statement": "Submit code online only.",
            "input_format": "stdin",
            "output_format": "stdout",
            "samples": [{"input": "1 2", "output": "3"}],
            "time_limit_ms": 1000,
            "memory_limit_mb": 128,
            "offline_enabled": True,
            "offline_policy": {"answer_visibility": "full", "sync_mode": "allow"},
            "judge_config": {"mode": "standard"},
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["type"] == "code"
    assert response.json()["offline_enabled"] is False


def test_offline_sync_respects_problem_sync_policy(client: TestClient, auth_headers) -> None:
    updated = client.patch(
        "/api/v1/admin/problems/P1003/offline-policy",
        headers=auth_headers("coach"),
        json={
            "offline_enabled": True,
            "offline_policy": {"answer_visibility": "full", "sync_mode": "disabled"},
        },
    )
    assert updated.status_code == 200, updated.text

    response = client.post(
        "/api/v1/offline-results/sync",
        headers=auth_headers("alice"),
        json={
            "results": [
                {
                    "problem_id": "P1003",
                    "answers": {"choice": "B"},
                    "practiced_at": "2026-05-25T00:00:00+00:00",
                    "client_result_key": "sync-disabled",
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["synced"] == []
    assert body["merged"] == []
    assert body["rejected"] == [{"problem_id": "P1003", "reason": "离线策略不允许同步该题结果"}]


def test_legacy_snapshot_backfills_offline_policy_defaults(tmp_path) -> None:
    data = seed_data()
    for problem in data["problems"]:
        problem.pop("offline_enabled", None)
        problem.pop("offline_policy", None)
    for problem_set in data["problem_sets"]:
        problem_set.pop("offline_enabled", None)
        problem_set.pop("offline_policy", None)
    target = tmp_path / "legacy-dev-db.json"
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    repository = SnapshotRepository.sqlite(tmp_path / "legacy.sqlite3", seed_path=target)

    assert repository.get_problem("P1001").offline_enabled is False  # type: ignore[union-attr]
    assert repository.get_problem("P1002").offline_enabled is True  # type: ignore[union-attr]
    assert repository.get_problem("P1002").offline_policy.answer_visibility == "full"  # type: ignore[union-attr]
    assert repository.get_problem_set("PS1001").offline_enabled is True  # type: ignore[union-attr]
