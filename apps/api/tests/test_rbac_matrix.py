from __future__ import annotations

from fastapi.testclient import TestClient


def test_admin_can_query_rbac_matrix(client: TestClient, auth_headers) -> None:
    response = client.get("/api/v1/admin/rbac/matrix", headers=auth_headers("admin"))

    assert response.status_code == 200
    payload = response.json()
    roles = {role["code"]: set(role["permissions"]) for role in payload["roles"]}

    assert {"student", "coach", "judge", "admin"} <= roles.keys()
    assert "problem:read" in roles["student"]
    assert "submission:create" in roles["student"]
    assert "problem:create" not in roles["student"]
    assert "submission:read:own" in roles["student"]
    assert "submission:read:all" not in roles["student"]
    assert "problem:create" in roles["coach"]
    assert "analytics:read" in roles["coach"]
    assert "submission:override" in roles["judge"]
    assert "judge:monitor" in roles["judge"]
    assert "user:ban" in roles["admin"]
    assert "user:role:update" in roles["admin"]
    assert "audit:read" in roles["admin"]
    assert "rbac:read" in roles["admin"]
    assert payload["matrix"]["admin"]["system:config"] is True
    assert payload["matrix"]["student"]["system:config"] is False


def test_rbac_matrix_requires_login(client: TestClient) -> None:
    response = client.get("/api/v1/admin/rbac/matrix")

    assert response.status_code == 401


def test_rbac_matrix_requires_admin(client: TestClient, auth_headers) -> None:
    response = client.get("/api/v1/admin/rbac/matrix", headers=auth_headers("alice"))

    assert response.status_code == 403


def test_admin_can_assign_user_role_and_audit_change(client: TestClient, auth_headers) -> None:
    admin_headers = auth_headers("admin")

    response = client.patch(
        "/api/v1/admin/users/u-student/role",
        headers=admin_headers,
        json={"role": "coach"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["role"] == "coach"
    assert "analytics:read" in payload["permissions"]

    coach_response = client.get("/api/v1/coach/analytics", headers=auth_headers("alice"))
    assert coach_response.status_code == 200, coach_response.text

    audit_response = client.get(
        "/api/v1/admin/audit-logs?action=user.role.update&resource=user:u-student",
        headers=admin_headers,
    )
    assert audit_response.status_code == 200, audit_response.text
    audit = audit_response.json()
    assert audit["total"] >= 1
    assert audit["items"][0]["metadata"]["old_role"] == "student"
    assert audit["items"][0]["metadata"]["new_role"] == "coach"


def test_role_assignment_requires_role_update_permission(client: TestClient, auth_headers) -> None:
    assert client.patch("/api/v1/admin/users/u-student/role", json={"role": "coach"}).status_code == 401

    response = client.patch(
        "/api/v1/admin/users/u-student/role",
        headers=auth_headers("judge"),
        json={"role": "coach"},
    )

    assert response.status_code == 403


def test_role_assignment_keeps_at_least_one_active_admin(client: TestClient, auth_headers) -> None:
    admin_headers = auth_headers("admin")

    response = client.patch(
        "/api/v1/admin/users/u-admin/role",
        headers=admin_headers,
        json={"role": "student"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "At least one active admin must remain"
    users = client.get("/api/v1/admin/users", headers=admin_headers).json()
    assert next(user for user in users if user["id"] == "u-admin")["role"] == "admin"
