from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.db import Repository


def test_admin_can_query_persisted_audit_logs(client: TestClient, auth_headers) -> None:
    headers = auth_headers("admin")

    update = client.put(
        "/api/v1/system/config",
        headers=headers,
        json={"maintenance_mode": True, "site_name": "gayoj Audit Test"},
    )
    assert update.status_code == 200, update.text

    response = client.get(
        "/api/v1/admin/audit-logs?action=system.config.update&resource=system:config&limit=1",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] >= 1
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["actor_id"] == "u-admin"
    assert item["action"] == "system.config.update"
    assert item["resource"] == "system:config"
    assert item["metadata"]["site_name"] == "gayoj Audit Test"


def test_audit_logs_require_admin(client: TestClient, auth_headers) -> None:
    unauthenticated = client.get("/api/v1/admin/audit-logs")
    assert unauthenticated.status_code == 401

    student = client.get("/api/v1/admin/audit-logs", headers=auth_headers("alice"))
    assert student.status_code == 403


def test_failed_login_is_audited_without_password(client: TestClient, auth_headers) -> None:
    failed = client.post("/api/v1/auth/login", json={"username": "alice", "password": "wrong-password"})
    assert failed.status_code == 401

    response = client.get("/api/v1/admin/audit-logs?action=auth.login_failed", headers=auth_headers("admin"))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] >= 1
    item = payload["items"][0]
    assert item["action"] == "auth.login_failed"
    assert item["actor_id"] == "u-student"
    assert item["metadata"]["username"] == "alice"
    assert "password" not in json.dumps(item["metadata"]).lower()


def test_repository_filters_and_paginates_audit_logs(store: Repository) -> None:
    store.add_audit("u-admin", "system.config.update", "system:config", {"field": "site_name"})
    store.add_audit(None, "auth.login_failed", "user:missing", {"username": "missing"})
    store.add_audit("u-judge", "submission.override", "submission:S1", {"score": 80})

    items, total = store.list_audit_logs(action="system.config.update", limit=10)
    assert total == 1
    assert items[0].actor_id == "u-admin"
    assert items[0].metadata["field"] == "site_name"

    second_page, total = store.list_audit_logs(resource="user:", limit=1, offset=0)
    assert total == 1
    assert second_page[0].actor_id is None

