from __future__ import annotations

from fastapi.testclient import TestClient


def test_login_and_me_expose_runtime_permissions(client: TestClient, auth_headers) -> None:
    alice = client.get("/api/v1/auth/me", headers=auth_headers("alice"))
    coach = client.get("/api/v1/auth/me", headers=auth_headers("coach"))

    assert alice.status_code == 200
    assert coach.status_code == 200
    assert "submission:create" in alice.json()["permissions"]
    assert "problem:create" not in alice.json()["permissions"]
    assert "problem:create" in coach.json()["permissions"]
    assert "tag:manage" in coach.json()["permissions"]
    assert "analytics:read" in coach.json()["permissions"]


def test_problem_create_uses_permission_code_and_does_not_return_judge_config(
    client: TestClient,
    auth_headers,
) -> None:
    payload = {
        "title": "权限码创建题目",
        "type": "blank",
        "difficulty": "基础",
        "tags": ["RBAC"],
        "statement": "填写 gayoj 的权限码分隔符。",
        "blanks": [{"key": "separator", "label": "分隔符", "score": 100}],
        "judge_config": {
            "case_sensitive": False,
            "trim_space": True,
            "answers": {"separator": [":"]},
            "scores": {"separator": 100},
        },
    }

    forbidden = client.post("/api/v1/problems", headers=auth_headers("alice"), json=payload)
    assert forbidden.status_code == 403

    created = client.post("/api/v1/problems", headers=auth_headers("coach"), json=payload)
    assert created.status_code == 200, created.text
    created_payload = created.json()
    assert created_payload["author_id"] == "u-coach"
    assert "judge_config" not in created_payload

    detail = client.get(f"/api/v1/problems/{created_payload['id']}", headers=auth_headers("coach"))
    assert detail.status_code == 200
    assert "judge_config" not in detail.json()


def test_permission_codes_control_submission_visibility(client: TestClient, auth_headers) -> None:
    coach_submission = client.post(
        "/api/v1/problems/P1003/submit-objective",
        headers=auth_headers("coach"),
        json={"answers": {"choice": "B"}},
    )
    assert coach_submission.status_code == 200, coach_submission.text
    submission_id = coach_submission.json()["id"]

    alice_forbidden = client.get(f"/api/v1/submissions/{submission_id}", headers=auth_headers("alice"))
    assert alice_forbidden.status_code == 403

    coach_visible = client.get(f"/api/v1/submissions/{submission_id}", headers=auth_headers("coach"))
    assert coach_visible.status_code == 200
    assert coach_visible.json()["id"] == submission_id


def test_admin_only_apis_are_guarded_by_admin_permission_codes(client: TestClient, auth_headers) -> None:
    assert client.get("/api/v1/admin/rbac/matrix", headers=auth_headers("coach")).status_code == 403
    assert client.get("/api/v1/admin/audit-logs", headers=auth_headers("judge")).status_code == 403

    matrix = client.get("/api/v1/admin/rbac/matrix", headers=auth_headers("admin"))
    assert matrix.status_code == 200
    assert matrix.json()["matrix"]["admin"]["rbac:read"] is True

    audit_logs = client.get("/api/v1/admin/audit-logs", headers=auth_headers("admin"))
    assert audit_logs.status_code == 200
    assert "items" in audit_logs.json()

