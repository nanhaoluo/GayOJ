from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.models import Contest, Discussion, Notification, Problem
from app.store import now


def test_discussions_are_paginated_searchable_and_scoped(client: TestClient, auth_headers, store) -> None:
    timestamp = now()
    hidden_problem = Problem(
        id="P-HIDDEN-DISCUSS",
        title="Hidden Objective Answer",
        type="blank",
        difficulty="提高",
        tags=["hidden"],
        statement="Private problem statement",
        blanks=[{"key": "secret_blank", "label": "secret", "score": 100}],
        author_id="u-coach",
        visible=False,
        judge_config={"answers": {"secret_blank": ["secret-answer"]}},
        created_at=timestamp,
    )
    private_contest = Contest(
        id="C-HIDDEN-DISCUSS",
        title="Private Contest",
        rule="ACM",
        start_at=timestamp - timedelta(hours=1),
        end_at=timestamp + timedelta(hours=1),
        problem_ids=["P1001"],
        status="running",
        visibility="private",
    )
    hidden_discussion = Discussion(
        id="D-HIDDEN",
        type="problem",
        target_id=hidden_problem.id,
        title="Hidden Discussion",
        content="secret-answer and judge_config should not leak",
        author_id="u-coach",
        author_name="Coach Lin",
        created_at=timestamp,
        updated_at=timestamp,
    )
    private_contest_discussion = Discussion(
        id="D-HIDDEN-CONTEST",
        type="contest",
        target_id=private_contest.id,
        title="Private Contest Discussion",
        content="private contest ops",
        author_id="u-admin",
        author_name="Admin",
        created_at=timestamp,
        updated_at=timestamp,
    )
    searchable = Discussion(
        id="D-SEARCH-1",
        type="general",
        title="Binary Search Practice",
        content="Discuss monotonic predicate.",
        author_id="u-student",
        author_name="Alice Chen",
        created_at=timestamp,
        updated_at=timestamp,
    )
    data = store._read()
    problem_item = hidden_problem.model_dump(mode="json")
    judge_config = problem_item.pop("judge_config")
    data["problems"].append(problem_item)
    data.setdefault("problem_judge_config", {})[hidden_problem.id] = judge_config
    data["contests"].append(private_contest.model_dump(mode="json"))
    data["discussions"].extend(
        [
            hidden_discussion.model_dump(mode="json"),
            private_contest_discussion.model_dump(mode="json"),
            searchable.model_dump(mode="json"),
        ]
    )
    store._write(data)

    response = client.get("/api/v1/discussions?q=binary&limit=1&offset=0")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 1
    assert payload["items"][0]["id"] == searchable.id
    serialized = str(client.get("/api/v1/discussions").json())
    assert "Hidden Discussion" not in serialized
    assert "Private Contest Discussion" not in serialized
    assert "secret-answer" not in serialized
    assert "judge_config" not in serialized
    assert client.get(f"/api/v1/discussions/{hidden_discussion.id}").status_code == 404

    coach_detail = client.get(f"/api/v1/discussions/{hidden_discussion.id}", headers=auth_headers("coach"))
    assert coach_detail.status_code == 200, coach_detail.text


def test_discussion_create_and_reply_validate_target_visibility(client: TestClient, auth_headers, store) -> None:
    hidden_problem = Problem(
        id="P-HIDDEN-CREATE",
        title="Private Create Target",
        type="blank",
        difficulty="提高",
        tags=[],
        statement="Hidden",
        blanks=[{"key": "answer", "label": "answer", "score": 100}],
        author_id="u-coach",
        visible=False,
        judge_config={"answers": {"answer": ["hidden"]}},
        created_at=now(),
    )
    data = store._read()
    problem_item = hidden_problem.model_dump(mode="json")
    judge_config = problem_item.pop("judge_config")
    data["problems"].append(problem_item)
    data.setdefault("problem_judge_config", {})[hidden_problem.id] = judge_config
    store._write(data)

    denied = client.post(
        "/api/v1/discussions",
        headers=auth_headers("alice"),
        json={"type": "problem", "target_id": hidden_problem.id, "title": "Denied", "content": "Hidden"},
    )
    assert denied.status_code == 403

    created = client.post(
        "/api/v1/discussions",
        headers=auth_headers("coach"),
        json={"type": "problem", "target_id": hidden_problem.id, "title": "Coach Note", "content": "Private note"},
    )
    assert created.status_code == 200, created.text
    discussion_id = created.json()["id"]

    reply = client.post(
        f"/api/v1/discussions/{discussion_id}/replies",
        headers=auth_headers("alice"),
        json={"content": "I should not see this"},
    )
    assert reply.status_code == 404


def test_notification_stream_is_user_scoped_and_redacted(client: TestClient, auth_headers, store) -> None:
    timestamp = now()
    data = store._read()
    data["notifications"].extend(
        [
            Notification(
                id="N-P8-ALICE",
                user_id="u-student",
                title="评测完成",
                content="source_code=int main(); expected=42 judge_config answers",
                type="judge",
                created_at=timestamp,
            ).model_dump(mode="json"),
            Notification(
                id="N-P8-COACH",
                user_id="u-coach",
                title="教练私有通知",
                content="coach-only content",
                type="system",
                created_at=timestamp,
            ).model_dump(mode="json"),
        ]
    )
    store._write(data)
    login = client.post("/api/v1/auth/login", json={"username": "alice", "password": "gayoj123"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    response = client.get(f"/api/v1/notifications/stream?token={token}", headers={"accept": "text/event-stream"})

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "N-P8-ALICE" in body
    assert "评测完成" in body
    assert "N-P8-COACH" not in body
    assert "coach-only" not in body
    assert "source_code" not in body
    assert "expected" not in body
    assert "judge_config" not in body
    assert "answers" not in body


def test_notification_stream_requires_valid_token(client: TestClient) -> None:
    response = client.get("/api/v1/notifications/stream?token=bad-token")

    assert response.status_code == 401
