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


def test_contest_detail_respects_visibility_and_problem_scope(client: TestClient, auth_headers, store) -> None:
    public_detail = client.get("/api/v1/contests/C1001")
    assert public_detail.status_code == 200, public_detail.text
    public_payload = public_detail.json()
    assert public_payload["id"] == "C1001"
    assert all("judge_config" not in item for item in public_payload["problems"])

    contest = store.get_contest("C1001")
    assert contest is not None
    contest.visibility = "private"
    store.update_contest(contest)

    anonymous = client.get("/api/v1/contests/C1001")
    student = client.get("/api/v1/contests/C1001", headers=auth_headers("alice"))
    judge = client.get("/api/v1/contests/C1001", headers=auth_headers("judge"))

    assert anonymous.status_code == 404
    assert student.status_code == 403
    assert judge.status_code == 200


def test_contest_problem_list_hides_non_visible_problem_and_unknown_problem(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    problem = store.get_problem("P1003")
    assert contest is not None and problem is not None

    contest.problem_ids = ["P1001", "P1003", "P-NOT-EXIST"]
    store.update_contest(contest)
    problem.visible = False
    store.update_problem(problem)

    response = client.get("/api/v1/contests/C1001/problems", headers=auth_headers("alice"))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["id"] for item in payload] == ["P1001"]


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
    item = next(entry for entry in balloons.json() if entry["submission_id"] == objective_body["id"])
    assert item["eligible"] is True
    assert item["released"] is False
    assert item["first_ac"] is True


def test_contest_submit_rejects_problem_outside_contest_and_non_student_account(client: TestClient, auth_headers) -> None:
    outsider = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1004", "answers": {"choices": ["A", "C"]}},
    )
    assert outsider.status_code == 404

    judge_submit = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("judge"),
        json={"problem_id": "P1001", "language": "python", "source_code": "print('no')\n"},
    )
    assert judge_submit.status_code == 403


def test_contest_balloons_are_acm_only(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    contest.rule = "OI"
    store.update_contest(contest)

    oi_submission = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1003", "answers": {"choice": "B"}},
    )
    assert oi_submission.status_code == 200, oi_submission.text

    balloons = client.get("/api/v1/contests/C1001/balloons", headers=auth_headers("judge"))
    assert balloons.status_code == 200, balloons.text
    assert balloons.json() == []


def test_contest_balloons_track_first_ac_per_user_problem(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    contest.rule = "ACM"
    store.update_contest(contest)

    first = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1002", "answers": {"edge_formula": "n(n-1)/2"}},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1002", "answers": {"edge_formula": "n(n-1)/2"}},
    )
    assert second.status_code == 200, second.text

    acm_balloons = client.get("/api/v1/contests/C1001/balloons", headers=auth_headers("judge"))
    assert acm_balloons.status_code == 200, acm_balloons.text
    payload = acm_balloons.json()
    first_item = next(item for item in payload if item["submission_id"] == first.json()["id"])
    assert first_item["problem_id"] == "P1002"
    assert first_item["released"] is False
    assert first_item["first_ac"] is True
    assert all(item["submission_id"] != second.json()["id"] for item in payload)


def test_contest_balloon_update_requires_judge_permission_and_tracks_release_metadata(client: TestClient, auth_headers) -> None:
    objective_response = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1003", "answers": {"choice": "B"}},
    )
    assert objective_response.status_code == 200, objective_response.text
    submission_id = objective_response.json()["id"]

    forbidden = client.patch(
        f"/api/v1/contests/C1001/balloons/{submission_id}",
        headers=auth_headers("alice"),
        json={"submission_id": submission_id, "released": True},
    )
    assert forbidden.status_code == 403

    released = client.patch(
        f"/api/v1/contests/C1001/balloons/{submission_id}",
        headers=auth_headers("judge"),
        json={"submission_id": submission_id, "released": True},
    )
    assert released.status_code == 200, released.text
    release_payload = released.json()
    assert release_payload["released"] is True
    assert release_payload["released_by"] == "u-judge"
    assert release_payload["released_at"] is not None

    reverted = client.patch(
        f"/api/v1/contests/C1001/balloons/{submission_id}",
        headers=auth_headers("judge"),
        json={"submission_id": submission_id, "released": False},
    )
    assert reverted.status_code == 200, reverted.text
    revert_payload = reverted.json()
    assert revert_payload["released"] is False
    assert revert_payload["released_by"] is None
    assert revert_payload["released_at"] is None


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


