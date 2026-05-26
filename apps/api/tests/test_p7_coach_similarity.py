from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.models import Assignment, Contest, ProblemSet, Submission, Team, User
from app.store import now


def _code_submission(
    *,
    submission_id: str,
    user_id: str,
    problem_id: str = "P1001",
    contest_id: str | None = None,
    source_code: str,
):
    return Submission(
        id=submission_id,
        user_id=user_id,
        problem_id=problem_id,
        problem_title=problem_id,
        problem_type="code",
        contest_id=contest_id,
        language="python",
        source_code=source_code,
        status="accepted",
        score=100,
        max_score=100,
        details=[],
        message="ok",
        created_at=now(),
        judged_at=now(),
    )


def test_coach_similarity_is_scoped_and_redacted(client: TestClient, auth_headers, store) -> None:
    timestamp = now()
    password_hash = store.get_user("u-student").password_hash
    scoped_student = User(
        id="u-sim-1",
        username="sim1",
        display_name="Sim One",
        role="student",
        school="Scoped Class",
        email="sim1@example.com",
        password_hash=password_hash,
    )
    foreign_student = User(
        id="u-sim-foreign",
        username="sim_foreign",
        display_name="Foreign Student",
        role="student",
        school="Foreign Class",
        email="foreign-student@example.com",
        password_hash=password_hash,
    )
    foreign_coach = User(
        id="u-sim-coach",
        username="sim_coach",
        display_name="Foreign Coach",
        role="coach",
        school="Foreign Class",
        email="foreign-coach@example.com",
        password_hash=password_hash,
    )
    scoped_team = Team(
        id="T-SIM-1",
        name="Similarity Class",
        description="Coach owned class",
        invite_code="SIM10001",
        owner_id="u-coach",
        member_ids=["u-student", scoped_student.id],
        created_at=timestamp,
    )
    foreign_team = Team(
        id="T-SIM-2",
        name="Foreign Similarity",
        description="Hidden class",
        invite_code="SIM20002",
        owner_id=foreign_coach.id,
        member_ids=[foreign_student.id],
        created_at=timestamp,
    )
    matching_source = "n = int(input())\nprint(n + 1)\n"
    variant_source = "value = int(input())\nprint(value + 1)\n"
    foreign_source = "n = int(input())\nprint(n + 1)\n# foreign source must stay hidden\n"
    objective_submission = Submission(
        id="S-SIM-OBJ",
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
    data["submissions"].extend(
        [
            _code_submission(submission_id="S-SIM-1", user_id="u-student", source_code=matching_source).model_dump(mode="json"),
            _code_submission(submission_id="S-SIM-2", user_id=scoped_student.id, source_code=variant_source).model_dump(mode="json"),
            _code_submission(submission_id="S-SIM-3", user_id=foreign_student.id, source_code=foreign_source).model_dump(mode="json"),
            objective_submission.model_dump(mode="json"),
        ]
    )
    store._write(data)

    response = client.get("/api/v1/coach/similarity?threshold=0.5", headers=auth_headers("coach"))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["findings"]
    finding = payload["findings"][0]
    assert finding["problem_id"] == "P1001"
    assert {finding["student_a"]["user_id"], finding["student_b"]["user_id"]} == {"u-student", scoped_student.id}
    assert finding["similarity"] >= 0.5
    serialized = str(payload)
    assert "source_code" not in serialized
    assert "print(n + 1)" not in serialized
    assert "foreign source" not in serialized
    assert "judge_config" not in serialized
    assert "expected" not in serialized
    assert "edge_formula" not in serialized


def test_coach_similarity_supports_problem_and_contest_filters(client: TestClient, auth_headers, store) -> None:
    timestamp = now()
    password_hash = store.get_user("u-student").password_hash
    other_student = User(
        id="u-sim-filter",
        username="sim_filter",
        display_name="Filter Student",
        role="student",
        school="Scoped Class",
        email="sim-filter@example.com",
        password_hash=password_hash,
    )
    team = Team(
        id="T-SIM-FILTER",
        name="Filter Class",
        description="Coach owned class",
        invite_code="SIMFILT1",
        owner_id="u-coach",
        member_ids=["u-student", other_student.id],
        created_at=timestamp,
    )
    contest = Contest(
        id="C-SIM-1",
        title="Similarity Round",
        rule="ACM",
        start_at=timestamp - timedelta(hours=1),
        end_at=timestamp + timedelta(hours=1),
        problem_ids=["P1001"],
        status="running",
        visibility="public",
    )
    data = store._read()
    data["users"].append(other_student.model_dump(mode="json"))
    data["teams"].append(team.model_dump(mode="json"))
    data["contests"].append(contest.model_dump(mode="json"))
    data["submissions"].extend(
        [
            _code_submission(
                submission_id="S-SIM-F1",
                user_id="u-student",
                contest_id=contest.id,
                source_code="x = int(input())\nprint(x * 2)\n",
            ).model_dump(mode="json"),
            _code_submission(
                submission_id="S-SIM-F2",
                user_id=other_student.id,
                contest_id=contest.id,
                source_code="num = int(input())\nprint(num * 2)\n",
            ).model_dump(mode="json"),
        ]
    )
    store._write(data)

    response = client.get(
        f"/api/v1/coach/similarity?problem_id=P1001&contest_id={contest.id}&threshold=0.5",
        headers=auth_headers("coach"),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["problem_id"] == "P1001"
    assert payload["contest_id"] == contest.id
    assert payload["findings"]
    assert payload["findings"][0]["contest_title"] == "Similarity Round"
    assert any(item["id"] == "P1001" for item in payload["problems"])
    assert any(item["id"] == contest.id for item in payload["contests"])


def test_coach_similarity_rejects_out_of_scope_filters(client: TestClient, auth_headers, store) -> None:
    response = client.get("/api/v1/coach/similarity?problem_id=P1004", headers=auth_headers("coach"))

    assert response.status_code == 403
    assert response.json()["detail"] == "Problem is outside coach scope"


def test_coach_similarity_requires_analytics_permission(client: TestClient, auth_headers) -> None:
    assert client.get("/api/v1/coach/similarity").status_code == 401

    response = client.get("/api/v1/coach/similarity", headers=auth_headers("alice"))

    assert response.status_code == 403
