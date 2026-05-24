from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import Repository


def test_disabled_user_is_blocked_across_authenticated_flows(
    client: TestClient,
    auth_headers,
    store: Repository,
) -> None:
    alice_headers = auth_headers("alice")
    admin_headers = auth_headers("admin")

    ban_response = client.patch(
        "/api/v1/admin/users/u-student/ban?disabled=true",
        headers=admin_headers,
    )
    assert ban_response.status_code == 200, ban_response.text
    assert ban_response.json()["disabled"] is True

    login_after_ban = client.post("/api/v1/auth/login", json={"username": "alice", "password": "gayoj123"})
    assert login_after_ban.status_code == 401

    blocked_requests = [
        client.get("/api/v1/auth/me", headers=alice_headers),
        client.get("/api/v1/users/me/profile", headers=alice_headers),
        client.patch(
            "/api/v1/users/me/profile",
            headers=alice_headers,
            json={"display_name": "Blocked Alice"},
        ),
        client.put(
            "/api/v1/users/me/password",
            headers=alice_headers,
            json={"current_password": "gayoj123", "new_password": "newpass1"},
        ),
        client.post(
            "/api/v1/problems/P1001/submit-code",
            headers=alice_headers,
            json={"language": "python", "source_code": "print(1 + 1)\n"},
        ),
        client.post(
            "/api/v1/problems/P1003/submit-objective",
            headers=alice_headers,
            json={"answers": {"choice": "B"}},
        ),
        client.get("/api/v1/training/offline-pack", headers=alice_headers),
        client.post(
            "/api/v1/offline-results/sync",
            headers=alice_headers,
            json={"results": [{"problem_id": "P1003", "answers": {"choice": "B"}}]},
        ),
    ]
    for response in blocked_requests:
        assert response.status_code == 403, response.text
        assert response.json()["detail"] == "Account is disabled"

    assert store.list_submissions() == []
    audit_logs, _ = store.list_audit_logs(action="user.ban")
    assert audit_logs
    assert audit_logs[0].resource == "user:u-student"
    assert audit_logs[0].metadata == {"target_username": "alice", "disabled": True}

    unban_response = client.patch(
        "/api/v1/admin/users/u-student/ban?disabled=false",
        headers=admin_headers,
    )
    assert unban_response.status_code == 200, unban_response.text
    assert unban_response.json()["disabled"] is False

    relogin = client.post("/api/v1/auth/login", json={"username": "alice", "password": "gayoj123"})
    assert relogin.status_code == 200, relogin.text
    fresh_headers = {"Authorization": f"Bearer {relogin.json()['access_token']}"}
    submission = client.post(
        "/api/v1/problems/P1003/submit-objective",
        headers=fresh_headers,
        json={"answers": {"choice": "B"}},
    )
    assert submission.status_code == 200, submission.text
    assert submission.json()["status"] == "accepted"


def test_last_active_admin_cannot_be_banned(client: TestClient, auth_headers) -> None:
    admin_headers = auth_headers("admin")

    response = client.patch(
        "/api/v1/admin/users/u-admin/ban?disabled=true",
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "At least one active admin must remain"

    users = client.get("/api/v1/admin/users", headers=admin_headers)
    assert users.status_code == 200, users.text
    admin = next(user for user in users.json() if user["id"] == "u-admin")
    assert admin["disabled"] is False
