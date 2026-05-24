from __future__ import annotations

import json

from fastapi.testclient import TestClient


def hydro_import_package() -> str:
    return json.dumps(
        {
            "format": "hydro",
            "problems": [
                {
                    "pid": "HYDRO_IMPORT_CODE",
                    "title": "Hydro 导入代码题",
                    "type": "code",
                    "difficulty": "入门",
                    "tags": ["P3", "Hydro"],
                    "content": "读取两个整数并输出和。",
                    "input": "一行两个整数。",
                    "output": "一个整数。",
                    "samples": [{"input": "1 2", "output": "3"}],
                    "limits": {"time_ms": 1000, "memory_mb": 128},
                    "judge": {"mode": "standard", "testdata_ref": "online-worker-only"},
                },
                {
                    "pid": "HYDRO_IMPORT_BLANK",
                    "title": "Hydro 导入填空题",
                    "type": "blank",
                    "difficulty": "基础",
                    "tags": ["P3", "Hydro"],
                    "content": "完全图 K_n 有多少条边？",
                    "blanks": [{"key": "edge_formula", "label": "边数公式", "score": 100}],
                    "judge": {
                        "case_sensitive": False,
                        "trim_space": True,
                        "answers": {"edge_formula": ["n(n-1)/2"]},
                        "scores": {"edge_formula": 100},
                    },
                },
            ],
        },
        ensure_ascii=False,
    )


def qdu_invalid_batch() -> str:
    return json.dumps(
        {
            "format": "qdu",
            "problems": [
                {
                    "_id": "QDU_IMPORT_VALID",
                    "title": "QDU 导入单选题",
                    "problem_type": "single_choice",
                    "difficulty": "基础",
                    "tags": ["P3", "QDU"],
                    "description": "哪项是二分查找条件？",
                    "options": [{"key": "A", "text": "单调"}, {"key": "B", "text": "随机"}],
                    "judge_config": {"answer": "A", "score": 100},
                },
                {
                    "_id": "QDU_IMPORT_INVALID",
                    "title": "QDU 无效填空题",
                    "problem_type": "blank",
                    "difficulty": "基础",
                    "description": "缺少答案配置。",
                    "blanks": [{"key": "answer", "label": "答案", "score": 100}],
                    "judge_config": {},
                },
            ],
        },
        ensure_ascii=False,
    )


def hydro_overwrite_package(problem_id: str, invalid: bool = False) -> str:
    return json.dumps(
        {
            "format": "hydro",
            "problems": [
                {
                    "pid": problem_id,
                    "title": "Hydro 覆盖导入题",
                    "type": "single_choice",
                    "difficulty": "基础",
                    "tags": ["P3", "Hydro"],
                    "content": "覆盖导入后的题面。",
                    "options": [{"key": "A", "text": "单调"}, {"key": "B", "text": "随机"}],
                    "judge": {"answer": "A" if not invalid else "Z", "score": 100},
                }
            ],
        },
        ensure_ascii=False,
    )


def test_admin_problem_export_requires_permission_and_keeps_public_detail_safe(
    client: TestClient,
    auth_headers,
) -> None:
    assert client.get("/api/v1/admin/problems/export?format=qdu&ids=P1002", headers=auth_headers("alice")).status_code == 403

    exported = client.get("/api/v1/admin/problems/export?format=qdu&ids=P1002", headers=auth_headers("admin"))
    assert exported.status_code == 200, exported.text
    body = exported.json()
    assert body["format"] == "qdu"
    assert body["problem_count"] == 1
    assert body["problem_ids"] == ["P1002"]

    package = json.loads(body["content"])
    assert package["problems"][0]["_id"] == "P1002"
    assert package["problems"][0]["judge_config"]["answers"]["edge_formula"]

    public_detail = client.get("/api/v1/problems/P1002", headers=auth_headers("admin"))
    assert public_detail.status_code == 200
    assert "judge_config" not in public_detail.json()


