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


def test_solution_category_like_and_bookmark_are_idempotent_and_redacted(client: TestClient, auth_headers, store) -> None:
    created = client.post(
        "/api/v1/discussions",
        headers=auth_headers("alice"),
        json={
            "type": "solution",
            "target_id": "P1001",
            "title": "Readable A+B solution",
            "content": "Read two integers and print the sum.",
            "solution_category": "tutorial",
        },
    )
    assert created.status_code == 200, created.text
    discussion = created.json()
    discussion_id = discussion["id"]
    assert discussion["solution_category"] == "tutorial"
    assert discussion["likes"] == 0
    assert discussion["liked"] is False
    assert discussion["bookmarked"] is False
    assert "liked_by" not in discussion
    assert "bookmarked_by" not in discussion

    first_like = client.put(f"/api/v1/discussions/{discussion_id}/like", headers=auth_headers("coach"))
    second_like = client.put(f"/api/v1/discussions/{discussion_id}/like", headers=auth_headers("coach"))
    bookmark = client.put(f"/api/v1/discussions/{discussion_id}/bookmark", headers=auth_headers("coach"))

    assert first_like.status_code == 200, first_like.text
    assert first_like.json()["changed"] is True
    assert first_like.json()["discussion"]["likes"] == 1
    assert first_like.json()["discussion"]["liked"] is True
    assert second_like.status_code == 200, second_like.text
    assert second_like.json()["changed"] is False
    assert second_like.json()["discussion"]["likes"] == 1
    assert bookmark.status_code == 200, bookmark.text
    assert bookmark.json()["discussion"]["bookmarked"] is True

    filtered = client.get(
        "/api/v1/discussions?type=solution&solution_category=tutorial",
        headers=auth_headers("coach"),
    )
    assert filtered.status_code == 200, filtered.text
    payload = filtered.json()
    assert any(item["id"] == discussion_id and item["liked"] and item["bookmarked"] for item in payload["items"])
    assert "liked_by" not in str(payload)
    assert "bookmarked_by" not in str(payload)

    unlike = client.delete(f"/api/v1/discussions/{discussion_id}/like", headers=auth_headers("coach"))
    unbookmark = client.delete(f"/api/v1/discussions/{discussion_id}/bookmark", headers=auth_headers("coach"))
    assert unlike.status_code == 200, unlike.text
    assert unlike.json()["changed"] is True
    assert unlike.json()["discussion"]["likes"] == 0
    assert unbookmark.status_code == 200, unbookmark.text
    assert unbookmark.json()["changed"] is True
    assert unbookmark.json()["discussion"]["bookmarked"] is False

    stored = store.get_discussion(discussion_id)
    assert stored is not None
    assert stored.liked_by == []
    assert stored.bookmarked_by == []


def test_solution_reactions_respect_visibility_and_type(client: TestClient, auth_headers, store) -> None:
    timestamp = now()
    hidden_problem = Problem(
        id="P-HIDDEN-SOLUTION",
        title="Hidden Solution Target",
        type="blank",
        difficulty="提高",
        tags=[],
        statement="Hidden",
        blanks=[{"key": "answer", "label": "answer", "score": 100}],
        author_id="u-coach",
        visible=False,
        judge_config={"answers": {"answer": ["hidden-answer"]}},
        created_at=timestamp,
    )
    hidden_solution = Discussion(
        id="D-HIDDEN-SOLUTION",
        type="solution",
        target_id=hidden_problem.id,
        title="Hidden solution",
        content="hidden-answer and judge_config should not leak",
        author_id="u-coach",
        author_name="Coach Lin",
        solution_category="analysis",
        created_at=timestamp,
        updated_at=timestamp,
    )
    general_discussion = Discussion(
        id="D-NOT-SOLUTION",
        type="general",
        title="General discussion",
        content="No reactions here.",
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
    data["discussions"].extend([hidden_solution.model_dump(mode="json"), general_discussion.model_dump(mode="json")])
    store._write(data)

    denied = client.put(f"/api/v1/discussions/{hidden_solution.id}/like", headers=auth_headers("alice"))
    assert denied.status_code == 404
    allowed = client.put(f"/api/v1/discussions/{hidden_solution.id}/like", headers=auth_headers("coach"))
    assert allowed.status_code == 200, allowed.text
    assert "hidden-answer" in allowed.json()["discussion"]["content"]
    serialized_public = str(client.get("/api/v1/discussions?type=solution").json())
    assert "Hidden solution" not in serialized_public
    assert "hidden-answer" not in serialized_public
    assert "judge_config" not in serialized_public

    wrong_type = client.put(f"/api/v1/discussions/{general_discussion.id}/like", headers=auth_headers("alice"))
    assert wrong_type.status_code == 400
    assert wrong_type.json()["detail"] == "Only solution posts support this action"


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
