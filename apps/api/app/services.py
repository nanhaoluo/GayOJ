from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import re
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from xml.sax.saxutils import escape as xml_escape

from .config import OFFLINE_PACK_SECRET, OFFLINE_PACK_TTL_HOURS
from .models import (
    Assignment,
    AssignmentAnalytics,
    AssignmentProgressState,
    AssignmentStudentStatus,
    ActivityHeatmapCell,
    CoachAnalyticsResponse,
    CoachSimilarityFinding,
    CoachSimilarityFilterOption,
    CoachSimilarityResponse,
    CoachSimilarityStudent,
    ContestBalloon,
    Contest,
    CoachReportFormat,
    ObjectiveItemResult,
    Problem,
    ProblemTypeMastery,
    ProblemSet,
    StudentAbilityProfile,
    Submission,
    TagMastery,
    Team,
    User,
)


PACK_SECRET = OFFLINE_PACK_SECRET
CODE_SIMILARITY_TOKEN_PATTERN = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|==|!=|<=|>=|&&|\|\||[{}()\[\];,.:+\-*/%<>=\"']"
)
CODE_SIMILARITY_COMMENT_PATTERN = re.compile(r"//.*?$|/\*.*?\*/|#.*?$", re.MULTILINE | re.DOTALL)
COACH_REPORT_MIME_TYPES: dict[CoachReportFormat, str] = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def make_submission_id() -> str:
    return f"S{uuid4().hex[:10].upper()}"


def ensure_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def assignment_student_state(
    *,
    problem_ids: set[str],
    solved_ids: set[str],
    due_at: datetime,
    now_value: datetime,
) -> AssignmentProgressState:
    if problem_ids and problem_ids.issubset(solved_ids):
        return "completed"
    if solved_ids:
        return "overdue" if now_value > due_at else "in_progress"
    return "overdue" if now_value > due_at else "not_started"


def submission_is_full_score(submission: Submission) -> bool:
    return submission.status in {"accepted", "manual_override"} and submission.score >= submission.max_score


def mastery_accuracy(accepted: int, attempts: int) -> float:
    return accepted / attempts if attempts else 0.0


def build_activity_heatmap(submissions: list[Submission]) -> list[ActivityHeatmapCell]:
    buckets: dict[str, dict[str, Any]] = {}
    for submission in submissions:
        submitted_at = ensure_utc_datetime(submission.judged_at) or ensure_utc_datetime(submission.created_at)
        if submitted_at is None:
            continue
        key = submitted_at.date().isoformat()
        bucket = buckets.setdefault(key, {"attempts": 0, "accepted": 0, "students": set()})
        bucket["attempts"] += 1
        bucket["students"].add(submission.user_id)
        if submission_is_full_score(submission):
            bucket["accepted"] += 1
    return [
        ActivityHeatmapCell(
            date=date,
            attempts=value["attempts"],
            accepted=value["accepted"],
            active_students=len(value["students"]),
        )
        for date, value in sorted(buckets.items())
    ]


def build_tag_mastery(
    submissions: list[Submission],
    problem_by_id: dict[str, Problem],
) -> list[TagMastery]:
    buckets: dict[str, dict[str, Any]] = {}
    for submission in submissions:
        problem = problem_by_id.get(submission.problem_id)
        if not problem:
            continue
        accepted = submission_is_full_score(submission)
        for tag in problem.tags:
            bucket = buckets.setdefault(tag, {"attempts": 0, "accepted": 0, "solved": set(), "students": set()})
            bucket["attempts"] += 1
            bucket["students"].add(submission.user_id)
            if accepted:
                bucket["accepted"] += 1
                bucket["solved"].add(submission.problem_id)
    return [
        TagMastery(
            tag=tag,
            attempts=value["attempts"],
            accepted=value["accepted"],
            solved=len(value["solved"]),
            student_count=len(value["students"]),
            accuracy=mastery_accuracy(value["accepted"], value["attempts"]),
        )
        for tag, value in sorted(buckets.items(), key=lambda item: (-item[1]["attempts"], item[0]))
    ]


