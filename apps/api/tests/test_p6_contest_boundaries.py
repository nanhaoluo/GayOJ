from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.models import ContestProblemLayoutItem, Submission, Team


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


def test_contest_create_returns_layout_and_allows_non_public_problem_reference(client: TestClient, auth_headers, store) -> None:
    hidden_problem = store.get_problem("P1004")
    assert hidden_problem is not None
    hidden_problem.visible = False
    store.update_problem(hidden_problem)

    response = client.post(
        "/api/v1/contests",
        headers=auth_headers("coach"),
        json={
            "title": "Private Final",
            "rule": "ACM",
            "start_at": "2026-05-26T10:00:00Z",
            "end_at": "2026-05-26T15:00:00Z",
            "visibility": "private",
            "problem_ids": ["P1001", "P1004"],
            "problem_layout": [
                {"problem_id": "P1001", "problem_key": "A", "allowed_languages": ["cpp", "python"]},
                {"problem_id": "P1004", "problem_key": "B", "allowed_languages": []},
            ],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["title"] == "Private Final"
    assert payload["visibility"] == "private"
    assert payload["problem_ids"] == ["P1001", "P1004"]
    assert payload["problem_layout"][0]["problem_key"] == "A"
    assert payload["problem_layout"][0]["allowed_languages"] == ["cpp", "python"]
    assert payload["problem_layout"][1]["problem_id"] == "P1004"

    problems = client.get(f"/api/v1/contests/{payload['id']}/problems", headers=auth_headers("judge"))
    assert problems.status_code == 200, problems.text
    problem_payload = problems.json()
    assert [item["id"] for item in problem_payload] == ["P1001", "P1004"]
    assert problem_payload[1]["problem_key"] == "B"
    assert problem_payload[1]["allowed_languages"] == []
    assert "judge_config" not in problem_payload[1]


def test_contest_problem_aliases_drive_submit_clarification_print_and_rejudge(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    current = datetime.now(timezone.utc)
    contest.start_at = current - timedelta(hours=2)
    contest.end_at = current + timedelta(hours=1)
    contest.problem_ids = ["P1001", "P1002"]
    contest.problem_layout = [
        ContestProblemLayoutItem(
            problem_id="P1001",
            problem_key="ALPHA",
            display_title="Contest Alpha",
            score=300,
            allowed_languages=["python"],
        ),
        ContestProblemLayoutItem(
            problem_id="P1002",
            problem_key="BETA",
            display_title="Contest Beta",
            score=200,
            allowed_languages=[],
        ),
    ]
    store.update_contest(contest)

    problems = client.get("/api/v1/contests/C1001/problems", headers=auth_headers("alice"))
    assert problems.status_code == 200, problems.text
    problem_payload = problems.json()
    assert problem_payload[0]["id"] == "P1001"
    assert problem_payload[0]["problem_key"] == "ALPHA"
    assert problem_payload[0]["title"] == "Contest Alpha"
    assert problem_payload[0]["display_title"] == "Contest Alpha"
    assert problem_payload[0]["score"] == 300
    assert problem_payload[0]["allowed_languages"] == ["python"]
    assert all("judge_config" not in item for item in problem_payload)

    submitted = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "alpha", "language": "python", "source_code": "print('alias submit')\n"},
    )
    assert submitted.status_code == 200, submitted.text
    submit_payload = submitted.json()
    assert submit_payload["problem_id"] == "P1001"
    assert submit_payload["problem_title"] == "Contest Alpha"
    assert submit_payload["contest_id"] == "C1001"
    stored_submission = store.get_submission(submit_payload["id"])
    assert stored_submission is not None
    assert stored_submission.problem_id == "P1001"
    assert stored_submission.problem_title == "A+B Problem"

    clarification = client.post(
        "/api/v1/contests/C1001/clarifications",
        headers=auth_headers("alice"),
        json={"problem_id": "ALPHA", "question": "Can we use the contest alias?"},
    )
    assert clarification.status_code == 200, clarification.text
    clarification_payload = clarification.json()
    assert clarification_payload["problem_id"] == "P1001"
    assert clarification_payload["problem_key"] == "ALPHA"
    assert clarification_payload["problem_title"] == "Contest Alpha"

    print_job = client.post(
        "/api/v1/contests/C1001/print",
        headers=auth_headers("judge"),
        json={"problem_id": "ALPHA", "language": "python", "source_code": "print('adhoc alias')\n"},
    )
    assert print_job.status_code == 200, print_job.text
    assert print_job.json()["problem_id"] == "P1001"
    assert print_job.json()["problem_key"] == "ALPHA"
    assert print_job.json()["problem_title"] == "Contest Alpha"

    contest.end_at = current - timedelta(minutes=1)
    store.update_contest(contest)
    rejudge = client.post(
        "/api/v1/contests/C1001/rejudge",
        headers=auth_headers("judge"),
        json={"problem_id": "ALPHA", "statuses": ["queued"], "reason": "alias scoped rejudge"},
    )
    assert rejudge.status_code == 200, rejudge.text
    rejudge_payload = rejudge.json()
    assert rejudge_payload["requeued_count"] == 1
    assert rejudge_payload["requeued"][0]["problem_id"] == "P1001"
    logs, total = store.list_audit_logs(action="contest.rejudge")
    assert total == 1
    assert logs[0].metadata["problem_id"] == "P1001"
    assert logs[0].metadata["problem_ref"] == "ALPHA"


def test_contest_update_preserves_freeze_state_and_reorders_layout(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    contest.frozen = True
    contest.frozen_at = datetime(2026, 5, 26, 11, 0, tzinfo=timezone.utc)
    contest.frozen_by = "u-judge"
    store.update_contest(contest)

    response = client.put(
        "/api/v1/contests/C1001",
        headers=auth_headers("judge"),
        json={
            "title": "Updated Round",
            "rule": "OI",
            "start_at": "2026-05-26T09:00:00Z",
            "end_at": "2026-05-26T13:00:00Z",
            "visibility": "public",
            "problem_ids": ["P1003", "P1001"],
            "problem_layout": [
                {"problem_id": "P1003", "problem_key": "A", "allowed_languages": []},
                {"problem_id": "P1001", "problem_key": "B", "allowed_languages": ["cpp"]},
            ],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["title"] == "Updated Round"
    assert payload["rule"] == "OI"
    assert payload["problem_ids"] == ["P1003", "P1001"]
    assert payload["problem_layout"][1]["problem_key"] == "B"
    assert payload["problem_layout"][1]["allowed_languages"] == ["cpp"]
    assert payload["frozen"] is True
    assert payload["frozen_by"] == "u-judge"
    assert payload["freeze_active"] is True


def test_contest_update_rejects_removing_problem_with_existing_contest_data(client: TestClient, auth_headers, store) -> None:
    created = client.post(
        "/api/v1/contests/C1001/clarifications",
        headers=auth_headers("alice"),
        json={"question": "keep problem scope", "problem_id": "P1001"},
    )
    assert created.status_code == 200, created.text

    submission = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1001", "language": "python", "source_code": "print('keep')\n"},
    )
    assert submission.status_code == 200, submission.text

    response = client.put(
        "/api/v1/contests/C1001",
        headers=auth_headers("judge"),
        json={
            "title": "Broken Update",
            "rule": "ACM",
            "start_at": "2026-05-26T09:00:00Z",
            "end_at": "2026-05-26T13:00:00Z",
            "visibility": "public",
            "problem_ids": ["P1002", "P1003"],
            "problem_layout": [
                {"problem_id": "P1002", "problem_key": "A", "allowed_languages": []},
                {"problem_id": "P1003", "problem_key": "B", "allowed_languages": []},
            ],
        },
    )

    assert response.status_code == 409
    assert "P1001" in response.json()["detail"]


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
    assert item["problem_key"] == "3"
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
        json={"question": "P1001 鐨勬牱渚嬫槸鍚﹀畬鏁达紵", "problem_id": "P1001"},
    )
    assert created.status_code == 200, created.text
    clarification = created.json()
    assert clarification["problem_id"] == "P1001"
    assert clarification["problem_title"] == "A+B Problem"
    clarification_id = clarification["id"]

    private_reply = client.patch(
        f"/api/v1/clarifications/{clarification_id}",
        headers=auth_headers("judge"),
        json={"answer": "杩欐槸绉佹湁鍥炲", "public": False, "broadcast": False},
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
    assert owner_item["answer"] == "杩欐槸绉佹湁鍥炲"
    assert owner_item["public"] is False
    assert owner_item["broadcast"] is False

    public_reply = client.patch(
        f"/api/v1/clarifications/{clarification_id}",
        headers=auth_headers("judge"),
        json={"answer": "杩欐槸鍏紑鍥炲", "public": True, "broadcast": False},
    )
    assert public_reply.status_code == 200, public_reply.text
    public_body = public_reply.json()
    assert public_body["public"] is True
    assert public_body["broadcast"] is False

    broadcast_reply = client.patch(
        f"/api/v1/clarifications/{clarification_id}",
        headers=auth_headers("judge"),
        json={"answer": "杩欐槸骞挎挱鍥炲", "broadcast": True},
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
        json={"question": "This question should be public."},
    )
    assert created.status_code == 200, created.text
    clarification_id = created.json()["id"]

    replied = client.patch(
        f"/api/v1/clarifications/{clarification_id}",
        headers=auth_headers("judge"),
        json={"answer": "Public clarification reply", "public": True},
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
    assert public_item["answer"] == "Public clarification reply"


def test_contest_clarification_judge_list_includes_private_and_audit_fields(client: TestClient, auth_headers, store) -> None:
    created = client.post(
        "/api/v1/contests/C1001/clarifications",
        headers=auth_headers("alice"),
        json={"question": "浠呰鍒ゅ拰鏈汉鍙"},
    )
    assert created.status_code == 200, created.text
    clarification_id = created.json()["id"]

    replied = client.patch(
        f"/api/v1/clarifications/{clarification_id}",
        headers=auth_headers("judge"),
        json={"answer": "鍐呴儴璇存槑", "public": False},
    )
    assert replied.status_code == 200, replied.text

    judge_list = client.get("/api/v1/contests/C1001/clarifications", headers=auth_headers("judge"))
    assert judge_list.status_code == 200, judge_list.text
    judge_item = next(item for item in judge_list.json() if item["id"] == clarification_id)
    assert judge_item["user_id"] == "u-student"
    assert judge_item["user_display_name"] == "Alice Chen"
    assert judge_item["answered_by"] == "u-judge"
    assert judge_item["answered_by_name"] == "Judge Wu"

    audit_logs, _ = store.list_audit_logs(action="clarification.reply")
    reply_log = next(item for item in audit_logs if item.resource == f"clarification:{clarification_id}")
    assert reply_log.metadata["contest_id"] == "C1001"
    assert reply_log.metadata["problem_id"] is None
    assert reply_log.metadata["question_user_id"] == "u-student"
    assert reply_log.metadata["public"] is False
    assert reply_log.metadata["broadcast"] is False


def test_judge_contest_clarification_route_requires_read_all_permission(client: TestClient, auth_headers) -> None:
    created = client.post(
        "/api/v1/contests/C1001/clarifications",
        headers=auth_headers("alice"),
        json={"question": "judge clar route"},
    )
    assert created.status_code == 200, created.text

    anonymous = client.get("/api/v1/judge/clar/C1001")
    student = client.get("/api/v1/judge/clar/C1001", headers=auth_headers("alice"))
    judge = client.get("/api/v1/judge/clar/C1001", headers=auth_headers("judge"))

    assert anonymous.status_code == 401
    assert student.status_code == 403
    assert judge.status_code == 200
    assert judge.json()[0]["id"] == created.json()["id"]


def test_judge_contest_clarification_route_rejects_unknown_contest(client: TestClient, auth_headers) -> None:
    response = client.get("/api/v1/judge/clar/C404", headers=auth_headers("judge"))
    assert response.status_code == 404


def test_contest_judge_monitor_requires_judge_permission_and_filters_contest_scope(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    contest.end_at = datetime(2026, 5, 26, 17, 0, tzinfo=timezone.utc)
    store.update_contest(contest)

    code_a = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1001", "language": "python", "source_code": "print('c1001')\n"},
    )
    assert code_a.status_code == 200, code_a.text
    objective_a = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1003", "answers": {"choice": "B"}},
    )
    assert objective_a.status_code == 200, objective_a.text
    clar_a = client.post(
        "/api/v1/contests/C1001/clarifications",
        headers=auth_headers("alice"),
        json={"question": "monitor question A", "problem_id": "P1001"},
    )
    assert clar_a.status_code == 200, clar_a.text

    second_contest = store.get_contest("C1001").model_copy(deep=True)
    second_contest.id = "C2001"
    second_contest.title = "Second Contest"
    second_contest.problem_ids = ["P1002"]
    second_contest.visibility = "public"
    store.add_contest(second_contest)

    code_b = client.post(
        "/api/v1/contests/C2001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1002", "answers": {"edge_formula": "n(n-1)/2"}},
    )
    assert code_b.status_code == 200, code_b.text
    clar_b = client.post(
        "/api/v1/contests/C2001/clarifications",
        headers=auth_headers("alice"),
        json={"question": "monitor question B", "problem_id": "P1002"},
    )
    assert clar_b.status_code == 200, clar_b.text
    ann_a = client.post(
        "/api/v1/contests/C1001/announcements",
        headers=auth_headers("judge"),
        json={"title": "C1001 Announcement", "content": "Only for C1001"},
    )
    assert ann_a.status_code == 200, ann_a.text
    ann_b = client.post(
        "/api/v1/contests/C2001/announcements",
        headers=auth_headers("judge"),
        json={"title": "C2001 Announcement", "content": "Only for C2001"},
    )
    assert ann_b.status_code == 200, ann_b.text

    anonymous = client.get("/api/v1/judge/monitor/C1001")
    student = client.get("/api/v1/judge/monitor/C1001", headers=auth_headers("alice"))
    coach = client.get("/api/v1/judge/monitor/C1001", headers=auth_headers("coach"))
    judge = client.get("/api/v1/judge/monitor/C1001", headers=auth_headers("judge"))

    assert anonymous.status_code == 401
    assert student.status_code == 403
    assert coach.status_code == 200, coach.text
    assert judge.status_code == 200, judge.text

    payload = judge.json()
    assert payload["contest"]["id"] == "C1001"
    assert payload["queue"]["depth"] == 1
    assert all(item["contest_id"] == "C1001" for item in payload["last_submissions"])
    assert code_a.json()["id"] in {item["id"] for item in payload["last_submissions"]}
    assert objective_a.json()["id"] in {item["id"] for item in payload["last_submissions"]}
    assert code_b.json()["id"] not in {item["id"] for item in payload["last_submissions"]}
    assert clar_a.json()["id"] in {item["id"] for item in payload["clarifications"]}
    assert clar_b.json()["id"] not in {item["id"] for item in payload["clarifications"]}
    assert ann_a.json()["id"] in {item["id"] for item in payload["announcements"]}
    assert ann_b.json()["id"] not in {item["id"] for item in payload["announcements"]}
    assert payload["balloons"][0]["contest_id"] == "C1001"
    assert all(item["contest_id"] == "C1001" for item in payload["balloons"])


def test_contest_judge_monitor_rejects_unknown_contest(client: TestClient, auth_headers) -> None:
    response = client.get("/api/v1/judge/monitor/C404", headers=auth_headers("judge"))
    assert response.status_code == 404


def test_contest_clarification_rejects_problem_outside_contest(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/api/v1/contests/C1001/clarifications",
        headers=auth_headers("alice"),
        json={"question": "P1004 is not part of this contest.", "problem_id": "P1004"},
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
        json={"question": "Only I should see this question."},
    )
    assert created.status_code == 200, created.text
    clarification_id = created.json()["id"]

    replied = client.patch(
        f"/api/v1/clarifications/{clarification_id}",
        headers=auth_headers("judge"),
        json={"answer": "绉佹湁绛斿", "public": False},
    )
    assert replied.status_code == 200, replied.text

    other_student = client.get("/api/v1/contests/C1001/clarifications", headers=auth_headers("coach"))
    assert other_student.status_code == 200, other_student.text
    assert all(item["id"] != clarification_id for item in other_student.json())


def test_contest_announcements_follow_contest_visibility_and_permission(client: TestClient, auth_headers, store) -> None:
    created = client.post(
        "/api/v1/contests/C1001/announcements",
        headers=auth_headers("judge"),
        json={"title": "Warmup", "content": "10 minutes left."},
    )
    assert created.status_code == 200, created.text

    public_list = client.get("/api/v1/contests/C1001/announcements")
    assert public_list.status_code == 200, public_list.text
    assert public_list.json()[0]["id"] == created.json()["id"]

    contest = store.get_contest("C1001")
    assert contest is not None
    contest.visibility = "private"
    store.update_contest(contest)

    anonymous = client.get("/api/v1/contests/C1001/announcements")
    student = client.get("/api/v1/contests/C1001/announcements", headers=auth_headers("alice"))
    judge = client.get("/api/v1/contests/C1001/announcements", headers=auth_headers("judge"))

    assert anonymous.status_code == 404
    assert student.status_code == 403
    assert judge.status_code == 200
    assert judge.json()[0]["id"] == created.json()["id"]


def test_contest_announcements_require_manage_or_judge_permission(client: TestClient, auth_headers) -> None:
    student_denied = client.post(
        "/api/v1/contests/C1001/announcements",
        headers=auth_headers("alice"),
        json={"title": "Nope", "content": "Student cannot post."},
    )
    assert student_denied.status_code == 403

    coach_created = client.post(
        "/api/v1/contests/C1001/announcements",
        headers=auth_headers("coach"),
        json={"title": "Coach Notice", "content": "Lineup check."},
    )
    assert coach_created.status_code == 200, coach_created.text
    assert coach_created.json()["created_by"] == "u-coach"

    judge_created = client.post(
        "/api/v1/contests/C1001/announcements",
        headers=auth_headers("judge"),
        json={"title": "Judge Notice", "content": "Do not refresh."},
    )
    assert judge_created.status_code == 200, judge_created.text
    assert judge_created.json()["created_by"] == "u-judge"


def test_private_contest_announcements_only_notify_owned_students(client: TestClient, auth_headers, store) -> None:
    submitted = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1003", "answers": {"choice": "B"}},
    )
    assert submitted.status_code == 200, submitted.text

    contest = store.get_contest("C1001")
    assert contest is not None
    contest.visibility = "private"
    store.update_contest(contest)

    created = client.post(
        "/api/v1/contests/C1001/announcements",
        headers=auth_headers("judge"),
        json={"title": "Private Notice", "content": "Only participants should receive this."},
    )
    assert created.status_code == 200, created.text

    alice_notifications = client.get("/api/v1/notifications", headers=auth_headers("alice"))
    coach_notifications = client.get("/api/v1/notifications", headers=auth_headers("coach"))
    assert alice_notifications.status_code == 200, alice_notifications.text
    assert coach_notifications.status_code == 200, coach_notifications.text

    assert any(item["title"] == "比赛公告：Private Notice" for item in alice_notifications.json())
    assert all(item["title"] != "比赛公告：Private Notice" for item in coach_notifications.json())


def test_contest_print_reads_submission_or_request_only(client: TestClient, auth_headers, store) -> None:
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
    own_body = own_print.json()
    assert "print only" in own_body["source_code"]
    assert own_body["status"] == "pending"
    assert own_body["source_kind"] == "submission"
    assert own_body["user_id"] == "u-student"
    assert store.list_contest_print_jobs("C1001")[0].id == own_body["id"]

    own_list = client.get("/api/v1/contests/C1001/print", headers=auth_headers("alice"))
    assert own_list.status_code == 200, own_list.text
    assert own_list.json()[0]["id"] == own_body["id"]
    assert "source_code" not in own_list.json()[0]

    judge_detail = client.get(f"/api/v1/contests/C1001/print/{own_body['id']}", headers=auth_headers("judge"))
    assert judge_detail.status_code == 200, judge_detail.text
    assert judge_detail.json()["source_code"] == own_body["source_code"]

    printed = client.patch(
        f"/api/v1/contests/C1001/print/{own_body['id']}",
        headers=auth_headers("judge"),
        json={"status": "printed", "note": "sent to printer A"},
    )
    assert printed.status_code == 200, printed.text
    printed_body = printed.json()
    assert printed_body["status"] == "printed"
    assert printed_body["printed_by"] == "u-judge"
    assert printed_body["printed_at"] is not None
    assert printed_body["note"] == "sent to printer A"

    coach = store.get_user("u-coach")
    assert coach is not None
    coach.role = "student"
    store.update_user(coach)

    other_student_list = client.get("/api/v1/contests/C1001/print", headers=auth_headers("coach"))
    assert other_student_list.status_code == 200, other_student_list.text
    assert all(item["id"] != own_body["id"] for item in other_student_list.json())

    other_student_detail = client.get(f"/api/v1/contests/C1001/print/{own_body['id']}", headers=auth_headers("coach"))
    assert other_student_detail.status_code == 403

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
    assert judge_adhoc.json()["status"] == "pending"


def test_private_contest_print_allows_existing_owner_and_blocks_non_owner(client: TestClient, auth_headers, store) -> None:
    submitted = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1001", "language": "python", "source_code": "print('private owner')\n"},
    )
    assert submitted.status_code == 200, submitted.text
    submission_id = submitted.json()["id"]

    contest = store.get_contest("C1001")
    assert contest is not None
    contest.visibility = "private"
    store.update_contest(contest)

    coach = store.get_user("u-coach")
    assert coach is not None
    coach.role = "student"
    store.update_user(coach)

    owner_print = client.post(
        "/api/v1/contests/C1001/print",
        headers=auth_headers("alice"),
        json={"submission_id": submission_id},
    )
    assert owner_print.status_code == 200, owner_print.text
    assert owner_print.json()["source_kind"] == "submission"

    non_owner_list = client.get("/api/v1/contests/C1001/print", headers=auth_headers("coach"))
    non_owner_print = client.post(
        "/api/v1/contests/C1001/print",
        headers=auth_headers("coach"),
        json={"submission_id": submission_id},
    )

    assert non_owner_list.status_code == 403
    assert non_owner_print.status_code == 403


