from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import JUDGE_NODE_TOKEN


def test_public_language_table_exposes_enabled_p4_languages(client: TestClient) -> None:
    response = client.get("/api/v1/judge/languages")

    assert response.status_code == 200, response.text
    languages = response.json()
    assert [item["code"] for item in languages] == ["c", "cpp", "java", "python"]
    assert {item["source_extension"] for item in languages} == {".c", ".cpp", ".java", ".py"}
    assert all("version" in item for item in languages)
    assert all("compile_command" not in item for item in languages)


def test_compiler_configs_require_admin_and_can_update_versions(client: TestClient, auth_headers) -> None:
    assert client.get("/api/v1/admin/compiler-configs").status_code == 401
    assert client.get("/api/v1/admin/compiler-configs", headers=auth_headers("alice")).status_code == 403

    admin_headers = auth_headers("admin")
    configs = client.get("/api/v1/admin/compiler-configs", headers=admin_headers)
    assert configs.status_code == 200, configs.text
    cpp = next(item for item in configs.json() if item["code"] == "cpp")
    assert "compile_command" in cpp

    updated = client.put(
        "/api/v1/admin/compiler-configs/cpp",
        headers=admin_headers,
        json={"version": "GCC 14.2 / C++20", "sort_order": cpp["sort_order"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == "GCC 14.2 / C++20"

    languages = client.get("/api/v1/judge/languages")
    assert languages.status_code == 200
    assert next(item for item in languages.json() if item["code"] == "cpp")["version"] == "GCC 14.2 / C++20"


def test_disabled_language_is_not_accepted_or_claimed(client: TestClient, auth_headers, store) -> None:
    admin_headers = auth_headers("admin")
    disabled = client.put(
        "/api/v1/admin/compiler-configs/c",
        headers=admin_headers,
        json={"enabled": False},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["enabled"] is False

    languages = client.get("/api/v1/judge/languages")
    assert [item["code"] for item in languages.json()] == ["cpp", "java", "python"]

    rejected = client.post(
        "/api/v1/problems/P1001/submit-code",
        headers=auth_headers("alice"),
        json={"language": "c", "source_code": "int main(void){return 0;}"},
    )
    assert rejected.status_code == 400
    assert store.list_judge_queue_jobs() == []

    heartbeat = client.post(
        "/api/v1/judge/nodes/heartbeat",
        headers={"x-judge-node-token": JUDGE_NODE_TOKEN},
        json={
            "id": "compiler-filter",
            "name": "compiler filter",
            "status": "online",
            "languages": ["c", "python", "rust"],
            "queue_depth": 0,
            "load": 0.1,
        },
    )
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["languages"] == ["python"]


def test_default_language_must_be_enabled(client: TestClient, auth_headers) -> None:
    admin_headers = auth_headers("admin")

    response = client.put(
        "/api/v1/admin/compiler-configs/cpp",
        headers=admin_headers,
        json={"enabled": False},
    )
    assert response.status_code == 409

    invalid_default = client.put(
        "/api/v1/system/config",
        headers=admin_headers,
        json={"default_language": "rust"},
    )
    assert invalid_default.status_code == 400