def test_hydro_import_creates_batch_and_code_submission_stays_queued(
    client: TestClient,
    auth_headers,
) -> None:
    response = client.post(
        "/api/v1/admin/problems/import",
        headers=auth_headers("admin"),
        json={"format": "hydro", "content": hydro_import_package(), "conflict_strategy": "create_new"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 2
    assert body["updated"] == 0
    targets = {item["source_id"]: item["target_id"] for item in body["items"]}

    blank_detail = client.get(f"/api/v1/admin/problems/{targets['HYDRO_IMPORT_BLANK']}", headers=auth_headers("admin"))
    assert blank_detail.status_code == 200, blank_detail.text
    assert blank_detail.json()["judge_config"]["answers"]["edge_formula"] == ["n(n-1)/2"]

    public_blank = client.get(f"/api/v1/problems/{targets['HYDRO_IMPORT_BLANK']}")
    assert public_blank.status_code == 200
    assert "judge_config" not in public_blank.json()

    code_submission = client.post(
        f"/api/v1/problems/{targets['HYDRO_IMPORT_CODE']}/submit-code",
        headers=auth_headers("alice"),
        json={"language": "python", "source_code": "print(1 + 2)\n"},
    )
    assert code_submission.status_code == 200, code_submission.text
    assert code_submission.json()["status"] == "queued"
    assert code_submission.json()["judged_at"] is None
    assert code_submission.json()["details"] == []


def test_invalid_batch_import_rolls_back_without_partial_problem(
    client: TestClient,
    auth_headers,
) -> None:
    before = client.get("/api/v1/admin/problems", headers=auth_headers("admin"))
    assert before.status_code == 200
    before_count = len(before.json())

    response = client.post(
        "/api/v1/admin/problems/import",
        headers=auth_headers("admin"),
        json={"format": "qdu", "content": qdu_invalid_batch(), "conflict_strategy": "create_new"},
    )
    assert response.status_code == 422

    after = client.get("/api/v1/admin/problems", headers=auth_headers("admin"))
    assert after.status_code == 200
    assert len(after.json()) == before_count
    assert client.get("/api/v1/problems/QDU_IMPORT_VALID").status_code == 404


def test_overwrite_import_archives_previous_version_atomically(
    client: TestClient,
    auth_headers,
) -> None:
    dry_run = client.post(
        "/api/v1/admin/problems/import",
        headers=auth_headers("admin"),
        json={
            "format": "hydro",
            "content": hydro_overwrite_package("P1003"),
            "conflict_strategy": "overwrite",
            "dry_run": True,
        },
    )
    assert dry_run.status_code == 200, dry_run.text
    assert dry_run.json()["updated"] == 1

    before_versions = client.get("/api/v1/admin/problems/P1003/versions", headers=auth_headers("admin"))
    assert before_versions.status_code == 200
    before_count = len(before_versions.json())

    overwritten = client.post(
        "/api/v1/admin/problems/import",
        headers=auth_headers("admin"),
        json={"format": "hydro", "content": hydro_overwrite_package("P1003"), "conflict_strategy": "overwrite"},
    )
    assert overwritten.status_code == 200, overwritten.text
    assert overwritten.json()["updated"] == 1

    detail = client.get("/api/v1/admin/problems/P1003", headers=auth_headers("admin"))
    assert detail.status_code == 200
    assert detail.json()["title"] == "Hydro 覆盖导入题"
    assert detail.json()["judge_config"]["answer"] == "A"

    after_versions = client.get("/api/v1/admin/problems/P1003/versions", headers=auth_headers("admin"))
    assert after_versions.status_code == 200
    history = after_versions.json()
    assert len(history) == before_count + 1
    assert history[0]["snapshot"]["title"] == "二分查找适用条件"

    invalid = client.post(
        "/api/v1/admin/problems/import",
        headers=auth_headers("admin"),
        json={"format": "hydro", "content": hydro_overwrite_package("P1003", invalid=True), "conflict_strategy": "overwrite"},
    )
    assert invalid.status_code == 422
    failed_versions = client.get("/api/v1/admin/problems/P1003/versions", headers=auth_headers("admin"))
    assert failed_versions.status_code == 200
    assert len(failed_versions.json()) == before_count + 1


def test_fps_export_roundtrips_as_new_problem(
    client: TestClient,
    auth_headers,
) -> None:
    exported = client.get("/api/v1/admin/problems/export?format=fps&ids=P1003", headers=auth_headers("admin"))
    assert exported.status_code == 200, exported.text
    body = exported.json()
    assert body["content_type"] == "application/xml"
    assert "<fps" in body["content"]
    assert "<judge_config>" in body["content"]

    imported = client.post(
        "/api/v1/admin/problems/import",
        headers=auth_headers("admin"),
        json={"format": "fps", "content": body["content"], "conflict_strategy": "create_new"},
    )
    assert imported.status_code == 200, imported.text
    result = imported.json()
    assert result["created"] == 1
    target_id = result["items"][0]["target_id"]
    assert target_id != "P1003"

    admin_detail = client.get(f"/api/v1/admin/problems/{target_id}", headers=auth_headers("admin"))
    assert admin_detail.status_code == 200
    assert admin_detail.json()["type"] == "single_choice"
    assert admin_detail.json()["judge_config"]["answer"] == "B"

    public_detail = client.get(f"/api/v1/problems/{target_id}")
    assert public_detail.status_code == 200
    assert "judge_config" not in public_detail.json()
