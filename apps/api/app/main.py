from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import PurePosixPath
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import (
    create_token,
    get_current_user,
    get_optional_user,
    hash_password,
    public_user,
    require_permissions,
    validate_password_policy,
    verify_password,
)
from . import config as app_config
from .config import (
    API_CORS_ORIGINS,
    TESTDATA_MAX_ARCHIVE_BYTES,
    TESTDATA_MAX_FILES,
    TESTDATA_MAX_UNCOMPRESSED_BYTES,
)
from .judge_queue import QueueBackendUnavailable, build_code_queue_job, get_judge_queue
from .models import (
    Assignment,
    AssignmentCreate,
    AuditLogList,
    Clarification,
    ClarificationCreate,
    ClarificationReply,
    CodeSubmitRequest,
    CompilerConfig,
    CompilerConfigUpdate,
    CompilerLanguage,
    CoachAnalyticsResponse,
    Contest,
    ContestCreate,
    ContestDetail,
    ContestBalloon,
    ContestFreezeRequest,
    ContestPrintRequest,
    ContestPrintResponse,
    ContestSubmitRequest,
    ContestBalloonUpdate,
    Discussion,
    DiscussionCreate,
    DiscussionReplyCreate,
    DEFAULT_STUDENT_SCHOOL,
    HealthResponse,
    LoginRequest,
    LoginResponse,
    Notification,
    OfflinePackResponse,
    OfflinePackLifecycle,
    OfflinePackStatusResponse,
    OfflinePackCreate,
    OfflinePackRecord,
    OfflinePackStatus,
    OfflinePolicyUpdate,
    OfflineResultReview,
    ObjectiveSubmitRequest,
    OfflineResultSyncRequest,
    OfflineResultSyncResponse,
    OverrideRequest,
    PasswordChangeRequest,
    Problem,
    ProblemAdminDetail,
    ProblemCreate,
    ProblemDetail,
    ProblemExportResponse,
    ProblemImportItem,
    ProblemImportRequest,
    ProblemImportResponse,
    ProblemPackageFormat,
    ProblemSet,
    ProblemSetCreate,
    ProblemSetDetail,
    ProblemSummary,
    ProblemTestData,
    ProblemUpdate,
    ProblemVisibilityUpdate,
    ProblemVersion,
    PublicUser,
    RankingRow,
    RbacMatrixResponse,
    RejudgeBatchRequest,
    RejudgeBatchResponse,
    RejudgeRequest,
    RejudgeSkipped,
    StandingRow,
    Submission,
    SubmissionReview,
    SystemConfig,
    SystemConfigUpdate,
    Tag,
    TagCreate,
    TagTreeNode,
    TagUpdate,
    Team,
    TeamCreate,
    User,
    UserRoleUpdate,
    UserProfile,
    UserProfileUpdate,
    JudgeMonitorResponse,
    JudgeNode,
    JudgeNodeClaimResponse,
    JudgeNodeHeartbeatRequest,
    JudgeNodeStatusUpdate,
)
from .rbac import role_has_permission, role_permission_matrix
from .services import build_offline_pack, judge_objective, make_submission_id, safe_print_source
from .db import Repository, get_repository, now
from .object_storage import ObjectNotFoundError, ObjectStorage, get_object_storage
from .problem_io import ProblemPackageError, export_problem_package, package_filename, parse_problem_package


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title="gayoj API",
    version="0.1.0",
    description="gayoj MVP backend generated from 1.md. Code submissions are queued for online judging workers; objective problems are judged by the rule engine.",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    default_response_class=UTF8JSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=API_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def student_user_ids(store: Repository) -> set[str]:
    return {user.id for user in store.list_users() if user.role == "student"}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def offline_result_key(
    problem_id: str,
    answers: dict[str, Any],
    practiced_at: datetime | None,
    client_key: str | None,
    pack_id: str | None = None,
) -> str:
    if client_key:
        if pack_id:
            raw_key = f"{pack_id}:{client_key}"
            return raw_key[:128] if len(raw_key) <= 128 else f"{pack_id}:{hashlib.sha256(raw_key.encode('utf-8')).hexdigest()}"
        return client_key[:128]
    practiced_at_text = practiced_at.isoformat() if practiced_at else ""
    payload = {"problem_id": problem_id, "answers": answers, "practiced_at": practiced_at_text, "pack_id": pack_id or ""}
    return f"legacy:{hashlib.sha256(_canonical_json(payload).encode('utf-8')).hexdigest()[:48]}"


def same_offline_result(submission: Submission, problem_id: str, answers: dict[str, Any]) -> bool:
    return submission.problem_id == problem_id and _canonical_json(submission.answers or {}) == _canonical_json(answers)


def offline_rejection(problem_id: str, reason_code: str, reason: str) -> dict[str, str]:
    return {"problem_id": problem_id, "reason_code": reason_code, "reason": reason}


def offline_source_matches_problem(source: dict[str, Any], problem: Problem, store: Repository) -> bool:
    if not source:
        return True
    source_type = str(source.get("type") or "")
    if source_type == "training":
        return True
    if source_type != "problem_set":
        return False
    problem_set_id = str(source.get("id") or "")
    if not problem_set_id:
        return False
    problem_set = store.get_problem_set(problem_set_id)
    if not problem_set or problem_set.visibility != "public" or not problem_set.offline_enabled:
        return False
    if problem_set.offline_policy.answer_visibility != "full":
        return False
    if problem_set.offline_policy.sync_mode == "disabled":
        return False
    return problem.id in problem_set.problem_ids


def offline_pack_source_matches_record(record: OfflinePackRecord, source: dict[str, Any]) -> bool:
    if not source:
        return True
    record_source = record.source if isinstance(record.source, dict) else {}
    if not record_source:
        return True
    source_type = str(source.get("type") or "")
    record_type = str(record_source.get("type") or "")
    if source_type != record_type:
        return False
    if source_type in {"training", "problem_set"}:
        return str(source.get("id") or "") == str(record_source.get("id") or "")
    return source == record_source


def offline_pack_authorizes_problem(
    pack_id: str | None,
    problem: Problem,
    store: Repository,
    *,
    user_id: str | None = None,
) -> bool:
    if not pack_id:
        return True
    record = store.get_offline_pack(pack_id)
    if not record:
        return False
    if user_id and record.created_by != user_id:
        return False
    status_value = pack_record_status(record)
    if status_value != "active":
        return False
    return problem.id in record.problem_ids


def sanitized_submission(
    submission: Submission,
    *,
    include_expected: bool = False,
    include_source: bool = True,
) -> SubmissionReview:
    payload = submission.model_dump()
    details: list[dict[str, Any]] = []
    for item in submission.details:
        detail = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        if not include_expected:
            detail.pop("expected", None)
        details.append(detail)
    payload["details"] = details
    if not include_source:
        payload["source_code"] = None
    return SubmissionReview(**payload)


def offline_result_review(submission: Submission, *, include_expected: bool = False) -> OfflineResultReview:
    if not submission.offline_result_key:
        raise ValueError("Submission is not an offline result")
    payload = sanitized_submission(
        submission,
        include_expected=include_expected,
        include_source=False,
    ).model_dump()
    payload["expected_visible"] = include_expected
    return OfflineResultReview(**payload)


def pack_lifecycle(
    source: dict[str, Any],
    policy: Any,
    *,
    downloaded: int = 0,
    status: str = "active",
    problem_ids: list[str] | None = None,
) -> OfflinePackLifecycle:
    return OfflinePackLifecycle(
        status=status,
        downloaded=downloaded,
        max_downloads=getattr(policy, "max_downloads", None),
        retention_days=getattr(policy, "retention_days", None),
        source=source,
        problem_set_id=source.get("id") if isinstance(source, dict) else None,
        problem_ids=problem_ids or [],
    )


def pack_record_status(record: OfflinePackRecord, *, now_value: datetime | None = None) -> str:
    current = now_value or now()
    if record.status in {"disabled", "expired", "download_limit_reached"}:
        return record.status
    if record.expires_at <= current:
        return "expired"
    if record.max_downloads is not None and record.downloaded >= record.max_downloads:
        return "download_limit_reached"
    return "active"


def pack_record_to_status(record: OfflinePackRecord, *, now_value: datetime | None = None) -> OfflinePackStatus:
    status_value = pack_record_status(record, now_value=now_value)
    return OfflinePackStatus(
        pack_id=record.pack_id,
        status=status_value,
        source=record.source,
        problem_set_id=record.problem_set_id,
        problem_ids=record.problem_ids,
        generated_at=record.generated_at,
        expires_at=record.expires_at,
        ttl_hours=record.ttl_hours,
        retention_days=record.retention_days,
        max_downloads=record.max_downloads,
        downloaded=record.downloaded,
        last_downloaded_at=record.last_downloaded_at,
    )


def problem_summary(problem: Problem, submissions: list[Submission], participant_ids: set[str] | None = None) -> ProblemSummary:
    related = [s for s in submissions if s.problem_id == problem.id and (participant_ids is None or s.user_id in participant_ids)]
    return ProblemSummary(
        id=problem.id,
        title=problem.title,
        type=problem.type,
        difficulty=problem.difficulty,
        tags=problem.tags,
        accepted=sum(1 for s in related if s.status in {"accepted", "manual_override"} and s.score == s.max_score),
        attempts=len(related),
    )


def problem_detail(
    problem: Problem,
    can_manage: bool = False,
    judge_config: dict[str, Any] | None = None,
) -> ProblemDetail:
    return ProblemDetail(
        id=problem.id,
        title=problem.title,
        type=problem.type,
        difficulty=problem.difficulty,
        tags=problem.tags,
        statement=problem.statement,
        input_format=problem.input_format,
        output_format=problem.output_format,
        samples=problem.samples,
        options=problem.options,
        blanks=problem.blanks,
        time_limit_ms=problem.time_limit_ms,
        memory_limit_mb=problem.memory_limit_mb,
        author_id=problem.author_id,
        created_at=problem.created_at,
        judge_config=judge_config if can_manage else None,
    )


def admin_problem_detail(problem: Problem, store: Repository) -> ProblemAdminDetail:
    return ProblemAdminDetail(
        **problem_detail(
            problem,
            can_manage=True,
            judge_config=store.get_problem_judge_config(problem.id),
        ).model_dump(),
        visible=problem.visible,
        offline_enabled=problem.offline_enabled,
        offline_policy=problem.offline_policy,
        test_data=store.get_problem_test_data(problem.id),
    )


def tag_slug(name: str) -> str:
    return "-".join(name.lower().replace("，", " ").replace(",", " ").split())


def tag_tree(tags: list[Tag]) -> list[TagTreeNode]:
    children_by_parent: dict[str | None, list[Tag]] = {}
    for tag in tags:
        children_by_parent.setdefault(tag.parent_id, []).append(tag)
    for bucket in children_by_parent.values():
        bucket.sort(key=lambda item: (item.sort_order, item.name, item.id))

    def build(parent_id: str | None) -> list[TagTreeNode]:
        return [
            TagTreeNode(**tag.model_dump(), children=build(tag.id))
            for tag in children_by_parent.get(parent_id, [])
        ]

    return build(None)


def normalize_tag_filters(*values: str | list[str]) -> list[str]:
    tags: list[str] = []
    for value in values:
        items = value if isinstance(value, list) else [value]
        for item in items:
            for part in str(item or "").replace("，", ",").split(","):
                text = part.strip()
                if text and text not in tags:
                    tags.append(text)
    return tags


def next_problem_id(store: Repository) -> str:
    numeric_ids = [
        int(problem.id[1:])
        for problem in store.list_problems()
        if problem.id.startswith("P") and problem.id[1:].isdigit()
    ]
    return f"P{max(numeric_ids, default=1000) + 1}"


_IMPORT_PROBLEM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def parse_problem_ids(value: str) -> list[str]:
    return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]