def test_contest_clarification_supports_problem_scope_private_public_and_broadcast(client: TestClient, auth_headers) -> None:
    created = client.post(
        "/api/v1/contests/C1001/clarifications",
        headers=auth_headers("alice"),
        json={"question": "P1001 的样例是否完整？", "problem_id": "P1001"},
    )
    assert created.status_code == 200, created.text
    clarification = created.json()
    assert clarification["problem_id"] == "P1001"
    assert clarification["problem_title"] == "A+B Problem"
    clarification_id = clarification["id"]

    private_reply = client.patch(
        f"/api/v1/clarifications/{clarification_id}",
        headers=auth_headers("judge"),
        json={"answer": "这是私有回复", "public": False, "broadcast": False},
    )
    assert private_reply.status_code == 200, private_reply.text
    private_body = private_reply.json()
    assert private_body["public"] is False
    assert private_body["broadcast"] is False
    assert private_body["answered_by"] == "u-judge"
    assert private_body["answered_by_name"] == "Judge Wu"
    assert private_body["answered_at"] is not None

    owner_list = client.get("/api/v1/contests/C1001/clarifications", headers=auth_headers("alice"))
    assert owner_list.status_code == 200, owner_list.text
    owner_item = next(item for item in owner_list.json() if item["id"] == clarification_id)
    assert owner_item["answer"] == "这是私有回复"
    assert owner_item["public"] is False
    assert owner_item["broadcast"] is False

    public_reply = client.patch(
        f"/api/v1/clarifications/{clarification_id}",
        headers=auth_headers("judge"),
        json={"answer": "这是公开回复", "public": True, "broadcast": False},
    )
    assert public_reply.status_code == 200, public_reply.text
    public_body = public_reply.json()
    assert public_body["public"] is True
    assert public_body["broadcast"] is False

    broadcast_reply = client.patch(
        f"/api/v1/clarifications/{clarification_id}",
        headers=auth_headers("judge"),
        json={"answer": "这是广播回复", "broadcast": True},
    )
    assert broadcast_reply.status_code == 200, broadcast_reply.text
    broadcast_body = broadcast_reply.json()
    assert broadcast_body["public"] is True
    assert broadcast_body["broadcast"] is True
    assert broadcast_body["broadcast_at"] is not None


def test_contest_clarification_public_view_redacts_other_student_identity(client: TestClient, auth_headers, store) -> None:
    coach = store.get_user("u-coach")
    assert coach is not None
    coach.role = "student"
    store.update_user(coach)

    created = client.post(
        "/api/v1/contests/C1001/clarifications",
        headers=auth_headers("alice"),
        json={"question": "这个问题想公开讨论"},
    )
    assert created.status_code == 200, created.text
    clarification_id = created.json()["id"]

    replied = client.patch(
        f"/api/v1/clarifications/{clarification_id}",
        headers=auth_headers("judge"),
        json={"answer": "公开回复内容", "public": True},
    )
    assert replied.status_code == 200, replied.text

    student = client.get("/api/v1/contests/C1001/clarifications", headers=auth_headers("alice"))
    assert student.status_code == 200, student.text
    own_item = next(item for item in student.json() if item["id"] == clarification_id)
    assert own_item["user_id"] == "u-student"
    assert own_item["user_display_name"] == "Alice Chen"

    other_student = client.get("/api/v1/contests/C1001/clarifications", headers=auth_headers("coach"))
    assert other_student.status_code == 200, other_student.text
    public_item = next(item for item in other_student.json() if item["id"] == clarification_id)
    assert public_item["user_id"] == ""
    assert public_item["user_display_name"] == "匿名选手"
    assert public_item["answer"] == "公开回复内容"


