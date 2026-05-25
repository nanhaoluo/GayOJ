from __future__ import annotations

from fastapi.testclient import TestClient


def sync_offline_result(
    client: TestClient,
    auth_headers,
    *,
    username: str = "alice",
    key: str = "review-result-1",
    answer: str = "B",
) -> dict:
    response = client.post(
        "/api/v1/offline-results/sync",
        headers=auth_headers(username),
        json={
            "results": [
                {
                    "problem_id": "P1003",
                    "answers": {"choice": answer},
                    "practiced_at": "2026-05-25T01:00:00+00:00",
                    "client_result_key": key,
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["synced"]) == 1
    return body["synced"][0]


def test_offline_sync_and_student_review_hide_expected_answers(client: TestClient, auth_headers) -> None:
    synced = sync_offline_result(client, auth_headers)

    assert synced["offline_result_key"] == "review-result-1"
    assert synced["details"][0]["received"] == "B"
    assert "expected" not in synced["details"][0]

    list_response = client.get("/api/v1/offline-results", headers=auth_headers("alice"))
    assert list_response.status_code == 200, list_response.text
    items = list_response.json()
    assert [item["id"] for item in items] == [synced["id"]]
    assert items[0]["expected_visible"] is False
    assert "expected" not in items[0]["details"][0]

    detail_response = client.get(
        f"/api/v1/offline-results/{synced['id']}?include_expected=true",
        headers=auth_headers("alice"),
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["expected_visible"] is False
    assert detail["answers"] == {"choice": "B"}
    assert "expected" not in detail["details"][0]


def test_authorized_reviewer_can_view_expected_answers_and_audit_review(
    client: TestClient,
    auth_headers,
    store,
) -> None:
    synced = sync_offline_result(client, auth_headers, key="review-result-2")

    response = client.get(
        "/api/v1/offline-results?user_id=u-student&include_expected=true",
        headers=auth_headers("coach"),
    )
    assert response.status_code == 200, response.text
    items = response.json()
    assert [item["id"] for item in items] == [synced["id"]]
    assert items[0]["expected_visible"] is True
    assert items[0]["details"][0]["expected"] == "B"

    detail_response = client.get(
        f"/api/v1/offline-results/{synced['id']}?include_expected=true",
        headers=auth_headers("coach"),
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["expected_visible"] is True
    assert detail["details"][0]["expected"] == "B"

    list_logs, _ = store.list_audit_logs(action="offline_results.review.list")
    detail_logs, _ = store.list_audit_logs(action="offline_results.review.detail")
    assert list_logs
    assert list_logs[0].metadata["include_expected"] is True
    assert list_logs[0].metadata["target_user_id"] == "u-student"
    assert detail_logs
    assert detail_logs[0].resource == f"submission:{synced['id']}"
    assert detail_logs[0].metadata["include_expected"] is True


def test_student_cannot_review_other_users_offline_results(client: TestClient, auth_headers, store) -> None:
    synced = sync_offline_result(client, auth_headers, key="review-result-3")
    coach = store.get_user_by_username("coach")
    assert coach is not None
    coach.username = "bob"
    coach.role = "student"
    store.update_user(coach)

    list_response = client.get("/api/v1/offline-results?user_id=u-student", headers=auth_headers("bob"))
    assert list_response.status_code == 403

    detail_response = client.get(f"/api/v1/offline-results/{synced['id']}", headers=auth_headers("bob"))
    assert detail_response.status_code == 403


def test_generic_submission_detail_hides_expected_for_owner_but_not_reviewer(
    client: TestClient,
    auth_headers,
) -> None:
    response = client.post(
        "/api/v1/problems/P1003/submit-objective",
        headers=auth_headers("alice"),
        json={"answers": {"choice": "B"}},
    )
    assert response.status_code == 200, response.text
    created = response.json()
    assert created["details"][0]["received"] == "B"
    assert "expected" not in created["details"][0]

    owner = client.get(f"/api/v1/submissions/{created['id']}", headers=auth_headers("alice"))
    assert owner.status_code == 200, owner.text
    assert "expected" not in owner.json()["details"][0]

    reviewer = client.get(f"/api/v1/submissions/{created['id']}", headers=auth_headers("coach"))
    assert reviewer.status_code == 200, reviewer.text
    assert reviewer.json()["details"][0]["expected"] == "B"