def build_type_mastery(
    submissions: list[Submission],
    problem_by_id: dict[str, Problem],
) -> list[ProblemTypeMastery]:
    buckets: dict[str, dict[str, Any]] = {}
    for submission in submissions:
        problem = problem_by_id.get(submission.problem_id)
        problem_type = problem.type if problem else submission.problem_type
        bucket = buckets.setdefault(str(problem_type), {"attempts": 0, "accepted": 0, "solved": set()})
        bucket["attempts"] += 1
        if submission_is_full_score(submission):
            bucket["accepted"] += 1
            bucket["solved"].add(submission.problem_id)
    return [
        ProblemTypeMastery(
            problem_type=problem_type,
            attempts=value["attempts"],
            accepted=value["accepted"],
            solved=len(value["solved"]),
            accuracy=mastery_accuracy(value["accepted"], value["attempts"]),
        )
        for problem_type, value in sorted(buckets.items())
    ]


def build_student_ability_profile(
    student: User,
    submissions: list[Submission],
    problem_by_id: dict[str, Problem],
) -> StudentAbilityProfile:
    sorted_submissions = sorted(
        submissions,
        key=lambda item: ensure_utc_datetime(item.judged_at) or ensure_utc_datetime(item.created_at) or datetime.min.replace(tzinfo=timezone.utc),
    )
    accepted_submissions = [submission for submission in sorted_submissions if submission_is_full_score(submission)]
    last_submission_at = None
    if sorted_submissions:
        last = sorted_submissions[-1]
        last_submission_at = ensure_utc_datetime(last.judged_at) or ensure_utc_datetime(last.created_at)
    return StudentAbilityProfile(
        user_id=student.id,
        display_name=student.display_name,
        school=student.school,
        attempts=len(sorted_submissions),
        accepted=len(accepted_submissions),
        solved=len({submission.problem_id for submission in accepted_submissions}),
        accuracy=mastery_accuracy(len(accepted_submissions), len(sorted_submissions)),
        last_submission_at=last_submission_at,
        tag_mastery=build_tag_mastery(sorted_submissions, problem_by_id),
        type_mastery=build_type_mastery(sorted_submissions, problem_by_id),
        heatmap=build_activity_heatmap(sorted_submissions),
    )


