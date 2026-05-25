from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.models import Submission


def _contest_submission(
    submission_id: str,
    *,
    user_id: str,
    contest_id: str,
    problem_id: str,
    problem_title: str,
    problem_type: str,
    status: str,
    created_at: datetime,
    judged_at: datetime | None = None,
    score: int = 100,
    max_score: int = 100,
) -> Submission:
    return Submission(
        id=submission_id,
        user_id=user_id,
        problem_id=problem_id,
        problem_title=problem_title,
        problem_type=problem_type,
        contest_id=contest_id,
        language="python" if problem_type == "code" else None,
        source_code="print('acm')\n" if problem_type == "code" else None,
        answers=None,
        status=status,
        score=score,
        max_score=max_score,
        details=[],
        message="seed standings",
        created_at=created_at,
        judged_at=judged_at,
    )


def test_contest_problem_list_hides_judge_config_and_respects_visibility(client: TestClient, auth_headers, store) -> None:
    response = client.get("/api/v1/contests/C1001/problems")
    assert response.status_code == 200, response.text
    assert response.json()
    assert all("judge_config" not in item for item in response.json())

    contest = store.get_contest("C1001")
    assert contest is not None
    contest.visibility = "private"
    store.update_contest(contest)

    anonymous = client.get("/api/v1/contests/C1001/problems")
    student = client.get("/api/v1/contests/C1001/problems", headers=auth_headers("alice"))
    judge = client.get("/api/v1/contests/C1001/problems", headers=auth_headers("judge"))

    assert anonymous.status_code == 404
    assert student.status_code == 403
    assert judge.status_code == 200


def test_contest_submit_routes_keep_code_queue_only_and_objective_scored(client: TestClient, auth_headers, store) -> None:
    code_response = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1001", "language": "python", "source_code": "print('contest queue only')\n"},
    )
    assert code_response.status_code == 200, code_response.text
    code_body = code_response.json()
    assert code_body["contest_id"] == "C1001"
    assert code_body["status"] == "queued"

    objective_response = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1003", "answers": {"choice": "B"}},
    )
    assert objective_response.status_code == 200, objective_response.text
    objective_body = objective_response.json()
    assert objective_body["contest_id"] == "C1001"
    assert objective_body["score"] == objective_body["max_score"] == 100

    balloons = client.get("/api/v1/contests/C1001/balloons", headers=auth_headers("judge"))
    assert balloons.status_code == 200, balloons.text
    assert any(item["submission_id"] == objective_body["id"] for item in balloons.json())


def test_contest_clarification_requires_auth_and_resource_scope(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    contest.visibility = "private"
    store.update_contest(contest)

    anonymous = client.get("/api/v1/contests/C1001/clarifications")
    assert anonymous.status_code == 401

    student = client.get("/api/v1/contests/C1001/clarifications", headers=auth_headers("alice"))
    judge = client.get("/api/v1/contests/C1001/clarifications", headers=auth_headers("judge"))

    assert student.status_code == 403
    assert judge.status_code == 200


def test_contest_print_reads_submission_or_request_only(client: TestClient, auth_headers) -> None:
    submitted = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1001", "language": "python", "source_code": "print('print only')\n"},
    )
    assert submitted.status_code == 200, submitted.text
    submission_id = submitted.json()["id"]

    own_print = client.post(
        "/api/v1/contests/C1001/print",
        headers=auth_headers("alice"),
        json={"submission_id": submission_id},
    )
    assert own_print.status_code == 200, own_print.text
    assert "print only" in own_print.json()["source_code"]

    denied_adhoc = client.post(
        "/api/v1/contests/C1001/print",
        headers=auth_headers("alice"),
        json={"problem_id": "P1001", "source_code": "print('manual')\n"},
    )
    assert denied_adhoc.status_code == 403

    judge_adhoc = client.post(
        "/api/v1/contests/C1001/print",
        headers=auth_headers("judge"),
        json={"problem_id": "P1001", "source_code": "print('manual')\n"},
    )
    assert judge_adhoc.status_code == 200
    assert judge_adhoc.json()["source_kind"] == "request"


def test_contest_freeze_and_rejudge_require_manage_permission(client: TestClient, auth_headers, store) -> None:
    forbidden = client.post(
        "/api/v1/contests/C1001/freeze",
        headers=auth_headers("alice"),
        json={"reason": "student cannot freeze"},
    )
    assert forbidden.status_code == 403

    freeze = client.post(
        "/api/v1/contests/C1001/freeze",
        headers=auth_headers("admin"),
        json={"reason": "manual freeze"},
    )
    assert freeze.status_code == 200, freeze.text
    assert freeze.json()["frozen"] is True

    submitted = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1001", "language": "python", "source_code": "print('rejudge')\n"},
    )
    assert submitted.status_code == 200, submitted.text

    rejudge = client.post(
        "/api/v1/contests/C1001/rejudge",
        headers=auth_headers("admin"),
        json={"reason": "contest rejudge"},
    )
    assert rejudge.status_code == 200, rejudge.text

    contest = store.get_contest("C1001")
    assert contest is not None
    assert contest.rejudge_by == "u-admin"


