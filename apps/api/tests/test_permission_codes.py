from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import now
from app.models import Submission


def test_login_and_me_expose_runtime_permissions(client: TestClient, auth_headers) -> None:
    alice = client.get("/api/v1/auth/me", headers=auth_headers("alice"))
    coach = client.get("/api/v1/auth/me", headers=auth_headers("coach"))
    judge = client.get("/api/v1/auth/me", headers=auth_headers("judge"))
    admin = client.get("/api/v1/auth/me", headers=auth_headers("admin"))

    assert alice.status_code == 200
    assert coach.status_code == 200
    assert judge.status_code == 200
    assert admin.status_code == 200
    assert "submission:create" in alice.json()["permissions"]
    assert "problem:create" not in alice.json()["permissions"]
    assert "training:offline" in alice.json()["permissions"]
    assert "problem:create" in coach.json()["permissions"]
    assert "tag:manage" in coach.json()["permissions"]
    assert "analytics:read" in coach.json()["permissions"]
    assert "submission:create" not in coach.json()["permissions"]
    assert "training:offline" not in coach.json()["permissions"]
    assert "judge:monitor" in judge.json()["permissions"]
    assert "submission:create" not in judge.json()["permissions"]
    assert "judge:monitor" in admin.json()["permissions"]
    assert "submission:override" in admin.json()["permissions"]
    assert "submission:create" not in admin.json()["permissions"]


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
    student_submission = client.post(
        "/api/v1/problems/P1003/submit-objective",
        headers=auth_headers("alice"),
        json={"answers": {"choice": "B"}},
    )
    assert student_submission.status_code == 200, student_submission.text
    submission_id = student_submission.json()["id"]

    coach_visible = client.get(f"/api/v1/submissions/{submission_id}", headers=auth_headers("coach"))
    assert coach_visible.status_code == 200
    assert coach_visible.json()["id"] == submission_id

    owner_visible = client.get(f"/api/v1/submissions/{submission_id}", headers=auth_headers("alice"))
    assert owner_visible.status_code == 200
    assert owner_visible.json()["id"] == submission_id


def test_only_students_can_participate_in_submission_and_training_flows(client: TestClient, auth_headers) -> None:
    for username in ["coach", "judge", "admin"]:
        code_response = client.post(
            "/api/v1/problems/P1001/submit-code",
            headers=auth_headers(username),
            json={"language": "python", "source_code": "print(1)\n"},
        )
        objective_response = client.post(
            "/api/v1/problems/P1003/submit-objective",
            headers=auth_headers(username),
            json={"answers": {"choice": "B"}},
        )
        offline_pack = client.get("/api/v1/training/offline-pack", headers=auth_headers(username))
        clarification = client.post(
            "/api/v1/contests/C1001/clarifications",
            headers=auth_headers(username),
            json={"question": "Can I participate?"},
        )

        assert code_response.status_code == 403
        assert objective_response.status_code == 403
        assert offline_pack.status_code == 403
        assert clarification.status_code == 403
        assert code_response.json()["detail"] == "Permission denied"
        assert objective_response.json()["detail"] == "Permission denied"


def test_rankings_and_problem_stats_ignore_legacy_non_student_submissions(client: TestClient, store) -> None:
    store.add_submission(
        Submission(
            id="S-LEGACY-COACH",
            user_id="u-coach",
            problem_id="P1003",
            problem_title="二分查找适用条件",
            problem_type="single_choice",
            answers={"choice": "B"},
            status="accepted",
            score=100,
            max_score=100,
            details=[],
            message="legacy non-student submission",
            created_at=now(),
            judged_at=now(),
        )
    )

    rankings = client.get("/api/v1/rankings")
    problems = client.get("/api/v1/problems")
    standings = client.get("/api/v1/contests/C1001/standings")

    assert rankings.status_code == 200, rankings.text
    assert [row["role"] for row in rankings.json()] == ["student"]
    assert all(row["user_id"] != "u-coach" for row in standings.json())
    p1003 = next(problem for problem in problems.json() if problem["id"] == "P1003")
    assert p1003["accepted"] == 0
    assert p1003["attempts"] == 0


def test_admin_only_apis_are_guarded_by_admin_permission_codes(client: TestClient, auth_headers) -> None:
    assert client.get("/api/v1/admin/rbac/matrix", headers=auth_headers("coach")).status_code == 403
    assert client.get("/api/v1/admin/audit-logs", headers=auth_headers("judge")).status_code == 403

    matrix = client.get("/api/v1/admin/rbac/matrix", headers=auth_headers("admin"))
    assert matrix.status_code == 200
    assert matrix.json()["matrix"]["admin"]["rbac:read"] is True

    audit_logs = client.get("/api/v1/admin/audit-logs", headers=auth_headers("admin"))
    assert audit_logs.status_code == 200
    assert "items" in audit_logs.json()

