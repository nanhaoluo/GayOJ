from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.models import Submission, Team, User
from app.store import now


def test_coach_profiles_are_scoped_aggregated_and_redacted(
    client: TestClient,
    auth_headers,
    store,
) -> None:
    timestamp = now()
    password_hash = store.get_user("u-student").password_hash
    scoped_student = User(
        id="u-profile-1",
        username="profile1",
        display_name="Profile One",
        role="student",
        school="Scoped Class",
        email="profile1@example.com",
        password_hash=password_hash,
    )
    foreign_student = User(
        id="u-profile-2",
        username="profile2",
        display_name="Profile Two",
        role="student",
        school="Foreign Class",
        email="profile2@example.com",
        password_hash=password_hash,
    )
    foreign_coach = User(
        id="u-coach-foreign",
        username="coach_foreign",
        display_name="Foreign Coach",
        role="coach",
        school="Foreign Class",
        email="foreign@example.com",
        password_hash=password_hash,
    )
    scoped_team = Team(
        id="T-PROFILE-1",
        name="Profile Class",
        description="Coach-owned class",
        invite_code="PROFILE1",
        owner_id="u-coach",
        member_ids=[scoped_student.id],
        created_at=timestamp,
    )
    foreign_team = Team(
        id="T-PROFILE-2",
        name="Foreign Class",
        description="Foreign coach class",
        invite_code="PROFILE2",
        owner_id=foreign_coach.id,
        member_ids=[foreign_student.id],
        created_at=timestamp,
    )
    scoped_submissions = [
        Submission(
            id="S-PROFILE-1",
            user_id=scoped_student.id,
            problem_id="P1002",
            problem_title="blank",
            problem_type="blank",
            answers={"edge_formula": "n(n-1)/2"},
            status="accepted",
            score=100,
            max_score=100,
            details=[{"key": "edge_formula", "expected": "n(n-1)/2", "received": "n(n-1)/2", "score": 100}],
            message="ok",
            created_at=timestamp - timedelta(days=1),
            judged_at=timestamp - timedelta(days=1),
        ),
        Submission(
            id="S-PROFILE-2",
            user_id=scoped_student.id,
            problem_id="P1003",
            problem_title="choice",
            problem_type="single_choice",
            answers={"choice": "A"},
            status="wrong_answer",
            score=0,
            max_score=100,
            details=[{"key": "choice", "expected": "B", "received": "A", "score": 0}],
            message="wrong",
            created_at=timestamp,
            judged_at=timestamp,
        ),
        Submission(
            id="S-PROFILE-3",
            user_id=scoped_student.id,
            problem_id="P1001",
            problem_title="code",
            problem_type="code",
            language="cpp",
            source_code="int main(){return 0;}",
            status="accepted",
            score=100,
            max_score=100,
            details=[],
            message="accepted",
            created_at=timestamp,
            judged_at=timestamp,
        ),
    ]
    foreign_submission = Submission(
        id="S-PROFILE-4",
        user_id=foreign_student.id,
        problem_id="P1004",
        problem_title="foreign",
        problem_type="multiple_choice",
        answers={"choices": ["A", "C"]},
        status="accepted",
        score=100,
        max_score=100,
        details=[{"key": "choices", "expected": ["A", "C"], "received": ["A", "C"], "score": 100}],
        message="ok",
        created_at=timestamp,
        judged_at=timestamp,
    )
    data = store._read()
    data["users"].extend(
        [
            scoped_student.model_dump(mode="json"),
            foreign_student.model_dump(mode="json"),
            foreign_coach.model_dump(mode="json"),
        ]
    )
    data["teams"].extend([scoped_team.model_dump(mode="json"), foreign_team.model_dump(mode="json")])
    data["submissions"].extend([submission.model_dump(mode="json") for submission in scoped_submissions + [foreign_submission]])
    store._write(data)

    response = client.get("/api/v1/coach/analytics", headers=auth_headers("coach"))

    assert response.status_code == 200, response.text
    payload = response.json()
    profile = next(item for item in payload["student_profiles"] if item["user_id"] == scoped_student.id)
    assert profile["attempts"] == 3
    assert profile["accepted"] == 2
    assert profile["solved"] == 2
    assert len(profile["tag_mastery"]) >= 4
    assert max(item["attempts"] for item in profile["tag_mastery"]) >= 1
    assert any(item["problem_type"] == "code" and item["solved"] == 1 for item in profile["type_mastery"])
    assert len(profile["heatmap"]) == 2
    assert {item["user_id"] for item in payload["student_profiles"]} >= {"u-student", scoped_student.id}
    assert foreign_student.id not in {item["user_id"] for item in payload["student_profiles"]}
    serialized = str(payload)
    assert "source_code" not in serialized
    assert "int main" not in serialized
    assert "judge_config" not in serialized
    assert "expected" not in serialized
    assert "choices" not in serialized


def test_coach_profiles_require_coach_analytics_permission(client: TestClient, auth_headers) -> None:
    assert client.get("/api/v1/coach/analytics").status_code == 401

    response = client.get("/api/v1/coach/analytics", headers=auth_headers("alice"))

    assert response.status_code == 403
