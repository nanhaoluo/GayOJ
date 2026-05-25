from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app
from app.services import sign_payload


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
    assert payload["signature_algorithm"] == "hmac-sha256"
    assert datetime.fromisoformat(payload["expires_at"]).astimezone(timezone.utc) > datetime.now(timezone.utc)
    assert {problem["type"] for problem in payload["problems"]} <= {"blank", "single_choice", "multiple_choice"}
    assert all(problem["judge_config"] for problem in payload["problems"])


def test_problem_set_offline_package_is_authorized_objective_only_and_signed(
    client: TestClient,
    auth_headers,
    offline_cli_module,
    tmp_path,
) -> None:
    assert client.get("/api/v1/problem-sets/PS1001/offline-package").status_code == 401
    assert client.get("/api/v1/problem-sets/UNKNOWN/offline-package", headers=auth_headers("alice")).status_code == 404
    assert client.get("/api/v1/problem-sets/PS1001/offline-package", headers=auth_headers("coach")).status_code == 403

    response = client.get("/api/v1/problem-sets/PS1001/offline-package", headers=auth_headers("alice"))
    assert response.status_code == 200, response.text
    body = response.json()
    payload = body["payload"]
    problems = payload["problems"]
    assert payload["scope"] == "objective-only"
    assert [problem["id"] for problem in problems] == ["P1002", "P1003"]
    assert {problem["type"] for problem in problems} == {"blank", "single_choice"}
    assert "P1001" not in {problem["id"] for problem in problems}
    assert all(problem["judge_config"] for problem in problems)
    assert body["signature"] == sign_payload(payload)

    pack_path = tmp_path / "problem-set-pack.json"
    pack_path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    loaded_payload = offline_cli_module.load_pack(pack_path)
    assert [problem["id"] for problem in loaded_payload["problems"]] == ["P1002", "P1003"]

    tampered = json.loads(json.dumps(body))
    tampered["payload"]["problems"][0]["title"] = "tampered"
    tampered_path = tmp_path / "tampered-pack.json"
    tampered_path.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")
    try:
        offline_cli_module.load_pack(tampered_path)
    except SystemExit as exc:
        assert "签名校验失败" in str(exc)
    else:
        raise AssertionError("tampered offline pack must be rejected")

    expired = json.loads(json.dumps(body))
    expired["payload"]["expires_at"] = "2000-01-01T00:00:00+00:00"
    expired["signature"] = sign_payload(expired["payload"])
    expired_path = tmp_path / "expired-pack.json"
    expired_path.write_text(json.dumps(expired, ensure_ascii=False), encoding="utf-8")
    try:
        offline_cli_module.load_pack(expired_path)
    except SystemExit as exc:
        assert "已过期" in str(exc)
    else:
        raise AssertionError("expired offline pack must be rejected")


def test_objective_only_problem_set_offline_package_contains_set_scope(client: TestClient, auth_headers) -> None:
    response = client.get("/api/v1/problem-sets/PS1002/offline-package", headers=auth_headers("alice"))

    assert response.status_code == 200, response.text
    problems = response.json()["payload"]["problems"]
    assert [problem["id"] for problem in problems] == ["P1004"]
    assert {problem["type"] for problem in problems} == {"multiple_choice"}

