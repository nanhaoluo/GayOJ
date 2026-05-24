from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import Repository
from app.models import DEFAULT_STUDENT_SCHOOL


def test_user_can_view_and_update_own_profile(
    client: TestClient,
    auth_headers,
    store: Repository,
) -> None:
    headers = auth_headers("alice")

    profile = client.get("/api/v1/users/me/profile", headers=headers)
    assert profile.status_code == 200, profile.text
    payload = profile.json()
    assert payload["username"] == "alice"
    assert payload["email"] == "alice@example.com"
    assert payload["role"] == "student"
    assert payload["school"] == DEFAULT_STUDENT_SCHOOL
    assert "submission:create" in payload["permissions"]
    assert "password_hash" not in payload

    updated = client.patch(
        "/api/v1/users/me/profile",
        headers=headers,
        json={
            "display_name": "Alice Settings",
            "school": "gayoj Updated Team",
            "email": "alice.settings@example.com",
        },
    )

    assert updated.status_code == 200, updated.text
    updated_payload = updated.json()
    assert updated_payload["display_name"] == "Alice Settings"
    assert updated_payload["school"] == "gayoj Updated Team"
    assert updated_payload["email"] == "alice.settings@example.com"
    assert updated_payload["role"] == "student"

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    me_payload = me.json()
    assert me_payload["display_name"] == "Alice Settings"
    assert "email" not in me_payload

    alice = store.get_user("u-student")
    assert alice is not None
    assert alice.email == "alice.settings@example.com"
    assert alice.display_name == "Alice Settings"
    assert alice.school == "gayoj Updated Team"

    audit_logs, total = store.list_audit_logs(action="user.profile.update")
    assert total == 1
    assert audit_logs[0].actor_id == "u-student"
    assert audit_logs[0].resource == "user:u-student"
    assert audit_logs[0].metadata == {"fields": ["display_name", "email", "school"]}


def test_profile_requires_authenticated_user(client: TestClient) -> None:
    get_response = client.get("/api/v1/users/me/profile")
    patch_response = client.patch(
        "/api/v1/users/me/profile",
        json={"display_name": "Anonymous"},
    )

    assert get_response.status_code == 401
    assert patch_response.status_code == 401


def test_profile_update_validates_user_controlled_fields(
    client: TestClient,
    auth_headers,
    store: Repository,
) -> None:
    headers = auth_headers("alice")

    blank_name = client.patch(
        "/api/v1/users/me/profile",
        headers=headers,
        json={"display_name": "   "},
    )
    invalid_email = client.patch(
        "/api/v1/users/me/profile",
        headers=headers,
        json={"email": "not-an-email"},
    )
    privileged_field = client.patch(
        "/api/v1/users/me/profile",
        headers=headers,
        json={"role": "admin", "rating": 9999},
    )

    assert blank_name.status_code == 422
    assert invalid_email.status_code == 422
    assert privileged_field.status_code == 422

    alice = store.get_user("u-student")
    assert alice is not None
    assert alice.role == "student"
    assert alice.rating == 1580
    assert alice.email == "alice@example.com"


def test_student_profile_backfills_default_school_when_missing(
    client: TestClient,
    auth_headers,
    store: Repository,
) -> None:
    alice = store.get_user("u-student")
    assert alice is not None
    alice.school = ""
    store.update_user(alice)

    profile = client.get("/api/v1/users/me/profile", headers=auth_headers("alice"))

    assert profile.status_code == 200, profile.text
    assert profile.json()["school"] == DEFAULT_STUDENT_SCHOOL
    assert store.get_user("u-student").school == DEFAULT_STUDENT_SCHOOL  # type: ignore[union-attr]


def test_role_change_to_student_assigns_default_school(
    client: TestClient,
    auth_headers,
    store: Repository,
) -> None:
    coach = store.get_user("u-coach")
    assert coach is not None
    coach.school = ""
    store.update_user(coach)

    response = client.patch(
        "/api/v1/admin/users/u-coach/role",
        headers=auth_headers("admin"),
        json={"role": "student"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["role"] == "student"
    assert response.json()["school"] == DEFAULT_STUDENT_SCHOOL