def test_contest_clarification_judge_list_includes_private_and_audit_fields(client: TestClient, auth_headers) -> None:
    created = client.post(
        "/api/v1/contests/C1001/clarifications",
        headers=auth_headers("alice"),
        json={"question": "仅裁判和本人可见"},
    )
    assert created.status_code == 200, created.text
    clarification_id = created.json()["id"]

    replied = client.patch(
        f"/api/v1/clarifications/{clarification_id}",
        headers=auth_headers("judge"),
        json={"answer": "内部说明", "public": False},
    )
    assert replied.status_code == 200, replied.text

    judge_list = client.get("/api/v1/contests/C1001/clarifications", headers=auth_headers("judge"))
    assert judge_list.status_code == 200, judge_list.text
    judge_item = next(item for item in judge_list.json() if item["id"] == clarification_id)
    assert judge_item["user_id"] == "u-student"
    assert judge_item["user_display_name"] == "Alice Chen"
    assert judge_item["answered_by"] == "u-judge"
    assert judge_item["answered_by_name"] == "Judge Wu"


def test_contest_clarification_rejects_problem_outside_contest(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/api/v1/contests/C1001/clarifications",
        headers=auth_headers("alice"),
        json={"question": "P1004 不在这场比赛里", "problem_id": "P1004"},
    )
    assert response.status_code == 404


def test_contest_clarification_private_reply_stays_hidden_from_other_students(client: TestClient, auth_headers, store) -> None:
    coach = store.get_user("u-coach")
    assert coach is not None
    coach.role = "student"
    store.update_user(coach)

    created = client.post(
        "/api/v1/contests/C1001/clarifications",
        headers=auth_headers("alice"),
        json={"question": "仅本人可见"},
    )
    assert created.status_code == 200, created.text
    clarification_id = created.json()["id"]

    replied = client.patch(
        f"/api/v1/clarifications/{clarification_id}",
        headers=auth_headers("judge"),
        json={"answer": "私有答复", "public": False},
    )
    assert replied.status_code == 200, replied.text

    other_student = client.get("/api/v1/contests/C1001/clarifications", headers=auth_headers("coach"))
    assert other_student.status_code == 200, other_student.text
    assert all(item["id"] != clarification_id for item in other_student.json())


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
    contest = store.get_contest("C1001")
    assert contest is not None
    contest.end_at = datetime(2026, 5, 20, 17, 0, tzinfo=timezone.utc)
    store.update_contest(contest)

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

    judge_rejudge = client.post(
        "/api/v1/contests/C1001/rejudge",
        headers=auth_headers("judge"),
        json={"reason": "judge contest rejudge"},
    )
    assert judge_rejudge.status_code == 200, judge_rejudge.text
    judge_payload = judge_rejudge.json()
    assert judge_payload["contest_id"] == "C1001"
    assert judge_payload["requeued_count"] == 1
    assert judge_payload["skipped_count"] == 0
    assert judge_payload["rejudge_by"] == "u-judge"
    assert judge_payload["rejudge_reason"] == "judge contest rejudge"

    rejudge = client.post(
        "/api/v1/contests/C1001/rejudge",
        headers=auth_headers("admin"),
        json={"reason": "contest rejudge"},
    )
    assert rejudge.status_code == 200, rejudge.text
    rejudge_payload = rejudge.json()
    assert rejudge_payload["contest_id"] == "C1001"
    assert rejudge_payload["requeued_count"] == 1
    assert rejudge_payload["skipped_count"] == 0

    contest = store.get_contest("C1001")
    assert contest is not None
    assert contest.rejudge_by == "u-admin"
    assert contest.rejudge_reason == "contest rejudge"