def build_coach_analytics(
    *,
    coach: User,
    users: list[User],
    teams: list[Team],
    assignments: list[Assignment],
    problem_sets: list[ProblemSet],
    problems: list[Problem],
    submissions: list[Submission],
    now_value: datetime | None = None,
) -> CoachAnalyticsResponse:
    current = ensure_utc_datetime(now_value) or datetime.now(timezone.utc)
    team_scope = [team for team in teams if team.owner_id == coach.id]
    team_by_id = {team.id: team for team in team_scope}
    scoped_team_ids = set(team_by_id)
    scoped_assignments = [
        assignment
        for assignment in assignments
        if assignment.created_by == coach.id or (assignment.team_id is not None and assignment.team_id in scoped_team_ids)
    ]
    student_scope_ids = {
        member_id
        for team in team_scope
        for member_id in team.member_ids
    }
    student_scope = [
        user
        for user in users
        if user.role == "student" and user.id in student_scope_ids
    ]
    student_by_id = {student.id: student for student in student_scope}
    problem_by_id = {problem.id: problem for problem in problems}
    problem_set_by_id = {problem_set.id: problem_set for problem_set in problem_sets}
    scoped_problem_ids = {
        problem_id
        for assignment in scoped_assignments
        for problem_id in (problem_set_by_id.get(assignment.problem_set_id).problem_ids if problem_set_by_id.get(assignment.problem_set_id) else [])
    }
    scoped_submissions = [
        submission
        for submission in submissions
        if submission.user_id in student_by_id and submission.problem_id in scoped_problem_ids
    ]

    solved_by_student: dict[str, set[str]] = {}
    latest_submission_at: dict[str, datetime] = {}
    for submission in scoped_submissions:
        judged_at = ensure_utc_datetime(submission.judged_at) or ensure_utc_datetime(submission.created_at)
        if judged_at is not None:
            previous = latest_submission_at.get(submission.user_id)
            if previous is None or judged_at > previous:
                latest_submission_at[submission.user_id] = judged_at
        if submission_is_full_score(submission):
            solved_by_student.setdefault(submission.user_id, set()).add(submission.problem_id)

    assignment_cards: list[AssignmentAnalytics] = []
    for assignment in sorted(scoped_assignments, key=lambda item: (ensure_utc_datetime(item.due_at) or current, item.id)):
        problem_set = problem_set_by_id.get(assignment.problem_set_id)
        problem_ids = set(problem_set.problem_ids if problem_set else [])
        members = (
            [student_by_id[member_id] for member_id in team_by_id.get(assignment.team_id, Team(id="", name="", invite_code="", owner_id="", created_at=current)).member_ids if member_id in student_by_id]
            if assignment.team_id
            else student_scope
        )
        student_states: list[AssignmentStudentStatus] = []
        state_counts: dict[AssignmentProgressState, int] = {
            "not_started": 0,
            "in_progress": 0,
            "overdue": 0,
            "completed": 0,
        }
        completed_count = 0
        for student in sorted(members, key=lambda item: (item.display_name, item.id)):
            solved_ids = solved_by_student.get(student.id, set()) & problem_ids
            state = assignment_student_state(
                problem_ids=problem_ids,
                solved_ids=solved_ids,
                due_at=ensure_utc_datetime(assignment.due_at) or current,
                now_value=current,
            )
            completion = (len(solved_ids) / len(problem_ids)) if problem_ids else 0.0
            if state == "completed":
                completed_count += 1
            state_counts[state] += 1
            student_states.append(
                AssignmentStudentStatus(
                    user_id=student.id,
                    display_name=student.display_name,
                    school=student.school,
                    status=state,
                    solved_count=len(solved_ids),
                    problem_count=len(problem_ids),
                    completion=completion,
                    last_submission_at=latest_submission_at.get(student.id),
                )
            )
        overall_state: AssignmentProgressState
        if student_states and completed_count == len(student_states):
            overall_state = "completed"
        elif ensure_utc_datetime(assignment.due_at) and current > (ensure_utc_datetime(assignment.due_at) or current):
            overall_state = "overdue"
        elif any(item.status == "in_progress" for item in student_states):
            overall_state = "in_progress"
        else:
            overall_state = "not_started"
        assignment_cards.append(
            AssignmentAnalytics(
                **assignment.model_dump(),
                problem_set_title=problem_set.title if problem_set else assignment.problem_set_id,
                problem_count=len(problem_ids),
                student_count=len(student_states),
                completed_count=completed_count,
                completion=(completed_count / len(student_states)) if student_states else 0.0,
                status=overall_state,
                state_counts=state_counts,
                students=student_states,
            )
        )

    return CoachAnalyticsResponse(
        class_size=len(student_scope),
        active_students=len({submission.user_id for submission in scoped_submissions}),
        assignments=assignment_cards,
        teams=team_scope,
        tag_mastery=build_tag_mastery(scoped_submissions, problem_by_id),
        type_mastery=build_type_mastery(scoped_submissions, problem_by_id),
        activity_heatmap=build_activity_heatmap(scoped_submissions),
        student_profiles=[
            build_student_ability_profile(
                student,
                [submission for submission in scoped_submissions if submission.user_id == student.id],
                problem_by_id,
            )
            for student in sorted(student_scope, key=lambda item: (item.display_name, item.id))
        ],
    )


def _dt(value: datetime | None) -> str:
    normalized = ensure_utc_datetime(value)
    return normalized.isoformat() if normalized else ""


def _percent_value(value: float) -> str:
    return f"{round(max(0.0, min(1.0, value)) * 100, 2):.2f}"


