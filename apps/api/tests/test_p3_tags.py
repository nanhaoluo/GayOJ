from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import SnapshotRepository, seed_data


def flatten_tag_names(nodes: list[dict[str, object]]) -> list[str]:
    names: list[str] = []
    for node in nodes:
        names.append(str(node["name"]))
        names.extend(flatten_tag_names(node.get("children", [])))  # type: ignore[arg-type]
    return names


def find_tag(nodes: list[dict[str, object]], name: str) -> dict[str, object]:
    for node in nodes:
        if node["name"] == name:
            return node
        found = find_tag(node.get("children", []), name) if node.get("children") else None  # type: ignore[arg-type]
        if found:
            return found
    raise AssertionError(f"missing tag: {name}")


def single_choice_payload(title: str, tags: list[str]) -> dict[str, object]:
    return {
        "title": title,
        "type": "single_choice",
        "difficulty": "基础",
        "tags": tags,
        "statement": "滑动窗口通常维护什么？",
        "options": [
            {"key": "A", "text": "一个可移动区间"},
            {"key": "B", "text": "固定递归栈"},
            {"key": "C", "text": "数据库连接"},
        ],
        "judge_config": {"answer": "A", "score": 100},
    }


def test_public_tag_tree_exposes_hierarchy_without_judge_config(client: TestClient) -> None:
    response = client.get("/api/v1/tags")
    assert response.status_code == 200, response.text
    tree = response.json()
    names = flatten_tag_names(tree)

    assert "算法" in names
    assert "基础算法" in names
    assert "二分" in names
    algorithm = find_tag(tree, "算法")
    assert any(child["name"] == "基础算法" for child in algorithm["children"])
    assert "judge_config" not in json.dumps(tree, ensure_ascii=False)


def test_problem_list_supports_multi_tag_filtering(client: TestClient) -> None:
    both = client.get("/api/v1/problems", params=[("tag", "组合数学"), ("tag", "图论")])
    assert both.status_code == 200, both.text
    assert [item["id"] for item in both.json()] == ["P1002"]

    repeated_tags = client.get("/api/v1/problems", params=[("tags", "组合数学"), ("tags", "图论")])
    assert repeated_tags.status_code == 200, repeated_tags.text
    assert [item["id"] for item in repeated_tags.json()] == ["P1002"]

    csv_tags = client.get("/api/v1/problems", params={"tags": "组合数学,二分"})
    assert csv_tags.status_code == 200, csv_tags.text
    assert csv_tags.json() == []


def test_tag_management_creates_hierarchy_and_updates_problem_tags(client: TestClient, auth_headers) -> None:
    public_tree = client.get("/api/v1/tags").json()
    parent = find_tag(public_tree, "基础算法")

    forbidden = client.post(
        "/api/v1/admin/tags",
        headers=auth_headers("alice"),
        json={"name": "滑动窗口", "parent_id": parent["id"], "sort_order": 50},
    )
    assert forbidden.status_code == 403

    created = client.post(
        "/api/v1/admin/tags",
        headers=auth_headers("coach"),
        json={"name": "滑动窗口", "parent_id": parent["id"], "sort_order": 50},
    )
    assert created.status_code == 200, created.text
    created_body = created.json()
    assert created_body["name"] == "滑动窗口"
    assert created_body["parent_id"] == parent["id"]

    duplicate = client.post(
        "/api/v1/admin/tags",
        headers=auth_headers("coach"),
        json={"name": "滑动窗口", "parent_id": parent["id"], "sort_order": 51},
    )
    assert duplicate.status_code == 409

    problem = client.post(
        "/api/v1/admin/problems",
        headers=auth_headers("coach"),
        json=single_choice_payload("滑动窗口基础", ["滑动窗口", "双指针"]),
    )
    assert problem.status_code == 200, problem.text
    problem_id = problem.json()["id"]

    filtered = client.get("/api/v1/problems", params=[("tag", "滑动窗口"), ("tag", "双指针")])
    assert filtered.status_code == 200, filtered.text
    assert [item["id"] for item in filtered.json()] == [problem_id]

    renamed = client.put(
        f"/api/v1/admin/tags/{created_body['id']}",
        headers=auth_headers("coach"),
        json={"name": "滑动窗口基础", "parent_id": parent["id"], "sort_order": 50},
    )
    assert renamed.status_code == 200, renamed.text

    detail = client.get(f"/api/v1/problems/{problem_id}")
    assert detail.status_code == 200
    assert "judge_config" not in detail.json()
    assert "滑动窗口基础" in detail.json()["tags"]
    assert "滑动窗口" not in detail.json()["tags"]

    delete_used = client.delete(f"/api/v1/admin/tags/{created_body['id']}", headers=auth_headers("coach"))
    assert delete_used.status_code == 409


def test_sqlite_repository_migrates_legacy_tag_shapes(tmp_path: Path) -> None:
    data = seed_data()
    data["tags"] = ["LegacyRoot"]
    data["problems"][0]["tags"] = ["LegacyRoot", "LegacyLeaf", "LegacyLeaf"]
    target = tmp_path / "legacy-tags.json"
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    repository = SnapshotRepository.sqlite(tmp_path / "legacy-tags.sqlite3", seed_path=target)
    names = [tag.name for tag in repository.list_tags()]
    after = json.loads(repository.database.read_payload())

    assert "算法" in names
    assert "LegacyRoot" in names
    assert "LegacyLeaf" in names
    assert all(isinstance(tag, dict) for tag in after["tags"])
    p1001 = next(problem for problem in after["problems"] if problem["id"] == "P1001")
    assert p1001["tags"] == ["LegacyRoot", "LegacyLeaf"]