def test_contest_rejudge_requires_judge_or_admin_and_contest_end(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None

    coach_denied = client.post(
        "/api/v1/contests/C1001/rejudge",
        headers=auth_headers("coach"),
        json={"reason": "coach should not rejudge"},
    )
    assert coach_denied.status_code == 403

    contest.end_at = datetime(2099, 5, 26, 17, 0, tzinfo=timezone.utc)
    store.update_contest(contest)

    running_response = client.post(
        "/api/v1/contests/C1001/rejudge",
        headers=auth_headers("judge"),
        json={"reason": "too early"},
    )
    assert running_response.status_code == 409
    assert "after the contest ends" in running_response.json()["detail"]


def test_contest_rejudge_skips_objective_submissions_with_clear_reason(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    contest.end_at = datetime(2026, 5, 20, 17, 0, tzinfo=timezone.utc)
    store.update_contest(contest)

    code_submitted = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1001", "language": "python", "source_code": "print('rejudge mix')\n"},
    )
    assert code_submitted.status_code == 200, code_submitted.text

    objective_submitted = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1003", "answers": {"choice": "B"}},
    )
    assert objective_submitted.status_code == 200, objective_submitted.text

    response = client.post(
        "/api/v1/contests/C1001/rejudge",
        headers=auth_headers("judge"),
        json={"reason": "contest-wide consistency check"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["requeued_count"] == 1
    assert payload["requeued"][0]["id"] == code_submitted.json()["id"]
    assert payload["skipped_count"] == 1
    skipped = {item["submission_id"]: item["reason"] for item in payload["skipped"]}
    assert "Only code submissions can be rejudged" in skipped[objective_submitted.json()["id"]]


def test_contest_unfreeze_requires_manage_permission(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    contest.frozen = True
    contest.frozen_at = datetime(2026, 5, 26, 4, 0, tzinfo=timezone.utc)
    contest.frozen_by = "u-admin"
    store.update_contest(contest)

    forbidden = client.post(
        "/api/v1/contests/C1001/unfreeze",
        headers=auth_headers("alice"),
        json={"reason": "student cannot unfreeze"},
    )
    assert forbidden.status_code == 403

    unfreeze = client.post(
        "/api/v1/contests/C1001/unfreeze",
        headers=auth_headers("admin"),
        json={"reason": "manual unfreeze"},
    )
    assert unfreeze.status_code == 200, unfreeze.text
    payload = unfreeze.json()
    assert payload["frozen"] is False
    assert payload["freeze_disabled"] is True
    assert payload["frozen_at"] is None


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


def test_acm_standings_show_full_board_to_judge_after_freeze(client: TestClient, auth_headers, store) -> None:
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
            "S-FULL-WA",
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
            "S-FULL-AC",
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

    student_response = client.get("/api/v1/contests/C1001/standings", headers=auth_headers("alice"))
    judge_response = client.get("/api/v1/contests/C1001/standings", headers=auth_headers("judge"))

    assert student_response.status_code == 200, student_response.text
    assert judge_response.status_code == 200, judge_response.text

    student_row = next(row for row in student_response.json() if row["user_id"] == "u-student")
    judge_row = next(row for row in judge_response.json() if row["user_id"] == "u-student")

    assert student_row["solved"] == 0
    assert student_row["problems"]["P1002"]["accepted_at"] is None

    assert judge_row["solved"] == 1
    assert judge_row["problems"]["P1002"]["accepted_at"] is not None


def test_acm_default_freeze_window_hides_late_submissions_without_manual_freeze(client: TestClient, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    current = datetime.now(timezone.utc)
    start_at = current - timedelta(minutes=90)
    contest.start_at = start_at
    contest.end_at = start_at + timedelta(hours=2)
    contest.frozen = False
    contest.freeze_disabled = False
    contest.frozen_at = None
    store.update_contest(contest)

    store.add_submission(
        _contest_submission(
            "S-AUTO-WA",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="wrong_answer",
            score=0,
            created_at=start_at + timedelta(minutes=45),
            judged_at=start_at + timedelta(minutes=45),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-AUTO-AC",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="accepted",
            created_at=start_at + timedelta(minutes=75),
            judged_at=start_at + timedelta(minutes=75),
        )
    )

    standings = client.get("/api/v1/contests/C1001/standings")
    detail = client.get("/api/v1/contests/C1001")

    assert standings.status_code == 200, standings.text
    assert detail.status_code == 200, detail.text

    alice = next(row for row in standings.json() if row["user_id"] == "u-student")
    assert alice["solved"] == 0
    assert alice["problems"]["P1001"]["accepted_at"] is None

    contest_payload = detail.json()
    assert contest_payload["freeze_active"] is True
    assert contest_payload["freeze_effective_at"] is not None


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


def test_oi_standings_use_highest_score_per_problem(client: TestClient, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    start_at = datetime(2026, 5, 26, 1, 0, tzinfo=timezone.utc)
    contest.rule = "OI"
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
            "S-OI-ALICE-60",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="wrong_answer",
            score=60,
            created_at=start_at + timedelta(minutes=10),
            judged_at=start_at + timedelta(minutes=10),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-OI-ALICE-100",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="accepted",
            score=100,
            created_at=start_at + timedelta(minutes=25),
            judged_at=start_at + timedelta(minutes=25),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-OI-ALICE-80",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1002",
            problem_title="完全图边数",
            problem_type="blank",
            status="wrong_answer",
            score=80,
            created_at=start_at + timedelta(minutes=35),
            judged_at=start_at + timedelta(minutes=35),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-OI-COACH-90",
            user_id="u-coach",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="wrong_answer",
            score=90,
            created_at=start_at + timedelta(minutes=12),
            judged_at=start_at + timedelta(minutes=12),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-OI-COACH-70",
            user_id="u-coach",
            contest_id="C1001",
            problem_id="P1002",
            problem_title="完全图边数",
            problem_type="blank",
            status="wrong_answer",
            score=70,
            created_at=start_at + timedelta(minutes=20),
            judged_at=start_at + timedelta(minutes=20),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-OI-JUDGE-100",
            user_id="u-judge",
            contest_id="C1001",
            problem_id="P1003",
            problem_title="二分查找适用条件",
            problem_type="single_choice",
            status="accepted",
            score=100,
            created_at=start_at + timedelta(minutes=15),
            judged_at=start_at + timedelta(minutes=15),
        )
    )

    response = client.get("/api/v1/contests/C1001/standings")
    assert response.status_code == 200, response.text
    body = response.json()

    assert [row["user_id"] for row in body[:3]] == ["u-student", "u-coach", "u-judge"]
    alice = body[0]
    coach_row = body[1]
    judge_row = body[2]

    assert alice["score"] == 180
    assert alice["solved"] == 1
    assert alice["penalty"] == 0
    assert alice["first_blood"] == 0
    assert alice["problems"]["P1001"]["score"] == 100
    assert alice["problems"]["P1001"]["attempts"] == 2
    assert alice["problems"]["P1002"]["score"] == 80

    assert coach_row["score"] == 160
    assert coach_row["solved"] == 0
    assert coach_row["problems"]["P1001"]["score"] == 90
    assert coach_row["problems"]["P1002"]["score"] == 70

    assert judge_row["score"] == 100
    assert judge_row["solved"] == 1
    assert judge_row["problems"]["P1003"]["attempts"] == 1


def test_oi_standings_hide_higher_score_after_freeze(client: TestClient, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    start_at = datetime(2026, 5, 26, 1, 0, tzinfo=timezone.utc)
    contest.rule = "OI"
    contest.start_at = start_at
    contest.end_at = start_at + timedelta(hours=5)
    contest.frozen = True
    contest.frozen_at = start_at + timedelta(minutes=60)
    store.update_contest(contest)

    store.add_submission(
        _contest_submission(
            "S-OI-FREEZE-LOW",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="wrong_answer",
            score=40,
            created_at=start_at + timedelta(minutes=30),
            judged_at=start_at + timedelta(minutes=30),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-OI-FREEZE-HIGH",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="accepted",
            score=100,
            created_at=start_at + timedelta(minutes=70),
            judged_at=start_at + timedelta(minutes=70),
        )
    )

    response = client.get("/api/v1/contests/C1001/standings")
    assert response.status_code == 200, response.text
    body = response.json()
    alice = next(row for row in body if row["user_id"] == "u-student")

    assert alice["score"] == 40
    assert alice["solved"] == 0
    assert alice["problems"]["P1001"]["score"] == 40
    assert alice["problems"]["P1001"]["attempts"] == 1