def _report_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return _dt(value)
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def build_coach_report_sheets(analytics: CoachAnalyticsResponse) -> dict[str, list[list[Any]]]:
    sheets: dict[str, list[list[Any]]] = {
        "Assignments": [
            [
                "assignment_id",
                "title",
                "problem_set_title",
                "team_id",
                "status",
                "student_count",
                "completed_count",
                "completion_percent",
                "problem_count",
                "not_started",
                "in_progress",
                "overdue",
                "due_at",
            ]
        ],
        "Students": [
            [
                "user_id",
                "display_name",
                "school",
                "attempts",
                "accepted",
                "solved",
                "accuracy_percent",
                "last_submission_at",
            ]
        ],
        "Tag Mastery": [
            [
                "tag",
                "attempts",
                "accepted",
                "solved",
                "student_count",
                "accuracy_percent",
            ]
        ],
        "Type Mastery": [
            [
                "problem_type",
                "attempts",
                "accepted",
                "solved",
                "accuracy_percent",
            ]
        ],
        "Activity": [
            [
                "date",
                "attempts",
                "accepted",
                "active_students",
            ]
        ],
    }

    for item in analytics.assignments:
        sheets["Assignments"].append(
            [
                item.id,
                item.title,
                item.problem_set_title,
                item.team_id or "",
                item.status,
                item.student_count,
                item.completed_count,
                _percent_value(item.completion),
                item.problem_count,
                item.state_counts.get("not_started", 0),
                item.state_counts.get("in_progress", 0),
                item.state_counts.get("overdue", 0),
                _dt(item.due_at),
            ]
        )

    for profile in analytics.student_profiles:
        sheets["Students"].append(
            [
                profile.user_id,
                profile.display_name,
                profile.school,
                profile.attempts,
                profile.accepted,
                profile.solved,
                _percent_value(profile.accuracy),
                _dt(profile.last_submission_at),
            ]
        )

    for item in analytics.tag_mastery:
        sheets["Tag Mastery"].append(
            [
                item.tag,
                item.attempts,
                item.accepted,
                item.solved,
                item.student_count,
                _percent_value(item.accuracy),
            ]
        )

    for item in analytics.type_mastery:
        sheets["Type Mastery"].append(
            [
                item.problem_type,
                item.attempts,
                item.accepted,
                item.solved,
                _percent_value(item.accuracy),
            ]
        )

    for item in analytics.activity_heatmap:
        sheets["Activity"].append([item.date, item.attempts, item.accepted, item.active_students])

    return sheets


def build_coach_report_csv(analytics: CoachAnalyticsResponse) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["section", "field_1", "field_2", "field_3", "field_4", "field_5", "field_6", "field_7", "field_8"])
    for sheet_name, rows in build_coach_report_sheets(analytics).items():
        header, *records = rows
        writer.writerow([sheet_name, *header])
        for row in records:
            writer.writerow([sheet_name, *[_report_cell(value) for value in row]])
    return "\ufeff" + output.getvalue()


def _xlsx_col(index: int) -> str:
    letters = ""
    value = index
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _xlsx_sheet_xml(rows: list[list[Any]]) -> str:
    xml_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells: list[str] = []
        for col_index, value in enumerate(row, start=1):
            ref = f"{_xlsx_col(col_index)}{row_index}"
            text = xml_escape(_report_cell(value))
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData>'
        "</worksheet>"
    )


def build_coach_report_xlsx(analytics: CoachAnalyticsResponse) -> bytes:
    sheets = build_coach_report_sheets(analytics)
    workbook_sheets = "".join(
        f'<sheet name="{xml_escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheets, start=1)
    )
    workbook_rels = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index, _name in enumerate(sheets, start=1)
    )
    content_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index, _name in enumerate(sheets, start=1)
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            f"{content_overrides}"
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{workbook_sheets}</sheets>"
            "</workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{workbook_rels}"
            "</Relationships>",
        )
        for index, rows in enumerate(sheets.values(), start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _xlsx_sheet_xml(rows))
    return buffer.getvalue()


def build_coach_report_export(
    analytics: CoachAnalyticsResponse,
    report_format: CoachReportFormat,
) -> tuple[bytes, str]:
    if report_format == "csv":
        return build_coach_report_csv(analytics).encode("utf-8"), COACH_REPORT_MIME_TYPES[report_format]
    return build_coach_report_xlsx(analytics), COACH_REPORT_MIME_TYPES[report_format]


