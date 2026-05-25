from __future__ import annotations

from fastapi.testclient import TestClient


def code_problem_payload(title: str = "P3 代码题") -> dict[str, object]:
    return {
        "title": title,
        "type": "code",
        "difficulty": "入门",
        "tags": ["P3", "代码"],
        "statement": "读取两个整数并输出和。",
        "input_format": "一行两个整数。",
        "output_format": "一个整数。",
        "samples": [{"input": "1 2", "output": "3"}],
        "time_limit_ms": 1000,
        "memory_limit_mb": 128,
        "judge_config": {"mode": "standard", "testdata_ref": "pending-online-worker"},
    }


def blank_problem_payload(title: str = "P3 填空题") -> dict[str, object]:
    return {
        "title": title,
        "type": "blank",
        "difficulty": "基础",
        "tags": ["P3", "填空"],
        "statement": "完全图 K_n 有多少条边？",
        "blanks": [{"key": "edge_formula", "label": "边数公式", "score": 100}],
        "judge_config": {
            "case_sensitive": False,
            "trim_space": True,
            "answers": {"edge_formula": ["n(n-1)/2", "n*(n-1)/2"]},
            "scores": {"edge_formula": 100},
        },
    }


def single_choice_payload(title: str = "P3 单选题") -> dict[str, object]:
    return {
        "title": title,
        "type": "single_choice",
        "difficulty": "基础",
        "tags": ["P3", "单选"],
        "statement": "二分查找的必要条件是什么？",
        "options": [
            {"key": "A", "text": "数据均为正数"},
            {"key": "B", "text": "搜索空间有序或单调"},
            {"key": "C", "text": "必须递归"},
            {"key": "D", "text": "必须 O(n)"},
        ],
        "judge_config": {"answer": "B", "score": 100},
    }


def multiple_choice_payload(title: str = "P3 多选题") -> dict[str, object]:
    return {
        "title": title,
        "type": "multiple_choice",
        "difficulty": "提高",
        "tags": ["P3", "多选"],
        "statement": "哪些属于代码评测沙箱安全策略？",
        "options": [
            {"key": "A", "text": "限制 CPU 时间"},
            {"key": "B", "text": "允许公网访问"},
            {"key": "C", "text": "禁用网络"},
            {"key": "D", "text": "直接在 API 进程执行用户代码"},
        ],
        "judge_config": {"answer": ["A", "C"], "score": 100},
    }