def import_source_id(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    return text if _IMPORT_PROBLEM_ID_PATTERN.fullmatch(text) else None


def next_import_problem_id(used_ids: set[str]) -> str:
    numeric_ids = [
        int(problem_id[1:])
        for problem_id in used_ids
        if problem_id.startswith("P") and problem_id[1:].isdigit()
    ]
    next_id = max(numeric_ids, default=1000) + 1
    while f"P{next_id}" in used_ids:
        next_id += 1
    return f"P{next_id}"


def next_tag_id(store: Repository) -> str:
    numeric_ids = [
        int(tag.id[3:])
        for tag in store.list_tags()
        if tag.id.startswith("TAG") and tag.id[3:].isdigit()
    ]
    return f"TAG{max(numeric_ids, default=1000) + 1}"


def can_edit_problem(user: User, problem: Problem) -> bool:
    return problem.author_id == user.id or role_has_permission(user.role, "problem:edit:all")


def ensure_problem_editable(user: User, problem: Problem) -> None:
    if not can_edit_problem(user, problem):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")


def ensure_code_problem_testdata_target(problem: Problem) -> None:
    if problem.type != "code":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Test data upload is only available for code problems")


_INPUT_SUFFIXES = (".in", ".input")
_OUTPUT_SUFFIXES = (".out", ".ans", ".answer")


def _safe_zip_member_name(raw_name: str) -> str:
    path = PurePosixPath(raw_name.replace("\\", "/"))
    if path.is_absolute() or not path.parts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ZIP contains an unsafe path")
    if any(part in {"", ".", ".."} or ":" in part for part in path.parts):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ZIP contains an unsafe path")
    return str(path)


def _case_stem(name: str, suffixes: tuple[str, ...]) -> str | None:
    lower = name.lower()
    for suffix in suffixes:
        if lower.endswith(suffix):
            return name[: -len(suffix)].lower()
    return None


def validate_testdata_zip(payload: bytes) -> dict[str, Any]:
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded test data ZIP is empty")
    if len(payload) > TESTDATA_MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Uploaded test data ZIP is too large")

    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded test data must be a valid ZIP archive") from exc

    with archive:
        files = [info for info in archive.infolist() if not info.is_dir()]
        if not files:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Test data ZIP must contain files")
        if len(files) > TESTDATA_MAX_FILES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Test data ZIP contains too many files")

        total_uncompressed = 0
        input_stems: set[str] = set()
        output_stems: set[str] = set()

        for info in files:
            if info.flag_bits & 0x1:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Encrypted ZIP entries are not supported")
            name = _safe_zip_member_name(info.filename)
            total_uncompressed += max(0, info.file_size)
            if total_uncompressed > TESTDATA_MAX_UNCOMPRESSED_BYTES:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uncompressed test data is too large")

            input_stem = _case_stem(name, _INPUT_SUFFIXES)
            output_stem = _case_stem(name, _OUTPUT_SUFFIXES)
            if input_stem:
                input_stems.add(input_stem)
            if output_stem:
                output_stems.add(output_stem)

        paired = sorted(input_stems & output_stems)
        if not paired:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Test data ZIP must include at least one matching input/output pair",
            )

        return {
            "file_count": len(files),
            "input_files": len(input_stems),
            "output_files": len(output_stems),
            "case_count": len(paired),
            "case_names": paired,
        }


def ensure_tag_parent_valid(store: Repository, tag_id: str, parent_id: str | None) -> None:
    if not parent_id:
        return
    if parent_id == tag_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tag cannot be its own parent")
    parent = store.get_tag(parent_id)
    if not parent:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent tag not found")
    current_parent_id = parent.parent_id
    while current_parent_id:
        if current_parent_id == tag_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tag parent cannot be a descendant")
        current_parent = store.get_tag(current_parent_id)
        current_parent_id = current_parent.parent_id if current_parent else None


def ensure_tag_name_available(store: Repository, name: str, tag_id: str | None = None) -> None:
    for tag in store.list_tags():
        if tag.name == name and tag.id != tag_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tag name already exists")


def add_notification(store: Repository, user_id: str, title: str, content: str, type: str = "system") -> None:
    store.add_notification(
        Notification(
            id=f"N{uuid4().hex[:10].upper()}",
            user_id=user_id,
            title=title,
            content=content,
            type=type,
            created_at=now(),
        )
    )


def enqueue_code_submission_job(
    store: Repository,
    submission: Submission,
    problem: Problem,
    *,
    message: str,
) -> Submission:
    if submission.problem_type != "code" or problem.type != "code":
        raise ValueError("Only code submissions can enter the judge queue")
    if not submission.language or not submission.source_code:
        raise ValueError("Code submission must include language and source_code")

    previous_submission = store.get_submission(submission.id)
    previous_job = store.get_judge_queue_job(previous_submission.queue_job_id) if previous_submission and previous_submission.queue_job_id else None
    queued_at = now()
    submission.status = "queued"
    submission.score = 0
    submission.max_score = 100
    submission.details = []
    submission.message = message
    submission.judged_at = None
    submission.queued_at = queued_at
    submission.queue_job_id = None

    queue = get_judge_queue(store)
    job = build_code_queue_job(
        submission,
        problem,
        store.get_problem_judge_config(problem.id),
        backend=queue.backend,
    )
    job.created_at = queued_at
    job.status = "pending"
    job.assigned_node_id = None
    job.attempts = 0
    job.last_error = ""
    job.leased_at = None
    job.completed_at = None
    submission.queue_job_id = job.id
    queue.enqueue_code_submission(
        submission,
        job,
        previous_submission=previous_submission,
        previous_job=previous_job,
    )
    return submission


def requeue_submission_for_rejudge(
    store: Repository,
    submission: Submission,
    actor: User,
    *,
    reason: str = "",
    action: str = "submission.rejudge",
) -> Submission:
    if submission.problem_type != "code":
        raise ValueError("Only code submissions can be rejudged")
    problem = store.get_problem(submission.problem_id)
    if not problem or problem.type != "code":
        raise ValueError("Code problem for submission was not found")

    requeued = enqueue_code_submission_job(
        store,
        submission,
        problem,
        message="已重新进入在线评测队列，等待 judge worker 重测。",
    )
    metadata = {
        "problem_id": requeued.problem_id,
        "queue_job_id": requeued.queue_job_id,
        "reason": reason,
    }
    store.add_audit(actor.id, action, f"submission:{requeued.id}", metadata)
    add_notification(
        store,
        requeued.user_id,
        "提交已进入重测队列",
        f"{requeued.problem_title} 已重新排队等待在线评测。",
        "judge",
    )
    return requeued


def profile_user(user: User) -> UserProfile:
    return UserProfile(**public_user(user).model_dump(), email=user.email)


def ensure_student_school(user: User) -> bool:
    if user.role != "student":
        return False
    if user.school.strip():
        return False
    user.school = DEFAULT_STUDENT_SCHOOL
    return True


def require_student_permissions(*permissions: str):
    def dependency(user: User = Depends(require_permissions(*permissions))) -> User:
        if user.role != "student":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only student accounts can participate",
            )
        return user

    return dependency


def query_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def auth_datetime(value: datetime | None) -> datetime | None:
    return query_datetime(value)


