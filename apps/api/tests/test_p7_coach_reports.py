from __future__ import annotations

import zipfile
from datetime import timedelta
from io import BytesIO

from fastapi.testclient import TestClient

from app.models import Assignment, ProblemSet, Submission, Team, User
from app.store import now


FORBIDDEN_REPORT_TEXT = [
    "source_code",
    "int main",
    "judge_config",
    "expected",
    "edge_formula",
    "choices",
    "n(n-1)/2",
]


def seed_report_scope(store) -> tuple[User, User]:
    timestamp = now()
    password_hash = store.get_user("u-student").password_hash
    scoped_student = User(
        id="u-report-1",
        username="report1",
        display_name="Report One",
        role="student",
        school="Scoped Report Class",
        email="report1@example.com",
        password_hash=password_hash,
    )
    foreign_student = User(
        id="u-report-2",
        username="report2",
        display_name="Report Two",
        role="student",
        school="Foreign Report Class",
        email="report2@example.com",
        password_hash=password_hash,
    )
    foreign_coach = User(
        id="u-report-coach",
        username="report_coach",
        display_name="Foreign Report Coach",
        role="coach",
        school="Foreign Report Class",
        email="report-coach@example.com",
        password_hash=password_hash,
    )
    scoped_team = Team(
        id="T-REPORT-1",
        name="Report Class",
        description="Coach-owned report class",
        invite_code="REPORT1",
        owner_id="u-coach",
        member_ids=[scoped_student.id],
        created_at=timestamp,
    )
    foreign_team = Team(
        id="T-REPORT-2",
        name="Foreign Report Class",
        description="Foreign coach report class",
        invite_code="REPORT2",
        owner_id=foreign_coach.id,
        member_ids=[foreign_student.id],
        created_at=timestamp,
    )
    scoped_set = ProblemSet(
        id="PS-REPORT-1",
        title="Report Problem Set",
        description="Scoped report set",
        type="assignment",
        visibility="private",
        owner_id="u-coach",
        problem_ids=["P1001", "P1002", "P1003"],
        created_at=timestamp,
        updated_at=timestamp,
    )
    foreign_set = ProblemSet(
        id="PS-REPORT-2",
        title="Foreign Report Set",
        description="Foreign report set",
        type="assignment",
        visibility="private",
        owner_id=foreign_coach.id,
        problem_ids=["P1004"],
        created_at=timestamp,
        updated_at=timestamp,
    )
    scoped_assignment = Assignment(
        id="A-REPORT-1",
        title="Report Export Assignment",
        description="Export scoped data",
        problem_set_id=scoped_set.id,
        team_id=scoped_team.id,
        due_at=timestamp + timedelta(days=3),
        created_by="u-coach",
        created_at=timestamp,
    )
    foreign_assignment = Assignment(
        id="A-REPORT-2",
        title="Foreign Export Assignment",
        description="Hidden foreign data",
        problem_set_id=foreign_set.id,
        team_id=foreign_team.id,
        due_at=timestamp + timedelta(days=3),
        created_by=foreign_coach.id,
        created_at=timestamp,
    )
    scoped_submissions = [
        Submission(
            id="S-REPORT-1",
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
            id="S-REPORT-2",
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
        id="S-REPORT-3",
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
    data["problem_sets"].extend([scoped_set.model_dump(mode="json"), foreign_set.model_dump(mode="json")])
    data["assignments"].extend([scoped_assignment.model_dump(mode="json"), foreign_assignment.model_dump(mode="json")])
    data["submissions"].extend([submission.model_dump(mode="json") for submission in scoped_submissions + [foreign_submission]])
    store._write(data)
    return scoped_student, foreign_student


def assert_report_is_scoped_and_redacted(text: str, scoped_student: User, foreign_student: User) -> None:
    assert scoped_student.display_name in text
    assert "Report Export Assignment" in text
    assert foreign_student.display_name not in text
    assert "Foreign Export Assignment" not in text
    for forbidden in FORBIDDEN_REPORT_TEXT:
        assert forbidden not in text


def test_coach_report_csv_is_scoped_and_redacted(client: TestClient, auth_headers, store) -> None:
    scoped_student, foreign_student = seed_report_scope(store)

    response = client.get("/api/v1/coach/reports/export?format=csv", headers=auth_headers("coach"))

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "coach-report-" in response.headers["content-disposition"]
    assert response.headers["content-disposition"].endswith('.csv"')
    assert_report_is_scoped_and_redacted(response.content.decode("utf-8-sig"), scoped_student, foreign_student)
    audit_logs, total = store.list_audit_logs(action="coach.report.export")
    assert total == 1
    assert audit_logs[0].metadata["format"] == "csv"


def test_coach_report_xlsx_can_open_and_is_redacted(client: TestClient, auth_headers, store) -> None:
    scoped_student, foreign_student = seed_report_scope(store)

    response = client.get("/api/v1/coach/reports/export?format=xlsx", headers=auth_headers("coach"))

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.headers["content-disposition"].endswith('.xlsx"')
    with zipfile.ZipFile(BytesIO(response.content)) as workbook:
        names = set(workbook.namelist())
        assert "xl/workbook.xml" in names
        assert "xl/worksheets/sheet1.xml" in names
        assert "xl/worksheets/sheet5.xml" in names
        combined_xml = "\n".join(workbook.read(name).decode("utf-8") for name in sorted(names) if name.endswith(".xml"))
    assert_report_is_scoped_and_redacted(combined_xml, scoped_student, foreign_student)


def test_coach_report_requires_analytics_permission(client: TestClient, auth_headers) -> None:
    assert client.get("/api/v1/coach/reports/export?format=csv").status_code == 401

    response = client.get("/api/v1/coach/reports/export?format=csv", headers=auth_headers("alice"))

    assert response.status_code == 403


def test_coach_report_rejects_invalid_format(client: TestClient, auth_headers) -> None:
    response = client.get("/api/v1/coach/reports/export?format=pdf", headers=auth_headers("coach"))

    assert response.status_code == 422
