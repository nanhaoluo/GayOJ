from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.db import Repository


def admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "gayoj123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def login(client: TestClient, username: str, password: str):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_failed_login_attempts_lock_account_and_are_audited(client: TestClient, store: Repository) -> None:
    headers = admin_headers(client)
    response = client.put(
        "/api/v1/system/config",
        headers=headers,
        json={"login_max_failed_attempts": 2, "login_lockout_minutes": 10},
    )
    assert response.status_code == 200, response.text

    first = login(client, "alice", "bad-password")
    assert first.status_code == 401

    second = login(client, "alice", "bad-password")
    assert second.status_code == 423

    locked = login(client, "alice", "gayoj123")
    assert locked.status_code == 423

    user = store.get_user_by_username("alice")
    assert user is not None
    assert user.failed_login_attempts == 2
    assert user.locked_until is not None

    logs = client.get("/api/v1/admin/audit-logs?action=auth.login_locked", headers=headers)
    assert logs.status_code == 200, logs.text
    item = logs.json()["items"][0]
    assert item["actor_id"] == "u-student"
    assert item["metadata"]["username"] == "alice"
    assert item["metadata"]["failed_login_attempts"] == 2
    assert "password" not in json.dumps(item["metadata"]).lower()


def test_successful_login_resets_failure_counter(client: TestClient, store: Repository) -> None:
    failed = login(client, "alice", "bad-password")
    assert failed.status_code == 401
    user = store.get_user_by_username("alice")
    assert user is not None
    assert user.failed_login_attempts == 1

    success = login(client, "alice", "gayoj123")
    assert success.status_code == 200, success.text
    user = store.get_user_by_username("alice")
    assert user is not None
    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    assert user.last_login_at is not None


def test_password_change_enforces_policy_without_logging_secret(client: TestClient, auth_headers) -> None:
    student_headers = auth_headers("alice")

    weak = client.put(
        "/api/v1/users/me/password",
        headers=student_headers,
        json={"current_password": "gayoj123", "new_password": "abcdef"},
    )
    assert weak.status_code == 422
    assert "digit" in weak.text.lower()

    admin = auth_headers("admin")
    logs = client.get("/api/v1/admin/audit-logs?action=auth.password_change_failed", headers=admin)
    assert logs.status_code == 200, logs.text
    metadata_text = json.dumps(logs.json()["items"][0]["metadata"]).lower()
    assert "abcdef" not in metadata_text
    assert "gayoj123" not in metadata_text
    assert "password" not in metadata_text


def test_password_change_succeeds_and_new_password_can_login(client: TestClient, auth_headers, store: Repository) -> None:
    student_headers = auth_headers("alice")
    changed = client.put(
        "/api/v1/users/me/password",
        headers=student_headers,
        json={"current_password": "gayoj123", "new_password": "newpass1"},
    )
    assert changed.status_code == 200, changed.text

    old_password = login(client, "alice", "gayoj123")
    assert old_password.status_code == 401

    new_password = login(client, "alice", "newpass1")
    assert new_password.status_code == 200, new_password.text

    user = store.get_user_by_username("alice")
    assert user is not None
    assert user.password_changed_at is not None
    assert user.failed_login_attempts == 0