def test_acm_standings_include_penalty_and_first_blood(client: TestClient, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    start_at = datetime(2026, 5, 26, 1, 0, tzinfo=timezone.utc)
    contest.start_at = start_at
    contest.end_at = start_at + timedelta(hours=5)
    contest.frozen = False
    store.update_contest(contest)

    coach = store.get_user("u-coach")
    judge = store.get_user("u-judge")
    assert coach is not None and judge is not None
    coach.role = "student"
    judge.role = "student"
    store.update_user(coach)
    store.update_user(judge)

    store.add_submission(
        _contest_submission(
            "S-ALICE-WA",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="wrong_answer",
            score=0,
            created_at=start_at + timedelta(minutes=10),
            judged_at=start_at + timedelta(minutes=10),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-COACH-AC",
            user_id="u-coach",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="accepted",
            created_at=start_at + timedelta(minutes=20),
            judged_at=start_at + timedelta(minutes=20),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-ALICE-AC1",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="accepted",
            created_at=start_at + timedelta(minutes=25),
            judged_at=start_at + timedelta(minutes=25),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-JUDGE-AC",
            user_id="u-judge",
            contest_id="C1001",
            problem_id="P1002",
            problem_title="完全图边数",
            problem_type="blank",
            status="accepted",
            created_at=start_at + timedelta(minutes=30),
            judged_at=start_at + timedelta(minutes=30),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-ALICE-AC2",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1002",
            problem_title="完全图边数",
            problem_type="blank",
            status="accepted",
            created_at=start_at + timedelta(minutes=40),
            judged_at=start_at + timedelta(minutes=40),
        )
    )

    response = client.get("/api/v1/contests/C1001/standings")
    assert response.status_code == 200, response.text
    body = response.json()

    assert [row["user_id"] for row in body[:3]] == ["u-student", "u-coach", "u-judge"]
    alice = body[0]
    coach_row = body[1]
    judge_row = body[2]

    assert alice["solved"] == 2
    assert alice["score"] == 200
    assert alice["penalty"] == 85
    assert alice["first_blood"] == 0
    assert alice["problems"]["P1001"]["attempts"] == 1
    assert alice["problems"]["P1001"]["penalty_minutes"] == 45
    assert alice["problems"]["P1001"]["first_blood"] is False

    assert coach_row["solved"] == 1
    assert coach_row["penalty"] == 20
    assert coach_row["first_blood"] == 1
    assert coach_row["problems"]["P1001"]["first_blood"] is True

    assert judge_row["solved"] == 1
    assert judge_row["penalty"] == 30
    assert judge_row["first_blood"] == 1
    assert judge_row["problems"]["P1002"]["first_blood"] is True


def test_acm_standings_hide_submissions_after_freeze(client: TestClient, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    start_at = datetime(2026, 5, 26, 1, 0, tzinfo=timezone.utc)
    contest.start_at = start_at
    contest.end_at = start_at + timedelta(hours=5)
    contest.frozen = True
    contest.frozen_at = start_at + timedelta(minutes=60)
    store.update_contest(contest)

    store.add_submission(
        _contest_submission(
            "S-FREEZE-WA",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1002",
            problem_title="完全图边数",
            problem_type="blank",
            status="wrong_answer",
            score=0,
            created_at=start_at + timedelta(minutes=30),
            judged_at=start_at + timedelta(minutes=30),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-FREEZE-AC",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1002",
            problem_title="完全图边数",
            problem_type="blank",
            status="accepted",
            created_at=start_at + timedelta(minutes=70),
            judged_at=start_at + timedelta(minutes=70),
        )
    )

    response = client.get("/api/v1/contests/C1001/standings")
    assert response.status_code == 200, response.text
    body = response.json()
    alice = next(row for row in body if row["user_id"] == "u-student")

    assert alice["solved"] == 0
    assert alice["penalty"] == 0
    assert alice["problems"]["P1002"]["attempts"] == 1
    assert alice["problems"]["P1002"]["accepted_at"] is None
    assert alice["problems"]["P1002"]["status"] == "wrong_answer"


def test_private_contest_standings_follow_visibility_and_permission(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    contest.visibility = "private"
    store.update_contest(contest)

    anonymous = client.get("/api/v1/contests/C1001/standings")
    student = client.get("/api/v1/contests/C1001/standings", headers=auth_headers("alice"))
    judge = client.get("/api/v1/contests/C1001/standings", headers=auth_headers("judge"))

    assert anonymous.status_code == 404
    assert student.status_code == 403
    assert judge.status_code == 200
