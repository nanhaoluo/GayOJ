from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .config import OFFLINE_PACK_SECRET, OFFLINE_PACK_TTL_HOURS
from .models import (
    Assignment,
    AssignmentAnalytics,
    AssignmentProgressState,
    AssignmentStudentStatus,
    CoachAnalyticsResponse,
    ContestBalloon,
    Contest,
    ObjectiveItemResult,
    Problem,
    ProblemSet,
    Submission,
    TagMastery,
    Team,
    User,
)


PACK_SECRET = OFFLINE_PACK_SECRET


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
    tag_counts: dict[str, dict[str, int]] = {}
    for submission in scoped_submissions:
        judged_at = ensure_utc_datetime(submission.judged_at) or ensure_utc_datetime(submission.created_at)
        if judged_at is not None:
            previous = latest_submission_at.get(submission.user_id)
            if previous is None or judged_at > previous:
                latest_submission_at[submission.user_id] = judged_at
        if submission.status in {"accepted", "manual_override"} and submission.score >= submission.max_score:
            solved_by_student.setdefault(submission.user_id, set()).add(submission.problem_id)
            problem = problem_by_id.get(submission.problem_id)
            if problem:
                for tag in problem.tags:
                    bucket = tag_counts.setdefault(tag, {"attempts": 0, "accepted": 0})
                    bucket["accepted"] += 1
        problem = problem_by_id.get(submission.problem_id)
        if problem:
            for tag in problem.tags:
                bucket = tag_counts.setdefault(tag, {"attempts": 0, "accepted": 0})
                bucket["attempts"] += 1

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
        tag_mastery=[
            TagMastery(tag=tag, attempts=value["attempts"], accepted=value["accepted"])
            for tag, value in sorted(tag_counts.items(), key=lambda item: (-item[1]["attempts"], item[0]))
        ],
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
