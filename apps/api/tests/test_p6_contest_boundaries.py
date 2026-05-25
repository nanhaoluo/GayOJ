from __future__ import annotations

from fastapi.testclient import TestClient


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
        headers=auth_headers("judge"),
        json={"reason": "judge cannot freeze"},
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
