from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_login_and_me(client: TestClient, auth_headers) -> None:
    headers = auth_headers("alice")

    response = client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["username"] == "alice"
    assert payload["role"] == "student"


def test_public_problem_detail_does_not_include_judge_config(client: TestClient) -> None:
    response = client.get("/api/v1/problems/P1002")

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "blank"
    assert "judge_config" not in payload


def test_student_problem_detail_does_not_include_judge_config(client: TestClient, auth_headers) -> None:
    response = client.get("/api/v1/problems/P1002", headers=auth_headers("alice"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "blank"
    assert "judge_config" not in payload


def test_manager_problem_detail_does_not_include_judge_config(client: TestClient, auth_headers) -> None:
    response = client.get("/api/v1/problems/P1002", headers=auth_headers("coach"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "blank"
    assert "judge_config" not in payload


def test_objective_submission_is_scored_server_side(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/api/v1/problems/P1003/submit-objective",
        headers=auth_headers("alice"),
        json={"answers": {"choice": "B"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["problem_type"] == "single_choice"
    assert payload["status"] == "accepted"
    assert payload["score"] == payload["max_score"] == 100


def test_code_submission_enters_online_judge_queue(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/api/v1/problems/P1001/submit-code",
        headers=auth_headers("alice"),
        json={"language": "python", "source_code": "a, b = map(int, input().split())\nprint(a + b)\n"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["problem_type"] == "code"
    assert payload["status"] == "queued"
    assert payload["message"] == "已进入在线评测队列。"
    assert payload["judged_at"] is None
    assert payload["details"] == []


def test_code_submission_is_not_locally_judged_by_api(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/api/v1/problems/P1001/submit-code",
        headers=auth_headers("alice"),
        json={"language": "python", "source_code": "x"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["score"] == 0
    assert payload["judged_at"] is None


def test_code_problem_rejected_by_objective_endpoint(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/api/v1/problems/P1001/submit-objective",
        headers=auth_headers("alice"),
        json={"answers": {"choice": "A"}},
    )

    assert response.status_code == 400
    assert "Code problems must be submitted to online judge" in response.json()["detail"]


def test_offline_pack_contains_only_objective_problems(client: TestClient, auth_headers) -> None:
    response = client.get("/api/v1/training/offline-pack", headers=auth_headers("alice"))

    assert response.status_code == 200
    problem_types = {problem["type"] for problem in response.json()["payload"]["problems"]}
    assert problem_types
    assert "code" not in problem_types


def test_cli_rejects_code_problem_judging(offline_cli_module) -> None:
    with pytest.raises(SystemExit):
        offline_cli_module.judge({"type": "code", "judge_config": {}}, {})