def config_int(config: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def enabled_compiler_languages(store: Repository) -> list[CompilerLanguage]:
    return [
        CompilerLanguage(**config.model_dump(include={"code", "display_name", "version", "source_extension"}))
        for config in store.list_compiler_configs()
        if config.enabled
    ]


def ensure_enabled_compiler_language(store: Repository, language: str) -> CompilerConfig:
    compiler_config = store.get_compiler_config(language)
    if not compiler_config or not compiler_config.enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Language is not enabled for online judging")
    return compiler_config


def auth_metadata(request: Request, username: str, reason: str, **extra: Any) -> dict[str, Any]:
    client_host = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")
    return {
        "username": username,
        "reason": reason,
        "client_host": client_host,
        "user_agent": user_agent[:200],
        **extra,
    }


def require_judge_node_token(x_judge_node_token: str | None = Header(default=None)) -> None:
    if x_judge_node_token != app_config.JUDGE_NODE_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid judge node token")


def is_login_locked(user: User, current: datetime) -> bool:
    locked_until = auth_datetime(user.locked_until)
    return bool(locked_until and locked_until > current)


def contest_detail(contest: Contest, store: Repository) -> ContestDetail:
    problems = {p.id: p for p in store.list_problems() if p.visible}
    submissions = store.list_submissions()
    participant_ids = student_user_ids(store)
    return ContestDetail(
        **contest.model_dump(),
        problems=[
            problem_summary(problems[pid], submissions, participant_ids)
            for pid in contest.problem_ids
            if pid in problems
        ],
    )


def contest_owners(store: Repository, contest: Contest) -> set[str]:
    owners: set[str] = set()
    for clarification in store.list_clarifications():
        if clarification.contest_id == contest.id:
            owners.add(clarification.user_id)
    for submission in store.list_submissions():
        if submission.contest_id == contest.id:
            owners.add(submission.user_id)
    return owners


def ensure_contest_access(user: User, contest: Contest, store: Repository) -> None:
    if role_has_permission(user.role, "contest:manage") or role_has_permission(user.role, "judge:monitor") or role_has_permission(user.role, "clarification:read:all"):
        return
    if user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    if contest.visibility != "public":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")


def ensure_contest_resource_owner(user: User, contest: Contest, store: Repository, *, include_students: bool = True) -> None:
    if role_has_permission(user.role, "contest:manage"):
        return
    if not include_students or user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    if user.id not in contest_owners(store, contest):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")


def ensure_contest_submission_owner(user: User, contest: Contest, submission: Submission) -> None:
    if submission.contest_id != contest.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    if role_has_permission(user.role, "submission:read:all") or role_has_permission(user.role, "contest:manage"):
        return
    if submission.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")


def contest_problem_lookup(contest: Contest, store: Repository, problem_id: str) -> Problem:
    problem = store.get_problem(problem_id)
    if not problem or not problem.visible or problem_id not in contest.problem_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    return problem


def contest_problem_details(contest: Contest, store: Repository, user: User | None = None) -> list[ProblemDetail]:
    problems = []
    for problem_id in contest.problem_ids:
        problem = store.get_problem(problem_id)
        if not problem or not problem.visible:
            continue
        problems.append(problem_detail(problem))
    return problems


def _submission_effective_time(submission: Submission) -> datetime:
    return auth_datetime(submission.judged_at) or auth_datetime(submission.created_at) or now()


def _contest_submission_before_freeze(submission: Submission, contest: Contest) -> bool:
    if not contest.frozen:
        return True
    freeze_at = auth_datetime(contest.frozen_at)
    if freeze_at is None:
        return True
    return _submission_effective_time(submission) <= freeze_at


def _standing_problem_payload() -> dict[str, Any]:
    return {
        "score": 0,
        "status": "",
        "attempts": 0,
        "accepted_at": None,
        "penalty_minutes": 0,
        "first_blood": False,
    }


def build_contest_standings(contest: Contest, store: Repository) -> list[StandingRow]:
    users = {u.id: u for u in store.list_users()}
    participant_ids = {user_id for user_id, item in users.items() if item.role == "student"}
    relevant_submissions = [
        submission
        for submission in store.list_submissions()
        if submission.contest_id == contest.id and submission.user_id in participant_ids
    ]
    relevant_submissions.sort(key=lambda item: (_submission_effective_time(item), item.created_at, item.id))

    if contest.rule != "ACM":
        rows: dict[str, dict[str, Any]] = {}
        for submission in relevant_submissions:
            row = rows.setdefault(
                submission.user_id,
                {
                    "user_id": submission.user_id,
                    "display_name": users.get(submission.user_id).display_name if users.get(submission.user_id) else submission.user_id,
                    "solved": 0,
                    "score": 0,
                    "penalty": 0,
                    "first_blood": 0,
                    "problems": {},
                },
            )
            best = row["problems"].get(submission.problem_id, _standing_problem_payload())
            if submission.score > best["score"]:
                row["problems"][submission.problem_id] = {
                    **best,
                    "score": submission.score,
                    "status": submission.status,
                }
        for row in rows.values():
            row["score"] = sum(item["score"] for item in row["problems"].values())
            row["solved"] = sum(1 for item in row["problems"].values() if item["score"] >= 100)
        return [StandingRow(**row) for row in sorted(rows.values(), key=lambda item: (-item["solved"], -item["score"], item["display_name"]))]

    rows: dict[str, dict[str, Any]] = {}
    first_blood_owner: dict[str, str] = {}
    first_blood_time: dict[str, datetime] = {}
    contest_start = auth_datetime(contest.start_at) or now()

    for submission in relevant_submissions:
        row = rows.setdefault(
            submission.user_id,
            {
                "user_id": submission.user_id,
                "display_name": users.get(submission.user_id).display_name if users.get(submission.user_id) else submission.user_id,
                "solved": 0,
                "score": 0,
                "penalty": 0,
                "first_blood": 0,
                "problems": {},
            },
        )
        problem_row = row["problems"].setdefault(submission.problem_id, _standing_problem_payload())
        visible_to_board = _contest_submission_before_freeze(submission, contest)
        if problem_row["accepted_at"] is not None:
            continue
        if not visible_to_board:
            continue
        if submission.status in {"accepted", "manual_override"} and submission.score >= submission.max_score:
            effective_time = _submission_effective_time(submission)
            elapsed_minutes = max(0, int((effective_time - contest_start).total_seconds() // 60))
            penalty_minutes = elapsed_minutes + problem_row["attempts"] * 20
            problem_row["score"] = submission.max_score
            problem_row["status"] = submission.status
            problem_row["accepted_at"] = effective_time
            problem_row["penalty_minutes"] = penalty_minutes
            if submission.problem_id not in first_blood_time or effective_time < first_blood_time[submission.problem_id]:
                first_blood_time[submission.problem_id] = effective_time
                first_blood_owner[submission.problem_id] = submission.user_id
        else:
            problem_row["attempts"] += 1
            problem_row["status"] = submission.status

    for row in rows.values():
        for problem_id, problem_row in row["problems"].items():
            if problem_row["accepted_at"] is None:
                continue
            is_first_blood = first_blood_owner.get(problem_id) == row["user_id"]
            problem_row["first_blood"] = is_first_blood
            row["solved"] += 1
            row["score"] += int(problem_row["score"])
            row["penalty"] += int(problem_row["penalty_minutes"])
            if is_first_blood:
                row["first_blood"] += 1

    return [
        StandingRow(**row)
        for row in sorted(
            rows.values(),
            key=lambda item: (-item["solved"], item["penalty"], -item["first_blood"], item["display_name"]),
        )
    ]


def contest_balloon_payload(
    contest: Contest,
    submission: Submission,
    *,
    display_name: str,
) -> ContestBalloon:
    return ContestBalloon(
        contest_id=contest.id,
        submission_id=submission.id,
        user_id=submission.user_id,
        display_name=display_name,
        problem_id=submission.problem_id,
        problem_title=submission.problem_title,
        status=submission.status,
        score=submission.score,
        max_score=submission.max_score,
        judged_at=submission.judged_at,
        released=bool(submission.judged_at),
    )


def contest_submission_to_balloon(submission: Submission, store: Repository) -> ContestBalloon:
    contest = store.get_contest(submission.contest_id or "")
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    user = store.get_user(submission.user_id)
    return contest_balloon_payload(
        contest,
        submission,
        display_name=user.display_name if user else submission.user_id,
    )


def contest_print_payload(contest: Contest, submission: Submission | None, request: ContestPrintRequest) -> ContestPrintResponse:
    if submission:
        source_code = submission.source_code or ""
        source_kind = "submission"
        problem_id = submission.problem_id
        language = submission.language
        submission_id = submission.id
    else:
        source_code = request.source_code or ""
        source_kind = "request"
        problem_id = request.problem_id
        language = request.language
        submission_id = request.submission_id
    source_code = safe_print_source(source_code)
    return ContestPrintResponse(
        contest_id=contest.id,
        submission_id=submission_id,
        problem_id=problem_id,
        language=language,
        source_kind=source_kind,  # type: ignore[arg-type]
        source_code=source_code,
        line_count=source_code.count("\n") + (0 if source_code.endswith("\n") else 1),
    )


def contest_submission_is_objective(problem: Problem) -> bool:
    return problem.type in {"blank", "single_choice", "multiple_choice"}


def problem_set_detail(problem_set: ProblemSet, store: Repository) -> ProblemSetDetail:
    problems = {p.id: p for p in store.list_problems() if p.visible}
    submissions = store.list_submissions()
    participant_ids = student_user_ids(store)
    return ProblemSetDetail(
        **problem_set.model_dump(),
        problems=[
            problem_summary(problems[pid], submissions, participant_ids)
            for pid in problem_set.problem_ids
            if pid in problems
        ],
    )


def offline_ttl_hours(*policies: Any) -> int | None:
    values = [int(policy.ttl_hours) for policy in policies if policy and policy.ttl_hours is not None]
    return min(values) if values else None


def pack_record_from_payload(
    payload: dict[str, Any],
    *,
    created_by: str,
    source: dict[str, Any],
    problem_set_id: str | None = None,
    problem_ids: list[str] | None = None,
    ttl_hours: int | None = None,
    retention_days: int | None = None,
    max_downloads: int | None = None,
    status: str = "active",
    downloaded: int = 0,
) -> OfflinePackRecord:
    generated_at = datetime.fromisoformat(str(payload["generated_at"]).replace("Z", "+00:00"))
    expires_at = datetime.fromisoformat(str(payload["expires_at"]).replace("Z", "+00:00"))
    return OfflinePackRecord(
        pack_id=str(payload["pack_id"]),
        source=source,
        problem_set_id=problem_set_id or source.get("id"),
        problem_ids=problem_ids or [str(problem.get("id")) for problem in payload.get("problems", []) if isinstance(problem, dict)],
        generated_at=generated_at,
        expires_at=expires_at,
        ttl_hours=ttl_hours,
        retention_days=retention_days,
        max_downloads=max_downloads,
        downloaded=downloaded,
        status=status if status in {"active", "expired", "disabled", "download_limit_reached"} else "active",
        created_by=created_by,
        created_at=generated_at,
        last_downloaded_at=None,
    )


def pack_problem_ids(payload: dict[str, Any]) -> list[str]:
    problems = payload.get("problems", [])
    if not isinstance(problems, list):
        return []
    return [str(problem.get("id")) for problem in problems if isinstance(problem, dict) and str(problem.get("id", "")).strip()]


def pack_is_expired(record: OfflinePackRecord, *, now_value: datetime | None = None) -> bool:
    return record.expires_at <= (now_value or now())


def can_export_offline_problem(problem: Problem, judge_config: dict[str, Any]) -> bool:
    if not problem.visible or problem.type == "code":
        return False
    if not problem.offline_enabled:
        return False
    if problem.offline_policy.answer_visibility != "full":
        return False
    return bool(judge_config)


def objective_offline_pack_response(
    problems: list[Problem],
    store: Repository,
    *,
    ttl_hours: int | None = None,
    source: dict[str, Any] | None = None,
    created_by: str | None = None,
) -> OfflinePackResponse:
    exportable: list[Problem] = []
    judge_configs: dict[str, dict[str, Any]] = {}
    for problem in problems:
        judge_config = store.get_problem_judge_config(problem.id) if problem.type != "code" else {}
        if not can_export_offline_problem(problem, judge_config):
            continue
        exportable.append(problem)
        judge_configs[problem.id] = judge_config
    pack_ttl_hours = ttl_hours or offline_ttl_hours(*(problem.offline_policy for problem in exportable))
    generated_at = datetime.now(timezone.utc)
    expires_at = generated_at + timedelta(hours=max(pack_ttl_hours or app_config.OFFLINE_PACK_TTL_HOURS, 1))
    max_downloads = next((problem.offline_policy.max_downloads for problem in exportable if problem.offline_policy.max_downloads is not None), None)
    retention_days = next((problem.offline_policy.retention_days for problem in exportable if problem.offline_policy.retention_days is not None), None)
    pack_id = f"pack-{uuid4().hex[:16]}"
    problem_ids = [problem.id for problem in exportable]
    built = build_offline_pack(
        exportable,
        judge_configs,
        ttl_hours=pack_ttl_hours,
        source=source,
        pack_id=pack_id,
        lifecycle=pack_lifecycle(
            source or {"type": "training"},
            type("Policy", (), {"max_downloads": max_downloads, "retention_days": retention_days})(),
            problem_ids=problem_ids,
        ),
        generated_at=generated_at,
        expires_at=expires_at,
    )
    payload = built["payload"]
    payload["lifecycle"] = pack_lifecycle(
        source or {"type": "training"},
        type("Policy", (), {"max_downloads": max_downloads, "retention_days": retention_days})(),
        downloaded=0,
        status="active",
        problem_ids=problem_ids,
    )
    record = pack_record_from_payload(
        payload,
        created_by=created_by or str((source or {}).get("type") or "system"),
        source=source or {"type": "training"},
        problem_set_id=(source or {}).get("id") if isinstance(source, dict) else None,
        problem_ids=problem_ids,
        ttl_hours=pack_ttl_hours,
        retention_days=retention_days,
        max_downloads=max_downloads,
        status="active",
        downloaded=0,
    )
    store.add_offline_pack(record)
    return OfflinePackResponse(**built)


@app.get("/health", response_model=HealthResponse, include_in_schema=False)
@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="gayoj API", time=datetime.now(timezone.utc).isoformat())


@app.post("/api/v1/auth/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    store: Repository = Depends(get_repository),
) -> LoginResponse:
    user = store.get_user_by_username(payload.username)
    current = now()
    config = store.get_system_config()
    max_attempts = config_int(config, "login_max_failed_attempts", 5, 1, 50)
    lockout_minutes = config_int(config, "login_lockout_minutes", 15, 1, 1440)

    if not user:
        store.add_audit(
            None,
            "auth.login_failed",
            f"user:{payload.username}",
            auth_metadata(request, payload.username, "unknown_user"),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    if user.disabled:
        store.add_audit(
            user.id,
            "auth.login_failed",
            f"user:{user.id}",
            auth_metadata(request, payload.username, "disabled"),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    if is_login_locked(user, current):
        store.add_audit(
            user.id,
            "auth.login_locked",
            f"user:{user.id}",
            auth_metadata(
                request,
                payload.username,
                "locked",
                failed_login_attempts=user.failed_login_attempts,
                locked_until=user.locked_until.isoformat() if user.locked_until else None,
            ),
        )
        raise HTTPException(status_code=423, detail="Account is temporarily locked")

    if user.locked_until and not is_login_locked(user, current):
        user.failed_login_attempts = 0
        user.locked_until = None

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts += 1
        locked_until: datetime | None = None
        if user.failed_login_attempts >= max_attempts:
            locked_until = current + timedelta(minutes=lockout_minutes)
            user.locked_until = locked_until
        store.update_user(user)
        metadata = auth_metadata(
            request,
            payload.username,
            "invalid_credentials",
            failed_login_attempts=user.failed_login_attempts,
            max_failed_attempts=max_attempts,
            locked_until=locked_until.isoformat() if locked_until else None,
        )
        store.add_audit(user.id, "auth.login_failed", f"user:{user.id}", metadata)
        if locked_until:
            store.add_audit(user.id, "auth.login_locked", f"user:{user.id}", metadata)
            raise HTTPException(status_code=423, detail="Account is temporarily locked")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    previous_failed_attempts = user.failed_login_attempts
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = current
    store.update_user(user)
    store.add_audit(
        user.id,
        "auth.login",
        f"user:{user.id}",
        auth_metadata(
            request,
            payload.username,
            "success",
            failed_login_attempts_reset=previous_failed_attempts,
        ),
    )
    return LoginResponse(access_token=create_token(user), user=public_user(user))


@app.get("/api/v1/auth/me", response_model=PublicUser)
def me(user: User = Depends(get_current_user)) -> PublicUser:
    return public_user(user)


@app.put("/api/v1/users/me/password", response_model=PublicUser)
def change_my_password(
    payload: PasswordChangeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    store: Repository = Depends(get_repository),
) -> PublicUser:
    if not verify_password(payload.current_password, user.password_hash):
        store.add_audit(
            user.id,
            "auth.password_change_failed",
            f"user:{user.id}",
            auth_metadata(request, user.username, "invalid_current_password"),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    policy_errors = validate_password_policy(payload.new_password, store.get_system_config())
    if policy_errors:
        store.add_audit(
            user.id,
            "auth.password_change_failed",
            f"user:{user.id}",
            auth_metadata(request, user.username, "policy_violation", violations=policy_errors),
        )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=policy_errors)

    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = now()
    user.failed_login_attempts = 0
    user.locked_until = None
    store.update_user(user)
    store.add_audit(user.id, "auth.password_changed", f"user:{user.id}", auth_metadata(request, user.username, "success"))
    return public_user(user)


@app.get("/api/v1/users/me/profile", response_model=UserProfile)
def get_my_profile(
    user: User = Depends(get_current_user),
    store: Repository = Depends(get_repository),
) -> UserProfile:
    if ensure_student_school(user):
        store.update_user(user)
    return profile_user(user)


@app.patch("/api/v1/users/me/profile", response_model=UserProfile)
def update_my_profile(
    payload: UserProfileUpdate,
    user: User = Depends(get_current_user),
    store: Repository = Depends(get_repository),
) -> UserProfile:
    update = payload.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in update.items():
        setattr(user, key, value)
    defaulted_school = ensure_student_school(user)
    if update or defaulted_school:
        store.update_user(user)
        if update:
            store.add_audit(user.id, "user.profile.update", f"user:{user.id}", {"fields": sorted(update)})
    return profile_user(user)


@app.get("/api/v1/problems", response_model=list[ProblemSummary])
def list_problems(
    q: str = "",
    type: str = "",
    tag: list[str] = Query(default=[]),
    tags: list[str] = Query(default=[]),
    store: Repository = Depends(get_repository),
) -> list[ProblemSummary]:
    selected_tags = normalize_tag_filters(tag, tags)
    submissions = store.list_submissions()
    participant_ids = student_user_ids(store)
    items = []
    for problem in store.list_problems():
        if not problem.visible:
            continue
        if q and q.lower() not in f"{problem.id} {problem.title} {' '.join(problem.tags)}".lower():
            continue
        if type and problem.type != type:
            continue
        if selected_tags and not all(item in problem.tags for item in selected_tags):
            continue
        items.append(problem_summary(problem, submissions, participant_ids))
    return items


@app.get("/api/v1/tags", response_model=list[TagTreeNode])
def list_tags(store: Repository = Depends(get_repository)) -> list[TagTreeNode]:
    return tag_tree(store.list_tags())


@app.get("/api/v1/admin/tags", response_model=list[Tag])
def admin_list_tags(
    user: User = Depends(require_permissions("tag:manage")),
    store: Repository = Depends(get_repository),
) -> list[Tag]:
    return sorted(store.list_tags(), key=lambda item: (item.sort_order, item.name, item.id))


@app.post("/api/v1/admin/tags", response_model=Tag)
def admin_create_tag(
    payload: TagCreate,
    user: User = Depends(require_permissions("tag:manage")),
    store: Repository = Depends(get_repository),
) -> Tag:
    ensure_tag_name_available(store, payload.name)
    tag_id = next_tag_id(store)
    ensure_tag_parent_valid(store, tag_id, payload.parent_id)
    tag = Tag(
        id=tag_id,
        name=payload.name,
        slug=tag_slug(payload.name),
        parent_id=payload.parent_id,
        sort_order=payload.sort_order,
        created_at=now(),
    )
    store.add_tag(tag)
    store.add_audit(user.id, "tag.create", f"tag:{tag.id}", {"name": tag.name, "parent_id": tag.parent_id})
    return tag


@app.put("/api/v1/admin/tags/{tag_id}", response_model=Tag)
def admin_update_tag(
    tag_id: str,
    payload: TagUpdate,
    user: User = Depends(require_permissions("tag:manage")),
    store: Repository = Depends(get_repository),
) -> Tag:
    existing = store.get_tag(tag_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    ensure_tag_name_available(store, payload.name, tag_id=tag_id)
    ensure_tag_parent_valid(store, tag_id, payload.parent_id)
    tag = Tag(
        id=existing.id,
        name=payload.name,
        slug=tag_slug(payload.name),
        parent_id=payload.parent_id,
        sort_order=payload.sort_order,
        created_at=existing.created_at,
    )
    store.update_tag(tag)
    store.add_audit(
        user.id,
        "tag.update",
        f"tag:{tag.id}",
        {"old_name": existing.name, "name": tag.name, "parent_id": tag.parent_id},
    )
    return tag


@app.delete("/api/v1/admin/tags/{tag_id}", response_model=Tag)
def admin_delete_tag(
    tag_id: str,
    user: User = Depends(require_permissions("tag:manage")),
    store: Repository = Depends(get_repository),
) -> Tag:
    tag = store.get_tag(tag_id)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    if any(item.parent_id == tag.id for item in store.list_tags()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tag has child tags")
    if any(tag.name in problem.tags for problem in store.list_problems()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tag is still used by problems")
    deleted = store.delete_tag(tag.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    store.add_audit(user.id, "tag.delete", f"tag:{tag.id}", {"name": tag.name})
    return deleted


@app.post("/api/v1/problems", response_model=ProblemDetail, response_model_exclude_none=True)
def create_problem(
    payload: ProblemCreate,
    user: User = Depends(require_permissions("problem:create")),
    store: Repository = Depends(get_repository),
) -> ProblemDetail:
    problem = Problem(
        id=next_problem_id(store),
        author_id=user.id,
        created_at=now(),
        **payload.model_dump(),
    )
    store.add_problem(problem)
    store.add_audit(user.id, "problem.create", f"problem:{problem.id}", {"title": problem.title})
    return problem_detail(problem)


@app.get("/api/v1/problems/{problem_id}", response_model=ProblemDetail, response_model_exclude_none=True)
def get_problem(
    problem_id: str,
    store: Repository = Depends(get_repository),
    user: User | None = Depends(get_optional_user),
) -> ProblemDetail:
    problem = store.get_problem(problem_id)
    if not problem or not problem.visible:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    return problem_detail(problem)


@app.get("/api/v1/admin/problems", response_model=list[ProblemAdminDetail])
def admin_list_problems(
    user: User = Depends(require_permissions("problem:edit:own")),
    store: Repository = Depends(get_repository),
) -> list[ProblemAdminDetail]:
    problems = store.list_problems()
    if not role_has_permission(user.role, "problem:edit:all"):
        problems = [problem for problem in problems if problem.author_id == user.id]
    return [admin_problem_detail(problem, store) for problem in problems]


@app.post("/api/v1/admin/problems", response_model=ProblemAdminDetail)
def admin_create_problem(
    payload: ProblemCreate,
    user: User = Depends(require_permissions("problem:create")),
    store: Repository = Depends(get_repository),
) -> ProblemAdminDetail:
    problem = Problem(
        id=next_problem_id(store),
        author_id=user.id,
        created_at=now(),
        **payload.model_dump(),
    )
    store.add_problem(problem)
    store.add_audit(
        user.id,
        "problem.create",
        f"problem:{problem.id}",
        {"title": problem.title, "type": problem.type, "visible": problem.visible},
    )
    return admin_problem_detail(problem, store)


@app.get("/api/v1/admin/problems/export", response_model=ProblemExportResponse)
def admin_export_problems(
    format: ProblemPackageFormat = Query(default="hydro"),
    ids: str = "",
    user: User = Depends(require_permissions("problem:edit:own")),
    store: Repository = Depends(get_repository),
) -> ProblemExportResponse:
    all_problems = {problem.id: problem for problem in store.list_problems()}
    requested_ids = parse_problem_ids(ids)
    if requested_ids:
        problems = []
        for problem_id in requested_ids:
            problem = all_problems.get(problem_id)
            if not problem:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Problem not found: {problem_id}")
            ensure_problem_editable(user, problem)
            problems.append(problem)
    else:
        problems = list(all_problems.values())
        if not role_has_permission(user.role, "problem:edit:all"):
            problems = [problem for problem in problems if problem.author_id == user.id]

    if not problems:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No manageable problems to export")

    package_items = [(problem, store.get_problem_judge_config(problem.id)) for problem in problems]
    try:
        content, content_type = export_problem_package(format, package_items)
    except ProblemPackageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    store.add_audit(
        user.id,
        "problem.export",
        "problem:package",
        {"format": format, "count": len(problems), "problem_ids": [problem.id for problem in problems]},
    )
    return ProblemExportResponse(
        format=format,
        filename=package_filename(format),
        content_type=content_type,
        content=content,
        problem_count=len(problems),
        problem_ids=[problem.id for problem in problems],
    )


@app.post("/api/v1/admin/problems/import", response_model=ProblemImportResponse)
def admin_import_problems(
    payload: ProblemImportRequest,
    user: User = Depends(require_permissions("problem:create")),
    store: Repository = Depends(get_repository),
) -> ProblemImportResponse:
    try:
        imported = parse_problem_package(payload.format, payload.content)
    except ProblemPackageError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    if not imported:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Problem package contains no problems")

    existing_by_id = {problem.id: problem for problem in store.list_problems()}
    used_ids = set(existing_by_id)
    planned: list[tuple[Problem, str, str | None]] = []
    skipped_items: list[ProblemImportItem] = []
    current = now()

    for item in imported:
        source_id = import_source_id(item.source_id)
        existing = existing_by_id.get(source_id) if source_id else None
        if existing and payload.conflict_strategy == "skip":
            skipped_items.append(
                ProblemImportItem(
                    source_id=item.source_id,
                    target_id=existing.id,
                    title=item.payload.title,
                    type=item.payload.type,
                    action="skipped",
                )
            )
            continue

        if existing and payload.conflict_strategy == "overwrite":
            ensure_problem_editable(user, existing)
            target_id = existing.id
            action = "updated"
            author_id = existing.author_id
            created_at = existing.created_at
        else:
            if source_id and source_id not in used_ids:
                target_id = source_id
            else:
                target_id = next_import_problem_id(used_ids)
            used_ids.add(target_id)
            action = "created"
            author_id = user.id
            created_at = current

        problem = Problem(
            id=target_id,
            author_id=author_id,
            created_at=created_at,
            **item.payload.model_dump(),
        )
        planned.append((problem, action, item.source_id))

    response_items = [
        ProblemImportItem(
            source_id=source_id,
            target_id=problem.id,
            title=problem.title,
            type=problem.type,
            action=action,
        )
        for problem, action, source_id in planned
    ] + skipped_items

    created = sum(1 for _, action, _ in planned if action == "created")
    updated = sum(1 for _, action, _ in planned if action == "updated")
    skipped = len(skipped_items)

    if not payload.dry_run and planned:
        version_snapshots: list[tuple[Problem, str, str]] = []
        for problem, action, _ in planned:
            if action == "updated":
                existing = existing_by_id[problem.id].model_copy(deep=True)
                existing.judge_config = store.get_problem_judge_config(existing.id)
                version_snapshots.append((existing, user.id, "update"))
        store.upsert_problems([problem for problem, _, _ in planned], version_snapshots=version_snapshots)
        store.add_audit(
            user.id,
            "problem.import",
            "problem:package",
            {
                "format": payload.format,
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "conflict_strategy": payload.conflict_strategy,
            },
        )

    return ProblemImportResponse(
        format=payload.format,
        dry_run=payload.dry_run,
        imported=created + updated,
        created=created,
        updated=updated,
        skipped=skipped,
        items=response_items,
    )


@app.get("/api/v1/admin/problems/{problem_id}", response_model=ProblemAdminDetail)
def admin_get_problem(
    problem_id: str,
    user: User = Depends(require_permissions("problem:edit:own")),
    store: Repository = Depends(get_repository),
) -> ProblemAdminDetail:
    problem = store.get_problem(problem_id)
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    ensure_problem_editable(user, problem)
    return admin_problem_detail(problem, store)


@app.get("/api/v1/admin/problems/{problem_id}/versions", response_model=list[ProblemVersion])
def admin_list_problem_versions(
    problem_id: str,
    user: User = Depends(require_permissions("problem:edit:own")),
    store: Repository = Depends(get_repository),
) -> list[ProblemVersion]:
    problem = store.get_problem(problem_id)
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    ensure_problem_editable(user, problem)
    return store.list_problem_versions(problem_id)


@app.post("/api/v1/admin/problems/{problem_id}/versions/{version_id}/restore", response_model=ProblemAdminDetail)
def admin_restore_problem_version(
    problem_id: str,
    version_id: str,
    user: User = Depends(require_permissions("problem:edit:own")),
    store: Repository = Depends(get_repository),
) -> ProblemAdminDetail:
    problem = store.get_problem(problem_id)
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    ensure_problem_editable(user, problem)
    version = store.get_problem_version(problem_id, version_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem version not found")
    problem.judge_config = store.get_problem_judge_config(problem.id)
    current_version = store.add_problem_version(problem, user.id, "restore")
    restored = store.restore_problem_version(problem_id, version_id)
    if not restored:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem version not found")
    store.add_audit(
        user.id,
        "problem.version.restore",
        f"problem:{problem_id}",
        {
            "restored_version": version.version,
            "archived_current_version": current_version.version,
            "title": restored.title,
        },
    )
    return admin_problem_detail(restored, store)


@app.put("/api/v1/admin/problems/{problem_id}", response_model=ProblemAdminDetail)
def admin_update_problem(
    problem_id: str,
    payload: ProblemUpdate,
    user: User = Depends(require_permissions("problem:edit:own")),
    store: Repository = Depends(get_repository),
) -> ProblemAdminDetail:
    existing = store.get_problem(problem_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    ensure_problem_editable(user, existing)
    existing.judge_config = store.get_problem_judge_config(existing.id)
    archived = store.add_problem_version(existing, user.id, "update")
    problem = Problem(
        id=existing.id,
        author_id=existing.author_id,
        created_at=existing.created_at,
        **payload.model_dump(),
    )
    store.update_problem(problem)
    store.add_audit(
        user.id,
        "problem.update",
        f"problem:{problem.id}",
        {"title": problem.title, "type": problem.type, "visible": problem.visible, "previous_version": archived.version},
    )
    return admin_problem_detail(problem, store)


@app.delete("/api/v1/admin/problems/{problem_id}", response_model=ProblemAdminDetail)
def admin_delete_problem(
    problem_id: str,
    user: User = Depends(require_permissions("problem:edit:own")),
    store: Repository = Depends(get_repository),
) -> ProblemAdminDetail:
    problem = store.get_problem(problem_id)
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    ensure_problem_editable(user, problem)
    problem.judge_config = store.get_problem_judge_config(problem.id)
    archived = store.add_problem_version(problem, user.id, "delete")
    deleted = store.delete_problem(problem.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    store.add_audit(
        user.id,
        "problem.delete",
        f"problem:{problem.id}",
        {"title": problem.title, "previous_version": archived.version},
    )
    return admin_problem_detail(deleted, store)


@app.patch("/api/v1/admin/problems/{problem_id}/visibility", response_model=ProblemAdminDetail)
def admin_update_problem_visibility(
    problem_id: str,
    payload: ProblemVisibilityUpdate,
    user: User = Depends(require_permissions("problem:edit:own")),
    store: Repository = Depends(get_repository),
) -> ProblemAdminDetail:
    problem = store.get_problem(problem_id)
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    ensure_problem_editable(user, problem)
    if problem.visible == payload.visible:
        return admin_problem_detail(problem, store)
    problem.judge_config = store.get_problem_judge_config(problem.id)
    archived = store.add_problem_version(problem, user.id, "update")
    problem.visible = payload.visible
    updated = store.update_problem(problem)
    store.add_audit(
        user.id,
        "problem.publish" if payload.visible else "problem.unpublish",
        f"problem:{problem.id}",
        {
            "title": problem.title,
            "visible": payload.visible,
            "previous_version": archived.version,
        },
    )
    return admin_problem_detail(updated, store)


@app.patch("/api/v1/admin/problems/{problem_id}/offline-policy", response_model=ProblemAdminDetail)
def admin_update_problem_offline_policy(
    problem_id: str,
    payload: OfflinePolicyUpdate,
    user: User = Depends(require_permissions("problem:edit:own")),
    store: Repository = Depends(get_repository),
) -> ProblemAdminDetail:
    problem = store.get_problem(problem_id)
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    ensure_problem_editable(user, problem)
    problem.judge_config = store.get_problem_judge_config(problem.id)
    archived = store.add_problem_version(problem, user.id, "update")
    problem.offline_enabled = payload.offline_enabled
    problem.offline_policy = payload.offline_policy
    updated = store.update_problem(problem)
    store.add_audit(
        user.id,
        "problem.offline_policy.update",
        f"problem:{problem.id}",
        {
            "offline_enabled": updated.offline_enabled,
            "offline_policy": updated.offline_policy.model_dump(mode="json"),
            "previous_version": archived.version,
        },
    )
    return admin_problem_detail(updated, store)


@app.get("/api/v1/admin/problems/{problem_id}/testdata", response_model=ProblemTestData)
def admin_get_problem_testdata(
    problem_id: str,
    user: User = Depends(require_permissions("problem:edit:own")),
    store: Repository = Depends(get_repository),
) -> ProblemTestData:
    problem = store.get_problem(problem_id)
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    ensure_problem_editable(user, problem)
    ensure_code_problem_testdata_target(problem)
    metadata = store.get_problem_test_data(problem.id)
    if not metadata:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test data not found")
    return metadata


@app.post("/api/v1/admin/problems/{problem_id}/testdata", response_model=ProblemTestData)
async def admin_upload_problem_testdata(
    problem_id: str,
    file: UploadFile = File(...),
    user: User = Depends(require_permissions("problem:edit:own")),
    store: Repository = Depends(get_repository),
    object_storage: ObjectStorage = Depends(get_object_storage),
) -> ProblemTestData:
    problem = store.get_problem(problem_id)
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    ensure_problem_editable(user, problem)
    ensure_code_problem_testdata_target(problem)

    filename = (file.filename or f"{problem.id}-testdata.zip").replace("\\", "/").split("/")[-1]
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Test data upload must be a ZIP archive")

    payload = await file.read(TESTDATA_MAX_ARCHIVE_BYTES + 1)
    validation = validate_testdata_zip(payload)
    digest = hashlib.sha256(payload).hexdigest()
    object_key = f"testdata/{problem.id}/{digest}.zip"
    object_storage.put_bytes(object_key, payload, content_type="application/zip")

    metadata = ProblemTestData(
        problem_id=problem.id,
        filename=filename,
        object_key=object_key,
        storage_backend=object_storage.backend,
        bucket=object_storage.bucket,
        size_bytes=len(payload),
        sha256=digest,
        uploaded_by=user.id,
        uploaded_at=now(),
        **validation,
    )
    store.set_problem_test_data(metadata)

    judge_config = store.get_problem_judge_config(problem.id)
    judge_config.update(
        {
            "testdata_ref": object_key,
            "testdata_sha256": digest,
            "testdata_cases": metadata.case_count,
        }
    )
    store.set_problem_judge_config(problem.id, judge_config)
    store.add_audit(
        user.id,
        "problem.testdata.upload",
        f"problem:{problem.id}",
        {"filename": filename, "size_bytes": len(payload), "case_count": metadata.case_count},
    )
    return metadata


@app.get(
    "/api/v1/admin/problems/{problem_id}/testdata/download",
    response_model=bytes,
    response_class=Response,
    responses={
        200: {
            "description": "Problem test data ZIP archive",
            "content": {
                "application/zip": {
                    "schema": {"type": "string", "format": "binary"},
                },
            },
        },
    },
)
def admin_download_problem_testdata(
    problem_id: str,
    user: User = Depends(require_permissions("problem:edit:own")),
    store: Repository = Depends(get_repository),
    object_storage: ObjectStorage = Depends(get_object_storage),
) -> Response:
    problem = store.get_problem(problem_id)
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    ensure_problem_editable(user, problem)
    ensure_code_problem_testdata_target(problem)
    metadata = store.get_problem_test_data(problem.id)
    if not metadata:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test data not found")
    try:
        payload = object_storage.get_bytes(metadata.object_key)
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored test data object not found") from exc

    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{problem.id}-testdata.zip"',
            "X-Content-SHA256": metadata.sha256,
            "Content-Length": str(len(payload)),
        },
    )


@app.get("/api/v1/judge/languages", response_model=list[CompilerLanguage])
def list_judge_languages(store: Repository = Depends(get_repository)) -> list[CompilerLanguage]:
    return enabled_compiler_languages(store)


@app.post("/api/v1/problems/{problem_id}/submit-code", response_model=Submission)
def submit_code(
    problem_id: str,
    payload: CodeSubmitRequest,
    user: User = Depends(require_student_permissions("submission:create")),
    store: Repository = Depends(get_repository),
) -> Submission:
    problem = store.get_problem(problem_id)
    if not problem or not problem.visible:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    if problem.type != "code":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This problem is not a code problem")
    compiler_config = ensure_enabled_compiler_language(store, payload.language)
    submission = Submission(
        id=make_submission_id(),
        user_id=user.id,
        problem_id=problem.id,
        problem_title=problem.title,
        problem_type=problem.type,
        contest_id=payload.contest_id,
        language=payload.language,
        source_code=payload.source_code,
        status="queued",
        score=0,
        max_score=100,
        created_at=now(),
    )
    try:
        enqueue_code_submission_job(store, submission, problem, message="已进入在线评测队列。")
    except QueueBackendUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    store.add_audit(
        user.id,
        "submission.code.queued",
        f"submission:{submission.id}",
        {
            "problem_id": problem.id,
            "queue_job_id": submission.queue_job_id,
            "language": compiler_config.code,
            "compiler_version": compiler_config.version,
        },
    )
    return submission


@app.post("/api/v1/problems/{problem_id}/submit-objective", response_model=SubmissionReview)
def submit_objective(
    problem_id: str,
    payload: ObjectiveSubmitRequest,
    user: User = Depends(require_student_permissions("submission:create")),
    store: Repository = Depends(get_repository),
) -> Submission:
    problem = store.get_problem(problem_id)
    if not problem or not problem.visible:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    if problem.type == "code":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Code problems must be submitted to online judge")
    score, max_score, details = judge_objective(problem, store.get_problem_judge_config(problem.id), payload.answers)
    submission = Submission(
        id=make_submission_id(),
        user_id=user.id,
        problem_id=problem.id,
        problem_title=problem.title,
        problem_type=problem.type,
        contest_id=payload.contest_id,
        answers=payload.answers,
        status="accepted" if score == max_score else "wrong_answer",
        score=score,
        max_score=max_score,
        details=details,
        message="客观题即时判分完成。",
        created_at=now(),
        judged_at=now(),
    )
    store.add_submission(submission)
    store.add_audit(user.id, "submission.objective", f"submission:{submission.id}", {"problem_id": problem.id})
    add_notification(store, user.id, "客观题判分完成", f"{problem.title}：得分 {score}/{max_score}", "judge")
    return sanitized_submission(submission)


@app.get("/api/v1/submissions", response_model=list[SubmissionReview])
def list_submissions(
    mine: bool = Query(default=False),
    user: User = Depends(require_permissions("submission:read:own")),
    store: Repository = Depends(get_repository),
) -> list[SubmissionReview]:
    submissions = store.list_submissions()
    can_read_all = role_has_permission(user.role, "submission:read:all")
    if mine or not can_read_all:
        submissions = [s for s in submissions if s.user_id == user.id]
    return [sanitized_submission(submission, include_expected=can_read_all) for submission in submissions]


@app.get("/api/v1/submissions/{submission_id}", response_model=SubmissionReview)
def get_submission(
    submission_id: str,
    user: User = Depends(require_permissions("submission:read:own")),
    store: Repository = Depends(get_repository),
) -> SubmissionReview:
    submission = store.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    can_read_all = role_has_permission(user.role, "submission:read:all")
    if submission.user_id != user.id and not can_read_all:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    return sanitized_submission(submission, include_expected=can_read_all)


@app.get("/api/v1/contests", response_model=list[ContestDetail])
def list_contests(
    user: User | None = Depends(get_optional_user),
    store: Repository = Depends(get_repository),
) -> list[ContestDetail]:
    contests = store.list_contests()
    if not user:
        contests = [contest for contest in contests if contest.visibility == "public"]
    elif not (role_has_permission(user.role, "contest:manage") or role_has_permission(user.role, "judge:monitor") or role_has_permission(user.role, "clarification:read:all")):
        contests = [contest for contest in contests if contest.visibility == "public"]
    return [contest_detail(contest, store) for contest in contests]


@app.post("/api/v1/contests", response_model=ContestDetail)
def create_contest(
    payload: ContestCreate,
    user: User = Depends(require_permissions("contest:manage")),
    store: Repository = Depends(get_repository),
) -> ContestDetail:
    existing = {p.id for p in store.list_problems() if p.visible}
    missing = [pid for pid in payload.problem_ids if pid not in existing]
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown problems: {', '.join(missing)}")
    current = now()
    contest = Contest(
        id=f"C{1000 + len(store.list_contests()) + 1}",
        title=payload.title,
        rule=payload.rule,
        start_at=payload.start_at,
        end_at=payload.end_at,
        problem_ids=payload.problem_ids,
        status="running" if payload.start_at <= current <= payload.end_at else "scheduled",
        visibility=payload.visibility,
    )
    store.add_contest(contest)
    store.add_audit(user.id, "contest.create", f"contest:{contest.id}", {"title": contest.title})
    for target in store.list_users():
        if target.role == "student":
            add_notification(store, target.id, "新比赛已发布", f"{contest.title} 已加入比赛列表。", "contest")
    return contest_detail(contest, store)


@app.post("/api/v1/contests/{contest_id}/freeze", response_model=ContestDetail)
def freeze_contest(
    contest_id: str,
    payload: ContestFreezeRequest,
    user: User = Depends(require_permissions("contest:manage")),
    store: Repository = Depends(get_repository),
) -> ContestDetail:
    contest = store.get_contest(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    if contest.frozen:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Contest is already frozen")
    contest.frozen = True
    contest.frozen_at = now()
    contest.frozen_by = user.id
    contest.freeze_reason = payload.reason
    store.update_contest(contest)
    store.add_audit(user.id, "contest.freeze", f"contest:{contest.id}", payload.model_dump())
    return contest_detail(contest, store)


@app.post("/api/v1/contests/{contest_id}/rejudge", response_model=ContestDetail)
def rejudge_contest(
    contest_id: str,
    payload: ContestFreezeRequest,
    user: User = Depends(require_permissions("contest:manage")),
    store: Repository = Depends(get_repository),
) -> ContestDetail:
    contest = store.get_contest(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    contest.rejudge_at = now()
    contest.rejudge_by = user.id
    contest.rejudge_reason = payload.reason
    store.update_contest(contest)
    requeued = 0
    for submission in store.list_submissions():
        if submission.contest_id != contest.id or submission.problem_type != "code":
            continue
        try:
            requeue_submission_for_rejudge(store, submission, user, reason=payload.reason, action="contest.rejudge")
            requeued += 1
        except Exception:
            continue
    store.add_audit(user.id, "contest.rejudge", f"contest:{contest.id}", payload.model_dump())
    return contest_detail(contest, store)


@app.get("/api/v1/contests/{contest_id}", response_model=ContestDetail)
def get_contest(
    contest_id: str,
    user: User | None = Depends(get_optional_user),
    store: Repository = Depends(get_repository),
) -> ContestDetail:
    contest = store.get_contest(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    if user and contest.visibility != "public" and not role_has_permission(user.role, "contest:manage") and not role_has_permission(user.role, "judge:monitor") and not role_has_permission(user.role, "clarification:read:all"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    if not user and contest.visibility != "public":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    return contest_detail(contest, store)


@app.get("/api/v1/contests/{contest_id}/standings", response_model=list[StandingRow])
def standings(
    contest_id: str,
    user: User | None = Depends(get_optional_user),
    store: Repository = Depends(get_repository),
) -> list[StandingRow]:
    contest = store.get_contest(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    if not user and contest.visibility != "public":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    if user:
        ensure_contest_access(user, contest, store)
    if user and user.role != "student" and not role_has_permission(user.role, "contest:manage") and not role_has_permission(user.role, "judge:monitor"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    return build_contest_standings(contest, store)


@app.get("/api/v1/contests/{contest_id}/problems", response_model=list[ProblemDetail], response_model_exclude_none=True)
def list_contest_problems(
    contest_id: str,
    user: User | None = Depends(get_optional_user),
    store: Repository = Depends(get_repository),
) -> list[ProblemDetail]:
    contest = store.get_contest(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    if not user and contest.visibility != "public":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    if user:
        ensure_contest_access(user, contest, store)
    return contest_problem_details(contest, store, user)


@app.post("/api/v1/contests/{contest_id}/clarifications", response_model=Clarification)
def create_clarification(
    contest_id: str,
    payload: ClarificationCreate,
    user: User = Depends(require_student_permissions("clarification:create")),
    store: Repository = Depends(get_repository),
) -> Clarification:
    contest = store.get_contest(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    ensure_contest_access(user, contest, store)
    clarification = Clarification(
        id=f"CL{uuid4().hex[:8].upper()}",
        contest_id=contest_id,
        user_id=user.id,
        question=payload.question,
        created_at=now(),
    )
    store.add_clarification(clarification)
    store.add_audit(user.id, "clarification.create", f"clarification:{clarification.id}")
    for target in store.list_users():
        if target.role in {"judge", "admin"}:
            add_notification(store, target.id, "新的 Clarification", payload.question, "contest")
    return clarification


@app.get("/api/v1/contests/{contest_id}/clarifications", response_model=list[Clarification])
def list_contest_clarifications(
    contest_id: str,
    user: User | None = Depends(get_optional_user),
    store: Repository = Depends(get_repository),
) -> list[Clarification]:
    contest = store.get_contest(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    ensure_contest_access(user, contest, store)
    clarifications = [c for c in store.list_clarifications() if c.contest_id == contest_id]
    if role_has_permission(user.role, "clarification:read:all") or role_has_permission(user.role, "contest:manage"):
        return clarifications
    return [c for c in clarifications if c.public or c.user_id == user.id]


@app.patch("/api/v1/clarifications/{clarification_id}", response_model=Clarification)
def reply_clarification(
    clarification_id: str,
    payload: ClarificationReply,
    user: User = Depends(require_permissions("clarification:reply")),
    store: Repository = Depends(get_repository),
) -> Clarification:
    clarification = store.get_clarification(clarification_id)
    if not clarification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clarification not found")
    contest = store.get_contest(clarification.contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    clarification.answer = payload.answer
    clarification.public = payload.public
    store.update_clarification(clarification)
    add_notification(store, clarification.user_id, "Clarification 已回复", payload.answer, "contest")
    if payload.public:
        for target in store.list_users():
            if target.id != clarification.user_id and target.role == "student":
                add_notification(store, target.id, "比赛公告", payload.answer, "contest")
    store.add_audit(user.id, "clarification.reply", f"clarification:{clarification.id}", payload.model_dump())
    return clarification


@app.get("/api/v1/contests/{contest_id}/submissions", response_model=list[SubmissionReview])
def list_contest_submissions(
    contest_id: str,
    user: User = Depends(require_permissions("submission:read:own")),
    store: Repository = Depends(get_repository),
) -> list[SubmissionReview]:
    contest = store.get_contest(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    if user.role != "student" and not role_has_permission(user.role, "submission:read:all") and not role_has_permission(user.role, "contest:manage"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    items = [submission for submission in store.list_submissions() if submission.contest_id == contest_id]
    if not role_has_permission(user.role, "submission:read:all") and not role_has_permission(user.role, "contest:manage"):
        items = [submission for submission in items if submission.user_id == user.id]
    return [sanitized_submission(submission, include_expected=True) for submission in items]


@app.post("/api/v1/contests/{contest_id}/submit", response_model=SubmissionReview)
def submit_contest_entry(
    contest_id: str,
    payload: ContestSubmitRequest,
    user: User = Depends(require_student_permissions("submission:create")),
    store: Repository = Depends(get_repository),
) -> SubmissionReview:
    contest = store.get_contest(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    ensure_contest_access(user, contest, store)
    problem = contest_problem_lookup(contest, store, payload.problem_id)
    if problem.type == "code":
        if not payload.language or not payload.source_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Code contest submissions require language and source_code")
        compiler_config = ensure_enabled_compiler_language(store, payload.language)
        submission = Submission(
            id=make_submission_id(),
            user_id=user.id,
            problem_id=problem.id,
            problem_title=problem.title,
            problem_type=problem.type,
            contest_id=contest.id,
            language=payload.language,
            source_code=payload.source_code,
            status="queued",
            score=0,
            max_score=100,
            created_at=now(),
        )
        try:
            enqueue_code_submission_job(store, submission, problem, message="已进入比赛在线评测队列。")
        except QueueBackendUnavailable as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        store.add_audit(
            user.id,
            "contest.submit.code",
            f"submission:{submission.id}",
            {"contest_id": contest.id, "problem_id": problem.id, "language": compiler_config.code},
        )
        return sanitized_submission(submission)
    if problem.type not in {"blank", "single_choice", "multiple_choice"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported contest problem type")
    if not payload.answers:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Objective contest submissions require answers")
    score, max_score, details = judge_objective(problem, store.get_problem_judge_config(problem.id), payload.answers)
    submission = Submission(
        id=make_submission_id(),
        user_id=user.id,
        problem_id=problem.id,
        problem_title=problem.title,
        problem_type=problem.type,
        contest_id=contest.id,
        answers=payload.answers,
        status="accepted" if score == max_score else "wrong_answer",
        score=score,
        max_score=max_score,
        details=details,
        message="比赛客观题即时判分完成。",
        created_at=now(),
        judged_at=now(),
    )
    store.add_submission(submission)
    store.add_audit(user.id, "contest.submit.objective", f"submission:{submission.id}", {"contest_id": contest.id, "problem_id": problem.id})
    balloon = contest_submission_to_balloon(submission, store)
    store.upsert_contest_balloon(balloon.model_dump(mode="json"))
    return sanitized_submission(submission)


@app.post("/api/v1/contests/{contest_id}/print", response_model=ContestPrintResponse)
def print_contest_source(
    contest_id: str,
    payload: ContestPrintRequest,
    user: User = Depends(require_permissions("submission:read:own")),
    store: Repository = Depends(get_repository),
) -> ContestPrintResponse:
    contest = store.get_contest(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    if user.role != "student" and not role_has_permission(user.role, "submission:read:all") and not role_has_permission(user.role, "contest:manage"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    submission: Submission | None = None
    if payload.submission_id:
        submission = store.get_submission(payload.submission_id)
        if not submission:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
        ensure_contest_submission_owner(user, contest, submission)
        if not submission.source_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Submission has no printable source")
    elif payload.source_code and not role_has_permission(user.role, "contest:manage") and not role_has_permission(user.role, "judge:monitor"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    elif payload.problem_id and not payload.source_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Print request requires source_code")
    return contest_print_payload(contest, submission, payload)


@app.get("/api/v1/contests/{contest_id}/balloons", response_model=list[ContestBalloon])
def list_contest_balloons(
    contest_id: str,
    user: User = Depends(require_permissions("judge:monitor")),
    store: Repository = Depends(get_repository),
) -> list[ContestBalloon]:
    contest = store.get_contest(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    users = {item.id: item for item in store.list_users()}
    balloons = []
    for balloon in store.list_contest_balloons(contest_id):
        submission = store.get_submission(str(balloon.get("submission_id") or ""))
        if not submission:
            continue
        payload = contest_submission_to_balloon(submission, store)
        payload.released = bool(balloon.get("released", payload.released))
        balloons.append(payload)
    return balloons


@app.patch("/api/v1/contests/{contest_id}/balloons/{submission_id}", response_model=ContestBalloon)
def update_contest_balloon(
    contest_id: str,
    submission_id: str,
    payload: ContestBalloonUpdate,
    user: User = Depends(require_permissions("judge:monitor")),
    store: Repository = Depends(get_repository),
) -> ContestBalloon:
    contest = store.get_contest(contest_id)
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    if payload.submission_id != submission_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Submission id mismatch")
    submission = store.get_submission(submission_id)
    if not submission or submission.contest_id != contest.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    balloon = contest_submission_to_balloon(submission, store)
    balloon.released = payload.released
    store.upsert_contest_balloon(balloon.model_dump(mode="json"))
    store.add_audit(
        user.id,
        "contest.balloon.update",
        f"contest:{contest.id}",
        {"submission_id": submission_id, "released": payload.released},
    )
    return balloon


@app.get("/api/v1/rankings", response_model=list[RankingRow])
def rankings(store: Repository = Depends(get_repository)) -> list[RankingRow]:
    users = [user for user in store.list_users() if user.role == "student"]
    submissions = store.list_submissions()
    rows = []
    for user in users:
        solved = {
            s.problem_id
            for s in submissions
            if s.user_id == user.id and s.status in {"accepted", "manual_override"} and s.score == s.max_score
        }
        rows.append(
            {
                "user_id": user.id,
                "display_name": user.display_name,
                "school": user.school,
                "role": user.role,
                "rating": user.rating,
                "solved": max(user.solved, len(solved)),
            }
        )
    return [RankingRow(**row) for row in sorted(rows, key=lambda item: (-item["solved"], -item["rating"], item["display_name"]))]


@app.get("/api/v1/coach/analytics", response_model=CoachAnalyticsResponse)
def coach_analytics(
    user: User = Depends(require_permissions("analytics:read")),
    store: Repository = Depends(get_repository),
) -> CoachAnalyticsResponse:
    submissions = store.list_submissions()
    users = [u for u in store.list_users() if u.role == "student"]
    participant_ids = {user.id for user in users}
    tag_counts: dict[str, dict[str, int]] = {}
    problems = {p.id: p for p in store.list_problems()}
    for submission in submissions:
        if submission.user_id not in participant_ids:
            continue
        problem = problems.get(submission.problem_id)
        if not problem:
            continue
        for tag in problem.tags:
            bucket = tag_counts.setdefault(tag, {"attempts": 0, "accepted": 0})
            bucket["attempts"] += 1
            if submission.status == "accepted":
                bucket["accepted"] += 1
    assignments = store.list_assignments()
    teams = store.list_teams()
    assignment_cards = []
    for assignment in assignments:
        problem_set = store.get_problem_set(assignment.problem_set_id)
        problem_ids = set(problem_set.problem_ids if problem_set else [])
        students = [u for u in users if not assignment.team_id or u.id in next((t.member_ids for t in teams if t.id == assignment.team_id), [])]
        completed = 0
        for student in students:
            solved = {
                s.problem_id
                for s in submissions
                if s.user_id == student.id and s.score == s.max_score and s.problem_id in problem_ids
            }
            if problem_ids and solved >= problem_ids:
                completed += 1
        assignment_cards.append(
            {
                **assignment.model_dump(mode="json"),
                "problem_set_title": problem_set.title if problem_set else assignment.problem_set_id,
                "completion": completed / len(students) if students else 0,
            }
        )
    return CoachAnalyticsResponse(
        class_size=len(users),
        active_students=len({s.user_id for s in submissions if s.user_id in participant_ids}),
        assignments=assignment_cards,
        teams=teams,
        tag_mastery=[{"tag": tag, **value} for tag, value in tag_counts.items()],
    )


@app.post("/api/v1/teams", response_model=Team)
def create_team(
    payload: TeamCreate,
    user: User = Depends(require_permissions("team:manage")),
    store: Repository = Depends(get_repository),
) -> Team:
    team = Team(
        id=f"T{1000 + len(store.list_teams()) + 1}",
        name=payload.name,
        description=payload.description,
        invite_code=uuid4().hex[:8].upper(),
        owner_id=user.id,
        member_ids=payload.member_ids,
        created_at=now(),
    )
    store.add_team(team)
    store.add_audit(user.id, "team.create", f"team:{team.id}", {"name": team.name})
    return team


@app.post("/api/v1/assignments", response_model=Assignment)
def create_assignment(
    payload: AssignmentCreate,
    user: User = Depends(require_permissions("assignment:manage")),
    store: Repository = Depends(get_repository),
) -> Assignment:
    if not store.get_problem_set(payload.problem_set_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem set not found")
    assignment = Assignment(
        id=f"A{1000 + len(store.list_assignments()) + 1}",
        created_by=user.id,
        created_at=now(),
        **payload.model_dump(),
    )
    store.add_assignment(assignment)
    store.add_audit(user.id, "assignment.create", f"assignment:{assignment.id}", {"title": assignment.title})
    team = next((t for t in store.list_teams() if t.id == assignment.team_id), None)
    targets = team.member_ids if team else [u.id for u in store.list_users() if u.role == "student"]
    for target in targets:
        add_notification(store, target, "训练作业已发布", assignment.title, "assignment")
    return assignment


@app.get("/api/v1/judge/monitor", response_model=JudgeMonitorResponse)
def judge_monitor(
    user: User = Depends(require_permissions("judge:monitor")),
    store: Repository = Depends(get_repository),
) -> JudgeMonitorResponse:
    submissions = store.list_submissions()
    try:
        queue = get_judge_queue(store).summary(limit=10)
    except QueueBackendUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return JudgeMonitorResponse(
        queue_depth=queue.depth,
        queue=queue,
        last_submissions=submissions[:10],
        judge_nodes=store.list_judge_nodes(),
        clarifications=store.list_clarifications(),
        contests=store.list_contests(),
        frozen_contests=[contest for contest in store.list_contests() if contest.frozen],
        balloons=[
            contest_submission_to_balloon(submission, store)
            for submission in submissions
            if submission.judged_at and submission.contest_id
        ],
    )


@app.post("/api/v1/judge/nodes/heartbeat", response_model=JudgeNode)
def judge_node_heartbeat(
    payload: JudgeNodeHeartbeatRequest,
    _node_token: None = Depends(require_judge_node_token),
    store: Repository = Depends(get_repository),
) -> JudgeNode:
    enabled_languages = {config.code for config in store.list_compiler_configs() if config.enabled}
    languages = [
        language
        for language in JudgeNode.normalize_languages(payload.languages)
        if language in enabled_languages
    ]
    node = JudgeNode(
        id=payload.id,
        name=payload.name or payload.id,
        status=payload.status,
        languages=languages,
        queue_depth=payload.queue_depth,
        load=payload.load,
        last_heartbeat=now(),
    )
    return store.update_judge_node(node)


@app.post("/api/v1/judge/nodes/{node_id}/claim", response_model=JudgeNodeClaimResponse)
def judge_node_claim(
    node_id: str,
    _node_token: None = Depends(require_judge_node_token),
    store: Repository = Depends(get_repository),
) -> JudgeNodeClaimResponse:
    node = next((item for item in store.list_judge_nodes() if item.id == node_id), None)
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Judge node not found")
    if node.status != "online":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Judge node is not online")
    claimed = store.claim_next_judge_queue_job(node_id=node.id)
    refreshed = next((item for item in store.list_judge_nodes() if item.id == node_id), node)
    if not claimed:
        return JudgeNodeClaimResponse(node=refreshed)
    job, submission = claimed
    return JudgeNodeClaimResponse(node=refreshed, job=job, submission=submission)


@app.post("/api/v1/judge/submissions/{submission_id}/override", response_model=Submission)
def override_submission(
    submission_id: str,
    payload: OverrideRequest,
    user: User = Depends(require_permissions("submission:override")),
    store: Repository = Depends(get_repository),
) -> Submission:
    submission = store.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    submission.status = "manual_override" if payload.status != "manual_override" else payload.status
    submission.score = max(0, min(payload.score, submission.max_score))
    submission.message = payload.message
    submission.judged_at = now()
    store.update_submission(submission)
    store.add_audit(user.id, "submission.override", f"submission:{submission.id}", payload.model_dump())
    add_notification(store, submission.user_id, "评测结果已被裁判修正", payload.message, "judge")
    return submission


@app.post("/api/v1/judge/submissions/{submission_id}/rejudge", response_model=Submission)
def rejudge_submission(
    submission_id: str,
    payload: RejudgeRequest,
    user: User = Depends(require_permissions("submission:override")),
    store: Repository = Depends(get_repository),
) -> Submission:
    submission = store.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    try:
        return requeue_submission_for_rejudge(store, submission, user, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except QueueBackendUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.post("/api/v1/judge/submissions/rejudge", response_model=RejudgeBatchResponse)
def rejudge_submissions(
    payload: RejudgeBatchRequest,
    user: User = Depends(require_permissions("submission:override")),
    store: Repository = Depends(get_repository),
) -> RejudgeBatchResponse:
    skipped: list[RejudgeSkipped] = []
    candidates: list[Submission] = []
    seen: set[str] = set()

    def append_candidate(submission: Submission) -> None:
        if submission.id in seen:
            return
        seen.add(submission.id)
        candidates.append(submission)

    if payload.submission_ids:
        for submission_id in payload.submission_ids:
            submission = store.get_submission(submission_id)
            if not submission:
                skipped.append(RejudgeSkipped(submission_id=submission_id, reason="Submission not found"))
                continue
            append_candidate(submission)
    else:
        for submission in store.list_submissions():
            if payload.problem_id and submission.problem_id != payload.problem_id:
                continue
            if payload.contest_id and submission.contest_id != payload.contest_id:
                continue
            if payload.statuses and submission.status not in payload.statuses:
                continue
            append_candidate(submission)

    requeued: list[Submission] = []
    allowed_statuses = set(payload.statuses) if payload.submission_ids else set()
    for submission in candidates:
        if allowed_statuses and submission.status not in allowed_statuses:
            skipped.append(
                RejudgeSkipped(
                    submission_id=submission.id,
                    reason=f"Status {submission.status} is outside the requested filter",
                )
            )
            continue
        try:
            requeued.append(
                requeue_submission_for_rejudge(
                    store,
                    submission,
                    user,
                    reason=payload.reason,
                    action="submission.rejudge.batch",
                )
            )
        except ValueError as exc:
            skipped.append(RejudgeSkipped(submission_id=submission.id, reason=str(exc)))
        except QueueBackendUnavailable as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return RejudgeBatchResponse(
        requeued=requeued,
        skipped=skipped,
        requeued_count=len(requeued),
        skipped_count=len(skipped),
    )


@app.get("/api/v1/admin/users", response_model=list[PublicUser])
def admin_users(
    user: User = Depends(require_permissions("user:read")),
    store: Repository = Depends(get_repository),
) -> list[PublicUser]:
    return [public_user(u) for u in store.list_users()]


@app.patch("/api/v1/admin/users/{user_id}/ban", response_model=PublicUser)
def admin_ban_user(
    user_id: str,
    disabled: bool = Query(default=True),
    user: User = Depends(require_permissions("user:ban")),
    store: Repository = Depends(get_repository),
) -> PublicUser:
    target = store.get_user(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if disabled and target.role == "admin" and not target.disabled:
        active_admins = [
            candidate
            for candidate in store.list_users()
            if candidate.id != target.id and candidate.role == "admin" and not candidate.disabled
        ]
        if not active_admins:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least one active admin must remain",
            )
    target.disabled = disabled
    store.update_user(target)
    store.add_audit(
        user.id,
        "user.ban" if disabled else "user.unban",
        f"user:{target.id}",
        {"target_username": target.username, "disabled": disabled},
    )
    return public_user(target)


@app.patch("/api/v1/admin/users/{user_id}/role", response_model=PublicUser)
def admin_update_user_role(
    user_id: str,
    payload: UserRoleUpdate,
    user: User = Depends(require_permissions("user:role:update")),
    store: Repository = Depends(get_repository),
) -> PublicUser:
    target = store.get_user(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.role == "admin" and payload.role != "admin" and not target.disabled:
        active_admins = [
            candidate
            for candidate in store.list_users()
            if candidate.id != target.id and candidate.role == "admin" and not candidate.disabled
        ]
        if not active_admins:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least one active admin must remain",
            )

    old_role = target.role
    target.role = payload.role
    ensure_student_school(target)
    store.update_user(target)
    store.add_audit(
        user.id,
        "user.role.update",
        f"user:{target.id}",
        {"target_username": target.username, "old_role": old_role, "new_role": target.role},
    )
    return public_user(target)


@app.get("/api/v1/admin/judge-nodes", response_model=list[JudgeNode])
def admin_judge_nodes(
    user: User = Depends(require_permissions("judge_node:manage")),
    store: Repository = Depends(get_repository),
) -> list[JudgeNode]:
    return store.list_judge_nodes()


@app.patch("/api/v1/admin/judge-nodes/{node_id}", response_model=JudgeNode)
def admin_update_judge_node(
    node_id: str,
    payload: JudgeNodeStatusUpdate,
    user: User = Depends(require_permissions("judge_node:manage")),
    store: Repository = Depends(get_repository),
) -> JudgeNode:
    node = next((item for item in store.list_judge_nodes() if item.id == node_id), None)
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Judge node not found")
    node.status = payload.status
    if payload.status == "online":
        node.last_heartbeat = now()
    updated = store.update_judge_node(node)
    store.add_audit(
        user.id,
        "judge_node.status.update",
        f"judge_node:{node.id}",
        {"status": updated.status},
    )
    return updated


@app.get("/api/v1/admin/compiler-configs", response_model=list[CompilerConfig])
def admin_compiler_configs(
    user: User = Depends(require_permissions("system:config")),
    store: Repository = Depends(get_repository),
) -> list[CompilerConfig]:
    return store.list_compiler_configs()


@app.put("/api/v1/admin/compiler-configs/{code}", response_model=CompilerConfig)
def admin_update_compiler_config(
    code: str,
    payload: CompilerConfigUpdate,
    user: User = Depends(require_permissions("system:config")),
    store: Repository = Depends(get_repository),
) -> CompilerConfig:
    existing = store.get_compiler_config(code)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compiler config not found")

    update = payload.model_dump(exclude_unset=True, exclude_none=True)
    next_config = existing.model_copy(update={**update, "updated_at": now()})
    configs = [
        next_config if item.code == existing.code else item
        for item in store.list_compiler_configs()
    ]
    if not any(item.enabled for item in configs):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="At least one compiler language must remain enabled")

    default_language = str(store.get_system_config().get("default_language", "cpp"))
    if existing.code == default_language and not next_config.enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Default language must remain enabled")

    updated = store.update_compiler_config(next_config)
    store.add_audit(
        user.id,
        "compiler_config.update",
        f"compiler_config:{updated.code}",
        {"fields": sorted(update), "enabled": updated.enabled, "version": updated.version},
    )
    return updated


@app.get("/api/v1/admin/audit-logs", response_model=AuditLogList)
def admin_audit_logs(
    actor_id: str | None = Query(default=None, min_length=1, max_length=128),
    action: str | None = Query(default=None, min_length=1, max_length=128),
    resource: str | None = Query(default=None, min_length=1, max_length=256),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_permissions("audit:read")),
    store: Repository = Depends(get_repository),
) -> AuditLogList:
    created_from = query_datetime(created_from)
    created_to = query_datetime(created_to)
    if created_from and created_to and created_from > created_to:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="created_from must be before created_to")
    items, total = store.list_audit_logs(
        actor_id=actor_id,
        action=action,
        resource=resource,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )
    return AuditLogList(items=items, total=total, limit=limit, offset=offset)


@app.get("/api/v1/admin/rbac/matrix", response_model=RbacMatrixResponse)
def admin_rbac_matrix(
    user: User = Depends(require_permissions("rbac:read")),
) -> RbacMatrixResponse:
    return RbacMatrixResponse(**role_permission_matrix())


@app.get("/api/v1/system/config", response_model=SystemConfig)
def get_system_config(
    user: User = Depends(require_permissions("system:config")),
    store: Repository = Depends(get_repository),
) -> SystemConfig:
    return SystemConfig(**store.get_system_config())


@app.put("/api/v1/system/config", response_model=SystemConfig)
def update_system_config(
    payload: SystemConfigUpdate,
    user: User = Depends(require_permissions("system:config")),
    store: Repository = Depends(get_repository),
) -> SystemConfig:
    update = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "default_language" in update:
        ensure_enabled_compiler_language(store, str(update["default_language"]))
    config = store.update_system_config(update)
    store.add_audit(user.id, "system.config.update", "system:config", update)
    return SystemConfig(**config)


@app.get("/api/v1/problem-sets", response_model=list[ProblemSetDetail])
def list_problem_sets(store: Repository = Depends(get_repository)) -> list[ProblemSetDetail]:
    return [problem_set_detail(item, store) for item in store.list_problem_sets() if item.visibility == "public"]


@app.post("/api/v1/problem-sets", response_model=ProblemSetDetail)
def create_problem_set(
    payload: ProblemSetCreate,
    user: User = Depends(require_permissions("problem_set:create")),
    store: Repository = Depends(get_repository),
) -> ProblemSetDetail:
    existing = {p.id for p in store.list_problems() if p.visible}
    missing = [pid for pid in payload.problem_ids if pid not in existing]
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown problems: {', '.join(missing)}")
    problem_set = ProblemSet(
        id=f"PS{1000 + len(store.list_problem_sets()) + 1}",
        owner_id=user.id,
        created_at=now(),
        updated_at=now(),
        **payload.model_dump(),
    )
    store.add_problem_set(problem_set)
    store.add_audit(user.id, "problem_set.create", f"problem_set:{problem_set.id}", {"title": problem_set.title})
    return problem_set_detail(problem_set, store)


@app.get("/api/v1/problem-sets/{problem_set_id}", response_model=ProblemSetDetail)
def get_problem_set(problem_set_id: str, store: Repository = Depends(get_repository)) -> ProblemSetDetail:
    problem_set = store.get_problem_set(problem_set_id)
    if not problem_set or problem_set.visibility != "public":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem set not found")
    return problem_set_detail(problem_set, store)


@app.get("/api/v1/problem-sets/{problem_set_id}/offline-package", response_model=OfflinePackResponse)
def problem_set_offline_package(
    problem_set_id: str,
    user: User = Depends(require_student_permissions("training:offline")),
    store: Repository = Depends(get_repository),
) -> OfflinePackResponse:
    problem_set = store.get_problem_set(problem_set_id)
    if not problem_set or problem_set.visibility != "public":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem set not found")
    if not problem_set.offline_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Problem set is not authorized for offline training")
    if problem_set.offline_policy.answer_visibility != "full":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Problem set offline policy does not allow answer export")
    visible_problems = {problem.id: problem for problem in store.list_problems() if problem.visible}
    problems = [visible_problems[pid] for pid in problem_set.problem_ids if pid in visible_problems]
    objective_count = sum(
        1
        for problem in problems
        if can_export_offline_problem(problem, store.get_problem_judge_config(problem.id) if problem.type != "code" else {})
    )
    store.add_audit(
        user.id,
        "problem_set.offline_package",
        f"problem_set:{problem_set.id}",
        {
            "problem_count": objective_count,
            "filtered_count": max(0, len(problems) - objective_count),
            "ttl_hours": offline_ttl_hours(problem_set.offline_policy),
            "source": {"type": "problem_set", "id": problem_set.id, "title": problem_set.title},
        },
    )
    return objective_offline_pack_response(
        problems,
        store,
        ttl_hours=offline_ttl_hours(problem_set.offline_policy),
        source={"type": "problem_set", "id": problem_set.id, "title": problem_set.title},
    )


@app.put("/api/v1/problem-sets/{problem_set_id}", response_model=ProblemSetDetail)
def update_problem_set(
    problem_set_id: str,
    payload: ProblemSetCreate,
    user: User = Depends(require_permissions("problem_set:edit:own")),
    store: Repository = Depends(get_repository),
) -> ProblemSetDetail:
    problem_set = store.get_problem_set(problem_set_id)
    if not problem_set:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem set not found")
    if problem_set.owner_id != user.id and not role_has_permission(user.role, "problem_set:edit:all"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    existing = {p.id for p in store.list_problems() if p.visible}
    missing = [pid for pid in payload.problem_ids if pid not in existing]
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown problems: {', '.join(missing)}")
    for key, value in payload.model_dump(exclude={"offline_policy"}).items():
        setattr(problem_set, key, value)
    problem_set.offline_policy = payload.offline_policy
    problem_set.updated_at = now()
    store.update_problem_set(problem_set)
    store.add_audit(user.id, "problem_set.update", f"problem_set:{problem_set.id}")
    return problem_set_detail(problem_set, store)


@app.patch("/api/v1/problem-sets/{problem_set_id}/offline-policy", response_model=ProblemSetDetail)
def update_problem_set_offline_policy(
    problem_set_id: str,
    payload: OfflinePolicyUpdate,
    user: User = Depends(require_permissions("problem_set:edit:own")),
    store: Repository = Depends(get_repository),
) -> ProblemSetDetail:
    problem_set = store.get_problem_set(problem_set_id)
    if not problem_set:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem set not found")
    if problem_set.owner_id != user.id and not role_has_permission(user.role, "problem_set:edit:all"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    problem_set.offline_enabled = payload.offline_enabled
    problem_set.offline_policy = payload.offline_policy
    problem_set.updated_at = now()
    updated = store.update_problem_set(problem_set)
    store.add_audit(
        user.id,
        "problem_set.offline_policy.update",
        f"problem_set:{updated.id}",
        {
            "offline_enabled": updated.offline_enabled,
            "offline_policy": updated.offline_policy.model_dump(mode="json"),
        },
    )
    return problem_set_detail(updated, store)


@app.get("/api/v1/discussions", response_model=list[Discussion])
def list_discussions(
    type: str = "",
    target_id: str = "",
    store: Repository = Depends(get_repository),
) -> list[Discussion]:
    items = store.list_discussions()
    if type:
        items = [d for d in items if d.type == type]
    if target_id:
        items = [d for d in items if d.target_id == target_id]
    return items


@app.post("/api/v1/discussions", response_model=Discussion)
def create_discussion(
    payload: DiscussionCreate,
    user: User = Depends(require_permissions("discussion:write")),
    store: Repository = Depends(get_repository),
) -> Discussion:
    discussion = Discussion(
        id=f"D{1000 + len(store.list_discussions()) + 1}",
        author_id=user.id,
        author_name=user.display_name,
        created_at=now(),
        updated_at=now(),
        **payload.model_dump(),
    )
    store.add_discussion(discussion)
    store.add_audit(user.id, "discussion.create", f"discussion:{discussion.id}", {"title": discussion.title})
    return discussion


@app.get("/api/v1/discussions/{discussion_id}", response_model=Discussion)
def get_discussion(discussion_id: str, store: Repository = Depends(get_repository)) -> Discussion:
    discussion = store.get_discussion(discussion_id)
    if not discussion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discussion not found")
    return discussion


@app.post("/api/v1/discussions/{discussion_id}/replies", response_model=Discussion)
def reply_discussion(
    discussion_id: str,
    payload: DiscussionReplyCreate,
    user: User = Depends(require_permissions("discussion:write")),
    store: Repository = Depends(get_repository),
) -> Discussion:
    discussion = store.get_discussion(discussion_id)
    if not discussion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discussion not found")
    discussion.replies.append(
        {
            "id": f"R{uuid4().hex[:8].upper()}",
            "author_id": user.id,
            "author_name": user.display_name,
            "content": payload.content,
            "created_at": now().isoformat(),
        }
    )
    discussion.updated_at = now()
    store.update_discussion(discussion)
    if discussion.author_id != user.id:
        add_notification(store, discussion.author_id, "讨论收到新回复", discussion.title, "reply")
    store.add_audit(user.id, "discussion.reply", f"discussion:{discussion.id}")
    return discussion


@app.get("/api/v1/notifications", response_model=list[Notification])
def list_notifications(
    user: User = Depends(require_permissions("notification:read")),
    store: Repository = Depends(get_repository),
) -> list[Notification]:
    return store.list_notifications(user.id)


@app.patch("/api/v1/notifications/{notification_id}/read", response_model=Notification)
def mark_notification_read(
    notification_id: str,
    user: User = Depends(require_permissions("notification:read")),
    store: Repository = Depends(get_repository),
) -> Notification:
    notification = store.mark_notification_read(notification_id, user.id)
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return notification


@app.get("/api/v1/training/offline-pack", response_model=OfflinePackResponse)
def offline_pack(
    user: User = Depends(require_student_permissions("training:offline")),
    store: Repository = Depends(get_repository),
) -> OfflinePackResponse:
    problems = [problem for problem in store.list_problems() if problem.visible]
    exportable_count = sum(
        1
        for problem in problems
        if can_export_offline_problem(problem, store.get_problem_judge_config(problem.id) if problem.type != "code" else {})
    )
    source = {"type": "training", "id": "objective"}
    store.add_audit(
        user.id,
        "training.offline_pack",
        "training:objective",
        {"problem_count": exportable_count, "filtered_count": max(0, len(problems) - exportable_count), "source": source},
    )
    return objective_offline_pack_response(problems, store, source=source, created_by=user.id)


@app.get("/api/v1/training/offline-pack/status", response_model=list[OfflinePackStatus])
def list_offline_pack_status(
    user: User = Depends(require_permissions("training:offline")),
    store: Repository = Depends(get_repository),
) -> list[OfflinePackStatus]:
    can_read_all = role_has_permission(user.role, "problem:edit:all")
    return [pack_record_to_status(record) for record in store.list_offline_packs() if can_read_all or record.created_by == user.id]


@app.get("/api/v1/training/offline-pack/{pack_id}", response_model=OfflinePackStatusResponse)
def get_offline_pack_status(
    pack_id: str,
    user: User = Depends(require_permissions("training:offline")),
    store: Repository = Depends(get_repository),
) -> OfflinePackStatusResponse:
    record = store.get_offline_pack(pack_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offline pack not found")
    if record.created_by != user.id and not role_has_permission(user.role, "problem:edit:all"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    return OfflinePackStatusResponse(payload=pack_record_to_status(record))


@app.post("/api/v1/offline-results/sync", response_model=OfflineResultSyncResponse)
def sync_offline_results(
    payload: OfflineResultSyncRequest,
    user: User = Depends(require_student_permissions("training:offline")),
    store: Repository = Depends(get_repository),
) -> OfflineResultSyncResponse:
    synced: list[Submission] = []
    merged: list[Submission] = []
    rejected: list[dict[str, str]] = []
    for item in payload.results:
        problem = store.get_problem(item.problem_id)
        if not problem or not problem.visible or problem.type == "code":
            rejected.append(offline_rejection(item.problem_id, "unsupported_problem", "仅支持同步授权客观题结果"))
            continue
        if (
            not problem.offline_enabled
            or problem.offline_policy.answer_visibility != "full"
            or problem.offline_policy.sync_mode == "disabled"
        ):
            rejected.append(offline_rejection(item.problem_id, "offline_policy_denied", "离线策略不允许同步该题结果"))
            continue
        if not offline_source_matches_problem(item.source, problem, store):
            rejected.append(offline_rejection(item.problem_id, "source_not_authorized", "离线结果来源未授权该题"))
            continue
        pack_record = store.get_offline_pack(item.pack_id) if item.pack_id else None
        if item.pack_id and not pack_record:
            rejected.append(offline_rejection(item.problem_id, "pack_not_authorized", "离线包未授权该题或已失效"))
            continue
        if pack_record and not offline_pack_source_matches_record(pack_record, item.source):
            rejected.append(offline_rejection(item.problem_id, "source_not_authorized", "离线结果来源与离线包不一致"))
            continue
        if not offline_pack_authorizes_problem(item.pack_id, problem, store, user_id=user.id):
            rejected.append(offline_rejection(item.problem_id, "pack_not_authorized", "离线包未授权该题或已失效"))
            continue
        result_key = offline_result_key(problem.id, item.answers, item.practiced_at, item.client_result_key, item.pack_id)
        duplicate = next(
            (
                submission
                for submission in store.list_submissions()
                if submission.user_id == user.id and submission.offline_result_key == result_key and submission.offline_pack_id == item.pack_id
            ),
            None,
        )
        if duplicate:
            if same_offline_result(duplicate, problem.id, item.answers):
                merged.append(duplicate)
            else:
                rejected.append(offline_rejection(item.problem_id, "idempotency_conflict", "离线结果幂等键冲突"))
            continue
        score, max_score, details = judge_objective(problem, store.get_problem_judge_config(problem.id), item.answers)
        submission = Submission(
            id=make_submission_id(),
            user_id=user.id,
            problem_id=problem.id,
            problem_title=problem.title,
            problem_type=problem.type,
            answers=item.answers,
            offline_result_key=result_key,
            offline_pack_id=item.pack_id,
            status="accepted" if score == max_score else "wrong_answer",
            score=score,
            max_score=max_score,
            details=details,
            message="离线训练结果同步完成。",
            created_at=item.practiced_at or now(),
            judged_at=now(),
        )
        store.add_submission(submission)
        synced.append(submission)
    if synced:
        add_notification(store, user.id, "离线训练结果已同步", f"已同步 {len(synced)} 条客观题训练记录。", "judge")
    store.add_audit(
        user.id,
        "offline_results.sync",
        "training:offline",
        {"synced": len(synced), "merged": len(merged), "rejected": len(rejected)},
    )
    return OfflineResultSyncResponse(
        synced=[sanitized_submission(submission) for submission in synced],
        merged=[sanitized_submission(submission) for submission in merged],
        rejected=rejected,
    )


@app.get("/api/v1/offline-results", response_model=list[OfflineResultReview])
def list_offline_results(
    user_id: str | None = Query(default=None, min_length=1, max_length=128),
    problem_id: str | None = Query(default=None, min_length=1, max_length=64),
    include_expected: bool = Query(default=False),
    user: User = Depends(require_permissions("submission:read:own")),
    store: Repository = Depends(get_repository),
) -> list[OfflineResultReview]:
    can_read_all = role_has_permission(user.role, "submission:read:all")
    if user_id and user_id != user.id and not can_read_all:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    target_user_id = user_id if can_read_all else user.id
    show_expected = include_expected and can_read_all
    current = now()
    submissions = [
        submission
        for submission in store.list_submissions()
        if submission.offline_result_key
        and (not target_user_id or submission.user_id == target_user_id)
        and (not problem_id or submission.problem_id == problem_id)
        and (
            not submission.offline_pack_id
            or not (pack_record := store.get_offline_pack(submission.offline_pack_id))
            or not pack_record.retention_days
            or submission.created_at >= current - timedelta(days=pack_record.retention_days or 0)
        )
    ]
    store.add_audit(
        user.id,
        "offline_results.review.list",
        "training:offline",
        {
            "target_user_id": target_user_id or "*",
            "problem_id": problem_id,
            "count": len(submissions),
            "include_expected": show_expected,
        },
    )
    return [offline_result_review(submission, include_expected=show_expected) for submission in submissions]


@app.get("/api/v1/offline-results/{submission_id}", response_model=OfflineResultReview)
def get_offline_result(
    submission_id: str,
    include_expected: bool = Query(default=False),
    user: User = Depends(require_permissions("submission:read:own")),
    store: Repository = Depends(get_repository),
) -> OfflineResultReview:
    submission = store.get_submission(submission_id)
    if not submission or not submission.offline_result_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offline result not found")
    can_read_all = role_has_permission(user.role, "submission:read:all")
    if submission.user_id != user.id and not can_read_all:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    if submission.offline_pack_id:
        record = store.get_offline_pack(submission.offline_pack_id)
        if record and record.retention_days and submission.created_at < now() - timedelta(days=record.retention_days):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offline result expired")
    show_expected = include_expected and can_read_all
    store.add_audit(
        user.id,
        "offline_results.review.detail",
        f"submission:{submission.id}",
        {
            "target_user_id": submission.user_id,
            "problem_id": submission.problem_id,
            "include_expected": show_expected,
        },
    )
    return offline_result_review(submission, include_expected=show_expected)

