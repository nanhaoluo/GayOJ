from __future__ import annotations

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app


def test_openapi_business_routes_are_versioned_and_typed() -> None:
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        assert route.path.startswith("/api/v1/"), route.path
        documented_content = any(response.get("content") for response in route.responses.values())
        assert route.response_model is not None or documented_content, route.path


def test_v1_health_endpoint_is_typed(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "gayoj API"
    assert payload["time"]


def test_system_config_requires_admin_and_uses_schema(client: TestClient, auth_headers) -> None:
    assert client.get("/api/v1/system/config").status_code == 401
    assert client.get("/api/v1/system/config", headers=auth_headers("alice")).status_code == 403

    admin_headers = auth_headers("admin")
    response = client.get("/api/v1/system/config", headers=admin_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["site_name"] == "gayoj"
    assert payload["judge_submit_rate_limit_per_minute"] >= 1

    invalid = client.put(
        "/api/v1/system/config",
        headers=admin_headers,
        json={"judge_submit_rate_limit_per_minute": 0},
    )
    assert invalid.status_code == 422

    updated = client.put(
        "/api/v1/system/config",
        headers=admin_headers,
        json={"site_name": "gayoj P1", "maintenance_mode": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["site_name"] == "gayoj P1"
    assert updated.json()["default_language"] == "cpp"


def test_judge_monitor_requires_judge_or_admin(client: TestClient, auth_headers) -> None:
    assert client.get("/api/v1/judge/monitor").status_code == 401
    assert client.get("/api/v1/judge/monitor", headers=auth_headers("alice")).status_code == 403

    response = client.get("/api/v1/judge/monitor", headers=auth_headers("judge"))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert isinstance(payload["queue_depth"], int)
    assert isinstance(payload["judge_nodes"], list)
    assert isinstance(payload["clarifications"], list)


def test_admin_judge_nodes_requires_admin(client: TestClient, auth_headers) -> None:
    assert client.get("/api/v1/admin/judge-nodes").status_code == 401
    assert client.get("/api/v1/admin/judge-nodes", headers=auth_headers("judge")).status_code == 403

    response = client.get("/api/v1/admin/judge-nodes", headers=auth_headers("admin"))
    assert response.status_code == 200, response.text
    assert response.json()[0]["id"].startswith("node-")


def test_problem_set_update_enforces_owner_or_admin(client: TestClient, auth_headers) -> None:
    create_payload = {
        "title": "Private owner check",
        "description": "P1 resource ownership regression",
        "type": "set",
        "visibility": "private",
        "problem_ids": ["P1002", "P1003"],
    }
    created = client.post("/api/v1/problem-sets", headers=auth_headers("coach"), json=create_payload)
    assert created.status_code == 200, created.text
    problem_set_id = created.json()["id"]
    assert created.json()["owner_id"] == "u-coach"

    forbidden = client.put(
        f"/api/v1/problem-sets/{problem_set_id}",
        headers=auth_headers("judge"),
        json={**create_payload, "title": "Judge cannot take ownership"},
    )
    assert forbidden.status_code == 403

    owner_update = client.put(
        f"/api/v1/problem-sets/{problem_set_id}",
        headers=auth_headers("coach"),
        json={**create_payload, "title": "Owner can update"},
    )
    assert owner_update.status_code == 200, owner_update.text
    assert owner_update.json()["title"] == "Owner can update"


def test_offline_pack_is_authorized_objective_only(client: TestClient, auth_headers) -> None:
    assert client.get("/api/v1/training/offline-pack").status_code == 401

    response = client.get("/api/v1/training/offline-pack", headers=auth_headers("alice"))
    assert response.status_code == 200, response.text
    payload = response.json()["payload"]
    assert payload["scope"] == "objective-only"
    assert {problem["type"] for problem in payload["problems"]} <= {"blank", "single_choice", "multiple_choice"}
    assert all(problem["judge_config"] for problem in payload["problems"])