def coach_report_filename(report_format: CoachReportFormat, generated_at: datetime | None = None) -> str:
    stamp = (ensure_utc_datetime(generated_at) or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    return f"coach-report-{stamp}.{report_format}"


def coach_scope(
    *,
    coach: User,
    users: list[User],
    teams: list[Team],
    assignments: list[Assignment],
    problem_sets: list[ProblemSet],
) -> dict[str, Any]:
    team_scope = [team for team in teams if team.owner_id == coach.id]
    scoped_team_ids = {team.id for team in team_scope}
    scoped_assignments = [
        assignment
        for assignment in assignments
        if assignment.created_by == coach.id or (assignment.team_id is not None and assignment.team_id in scoped_team_ids)
    ]
    student_ids = {
        member_id
        for team in team_scope
        for member_id in team.member_ids
    }
    students = [user for user in users if user.role == "student" and user.id in student_ids]
    problem_set_by_id = {problem_set.id: problem_set for problem_set in problem_sets}
    problem_ids = {
        problem_id
        for assignment in scoped_assignments
        for problem_id in (problem_set_by_id.get(assignment.problem_set_id).problem_ids if problem_set_by_id.get(assignment.problem_set_id) else [])
    }
    return {
        "teams": team_scope,
        "assignments": scoped_assignments,
        "students": students,
        "student_ids": {student.id for student in students},
        "problem_ids": problem_ids,
    }


def code_similarity_tokens(source_code: str) -> set[str]:
    without_comments = CODE_SIMILARITY_COMMENT_PATTERN.sub(" ", source_code.lower())
    tokens = CODE_SIMILARITY_TOKEN_PATTERN.findall(without_comments)
    normalized: set[str] = set()
    for token in tokens:
        if not token.strip():
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            normalized.add("<num>")
        else:
            normalized.add(token)
    return normalized


def code_token_similarity(tokens_a: set[str], tokens_b: set[str]) -> tuple[float, int]:
    if not tokens_a or not tokens_b:
        return 0.0, 0
    shared = len(tokens_a & tokens_b)
    smaller = min(len(tokens_a), len(tokens_b))
    return shared / smaller if smaller else 0.0, shared


def build_coach_similarity(
    *,
    coach: User,
    users: list[User],
    teams: list[Team],
    assignments: list[Assignment],
    problem_sets: list[ProblemSet],
    problems: list[Problem],
    contests: list[Contest],
    submissions: list[Submission],
    problem_id: str | None = None,
    contest_id: str | None = None,
    threshold: float = 0.82,
    limit: int = 50,
    now_value: datetime | None = None,
) -> CoachSimilarityResponse:
    current = ensure_utc_datetime(now_value) or datetime.now(timezone.utc)
    scope = coach_scope(
        coach=coach,
        users=users,
        teams=teams,
        assignments=assignments,
        problem_sets=problem_sets,
    )
    scoped_problem_ids: set[str] = set(scope["problem_ids"])
    student_ids: set[str] = set(scope["student_ids"])
    problem_by_id = {problem.id: problem for problem in problems}
    contest_by_id = {contest.id: contest for contest in contests}
    team_by_member: dict[str, list[Team]] = {}
    for team in scope["teams"]:
        for member_id in team.member_ids:
            team_by_member.setdefault(member_id, []).append(team)
    student_by_id = {student.id: student for student in scope["students"]}

    scoped_submissions = [
        submission
        for submission in submissions
        if submission.user_id in student_ids
        and submission.problem_id in scoped_problem_ids
        and submission.problem_type == "code"
        and submission.source_code
    ]

    problem_counts: dict[str, int] = {}
    contest_counts: dict[str, int] = {}
    for submission in scoped_submissions:
        problem_counts[submission.problem_id] = problem_counts.get(submission.problem_id, 0) + 1
        if submission.contest_id:
            contest_counts[submission.contest_id] = contest_counts.get(submission.contest_id, 0) + 1

    if problem_id:
        scoped_submissions = [submission for submission in scoped_submissions if submission.problem_id == problem_id]
    if contest_id:
        scoped_submissions = [submission for submission in scoped_submissions if submission.contest_id == contest_id]

    token_by_submission_id = {
        submission.id: code_similarity_tokens(submission.source_code or "")
        for submission in scoped_submissions
    }
    candidate_pair_count = 0
    findings: list[CoachSimilarityFinding] = []

    grouped: dict[tuple[str, str | None, str], list[Submission]] = {}
    for submission in scoped_submissions:
        language = str(submission.language or "").strip().lower()
        if not language:
            continue
        grouped.setdefault((submission.problem_id, submission.contest_id, language), []).append(submission)

    def similarity_student(user_id: str) -> CoachSimilarityStudent:
        student = student_by_id.get(user_id)
        memberships = sorted(team_by_member.get(user_id, []), key=lambda team: (team.name, team.id))
        return CoachSimilarityStudent(
            user_id=user_id,
            display_name=student.display_name if student else user_id,
            school=student.school if student else "",
            team_ids=[team.id for team in memberships],
            team_names=[team.name for team in memberships],
        )

    for (group_problem_id, group_contest_id, language), group_submissions in grouped.items():
        sorted_group = sorted(group_submissions, key=lambda item: (ensure_utc_datetime(item.created_at) or current, item.id))
        for left_index, left in enumerate(sorted_group):
            for right in sorted_group[left_index + 1 :]:
                if left.user_id == right.user_id:
                    continue
                candidate_pair_count += 1
                left_tokens = token_by_submission_id.get(left.id, set())
                right_tokens = token_by_submission_id.get(right.id, set())
                similarity, shared = code_token_similarity(left_tokens, right_tokens)
                if similarity < threshold:
                    continue
                problem = problem_by_id.get(group_problem_id)
                contest = contest_by_id.get(group_contest_id or "")
                findings.append(
                    CoachSimilarityFinding(
                        problem_id=group_problem_id,
                        problem_title=problem.title if problem else left.problem_title,
                        contest_id=group_contest_id,
                        contest_title=contest.title if contest else None,
                        language=language,
                        similarity=round(similarity, 4),
                        shared_token_count=shared,
                        token_count_a=len(left_tokens),
                        token_count_b=len(right_tokens),
                        submission_a_id=left.id,
                        submission_b_id=right.id,
                        submitted_at_a=ensure_utc_datetime(left.created_at) or current,
                        submitted_at_b=ensure_utc_datetime(right.created_at) or current,
                        status_a=left.status,
                        status_b=right.status,
                        student_a=similarity_student(left.user_id),
                        student_b=similarity_student(right.user_id),
                        reason="high_token_overlap",
                    )
                )

    findings.sort(
        key=lambda item: (
            -item.similarity,
            item.problem_title,
            item.submitted_at_a,
            item.submission_a_id,
            item.submission_b_id,
        )
    )
    limited_findings = findings[: max(1, limit)]

    problem_options = [
        CoachSimilarityFilterOption(
            id=pid,
            title=problem_by_id[pid].title if pid in problem_by_id else pid,
            count=count,
        )
        for pid, count in sorted(problem_counts.items(), key=lambda item: (problem_by_id.get(item[0]).title if problem_by_id.get(item[0]) else item[0], item[0]))
    ]
    contest_options = [
        CoachSimilarityFilterOption(
            id=cid,
            title=contest_by_id[cid].title if cid in contest_by_id else cid,
            count=count,
        )
        for cid, count in sorted(contest_counts.items(), key=lambda item: (contest_by_id.get(item[0]).title if contest_by_id.get(item[0]) else item[0], item[0]))
    ]
    return CoachSimilarityResponse(
        generated_at=current,
        threshold=threshold,
        limit=max(1, limit),
        problem_id=problem_id,
        contest_id=contest_id,
        scanned_submission_count=len(scoped_submissions),
        candidate_pair_count=candidate_pair_count,
        findings=limited_findings,
        problems=problem_options,
        contests=contest_options,
    )


def normalize_blank(value: Any, case_sensitive: bool, trim_space: bool) -> str:
    text = str(value)
    if trim_space:
        text = re.sub(r"\s+", "", text)
    if not case_sensitive:
        text = text.lower()
    return text


def blank_rule_for(config: dict[str, Any], key: str) -> dict[str, Any]:
    rules = config.get("blank_rules", {})
    if not isinstance(rules, dict):
        return {}
    rule = rules.get(key, {})
    return rule if isinstance(rule, dict) else {}


def numeric_value(value: Any, trim_space: bool) -> float | None:
    text = str(value)
    if trim_space:
        text = re.sub(r"\s+", "", text)
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def blank_answer_matches(
    received: Any,
    expected_values: list[Any],
    rule: dict[str, Any],
    *,
    case_sensitive: bool,
    trim_space: bool,
) -> bool:
    match_type = str(rule.get("match", "exact")).strip().lower() or "exact"

    if match_type == "regex":
        flags = 0 if case_sensitive else re.IGNORECASE
        received_text = str(received)
        if trim_space:
            received_text = re.sub(r"\s+", "", received_text)
        for pattern in expected_values:
            try:
                if re.fullmatch(str(pattern), received_text, flags=flags):
                    return True
            except re.error:
                continue
        return False

    if match_type == "numeric":
        received_value = numeric_value(received, trim_space)
        if received_value is None:
            return False
        try:
            tolerance = max(float(rule.get("tolerance", 0)), 0.0)
        except (TypeError, ValueError):
            tolerance = 0.0
        for expected in expected_values:
            expected_value = numeric_value(expected, trim_space)
            if expected_value is not None and abs(received_value - expected_value) <= tolerance:
                return True
        return False

    expected_normalized = [normalize_blank(v, case_sensitive, trim_space) for v in expected_values]
    return normalize_blank(received, case_sensitive, trim_space) in expected_normalized


def judge_objective(
    problem: Problem,
    judge_config: dict[str, Any],
    answers: dict[str, Any],
) -> tuple[int, int, list[ObjectiveItemResult]]:
    config = judge_config
    results: list[ObjectiveItemResult] = []

    if problem.type == "blank":
        case_sensitive = bool(config.get("case_sensitive", False))
        trim_space = bool(config.get("trim_space", True))
        scores: dict[str, int] = config.get("scores", {})
        expected_map: dict[str, list[str]] = config.get("answers", {})
        total = sum(int(v) for v in scores.values()) or 100
        score = 0
        for key, expected_values in expected_map.items():
            received = answers.get(key, "")
            correct = blank_answer_matches(
                received,
                expected_values,
                blank_rule_for(config, key),
                case_sensitive=case_sensitive,
                trim_space=trim_space,
            )
            item_score = int(scores.get(key, 0)) if correct else 0
            score += item_score
            results.append(
                ObjectiveItemResult(
                    key=key,
                    correct=correct,
                    expected=expected_values[0] if expected_values else None,
                    received=received,
                    score=item_score,
                )
            )
        return score, total, results

    if problem.type == "single_choice":
        expected = str(config.get("answer", ""))
        received = str(answers.get("choice", ""))
        total = int(config.get("score", 100))
        correct = received == expected
        return (
            total if correct else 0,
            total,
            [
                ObjectiveItemResult(
                    key="choice",
                    correct=correct,
                    expected=expected,
                    received=received,
                    score=total if correct else 0,
                )
            ],
        )

    if problem.type == "multiple_choice":
        expected = sorted(str(item) for item in config.get("answer", []))
        received = sorted(str(item) for item in answers.get("choices", []))
        total = int(config.get("score", 100))
        correct = received == expected
        return (
            total if correct else 0,
            total,
            [
                ObjectiveItemResult(
                    key="choices",
                    correct=correct,
                    expected=expected,
                    received=received,
                    score=total if correct else 0,
                )
            ],
        )

    raise ValueError("Unsupported objective problem type")


def sign_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(PACK_SECRET.encode(), raw, hashlib.sha256).hexdigest()


def build_offline_pack(
    problems: list[Problem],
    judge_configs: dict[str, dict[str, Any]],
    *,
    ttl_hours: int | None = None,
    source: dict[str, Any] | None = None,
    pack_id: str | None = None,
    lifecycle: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    expires_at = expires_at or generated_at + timedelta(hours=max(ttl_hours or OFFLINE_PACK_TTL_HOURS, 1))
    lifecycle_payload = lifecycle.model_dump(mode="json") if hasattr(lifecycle, "model_dump") else (lifecycle or {})
    pack = {
        "version": "1.0",
        "pack_id": pack_id or f"pack-{uuid4().hex[:16]}",
        "generated_at": generated_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "signature_algorithm": "hmac-sha256",
        "scope": "objective-only",
        "source": source or {"type": "training"},
        "lifecycle": lifecycle_payload,
        "problems": [
            {
                "id": p.id,
                "title": p.title,
                "type": p.type,
                "difficulty": p.difficulty,
                "tags": p.tags,
                "statement": p.statement,
                "options": p.options,
                "blanks": p.blanks,
                "judge_config": judge_configs.get(p.id, {}),
            }
            for p in problems
            if p.type != "code"
        ],
    }
    return {"payload": pack, "signature": sign_payload(pack)}


def safe_print_source(source_code: str) -> str:
    source = source_code.replace("\r\n", "\n").replace("\r", "\n")
    return source if source.endswith("\n") else f"{source}\n"


def contest_submission_is_accepted(submission: Submission) -> bool:
    return submission.status in {"accepted", "manual_override"} and submission.score >= submission.max_score


def contest_submission_is_balloon_eligible(contest: Contest, submission: Submission) -> bool:
    if contest.rule != "ACM":
        return False
    return contest_submission_is_accepted(submission)


def contest_submission_effective_time(submission: Submission) -> datetime:
    return submission.judged_at or submission.created_at


def build_contest_balloon(
    contest: Contest,
    submission: Submission,
    *,
    display_name: str,
    first_ac: bool,
    released: bool = False,
    released_at: datetime | None = None,
    released_by: str | None = None,
) -> ContestBalloon:
    return ContestBalloon(
        contest_id=contest.id,
        submission_id=submission.id,
        user_id=submission.user_id,
        display_name=display_name,
        problem_id=submission.problem_id,
        problem_title=submission.problem_title,
        eligible=contest_submission_is_balloon_eligible(contest, submission),
        first_ac=first_ac,
        status=submission.status,
        score=submission.score,
        max_score=submission.max_score,
        judged_at=submission.judged_at,
        released=released,
        released_at=released_at,
        released_by=released_by,
    )


def reconcile_contest_balloon(
    contest: Contest,
    submission: Submission,
    *,
    display_name: str,
    prior: dict[str, Any] | None = None,
    siblings: list[Submission] | None = None,
) -> ContestBalloon | None:
    if siblings is None:
        siblings = []
    if not contest_submission_is_balloon_eligible(contest, submission):
        return None
    submission_time = contest_submission_effective_time(submission)
    earlier_accepted = [
        item
        for item in siblings
        if item.id != submission.id
        and item.user_id == submission.user_id
        and item.problem_id == submission.problem_id
        and item.contest_id == contest.id
        and contest_submission_is_accepted(item)
        and (
            contest_submission_effective_time(item) < submission_time
            or (
                contest_submission_effective_time(item) == submission_time
                and str(item.id) < str(submission.id)
            )
        )
    ]
    if earlier_accepted:
        return None
    return build_contest_balloon(
        contest,
        submission,
        display_name=display_name,
        first_ac=not any(
            item.id != submission.id
            and item.problem_id == submission.problem_id
            and item.contest_id == contest.id
            and contest_submission_is_accepted(item)
            and (
                contest_submission_effective_time(item) < submission_time
                or (
                    contest_submission_effective_time(item) == submission_time
                    and str(item.id) < str(submission.id)
                )
            )
            for item in siblings
        ),
        released=bool((prior or {}).get("released", False)),
        released_at=prior.get("released_at") if prior else None,
        released_by=prior.get("released_by") if prior else None,
    )


def refresh_contest_balloon_for_submission(store: Any, submission: Submission) -> ContestBalloon | None:
    contest_id = submission.contest_id or ""
    if not contest_id:
        return None
    contest = store.get_contest(contest_id)
    if not contest:
        return None
    user: User | None = store.get_user(submission.user_id)
    siblings = [item for item in store.list_submissions() if item.contest_id == contest.id]
    sibling_group = [
        item
        for item in siblings
        if item.user_id == submission.user_id and item.problem_id == submission.problem_id
    ]
    accepted_group = [
        item
        for item in sibling_group
        if contest_submission_is_balloon_eligible(contest, item)
    ]
    existing = [
        item
        for item in store.list_contest_balloons(contest.id)
        if str(item.get("user_id") or "") == submission.user_id and str(item.get("problem_id") or "") == submission.problem_id
    ]
    if contest.rule != "ACM":
        if existing:
            store.delete_contest_balloon(contest.id, submission.user_id, submission.problem_id)
        return None
    if not accepted_group:
        if existing:
            store.delete_contest_balloon(contest.id, submission.user_id, submission.problem_id)
        return None
    candidate = min(
        accepted_group,
        key=lambda item: (contest_submission_effective_time(item), str(item.id)),
    )
    prior = existing[0] if existing else None
    balloon = reconcile_contest_balloon(
        contest,
        candidate,
        display_name=user.display_name if user else submission.user_id,
        prior=prior,
        siblings=siblings,
    )
    if balloon is None:
        if existing:
            store.delete_contest_balloon(contest.id, submission.user_id, submission.problem_id)
        return None
    store.upsert_contest_balloon(balloon.model_dump(mode="json"))
    return balloon