def test_admin_problem_crud_creates_all_problem_types_and_keeps_public_detail_safe(
    client: TestClient,
    auth_headers,
) -> None:
    payloads = [
        code_problem_payload(),
        blank_problem_payload(),
        single_choice_payload(),
        multiple_choice_payload(),
    ]

    assert client.get("/api/v1/admin/problems", headers=auth_headers("alice")).status_code == 403

    created = []
    for payload in payloads:
        response = client.post("/api/v1/admin/problems", headers=auth_headers("coach"), json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        created.append(body)
        assert body["type"] == payload["type"]
        assert body["author_id"] == "u-coach"
        assert body["visible"] is True
        assert "judge_config" in body

        public_detail = client.get(f"/api/v1/problems/{body['id']}", headers=auth_headers("coach"))
        assert public_detail.status_code == 200
        assert "judge_config" not in public_detail.json()

    code_problem = next(item for item in created if item["type"] == "code")
    submission = client.post(
        f"/api/v1/problems/{code_problem['id']}/submit-code",
        headers=auth_headers("alice"),
        json={"language": "python", "source_code": "print(1 + 2)\n"},
    )
    assert submission.status_code == 200, submission.text
    assert submission.json()["status"] == "queued"
    assert submission.json()["judged_at"] is None
    assert submission.json()["details"] == []


def test_problem_update_permissions_and_soft_delete(client: TestClient, auth_headers) -> None:
    created = client.post(
        "/api/v1/admin/problems",
        headers=auth_headers("judge"),
        json=blank_problem_payload("P3 仅裁判可编辑"),
    )
    assert created.status_code == 200, created.text
    problem_id = created.json()["id"]

    coach_update = client.put(
        f"/api/v1/admin/problems/{problem_id}",
        headers=auth_headers("coach"),
        json=single_choice_payload("越权编辑"),
    )
    assert coach_update.status_code == 403

    admin_detail = client.get(f"/api/v1/admin/problems/{problem_id}", headers=auth_headers("admin"))
    assert admin_detail.status_code == 200
    assert admin_detail.json()["judge_config"]["answers"]["edge_formula"]

    updated = client.put(
        f"/api/v1/admin/problems/{problem_id}",
        headers=auth_headers("admin"),
        json=single_choice_payload("P3 已更新为单选题"),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["type"] == "single_choice"
    assert updated.json()["judge_config"]["answer"] == "B"

    deleted = client.delete(f"/api/v1/admin/problems/{problem_id}", headers=auth_headers("admin"))
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["visible"] is False
    assert deleted.json()["judge_config"]["answer"] == "B"

    public_detail = client.get(f"/api/v1/problems/{problem_id}")
    assert public_detail.status_code == 404

    objective_submit = client.post(
        f"/api/v1/problems/{problem_id}/submit-objective",
        headers=auth_headers("alice"),
        json={"answers": {"choice": "B"}},
    )
    assert objective_submit.status_code == 404

    managed = client.get(f"/api/v1/admin/problems/{problem_id}", headers=auth_headers("admin"))
    assert managed.status_code == 200
    assert managed.json()["visible"] is False
    assert managed.json()["judge_config"]["answer"] == "B"

    republished = client.patch(
        f"/api/v1/admin/problems/{problem_id}/visibility",
        headers=auth_headers("admin"),
        json={"visible": True},
    )
    assert republished.status_code == 200, republished.text
    assert republished.json()["visible"] is True
    assert republished.json()["judge_config"]["answer"] == "B"

    public_after_republish = client.get(f"/api/v1/problems/{problem_id}")
    assert public_after_republish.status_code == 200
    assert "judge_config" not in public_after_republish.json()

    hidden = client.patch(
        f"/api/v1/admin/problems/{problem_id}/visibility",
        headers=auth_headers("admin"),
        json={"visible": False},
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["visible"] is False


def test_problem_updates_keep_version_history_and_support_restore(client: TestClient, auth_headers) -> None:
    created = client.post(
        "/api/v1/admin/problems",
        headers=auth_headers("coach"),
        json=single_choice_payload("P3 版本控制原始题"),
    )
    assert created.status_code == 200, created.text
    problem_id = created.json()["id"]

    changed_payload = single_choice_payload("P3 版本控制改动后")
    changed_payload["statement"] = "改动后的题面。"
    changed_payload["judge_config"] = {"answer": "C", "score": 100}
    updated = client.put(
        f"/api/v1/admin/problems/{problem_id}",
        headers=auth_headers("coach"),
        json=changed_payload,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "P3 版本控制改动后"
    assert updated.json()["judge_config"]["answer"] == "C"

    forbidden = client.get(f"/api/v1/admin/problems/{problem_id}/versions", headers=auth_headers("alice"))
    assert forbidden.status_code == 403

    versions = client.get(f"/api/v1/admin/problems/{problem_id}/versions", headers=auth_headers("coach"))
    assert versions.status_code == 200, versions.text
    history = versions.json()
    assert len(history) == 1
    assert history[0]["version"] == 1
    assert history[0]["action"] == "update"
    assert history[0]["snapshot"]["title"] == "P3 版本控制原始题"
    assert history[0]["snapshot"]["judge_config"]["answer"] == "B"

    public_detail = client.get(f"/api/v1/problems/{problem_id}")
    assert public_detail.status_code == 200
    assert "judge_config" not in public_detail.json()

    restored = client.post(
        f"/api/v1/admin/problems/{problem_id}/versions/{history[0]['id']}/restore",
        headers=auth_headers("coach"),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["title"] == "P3 版本控制原始题"
    assert restored.json()["judge_config"]["answer"] == "B"

    after_restore = client.get(f"/api/v1/admin/problems/{problem_id}/versions", headers=auth_headers("coach"))
    assert after_restore.status_code == 200
    restored_history = after_restore.json()
    assert len(restored_history) == 2
    assert restored_history[0]["action"] == "restore"
    assert restored_history[0]["snapshot"]["title"] == "P3 版本控制改动后"


def test_problem_form_validation_rejects_incomplete_objective_config(
    client: TestClient,
    auth_headers,
) -> None:
    invalid_blank = blank_problem_payload()
    invalid_blank["judge_config"] = {"answers": {}, "scores": {}}
    response = client.post("/api/v1/admin/problems", headers=auth_headers("coach"), json=invalid_blank)
    assert response.status_code == 422

    invalid_choice = single_choice_payload()
    invalid_choice["judge_config"] = {"answer": "Z", "score": 100}
    response = client.post("/api/v1/admin/problems", headers=auth_headers("coach"), json=invalid_choice)
    assert response.status_code == 422
