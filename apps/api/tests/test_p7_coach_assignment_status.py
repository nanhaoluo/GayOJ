from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.models import Assignment, Submission, Team, User
from app.store import now


def test_coach_analytics_only_exposes_owned_teams_and_assignments(
    client: TestClient,
    auth_headers,
    store,
) -> None:
    student = User(
        id="u-student-2",
        username="bob",
        display_name="Bob Li",
        role="student",
        school="Team Bob",
        email="bob@example.com",
        password_hash=store.get_user("u-student").password_hash,
    )
    other_coach = User(
        id="u-coach-2",
        username="coach2",
        display_name="Coach Zhao",
        role="coach",
        school="Other Team",
        email="coach2@example.com",
        password_hash=store.get_user("u-coach").password_hash,
    )
    store._write(
        {
            **store._read(),
            "users": store._read()["users"]
            + [student.model_dump(mode="json"), other_coach.model_dump(mode="json")],
            "teams": store._read()["teams"]
            + [
                Team(
                    id="T2001",
                    name="Other Team",
                    description="Should stay hidden",
                    invite_code="OTHER2001",
                    owner_id="u-coach-2",
                    member_ids=["u-student-2"],
                    created_at=now(),
                ).model_dump(mode="json")
            ],
            "assignments": store._read()["assignments"]
            + [
                Assignment(
                    id="A2001",
                    title="Other Coach Assignment",
                    description="Hidden assignment",
                    problem_set_id="PS1002",
                    team_id="T2001",
                    due_at=now() + timedelta(days=3),
                    created_by="u-coach-2",
                    created_at=now(),
                ).model_dump(mode="json")
            ],
        }
    )

    response = client.get("/api/v1/coach/analytics", headers=auth_headers("coach"))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert {team["id"] for team in payload["teams"]} == {"T1001"}
    assert {assignment["id"] for assignment in payload["assignments"]} == {"A1001"}
    assert payload["class_size"] == 1
    serialized = str(payload)
    assert "u-coach-2" not in serialized
    assert "u-student-2" not in serialized
    assert "source_code" not in serialized
    assert "judge_config" not in serialized


