from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


def test_offline_result_sync_merges_duplicate_client_key(client: TestClient, auth_headers, store) -> None:
    payload = {
        "results": [
            {
                "problem_id": "P1003",
                "answers": {"choice": "B"},
                "practiced_at": "2026-05-25T00:00:00+00:00",
                "client_result_key": "local-result-1",
            }
        ]
    }

    first = client.post("/api/v1/offline-results/sync", headers=auth_headers("alice"), json=payload)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert len(first_body["synced"]) == 1
    assert first_body["merged"] == []
    assert first_body["rejected"] == []
    first_submission_id = first_body["synced"][0]["id"]
    assert first_body["synced"][0]["offline_result_key"] == "local-result-1"

    second = client.post("/api/v1/offline-results/sync", headers=auth_headers("alice"), json=payload)
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["synced"] == []
    assert len(second_body["merged"]) == 1
    assert second_body["merged"][0]["id"] == first_submission_id
    assert second_body["rejected"] == []

    submissions = [item for item in store.list_submissions() if item.offline_result_key == "local-result-1"]
    assert len(submissions) == 1


def test_offline_result_sync_rejects_conflicting_client_key(client: TestClient, auth_headers, store) -> None:
    headers = auth_headers("alice")
    accepted = client.post(
        "/api/v1/offline-results/sync",
        headers=headers,
        json={
            "results": [
                {
                    "problem_id": "P1003",
                    "answers": {"choice": "B"},
                    "practiced_at": "2026-05-25T00:00:00+00:00",
                    "client_result_key": "local-conflict-1",
                }
            ]
        },
    )
    assert accepted.status_code == 200, accepted.text

    conflict = client.post(
        "/api/v1/offline-results/sync",
        headers=headers,
        json={
            "results": [
                {
                    "problem_id": "P1003",
                    "answers": {"choice": "A"},
                    "practiced_at": "2026-05-25T00:01:00+00:00",
                    "client_result_key": "local-conflict-1",
                }
            ]
        },
    )
    assert conflict.status_code == 200, conflict.text
    body = conflict.json()
    assert body["synced"] == []
    assert body["merged"] == []
    assert len(body["rejected"]) == 1
    assert "冲突" in body["rejected"][0]["reason"]
    assert len([item for item in store.list_submissions() if item.offline_result_key == "local-conflict-1"]) == 1


def test_offline_result_sync_is_idempotent_for_legacy_files_without_key(client: TestClient, auth_headers, store) -> None:
    payload = {
        "results": [
            {
                "problem_id": "P1002",
                "answers": {"edge_formula": "n(n-1)/2"},
                "practiced_at": "2026-05-25T00:02:00+00:00",
            }
        ]
    }

    first = client.post("/api/v1/offline-results/sync", headers=auth_headers("alice"), json=payload)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert len(first_body["synced"]) == 1
    legacy_key = first_body["synced"][0]["offline_result_key"]
    assert legacy_key.startswith("legacy:")

    second = client.post("/api/v1/offline-results/sync", headers=auth_headers("alice"), json=payload)
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["synced"] == []
    assert len(second_body["merged"]) == 1
    assert second_body["merged"][0]["offline_result_key"] == legacy_key
    assert len([item for item in store.list_submissions() if item.offline_result_key == legacy_key]) == 1


def test_offline_result_sync_still_rejects_code_problem(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/api/v1/offline-results/sync",
        headers=auth_headers("alice"),
        json={
            "results": [
                {
                    "problem_id": "P1001",
                    "answers": {"choice": "B"},
                    "practiced_at": "2026-05-25T00:03:00+00:00",
                    "client_result_key": "code-must-not-sync",
                }
            ]
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["synced"] == []
    assert body["merged"] == []
    assert len(body["rejected"]) == 1
    assert "客观题" in body["rejected"][0]["reason"]


def test_offline_cli_result_key_is_stable_and_sync_payload_backfills_legacy_key(
    offline_cli_module,
    tmp_path: Path,
    monkeypatch,
) -> None:
    practiced_at = datetime(2026, 5, 25, tzinfo=timezone.utc).isoformat()
    answers = {"choices": ["C", "A"]}

    key = offline_cli_module.make_result_key("P1004", answers, practiced_at)
    assert key == offline_cli_module.make_result_key("P1004", {"choices": ["C", "A"]}, practiced_at)
    assert key.startswith("cli:")

    results_path = tmp_path / "offline-results.json"
    results_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "problem_id": "P1004",
                        "answers": answers,
                        "practiced_at": practiced_at,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}

    def fake_request_json(url: str, method: str = "GET", token: str | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        captured["url"] = url
        captured["method"] = method
        captured["token"] = token
        captured["body"] = body
        return {"synced": [], "merged": [{"id": "S1"}], "rejected": []}

    monkeypatch.setattr(offline_cli_module, "request_json", fake_request_json)

    offline_cli_module.cmd_sync_results(
        argparse.Namespace(results=str(results_path), api="http://example.test/api/v1", token="token-1")
    )

    item = captured["body"]["results"][0]
    assert item["client_result_key"] == key
    assert item["problem_id"] == "P1004"
    assert captured["method"] == "POST"