def test_contest_print_requires_problem_scope_and_writes_audit(client: TestClient, auth_headers, store) -> None:
    missing_problem = client.post(
        "/api/v1/contests/C1001/print",
        headers=auth_headers("judge"),
        json={"source_code": "print('manual')\n"},
    )
    assert missing_problem.status_code == 400

    outside_problem = client.post(
        "/api/v1/contests/C1001/print",
        headers=auth_headers("judge"),
        json={"problem_id": "P1004", "source_code": "print('manual')\n"},
    )
    assert outside_problem.status_code == 404

    printed = client.post(
        "/api/v1/contests/C1001/print",
        headers=auth_headers("judge"),
        json={"problem_id": "P1001", "language": "python", "source_code": "print('manual')\n"},
    )
    assert printed.status_code == 200, printed.text
    payload = printed.json()
    assert payload["source_kind"] == "request"
    assert payload["problem_id"] == "P1001"

    logs, total = store.list_audit_logs(action="contest.print")
    assert total == 1
    metadata = logs[0].metadata
    assert metadata["problem_id"] == "P1001"
    assert metadata["source_kind"] == "request"
    assert "source_sha256" in metadata
    assert "source_code" not in metadata


def test_contest_freeze_and_rejudge_require_manage_permission(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    contest.start_at = datetime.now(timezone.utc) - timedelta(hours=2)
    contest.end_at = datetime.now(timezone.utc) + timedelta(hours=1)
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

    contest.end_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    store.update_contest(contest)

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
    contest.start_at = datetime.now(timezone.utc) - timedelta(hours=2)
    contest.end_at = datetime.now(timezone.utc) + timedelta(hours=1)
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

    contest.end_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    store.update_contest(contest)

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


def test_contest_rejudge_filters_stay_inside_contest_and_problem_scope(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    current = datetime.now(timezone.utc)
    contest.start_at = current - timedelta(hours=4)
    contest.end_at = current - timedelta(minutes=1)
    contest.problem_ids = ["P1001", "P1002"]
    contest.problem_layout = [
        ContestProblemLayoutItem(problem_id="P1001", problem_key="A", allowed_languages=["python"]),
        ContestProblemLayoutItem(problem_id="P1002", problem_key="B", allowed_languages=[]),
    ]
    store.update_contest(contest)

    inside_target = _contest_submission(
        "S-P6-07-IN-TARGET",
        user_id="u-student",
        contest_id="C1001",
        problem_id="P1001",
        problem_title="A+B Problem",
        problem_type="code",
        status="accepted",
        created_at=current - timedelta(hours=3),
        judged_at=current - timedelta(hours=3),
    )
    inside_other_problem = _contest_submission(
        "S-P6-07-IN-OTHER",
        user_id="u-student",
        contest_id="C1001",
        problem_id="P1002",
        problem_title="Complete Graph Edges",
        problem_type="code",
        status="accepted",
        created_at=current - timedelta(hours=3, minutes=5),
        judged_at=current - timedelta(hours=3, minutes=5),
    )
    outside_contest = _contest_submission(
        "S-P6-07-OUT-CONTEST",
        user_id="u-student",
        contest_id="C9999",
        problem_id="P1001",
        problem_title="A+B Problem",
        problem_type="code",
        status="accepted",
        created_at=current - timedelta(hours=3, minutes=10),
        judged_at=current - timedelta(hours=3, minutes=10),
    )
    outside_problem_set = _contest_submission(
        "S-P6-07-OUT-PROBLEM",
        user_id="u-student",
        contest_id="C1001",
        problem_id="P1003",
        problem_title="Single Choice",
        problem_type="code",
        status="accepted",
        created_at=current - timedelta(hours=3, minutes=15),
        judged_at=current - timedelta(hours=3, minutes=15),
    )
    for submission in [inside_target, inside_other_problem, outside_contest, outside_problem_set]:
        store.add_submission(submission)

    response = client.post(
        "/api/v1/contests/C1001/rejudge",
        headers=auth_headers("judge"),
        json={
            "submission_ids": [
                inside_target.id,
                inside_other_problem.id,
                outside_contest.id,
                outside_problem_set.id,
                "S-P6-07-MISSING",
            ],
            "problem_id": "P1001",
            "statuses": ["accepted"],
            "reason": "scoped contest hacking",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["requeued_count"] == 1
    assert [item["id"] for item in payload["requeued"]] == [inside_target.id]
    skipped = {item["submission_id"]: item["reason"] for item in payload["skipped"]}
    assert "Problem P1002 is outside" in skipped[inside_other_problem.id]
    assert skipped[outside_contest.id] == "Submission does not belong to this contest"
    assert skipped[outside_problem_set.id] == "Submission problem is not part of this contest"
    assert skipped["S-P6-07-MISSING"] == "Submission not found"
    assert store.get_submission(inside_target.id).status == "queued"
    assert store.get_submission(inside_other_problem.id).status == "accepted"
    assert store.get_submission(outside_contest.id).status == "accepted"

    logs, total = store.list_audit_logs(action="contest.rejudge")
    assert total == 1
    assert logs[0].metadata["problem_id"] == "P1001"
    assert logs[0].metadata["statuses"] == ["accepted"]


def test_contest_rejudge_clears_stale_balloon_for_requeued_submission(client: TestClient, auth_headers, store) -> None:
    from app.db import now
    from app.services import refresh_contest_balloon_for_submission

    contest = store.get_contest("C1001")
    assert contest is not None
    contest.start_at = now() - timedelta(hours=4)
    contest.end_at = now() - timedelta(minutes=1)
    contest.rule = "ACM"
    store.update_contest(contest)

    accepted = _contest_submission(
        "S-P6-07-AC-BALLOON",
        user_id="u-student",
        contest_id="C1001",
        problem_id="P1001",
        problem_title="A+B Problem",
        problem_type="code",
        status="accepted",
        created_at=now() - timedelta(hours=3),
        judged_at=now() - timedelta(hours=3),
    )
    store.add_submission(accepted)
    assert refresh_contest_balloon_for_submission(store, accepted) is not None
    assert store.list_contest_balloons("C1001")

    response = client.post(
        "/api/v1/contests/C1001/rejudge",
        headers=auth_headers("judge"),
        json={"reason": "accepted source changed"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["requeued_count"] == 1
    assert store.get_submission(accepted.id).status == "queued"
    assert store.list_contest_balloons("C1001") == []


def test_submission_override_refreshes_contest_balloon(client: TestClient, auth_headers, store) -> None:
    from app.db import now

    contest = store.get_contest("C1001")
    assert contest is not None
    contest.start_at = now() - timedelta(hours=1)
    contest.end_at = now() + timedelta(hours=1)
    contest.rule = "ACM"
    store.update_contest(contest)

    submission = _contest_submission(
        "S-P6-07-OVERRIDE-AC",
        user_id="u-student",
        contest_id="C1001",
        problem_id="P1001",
        problem_title="A+B Problem",
        problem_type="code",
        status="wrong_answer",
        created_at=now() - timedelta(minutes=20),
        judged_at=now() - timedelta(minutes=20),
        score=0,
    )
    store.add_submission(submission)

    response = client.post(
        f"/api/v1/judge/submissions/{submission.id}/override",
        headers=auth_headers("judge"),
        json={"status": "accepted", "score": 100, "message": "manual AC after appeal"},
    )

    assert response.status_code == 200, response.text
    balloons = store.list_contest_balloons("C1001")
    assert len(balloons) == 1
    assert balloons[0]["submission_id"] == submission.id
    assert balloons[0]["eligible"] is True


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


def test_auto_freeze_can_be_unfrozen_and_disables_default_window(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    current = datetime.now(timezone.utc)
    start_at = current - timedelta(minutes=90)
    contest.rule = "ACM"
    contest.start_at = start_at
    contest.end_at = start_at + timedelta(hours=2)
    contest.frozen = False
    contest.freeze_disabled = False
    contest.frozen_at = None
    store.update_contest(contest)

    detail = client.get("/api/v1/contests/C1001")
    assert detail.status_code == 200, detail.text
    assert detail.json()["freeze_active"] is True

    unfreeze = client.post(
        "/api/v1/contests/C1001/unfreeze",
        headers=auth_headers("admin"),
        json={"reason": "open public board"},
    )
    assert unfreeze.status_code == 200, unfreeze.text
    payload = unfreeze.json()
    assert payload["frozen"] is False
    assert payload["freeze_disabled"] is True
    assert payload["freeze_active"] is False
    assert payload["freeze_effective_at"] is None


def test_acm_standings_include_penalty_and_first_blood(client: TestClient, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    start_at = datetime.now(timezone.utc) - timedelta(hours=1)
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
            problem_title="Complete Graph Edges",
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
            problem_title="Complete Graph Edges",
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


def test_acm_standings_ignore_records_outside_contest_problem_set(client: TestClient, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    start_at = datetime(2026, 5, 26, 1, 0, tzinfo=timezone.utc)
    contest.start_at = start_at
    contest.end_at = start_at + timedelta(hours=5)
    contest.problem_ids = ["P1001"]
    contest.problem_layout = [ContestProblemLayoutItem(problem_id="P1001", problem_key="A")]
    store.update_contest(contest)

    store.add_submission(
        _contest_submission(
            "S-ACM-INSIDE",
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
            "S-ACM-OUTSIDE",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1002",
            problem_title="Complete Graph Edges",
            problem_type="blank",
            status="accepted",
            score=100,
            created_at=start_at + timedelta(minutes=15),
            judged_at=start_at + timedelta(minutes=15),
        )
    )

    response = client.get("/api/v1/contests/C1001/standings")
    assert response.status_code == 200, response.text
    alice = next(row for row in response.json() if row["user_id"] == "u-student")

    assert alice["solved"] == 0
    assert alice["penalty"] == 0
    assert "P1001" in alice["problems"]
    assert "P1002" not in alice["problems"]


def test_acm_standings_use_submit_time_for_penalty_and_first_blood(client: TestClient, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    start_at = datetime(2026, 5, 26, 1, 0, tzinfo=timezone.utc)
    contest.start_at = start_at
    contest.end_at = start_at + timedelta(hours=5)
    contest.frozen = False
    store.update_contest(contest)

    coach = store.get_user("u-coach")
    assert coach is not None
    coach.role = "student"
    store.update_user(coach)

    store.add_submission(
        _contest_submission(
            "S-ACM-DELAYED-ALICE-WA",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="wrong_answer",
            score=0,
            created_at=start_at + timedelta(minutes=8),
            judged_at=start_at + timedelta(minutes=80),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-ACM-DELAYED-ALICE-AC",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="accepted",
            created_at=start_at + timedelta(minutes=18),
            judged_at=start_at + timedelta(minutes=90),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-ACM-DELAYED-COACH-AC",
            user_id="u-coach",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="accepted",
            created_at=start_at + timedelta(minutes=20),
            judged_at=start_at + timedelta(minutes=30),
        )
    )

    response = client.get("/api/v1/contests/C1001/standings")
    assert response.status_code == 200, response.text
    body = response.json()

    alice = next(row for row in body if row["user_id"] == "u-student")
    coach_row = next(row for row in body if row["user_id"] == "u-coach")

    assert alice["penalty"] == 38
    assert alice["problems"]["P1001"]["penalty_minutes"] == 38
    assert alice["problems"]["P1001"]["first_blood"] is True
    assert coach_row["problems"]["P1001"]["first_blood"] is False


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
            problem_title="Complete Graph Edges",
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
            problem_title="Complete Graph Edges",
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


def test_acm_standings_freeze_uses_submit_time_not_judge_time(client: TestClient, store) -> None:
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
            "S-FREEZE-DELAYED-AC",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1002",
            problem_title="Complete Graph Edges",
            problem_type="blank",
            status="accepted",
            score=100,
            created_at=start_at + timedelta(minutes=50),
            judged_at=start_at + timedelta(minutes=70),
        )
    )

    response = client.get("/api/v1/contests/C1001/standings")
    assert response.status_code == 200, response.text
    alice = next(row for row in response.json() if row["user_id"] == "u-student")

    assert alice["solved"] == 1
    assert alice["penalty"] == 50
    assert alice["problems"]["P1002"]["accepted_at"] is not None


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
            problem_title="Complete Graph Edges",
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
            problem_title="Complete Graph Edges",
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


def test_public_freeze_view_hides_late_only_rows_and_problem_summary(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    start_at = datetime(2026, 5, 26, 1, 0, tzinfo=timezone.utc)
    contest.start_at = start_at
    contest.end_at = start_at + timedelta(hours=5)
    contest.frozen = True
    contest.frozen_at = start_at + timedelta(minutes=60)
    store.update_contest(contest)

    coach = store.get_user("u-coach")
    assert coach is not None
    coach.role = "student"
    store.update_user(coach)

    store.add_submission(
        _contest_submission(
            "S-LATE-ONLY-AC",
            user_id="u-coach",
            contest_id="C1001",
            problem_id="P1002",
            problem_title="Complete Graph Edges",
            problem_type="blank",
            status="accepted",
            created_at=start_at + timedelta(minutes=80),
            judged_at=start_at + timedelta(minutes=80),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-EARLY-ONLY-WA",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1002",
            problem_title="Complete Graph Edges",
            problem_type="blank",
            status="wrong_answer",
            score=0,
            created_at=start_at + timedelta(minutes=40),
            judged_at=start_at + timedelta(minutes=40),
        )
    )

    public_standings = client.get("/api/v1/contests/C1001/standings")
    public_detail = client.get("/api/v1/contests/C1001")
    judge_standings = client.get("/api/v1/contests/C1001/standings", headers=auth_headers("judge"))
    judge_detail = client.get("/api/v1/contests/C1001", headers=auth_headers("judge"))

    assert public_standings.status_code == 200, public_standings.text
    assert public_detail.status_code == 200, public_detail.text
    assert judge_standings.status_code == 200, judge_standings.text
    assert judge_detail.status_code == 200, judge_detail.text

    assert all(row["user_id"] != "u-coach" for row in public_standings.json())
    assert any(row["user_id"] == "u-coach" for row in judge_standings.json())

    public_problem = next(item for item in public_detail.json()["problems"] if item["id"] == "P1002")
    judge_problem = next(item for item in judge_detail.json()["problems"] if item["id"] == "P1002")
    assert public_problem["accepted"] == 0
    assert public_problem["attempts"] == 1
    assert judge_problem["accepted"] == 1
    assert judge_problem["attempts"] == 2


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
            problem_title="Complete Graph Edges",
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
            problem_title="Complete Graph Edges",
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
            problem_title="浜屽垎鏌ユ壘閫傜敤鏉′欢",
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


def test_external_and_live_board_only_expose_public_frozen_view(client: TestClient, auth_headers, store) -> None:
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
            "S-BOARD-WA",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1002",
            problem_title="Complete Graph Edges",
            problem_type="blank",
            status="wrong_answer",
            score=0,
            created_at=start_at + timedelta(minutes=30),
            judged_at=start_at + timedelta(minutes=30),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-BOARD-AC",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1002",
            problem_title="Complete Graph Edges",
            problem_type="blank",
            status="accepted",
            created_at=start_at + timedelta(minutes=70),
            judged_at=start_at + timedelta(minutes=70),
        )
    )

    external = client.get("/api/v1/contests/C1001/external-board")
    live = client.get("/api/v1/contests/C1001/live-board")
    internal_judge = client.get("/api/v1/contests/C1001/standings", headers=auth_headers("judge"))

    assert external.status_code == 200, external.text
    assert live.status_code == 200, live.text
    assert internal_judge.status_code == 200, internal_judge.text

    external_payload = external.json()
    live_payload = live.json()
    judge_payload = internal_judge.json()

    assert external_payload["board_kind"] == "external"
    assert live_payload["board_kind"] == "live"
    assert external_payload["contest"]["freeze_active"] is True
    assert live_payload["contest"]["freeze_active"] is True

    external_row = next(row for row in external_payload["standings"] if row["user_id"] == "u-student")
    live_row = next(row for row in live_payload["standings"] if row["user_id"] == "u-student")
    judge_row = next(row for row in judge_payload if row["user_id"] == "u-student")

    assert external_row["solved"] == 0
    assert external_row["problems"]["P1002"]["accepted_at"] is None
    assert live_row == external_row
    assert judge_row["solved"] == 1
    assert judge_row["problems"]["P1002"]["accepted_at"] is not None


def test_external_and_live_board_hide_private_contest(client: TestClient, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    contest.visibility = "private"
    store.update_contest(contest)

    external = client.get("/api/v1/contests/C1001/external-board")
    live = client.get("/api/v1/contests/C1001/live-board")

    assert external.status_code == 404
    assert live.status_code == 404


def test_rolling_board_requires_judge_or_manage_and_contest_end(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    start_at = datetime.now(timezone.utc) - timedelta(hours=1)
    contest.start_at = start_at
    contest.end_at = start_at + timedelta(hours=5)
    contest.frozen = True
    contest.frozen_at = start_at + timedelta(minutes=60)
    store.update_contest(contest)

    store.add_submission(
        _contest_submission(
            "S-ROLL-WA",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="wrong_answer",
            score=0,
            created_at=start_at + timedelta(minutes=20),
            judged_at=start_at + timedelta(minutes=20),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-ROLL-AC",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="accepted",
            created_at=start_at + timedelta(minutes=80),
            judged_at=start_at + timedelta(minutes=80),
        )
    )

    anonymous = client.get("/api/v1/contests/C1001/rolling-board")
    student = client.get("/api/v1/contests/C1001/rolling-board", headers=auth_headers("alice"))
    judge_during = client.get("/api/v1/contests/C1001/rolling-board", headers=auth_headers("judge"))
    admin_during = client.get("/api/v1/contests/C1001/rolling-board", headers=auth_headers("admin"))

    assert anonymous.status_code == 401
    assert student.status_code == 403
    assert judge_during.status_code == 409
    assert admin_during.status_code == 409

    contest.end_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    store.update_contest(contest)

    judge_after = client.get("/api/v1/contests/C1001/rolling-board", headers=auth_headers("judge"))
    admin_after = client.get("/api/v1/contests/C1001/rolling-board", headers=auth_headers("admin"))

    assert judge_after.status_code == 200, judge_after.text
    assert admin_after.status_code == 200, admin_after.text

    judge_payload = judge_after.json()
    public_row = next(row for row in judge_payload["public_standings"] if row["user_id"] == "u-student")
    final_row = next(row for row in judge_payload["final_standings"] if row["user_id"] == "u-student")

    assert public_row["solved"] == 0
    assert public_row["problems"]["P1001"]["accepted_at"] is None
    assert final_row["solved"] == 1
    assert final_row["problems"]["P1001"]["accepted_at"] is not None


def test_contest_submission_status_view_limits_students_to_own_records(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    start_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    contest.start_at = start_at
    contest.end_at = start_at + timedelta(hours=2)
    store.update_contest(contest)

    store.add_submission(
        _contest_submission(
            "S-CONTEST-OWN",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="accepted",
            created_at=start_at + timedelta(minutes=5),
            judged_at=start_at + timedelta(minutes=5),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-CONTEST-OTHER",
            user_id="u-coach",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="wrong_answer",
            created_at=start_at + timedelta(minutes=8),
            judged_at=start_at + timedelta(minutes=8),
        )
    )

    response = client.get("/api/v1/contests/C1001/submissions", headers=auth_headers("alice"))
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["contest_id"] == "C1001"
    assert body["can_view_all"] is False
    assert body["show_team_view"] is False
    assert len(body["submissions"]) == 1
    assert body["submissions"][0]["id"] == "S-CONTEST-OWN"
    assert body["submissions"][0]["can_view_source"] is True
    assert body["submissions"][0]["source_code"] is not None
    assert body["teams"] == []


def test_contest_submission_status_view_groups_teams_for_judge(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    start_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    contest.start_at = start_at
    contest.end_at = start_at + timedelta(hours=2)
    store.update_contest(contest)

    coach = store.get_user("u-coach")
    assert coach is not None
    coach.role = "student"
    store.update_user(coach)

    team = Team(
        id="T2001",
        name="Contest Team",
        description="contest members",
        invite_code="TEAM2001",
        owner_id="u-coach",
        member_ids=["u-student", "u-coach"],
        created_at=start_at,
    )
    store.add_team(team)

    store.add_submission(
        _contest_submission(
            "S-TEAM-1",
            user_id="u-student",
            contest_id="C1001",
            problem_id="P1002",
            problem_title="P1002",
            problem_type="blank",
            status="accepted",
            created_at=start_at + timedelta(minutes=3),
            judged_at=start_at + timedelta(minutes=3),
        )
    )
    store.add_submission(
        _contest_submission(
            "S-TEAM-2",
            user_id="u-coach",
            contest_id="C1001",
            problem_id="P1001",
            problem_title="A+B Problem",
            problem_type="code",
            status="wrong_answer",
            score=0,
            created_at=start_at + timedelta(minutes=4),
            judged_at=start_at + timedelta(minutes=4),
        )
    )

    response = client.get("/api/v1/contests/C1001/submissions", headers=auth_headers("judge"))
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["can_view_all"] is True
    assert body["show_team_view"] is True
    assert len(body["submissions"]) == 2
    assert all(item["team_id"] == "T2001" for item in body["submissions"])
    assert body["teams"]
    team_summary = next(item for item in body["teams"] if item["team_id"] == "T2001")
    assert team_summary["submission_count"] == 2
    assert team_summary["accepted_count"] == 1


def test_contest_submission_rejects_before_start_and_after_end(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    contest.start_at = future
    contest.end_at = future + timedelta(hours=2)
    store.update_contest(contest)

    before_start = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1003", "answers": {"choice": "B"}},
    )
    assert before_start.status_code == 409
    assert before_start.json()["detail"] == "Contest has not started"

    contest.start_at = datetime.now(timezone.utc) - timedelta(hours=2)
    contest.end_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    store.update_contest(contest)

    after_end = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1003", "answers": {"choice": "B"}},
    )
    assert after_end.status_code == 409
    assert after_end.json()["detail"] == "Contest has ended"


def test_contest_submission_respects_problem_language_restrictions(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    contest.start_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    contest.end_at = datetime.now(timezone.utc) + timedelta(hours=1)
    contest.problem_layout = [
        ContestProblemLayoutItem(problem_id="P1001", problem_key="A", allowed_languages=["cpp"]),
        ContestProblemLayoutItem(problem_id="P1002", problem_key="B", allowed_languages=[]),
        ContestProblemLayoutItem(problem_id="P1003", problem_key="C", allowed_languages=[]),
    ]
    store.update_contest(contest)

    forbidden = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1001", "language": "python", "source_code": "print('x')\n"},
    )
    assert forbidden.status_code == 400
    assert "not allowed" in forbidden.json()["detail"]

    allowed = client.post(
        "/api/v1/contests/C1001/submit",
        headers=auth_headers("alice"),
        json={"problem_id": "P1001", "language": "cpp", "source_code": "#include <bits/stdc++.h>\nint main(){return 0;}\n"},
    )
    assert allowed.status_code == 200, allowed.text


def test_regular_submission_routes_cannot_attach_contest_id(client: TestClient, auth_headers, store) -> None:
    contest = store.get_contest("C1001")
    assert contest is not None
    contest.start_at = datetime.now(timezone.utc) + timedelta(hours=1)
    contest.end_at = contest.start_at + timedelta(hours=2)
    contest.problem_layout = [
        ContestProblemLayoutItem(problem_id="P1001", problem_key="A", allowed_languages=["cpp"]),
        ContestProblemLayoutItem(problem_id="P1002", problem_key="B", allowed_languages=[]),
        ContestProblemLayoutItem(problem_id="P1003", problem_key="C", allowed_languages=[]),
    ]
    store.update_contest(contest)

    code_response = client.post(
        "/api/v1/problems/P1001/submit-code",
        headers=auth_headers("alice"),
        json={
            "language": "python",
            "source_code": "print('must stay outside contest')\n",
            "contest_id": "C1001",
        },
    )
    objective_response = client.post(
        "/api/v1/problems/P1003/submit-objective",
        headers=auth_headers("alice"),
        json={"answers": {"choice": "B"}, "contest_id": "C1001"},
    )

    assert code_response.status_code == 422
    assert objective_response.status_code == 422
    assert [submission for submission in store.list_submissions() if submission.contest_id == "C1001"] == []