def test_coach_assignment_states_cover_not_started_in_progress_overdue_completed(
    client: TestClient,
    auth_headers,
    store,
) -> None:
    password_hash = store.get_user("u-student").password_hash
    t0 = now()
    students = [
        User(
            id="u-s1",
            username="s1",
            display_name="Student One",
            role="student",
            school="Class 1",
            email="s1@example.com",
            password_hash=password_hash,
        ),
        User(
            id="u-s2",
            username="s2",
            display_name="Student Two",
            role="student",
            school="Class 1",
            email="s2@example.com",
            password_hash=password_hash,
        ),
        User(
            id="u-s3",
            username="s3",
            display_name="Student Three",
            role="student",
            school="Class 1",
            email="s3@example.com",
            password_hash=password_hash,
        ),
        User(
            id="u-s4",
            username="s4",
            display_name="Student Four",
            role="student",
            school="Class 1",
            email="s4@example.com",
            password_hash=password_hash,
        ),
    ]
    team = Team(
        id="T2002",
        name="Coach Scope Team",
        description="State coverage team",
        invite_code="STATE202",
        owner_id="u-coach",
        member_ids=[student.id for student in students],
        created_at=t0,
    )
    assignment = Assignment(
        id="A2002",
        title="State Coverage Assignment",
        description="Covers all coach-visible states",
        problem_set_id="PS1001",
        team_id=team.id,
        due_at=t0 - timedelta(hours=2),
        created_by="u-coach",
        created_at=t0,
    )
    submissions = [
        Submission(
            id="S2001",
            user_id="u-s2",
            problem_id="P1002",
            problem_title="P1002",
            problem_type="blank",
            answers={"edge_formula": "n(n-1)/2"},
            status="accepted",
            score=100,
            max_score=100,
            details=[],
            message="ok",
            created_at=t0 - timedelta(hours=3),
            judged_at=t0 - timedelta(hours=3),
        ),
        Submission(
            id="S2002",
            user_id="u-s3",
            problem_id="P1002",
            problem_title="P1002",
            problem_type="blank",
            answers={"edge_formula": "n(n-1)/2"},
            status="accepted",
            score=100,
            max_score=100,
            details=[],
            message="ok",
            created_at=t0 - timedelta(days=1),
            judged_at=t0 - timedelta(days=1),
        ),
        Submission(
            id="S2003",
            user_id="u-s3",
            problem_id="P1003",
            problem_title="P1003",
            problem_type="single_choice",
            answers={"choice": "B"},
            status="accepted",
            score=100,
            max_score=100,
            details=[],
            message="ok",
            created_at=t0 - timedelta(days=1),
            judged_at=t0 - timedelta(days=1),
        ),
        Submission(
            id="S2004",
            user_id="u-s3",
            problem_id="P1001",
            problem_title="P1001",
            problem_type="code",
            language="cpp",
            source_code="int main(){}",
            status="accepted",
            score=100,
            max_score=100,
            details=[],
            message="queued",
            created_at=t0 - timedelta(days=1),
            judged_at=t0 - timedelta(days=1),
        ),
        Submission(
            id="S2005",
            user_id="u-s4",
            problem_id="P1002",
            problem_title="P1002",
            problem_type="blank",
            answers={"edge_formula": "n(n-1)/2"},
            status="accepted",
            score=100,
            max_score=100,
            details=[],
            message="ok",
            created_at=t0 - timedelta(hours=1),
            judged_at=t0 - timedelta(hours=1),
        ),
    ]
    data = store._read()
    data["users"].extend([student.model_dump(mode="json") for student in students])
    data["teams"].append(team.model_dump(mode="json"))
    data["assignments"].append(assignment.model_dump(mode="json"))
    data["submissions"].extend([submission.model_dump(mode="json") for submission in submissions])
    store._write(data)

    response = client.get("/api/v1/coach/analytics", headers=auth_headers("coach"))

    assert response.status_code == 200, response.text
    payload = response.json()
    assignment_payload = next(item for item in payload["assignments"] if item["id"] == "A2002")
    assert assignment_payload["status"] == "overdue"
    assert assignment_payload["student_count"] == 4
    assert assignment_payload["completed_count"] == 1
    assert assignment_payload["problem_count"] == 3
    assert assignment_payload["state_counts"] == {
        "not_started": 0,
        "in_progress": 0,
        "overdue": 3,
        "completed": 1,
    }
    states = {item["user_id"]: item["status"] for item in assignment_payload["students"]}
    assert states == {
        "u-s1": "overdue",
        "u-s2": "overdue",
        "u-s3": "completed",
        "u-s4": "overdue",
    }
    student_three = next(item for item in assignment_payload["students"] if item["user_id"] == "u-s3")
    assert student_three["completion"] == 1
    assert student_three["solved_count"] == 3
    assert "source_code" not in str(student_three)


def test_coach_can_create_assignment_only_for_owned_team(client: TestClient, auth_headers, store) -> None:
    password_hash = store.get_user("u-student").password_hash
    data = store._read()
    data["users"].append(
        User(
            id="u-coach-2",
            username="coach2",
            display_name="Coach Zhao",
            role="coach",
            school="Other Team",
            email="coach2@example.com",
            password_hash=password_hash,
        ).model_dump(mode="json")
    )
    data["teams"].append(
        Team(
            id="T3001",
            name="Other Coach Team",
            description="Forbidden target",
            invite_code="FORBID01",
            owner_id="u-coach-2",
            member_ids=["u-student"],
            created_at=now(),
        ).model_dump(mode="json")
    )
    store._write(data)

    response = client.post(
        "/api/v1/assignments",
        headers=auth_headers("coach"),
        json={
            "title": "Blocked Assignment",
            "description": "Should be rejected",
            "problem_set_id": "PS1001",
            "team_id": "T3001",
            "due_at": (now() + timedelta(days=1)).isoformat(),
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"
