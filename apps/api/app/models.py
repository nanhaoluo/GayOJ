from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Role = Literal["student", "coach", "judge", "admin"]
ProblemType = Literal["code", "blank", "single_choice", "multiple_choice"]
LanguageCode = Literal["c", "cpp", "java", "python"]
ProblemPackageFormat = Literal["fps", "qdu", "hydro"]
ProblemImportConflictStrategy = Literal["create_new", "overwrite", "skip"]
CoachReportFormat = Literal["csv", "xlsx"]
AssignmentProgressState = Literal["not_started", "in_progress", "overdue", "completed"]
SubmissionStatus = Literal[
    "queued",
    "judging",
    "accepted",
    "wrong_answer",
    "time_limit_exceeded",
    "memory_limit_exceeded",
    "output_limit_exceeded",
    "compile_error",
    "runtime_error",
    "system_error",
    "manual_override",
]
JudgeNodeStatus = Literal["online", "offline", "draining"]
JudgeQueueBackend = Literal["json", "redis", "kafka"]
JudgeQueueJobStatus = Literal["pending", "leased", "completed", "failed"]
ContestPrintSourceKind = Literal["submission", "request"]
ContestPrintStatus = Literal["pending", "printed", "cancelled"]
DiscussionType = Literal["general", "problem", "contest", "solution"]
Visibility = Literal["public", "private"]
OfflineAnswerVisibility = Literal["full", "none"]
OfflineSyncMode = Literal["allow", "disabled"]
SolutionCategory = Literal["general", "tutorial", "analysis", "official", "trick"]

DEFAULT_STUDENT_SCHOOL = "GayOJ University (GOJU)"


class OfflinePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ttl_hours: int | None = Field(default=None, ge=1, le=24 * 365)
    answer_visibility: OfflineAnswerVisibility = "full"
    sync_mode: OfflineSyncMode = "allow"
    max_downloads: int | None = Field(default=None, ge=1, le=100000)
    retention_days: int | None = Field(default=30, ge=1, le=3650)


class OfflinePolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offline_enabled: bool
    offline_policy: OfflinePolicy = Field(default_factory=OfflinePolicy)


class User(BaseModel):
    id: str
    username: str
    display_name: str
    role: Role
    school: str = ""
    email: str = ""
    rating: int = 1500
    solved: int = 0
    disabled: bool = False
    password_hash: str
    failed_login_attempts: int = 0
    locked_until: datetime | None = None
    last_login_at: datetime | None = None
    password_changed_at: datetime | None = None


class PublicUser(BaseModel):
    id: str
    username: str
    display_name: str
    role: Role
    permissions: list[str] = Field(default_factory=list)
    school: str = ""
    rating: int = 1500
    solved: int = 0
    disabled: bool = False


class UserProfile(PublicUser):
    email: str = ""


class UserProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    school: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)

    @field_validator("display_name", "school", "email", mode="before")
    @classmethod
    def strip_profile_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return str(value).strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if not value:
            return value
        local, separator, domain = value.partition("@")
        if not local or separator != "@" or "." not in domain:
            raise ValueError("Invalid email address")
        return value


class UserRoleUpdate(BaseModel):
    role: Role


class PermissionInfo(BaseModel):
    code: str
    description: str
    category: str


class RolePermissionInfo(BaseModel):
    code: Role
    name: str
    description: str
    permissions: list[str]


class RbacMatrixResponse(BaseModel):
    roles: list[RolePermissionInfo]
    permissions: list[PermissionInfo]
    matrix: dict[str, dict[str, bool]]


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: PublicUser


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class HealthResponse(BaseModel):
    status: str
    service: str
    time: str


class Problem(BaseModel):
    id: str
    title: str
    type: ProblemType
    difficulty: Literal["入门", "基础", "提高", "困难"] = "基础"
    tags: list[str] = Field(default_factory=list)
    statement: str
    input_format: str = ""
    output_format: str = ""
    samples: list[dict[str, str]] = Field(default_factory=list)
    options: list[dict[str, str]] = Field(default_factory=list)
    blanks: list[dict[str, Any]] = Field(default_factory=list)
    time_limit_ms: int | None = None
    memory_limit_mb: int | None = None
    author_id: str
    visible: bool = True
    offline_enabled: bool = True
    offline_policy: OfflinePolicy = Field(default_factory=OfflinePolicy)
    judge_config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ProblemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    type: ProblemType
    difficulty: Literal["入门", "基础", "提高", "困难"] = "基础"
    tags: list[str] = Field(default_factory=list)
    statement: str = Field(min_length=1)
    input_format: str = ""
    output_format: str = ""
    samples: list[dict[str, str]] = Field(default_factory=list)
    options: list[dict[str, str]] = Field(default_factory=list)
    blanks: list[dict[str, Any]] = Field(default_factory=list)
    time_limit_ms: int | None = Field(default=None, ge=1)
    memory_limit_mb: int | None = Field(default=None, ge=1)
    visible: bool = True
    offline_enabled: bool = True
    offline_policy: OfflinePolicy = Field(default_factory=OfflinePolicy)
    judge_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "statement", "input_format", "output_format", mode="before")
    @classmethod
    def strip_problem_text(cls, value: str | None) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = value.replace("，", ",").split(",")
        tags = []
        for item in value:
            text = str(item).strip()
            if text and text not in tags:
                tags.append(text)
        return tags

    @model_validator(mode="after")
    def validate_type_specific_fields(self) -> "ProblemCreate":
        option_keys = [str(option.get("key", "")).strip() for option in self.options]
        option_keys = [key for key in option_keys if key]
        blank_keys = [str(blank.get("key", "")).strip() for blank in self.blanks]
        blank_keys = [key for key in blank_keys if key]

        if len(option_keys) != len(set(option_keys)):
            raise ValueError("Option keys must be unique")
        if len(blank_keys) != len(set(blank_keys)):
            raise ValueError("Blank keys must be unique")

        if self.type == "code":
            self.offline_enabled = False
            return self

        if self.type == "blank":
            if not blank_keys:
                raise ValueError("Blank problems must define at least one blank")
            answers = self.judge_config.get("answers")
            if not isinstance(answers, dict):
                raise ValueError("Blank problems must define judge_config.answers")
            scores = self.judge_config.get("scores")
            if not isinstance(scores, dict):
                raise ValueError("Blank problems must define judge_config.scores")
            missing = [key for key in blank_keys if key not in answers]
            if missing:
                raise ValueError(f"Missing blank answers for: {', '.join(missing)}")
            for key in blank_keys:
                expected = answers.get(key)
                if not isinstance(expected, list) or not expected:
                    raise ValueError(f"Blank answer list for {key} must not be empty")
                try:
                    if int(scores.get(key, 0)) <= 0:
                        raise ValueError
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Blank score for {key} must be positive") from exc
            blank_rules = self.judge_config.get("blank_rules", {})
            if blank_rules is not None and not isinstance(blank_rules, dict):
                raise ValueError("Blank judge_config.blank_rules must be an object")
            for key, rule in (blank_rules or {}).items():
                if key not in blank_keys:
                    raise ValueError(f"Blank rule references unknown blank key: {key}")
                if not isinstance(rule, dict):
                    raise ValueError(f"Blank rule for {key} must be an object")
                match_type = str(rule.get("match", "exact")).strip().lower() or "exact"
                if match_type not in {"exact", "regex", "numeric"}:
                    raise ValueError(f"Blank rule for {key} has unsupported match type: {match_type}")
                if match_type == "regex":
                    flags = 0 if bool(self.judge_config.get("case_sensitive", False)) else re.IGNORECASE
                    for pattern in answers.get(str(key), []):
                        try:
                            re.compile(str(pattern), flags=flags)
                        except re.error as exc:
                            raise ValueError(f"Blank regex for {key} is invalid") from exc
                if match_type == "numeric":
                    try:
                        if float(rule.get("tolerance", 0)) < 0:
                            raise ValueError
                    except (TypeError, ValueError) as exc:
                        raise ValueError(f"Blank numeric tolerance for {key} must be non-negative") from exc
            return self

        if len(option_keys) < 2:
            raise ValueError("Choice problems must define at least two options")

        if self.type == "single_choice":
            answer = str(self.judge_config.get("answer", "")).strip()
            if answer not in option_keys:
                raise ValueError("Single choice answer must match an option key")
            return self

        if self.type == "multiple_choice":
            answers = self.judge_config.get("answer", [])
            if not isinstance(answers, list) or not answers:
                raise ValueError("Multiple choice answer must be a non-empty list")
            unknown = sorted({str(item).strip() for item in answers} - set(option_keys))
            if unknown:
                raise ValueError(f"Multiple choice answers include unknown option keys: {', '.join(unknown)}")
            return self

        return self


class ProblemUpdate(ProblemCreate):
    pass


class ProblemVisibilityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visible: bool


class Tag(BaseModel):
    id: str
    name: str
    slug: str
    parent_id: str | None = None
    sort_order: int = 0
    created_at: datetime


class TagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    parent_id: str | None = None
    sort_order: int = 0

    @field_validator("name", "parent_id", mode="before")
    @classmethod
    def strip_tag_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return str(value).strip() or None


class TagUpdate(TagCreate):
    pass


class TagTreeNode(Tag):
    children: list["TagTreeNode"] = Field(default_factory=list)


class ProblemSummary(BaseModel):
    id: str
    title: str
    type: ProblemType
    difficulty: str
    tags: list[str]
    accepted: int = 0
    attempts: int = 0


class ProblemDetail(BaseModel):
    id: str
    title: str
    type: ProblemType
    difficulty: str
    tags: list[str]
    statement: str
    input_format: str = ""
    output_format: str = ""
    samples: list[dict[str, str]] = Field(default_factory=list)
    options: list[dict[str, str]] = Field(default_factory=list)
    blanks: list[dict[str, Any]] = Field(default_factory=list)
    time_limit_ms: int | None = None
    memory_limit_mb: int | None = None
    author_id: str
    created_at: datetime
    judge_config: dict[str, Any] | None = None


class ProblemTestData(BaseModel):
    problem_id: str
    filename: str
    object_key: str
    storage_backend: str = "local"
    bucket: str = "gayoj-testdata"
    archive_format: Literal["zip"] = "zip"
    size_bytes: int = Field(ge=0)
    sha256: str
    file_count: int = Field(ge=0)
    input_files: int = Field(ge=0)
    output_files: int = Field(ge=0)
    case_count: int = Field(ge=0)
    case_names: list[str] = Field(default_factory=list)
    uploaded_by: str
    uploaded_at: datetime


class ProblemAdminDetail(ProblemDetail):
    visible: bool
    offline_enabled: bool = True
    offline_policy: OfflinePolicy = Field(default_factory=OfflinePolicy)
    judge_config: dict[str, Any] = Field(default_factory=dict)
    test_data: ProblemTestData | None = None


class ProblemExportResponse(BaseModel):
    format: ProblemPackageFormat
    filename: str
    content_type: str
    content: str
    problem_count: int
    problem_ids: list[str]


class ProblemImportRequest(BaseModel):
    format: ProblemPackageFormat
    content: str = Field(min_length=1, max_length=5_000_000)
    conflict_strategy: ProblemImportConflictStrategy = "create_new"
    dry_run: bool = False


class ProblemImportItem(BaseModel):
    source_id: str | None = None
    target_id: str | None = None
    title: str
    type: ProblemType
    action: Literal["created", "updated", "skipped"]


class ProblemImportResponse(BaseModel):
    format: ProblemPackageFormat
    dry_run: bool
    rollback_on_error: bool = True
    imported: int
    created: int
    updated: int
    skipped: int
    items: list[ProblemImportItem] = Field(default_factory=list)


class ProblemVersion(BaseModel):
    id: str
    problem_id: str
    version: int = Field(ge=1)
    saved_by: str
    action: Literal["update", "delete", "restore"] = "update"
    saved_at: datetime
    snapshot: Problem


class CodeSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: LanguageCode
    source_code: str = Field(min_length=1, max_length=65536)


class ObjectiveSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: dict[str, Any]


class ObjectiveItemResult(BaseModel):
    key: str
    correct: bool
    expected: Any | None = None
    received: Any
    score: int


class Submission(BaseModel):
    id: str
    user_id: str
    problem_id: str
    problem_title: str
    problem_type: ProblemType
    contest_id: str | None = None
    language: str | None = None
    source_code: str | None = None
    queue_job_id: str | None = None
    queued_at: datetime | None = None
    offline_result_key: str | None = Field(default=None, max_length=128)
    offline_pack_id: str | None = Field(default=None, max_length=128)
    answers: dict[str, Any] | None = None
    status: SubmissionStatus
    score: int
    max_score: int
    details: list[ObjectiveItemResult] | list[dict[str, Any]] = Field(default_factory=list)
    message: str = ""
    created_at: datetime
    judged_at: datetime | None = None


class SubmissionReview(BaseModel):
    id: str
    user_id: str
    problem_id: str
    problem_title: str
    problem_type: ProblemType
    contest_id: str | None = None
    language: str | None = None
    source_code: str | None = None
    queue_job_id: str | None = None
    queued_at: datetime | None = None
    offline_result_key: str | None = None
    offline_pack_id: str | None = None
    answers: dict[str, Any] | None = None
    status: SubmissionStatus
    score: int
    max_score: int
    details: list[dict[str, Any]] = Field(default_factory=list)
    message: str = ""
    created_at: datetime
    judged_at: datetime | None = None


class OfflineResultReview(SubmissionReview):
    offline_result_key: str
    expected_visible: bool = False


class ContestProblemLayoutItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_id: str = Field(min_length=1, max_length=64)
    problem_key: str = Field(min_length=1, max_length=16)
    allowed_languages: list[LanguageCode] = Field(default_factory=list)

    @field_validator("problem_id", "problem_key", mode="before")
    @classmethod
    def strip_contest_problem_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("allowed_languages", mode="before")
    @classmethod
    def normalize_allowed_languages(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = value.replace("，", ",").split(",")
        languages: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item or "").strip().lower()
            if text and text not in seen:
                seen.add(text)
                languages.append(text)
        return languages


class Contest(BaseModel):
    id: str
    title: str
    rule: Literal["ACM", "OI", "IOI", "CF"]
    start_at: datetime
    end_at: datetime
    problem_ids: list[str]
    problem_layout: list[ContestProblemLayoutItem] = Field(default_factory=list)
    status: Literal["scheduled", "running", "ended"]
    visibility: Literal["public", "private"] = "public"
    frozen: bool = False
    freeze_disabled: bool = False
    frozen_at: datetime | None = None
    frozen_by: str | None = None
    freeze_reason: str = ""
    rejudge_at: datetime | None = None
    rejudge_by: str | None = None
    rejudge_reason: str = ""


class ContestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    rule: Literal["ACM", "OI", "IOI", "CF"] = "ACM"
    start_at: datetime
    end_at: datetime
    problem_ids: list[str]
    problem_layout: list[ContestProblemLayoutItem] = Field(default_factory=list)
    visibility: Visibility = "public"

    @field_validator("title", mode="before")
    @classmethod
    def strip_contest_title(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("problem_ids", mode="before")
    @classmethod
    def normalize_problem_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = value.replace("，", ",").split(",")
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item or "").strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
        return result

    @model_validator(mode="after")
    def validate_contest_payload(self) -> "ContestCreate":
        if not self.title:
            raise ValueError("Contest title is required")
        if not self.problem_ids:
            raise ValueError("Contest must include at least one problem")
        if self.end_at <= self.start_at:
            raise ValueError("Contest end_at must be later than start_at")
        if self.problem_layout:
            layout_problem_ids = [item.problem_id for item in self.problem_layout]
            if layout_problem_ids != self.problem_ids:
                raise ValueError("problem_layout must match problem_ids in order")
            seen_keys: set[str] = set()
            for item in self.problem_layout:
                if item.problem_key in seen_keys:
                    raise ValueError("Contest problem_key must be unique")
                seen_keys.add(item.problem_key)
        return self


class ContestUpdate(ContestCreate):
    pass


class ContestDetail(Contest):
    problems: list[ProblemSummary] = Field(default_factory=list)
    freeze_active: bool = False
    freeze_effective_at: datetime | None = None


class ContestProblemDetail(ProblemDetail):
    problem_key: str
    allowed_languages: list[LanguageCode] = Field(default_factory=list)


class ContestProblemView(BaseModel):
    problem_id: str
    problem_key: str
    title: str
    type: ProblemType
    allowed_languages: list[LanguageCode] = Field(default_factory=list)


class ContestSubmissionView(SubmissionReview):
    problem_key: str
    team_id: str | None = None
    team_name: str | None = None
    can_view_source: bool = False


class ContestTeamSubmissionSummary(BaseModel):
    team_id: str
    team_name: str
    member_ids: list[str] = Field(default_factory=list)
    submission_count: int = 0
    accepted_count: int = 0
    latest_submission_at: datetime | None = None
    latest_status: SubmissionStatus | None = None


class ContestSubmissionStatusResponse(BaseModel):
    contest_id: str
    contest_title: str
    rule: Literal["ACM", "OI", "IOI", "CF"]
    now: datetime
    can_submit: bool
    status: Literal["scheduled", "running", "ended"]
    can_view_all: bool
    show_team_view: bool
    problems: list[ContestProblemView] = Field(default_factory=list)
    submissions: list[ContestSubmissionView] = Field(default_factory=list)
    teams: list[ContestTeamSubmissionSummary] = Field(default_factory=list)


class StandingProblemResult(BaseModel):
    score: int = 0
    max_score: int = 100
    status: str = ""
    attempts: int = 0
    accepted_at: datetime | None = None
    penalty_minutes: int = 0
    first_blood: bool = False


class StandingRow(BaseModel):
    user_id: str
    display_name: str
    solved: int
    score: int
    penalty: int = 0
    first_blood: int = 0
    problems: dict[str, StandingProblemResult] = Field(default_factory=dict)


class ContestBoardResponse(BaseModel):
    contest: ContestDetail
    board_kind: Literal["external", "live"]
    standings: list[StandingRow] = Field(default_factory=list)
    generated_at: datetime


class ContestRollingResponse(BaseModel):
    contest: ContestDetail
    public_standings: list[StandingRow] = Field(default_factory=list)
    final_standings: list[StandingRow] = Field(default_factory=list)
    generated_at: datetime


class RankingRow(BaseModel):
    user_id: str
    display_name: str
    school: str = ""
    role: Role
    rating: int
    solved: int


class Clarification(BaseModel):
    id: str
    contest_id: str
    user_id: str
    user_display_name: str = ""
    problem_id: str | None = None
    problem_title: str | None = None
    question: str
    answer: str | None = None
    public: bool = False
    broadcast: bool = False
    answered_by: str | None = None
    answered_by_name: str | None = None
    answered_at: datetime | None = None
    broadcast_at: datetime | None = None
    created_at: datetime


class ClarificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    problem_id: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("question", "problem_id", mode="before")
    @classmethod
    def strip_clarification_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class ClarificationReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=4000)
    public: bool = False
    broadcast: bool = False

    @field_validator("answer", mode="before")
    @classmethod
    def strip_clarification_answer(cls, value: str | None) -> str:
        return str(value or "").strip()

    @model_validator(mode="after")
    def normalize_broadcast_visibility(self) -> "ClarificationReply":
        if self.broadcast:
            self.public = True
        return self


class ContestAnnouncement(BaseModel):
    id: str
    contest_id: str
    title: str
    content: str
    created_by: str
    created_by_name: str
    created_at: datetime


class ContestAnnouncementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("title", "content", mode="before")
    @classmethod
    def strip_announcement_text(cls, value: str | None) -> str:
        return str(value or "").strip()


class ContestFreezeRequest(BaseModel):
    reason: str = Field(default="", max_length=300)

    @field_validator("reason", mode="before")
    @classmethod
    def strip_reason(cls, value: str | None) -> str:
        return str(value or "").strip()


class ContestUnfreezeRequest(BaseModel):
    reason: str = Field(default="", max_length=300)

    @field_validator("reason", mode="before")
    @classmethod
    def strip_reason(cls, value: str | None) -> str:
        return str(value or "").strip()


class ContestPrintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str | None = Field(default=None, min_length=1, max_length=64)
    source_code: str | None = Field(default=None, min_length=1, max_length=65536)
    problem_id: str | None = Field(default=None, min_length=1, max_length=64)
    language: str | None = Field(default=None, max_length=32)

    @field_validator("submission_id", "problem_id", "language", mode="before")
    @classmethod
    def strip_optional_print_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("source_code", mode="before")
    @classmethod
    def strip_source_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text if text.strip() else None

    @model_validator(mode="after")
    def require_source(self) -> "ContestPrintRequest":
        if not self.submission_id and not self.source_code:
            raise ValueError("Print request requires submission_id or source_code")
        if self.submission_id and self.source_code:
            raise ValueError("Print request must use submission_id or source_code, not both")
        return self


class ContestPrintJob(BaseModel):
    id: str
    contest_id: str
    submission_id: str | None = None
    user_id: str
    user_display_name: str = ""
    problem_id: str | None = None
    problem_key: str | None = None
    problem_title: str | None = None
    language: str | None = None
    source_kind: ContestPrintSourceKind
    source_code: str
    status: ContestPrintStatus = "pending"
    line_count: int = Field(ge=0)
    requested_at: datetime
    printed_at: datetime | None = None
    printed_by: str | None = None
    note: str = ""


class ContestPrintJobSummary(BaseModel):
    id: str
    contest_id: str
    submission_id: str | None = None
    user_id: str
    user_display_name: str = ""
    problem_id: str | None = None
    problem_key: str | None = None
    problem_title: str | None = None
    language: str | None = None
    source_kind: ContestPrintSourceKind
    status: ContestPrintStatus = "pending"
    line_count: int = Field(ge=0)
    requested_at: datetime
    printed_at: datetime | None = None
    printed_by: str | None = None
    note: str = ""


class ContestPrintResponse(ContestPrintJobSummary):
    source_code: str


class ContestPrintUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ContestPrintStatus = "printed"
    note: str = Field(default="", max_length=300)

    @field_validator("note", mode="before")
    @classmethod
    def strip_note(cls, value: str | None) -> str:
        return str(value or "").strip()


class ContestSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_id: str = Field(min_length=1, max_length=64)
    language: LanguageCode | None = None
    source_code: str | None = Field(default=None, min_length=1, max_length=65536)
    answers: dict[str, Any] | None = None

    @field_validator("problem_id", "language", mode="before")
    @classmethod
    def strip_submit_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @model_validator(mode="after")
    def require_payload(self) -> "ContestSubmitRequest":
        if not self.source_code and not self.answers:
            raise ValueError("Contest submission requires source_code or answers")
        return self


class ContestBalloonUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str = Field(min_length=1, max_length=64)
    released: bool = True

    @field_validator("submission_id", mode="before")
    @classmethod
    def strip_balloon_submission(cls, value: str | None) -> str:
        return str(value or "").strip()


class ContestBalloon(BaseModel):
    contest_id: str
    submission_id: str
    user_id: str
    display_name: str
    problem_id: str
    problem_title: str
    eligible: bool = False
    first_ac: bool = False
    status: SubmissionStatus
    score: int
    max_score: int
    judged_at: datetime | None = None
    released: bool = False
    released_at: datetime | None = None
    released_by: str | None = None


class JudgeNode(BaseModel):
    id: str
    name: str
    status: JudgeNodeStatus
    languages: list[str]
    queue_depth: int = Field(ge=0)
    load: float = Field(ge=0)
    last_heartbeat: datetime

    @field_validator("id", "name", mode="before")
    @classmethod
    def strip_node_text(cls, value: str | None) -> str:
        return str(value or "").strip()

    @field_validator("languages", mode="before")
    @classmethod
    def normalize_languages(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = value.replace("，", ",").split(",")
        languages: list[str] = []
        seen: set[str] = set()
        for item in value:
            language = str(item or "").strip().lower()
            if language and language not in seen:
                languages.append(language)
                seen.add(language)
        return languages


class JudgeNodeHeartbeatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    name: str | None = Field(default=None, max_length=120)
    status: JudgeNodeStatus = "online"
    languages: list[str] = Field(default_factory=list)
    queue_depth: int = Field(default=0, ge=0)
    load: float = Field(default=0, ge=0)

    @field_validator("id", "name", mode="before")
    @classmethod
    def strip_heartbeat_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return str(value).strip()

    @field_validator("languages", mode="before")
    @classmethod
    def normalize_heartbeat_languages(cls, value: Any) -> list[str]:
        return JudgeNode.normalize_languages(value)


class JudgeNodeStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: JudgeNodeStatus


class CompilerLanguage(BaseModel):
    code: LanguageCode
    display_name: str
    version: str
    source_extension: str


class CompilerConfig(CompilerLanguage):
    compile_command: list[str] = Field(default_factory=list)
    run_command: list[str] = Field(default_factory=list)
    enabled: bool = True
    sort_order: int = 0
    updated_at: datetime


class CompilerConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    version: str | None = Field(default=None, min_length=1, max_length=120)
    source_extension: str | None = Field(default=None, min_length=1, max_length=16)
    compile_command: list[str] | None = None
    run_command: list[str] | None = None
    enabled: bool | None = None
    sort_order: int | None = None

    @field_validator("display_name", "version", "source_extension", mode="before")
    @classmethod
    def strip_config_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return str(value).strip()

    @field_validator("compile_command", "run_command", mode="before")
    @classmethod
    def normalize_command(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("Command template must be a list")
        return [str(item).strip() for item in value if str(item).strip()]


class JudgeQueueJob(BaseModel):
    id: str
    submission_id: str
    problem_id: str
    user_id: str
    contest_id: str | None = None
    language: str
    source_ref: str
    source_sha256: str
    limits: dict[str, int | None] = Field(default_factory=dict)
    testdata_ref: str | None = None
    priority: int = 0
    status: JudgeQueueJobStatus = "pending"
    backend: JudgeQueueBackend = "json"
    assigned_node_id: str | None = None
    attempts: int = 0
    last_error: str = ""
    created_at: datetime
    leased_at: datetime | None = None
    completed_at: datetime | None = None


class JudgeQueueSummary(BaseModel):
    backend: JudgeQueueBackend
    topic: str
    depth: int
    pending: int
    leased: int
    last_jobs: list[JudgeQueueJob] = Field(default_factory=list)


class JudgeNodeClaimResponse(BaseModel):
    node: JudgeNode
    job: JudgeQueueJob | None = None
    submission: Submission | None = None


class AuditLog(BaseModel):
    id: str
    actor_id: str | None = None
    action: str
    resource: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditLogList(BaseModel):
    items: list[AuditLog]
    total: int
    limit: int
    offset: int


class OverrideRequest(BaseModel):
    status: SubmissionStatus
    score: int
    message: str


class RejudgeRequest(BaseModel):
    reason: str = Field(default="", max_length=300)

    @field_validator("reason", mode="before")
    @classmethod
    def strip_reason(cls, value: str | None) -> str:
        return str(value or "").strip()


class RejudgeBatchRequest(RejudgeRequest):
    submission_ids: list[str] = Field(default_factory=list, max_length=200)
    problem_id: str | None = None
    contest_id: str | None = None
    statuses: list[SubmissionStatus] = Field(default_factory=list)

    @field_validator("submission_ids", "statuses", mode="before")
    @classmethod
    def normalize_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = value.replace("，", ",").split(",")
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text and text not in result:
                result.append(text)
        return result

    @field_validator("problem_id", "contest_id", mode="before")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @model_validator(mode="after")
    def require_selector(self) -> "RejudgeBatchRequest":
        if not self.submission_ids and not self.problem_id and not self.contest_id:
            raise ValueError("Batch rejudge requires submission_ids, problem_id, or contest_id")
        return self


class ContestRejudgeRequest(RejudgeRequest):
    submission_ids: list[str] = Field(default_factory=list, max_length=500)
    problem_id: str | None = None
    statuses: list[SubmissionStatus] = Field(default_factory=list)

    @field_validator("submission_ids", "statuses", mode="before")
    @classmethod
    def normalize_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = value.replace("，", ",").split(",")
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text and text not in result:
                result.append(text)
        return result

    @field_validator("problem_id", mode="before")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class RejudgeSkipped(BaseModel):
    submission_id: str
    reason: str


class RejudgeBatchResponse(BaseModel):
    requeued: list[Submission]
    skipped: list[RejudgeSkipped]
    requeued_count: int
    skipped_count: int


class ContestRejudgeResponse(RejudgeBatchResponse):
    contest_id: str
    rejudge_at: datetime
    rejudge_by: str
    rejudge_reason: str


class ProblemSet(BaseModel):
    id: str
    title: str
    description: str
    type: Literal["set", "exam", "assignment"] = "set"
    visibility: Visibility = "public"
    problem_ids: list[str]
    owner_id: str
    duration_minutes: int | None = None
    due_at: datetime | None = None
    offline_enabled: bool = True
    offline_policy: OfflinePolicy = Field(default_factory=OfflinePolicy)
    created_at: datetime
    updated_at: datetime


class ProblemSetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    description: str = ""
    type: Literal["set", "exam", "assignment"] = "set"
    visibility: Visibility = "public"
    problem_ids: list[str]
    duration_minutes: int | None = None
    due_at: datetime | None = None
    offline_enabled: bool = True
    offline_policy: OfflinePolicy = Field(default_factory=OfflinePolicy)


class ProblemSetDetail(ProblemSet):
    problems: list[ProblemSummary] = Field(default_factory=list)


class Assignment(BaseModel):
    id: str
    title: str
    description: str
    problem_set_id: str
    team_id: str | None = None
    due_at: datetime
    created_by: str
    created_at: datetime


class AssignmentCreate(BaseModel):
    title: str
    description: str = ""
    problem_set_id: str
    team_id: str | None = None
    due_at: datetime


class AssignmentStudentStatus(BaseModel):
    user_id: str
    display_name: str
    school: str
    status: AssignmentProgressState
    solved_count: int
    problem_count: int
    completion: float
    last_submission_at: datetime | None = None


class AssignmentAnalytics(BaseModel):
    id: str
    title: str
    description: str
    problem_set_id: str
    team_id: str | None = None
    due_at: datetime
    created_by: str
    created_at: datetime
    problem_set_title: str
    problem_count: int
    student_count: int
    completed_count: int
    completion: float
    status: AssignmentProgressState
    state_counts: dict[AssignmentProgressState, int] = Field(default_factory=dict)
    students: list[AssignmentStudentStatus] = Field(default_factory=list)


class Team(BaseModel):
    id: str
    name: str
    description: str = ""
    invite_code: str
    owner_id: str
    member_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class TeamCreate(BaseModel):
    name: str
    description: str = ""
    member_ids: list[str] = Field(default_factory=list)


class TagMastery(BaseModel):
    tag: str
    attempts: int
    accepted: int
    solved: int = 0
    student_count: int = 0
    accuracy: float = 0.0


class ProblemTypeMastery(BaseModel):
    problem_type: ProblemType
    attempts: int
    accepted: int
    solved: int
    accuracy: float = 0.0


class ActivityHeatmapCell(BaseModel):
    date: str
    attempts: int
    accepted: int
    active_students: int


class StudentAbilityProfile(BaseModel):
    user_id: str
    display_name: str
    school: str
    attempts: int
    accepted: int
    solved: int
    accuracy: float
    last_submission_at: datetime | None = None
    tag_mastery: list[TagMastery] = Field(default_factory=list)
    type_mastery: list[ProblemTypeMastery] = Field(default_factory=list)
    heatmap: list[ActivityHeatmapCell] = Field(default_factory=list)


class CoachSimilarityStudent(BaseModel):
    user_id: str
    display_name: str
    school: str
    team_ids: list[str] = Field(default_factory=list)
    team_names: list[str] = Field(default_factory=list)


class CoachSimilarityFinding(BaseModel):
    problem_id: str
    problem_title: str
    contest_id: str | None = None
    contest_title: str | None = None
    language: str
    similarity: float = Field(ge=0, le=1)
    shared_token_count: int = Field(ge=0)
    token_count_a: int = Field(ge=0)
    token_count_b: int = Field(ge=0)
    submission_a_id: str
    submission_b_id: str
    submitted_at_a: datetime
    submitted_at_b: datetime
    status_a: SubmissionStatus
    status_b: SubmissionStatus
    student_a: CoachSimilarityStudent
    student_b: CoachSimilarityStudent
    reason: str


class CoachSimilarityFilterOption(BaseModel):
    id: str
    title: str
    count: int = Field(ge=0)


class CoachSimilarityResponse(BaseModel):
    generated_at: datetime
    threshold: float = Field(ge=0, le=1)
    limit: int = Field(ge=1)
    problem_id: str | None = None
    contest_id: str | None = None
    scanned_submission_count: int = Field(ge=0)
    candidate_pair_count: int = Field(ge=0)
    findings: list[CoachSimilarityFinding] = Field(default_factory=list)
    problems: list[CoachSimilarityFilterOption] = Field(default_factory=list)
    contests: list[CoachSimilarityFilterOption] = Field(default_factory=list)


class CoachAnalyticsResponse(BaseModel):
    class_size: int
    active_students: int
    assignments: list[AssignmentAnalytics]
    teams: list[Team]
    tag_mastery: list[TagMastery]
    type_mastery: list[ProblemTypeMastery] = Field(default_factory=list)
    activity_heatmap: list[ActivityHeatmapCell] = Field(default_factory=list)
    student_profiles: list[StudentAbilityProfile] = Field(default_factory=list)


class Discussion(BaseModel):
    id: str
    type: DiscussionType = "general"
    target_id: str | None = None
    title: str
    content: str
    author_id: str
    author_name: str
    pinned: bool = False
    likes: int = 0
    solution_category: SolutionCategory | None = None
    liked_by: list[str] = Field(default_factory=list)
    bookmarked_by: list[str] = Field(default_factory=list)
    replies: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DiscussionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: DiscussionType = "general"
    target_id: str | None = Field(default=None, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=8000)
    solution_category: SolutionCategory | None = None

    @field_validator("target_id", "title", "content", mode="before")
    @classmethod
    def strip_discussion_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = str(value).strip()
        return text or None

    @field_validator("solution_category", mode="before")
    @classmethod
    def normalize_solution_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        return text or None


class DiscussionReplyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content", mode="before")
    @classmethod
    def strip_reply_text(cls, value: str | None) -> str:
        return str(value or "").strip()


class DiscussionListResponse(BaseModel):
    items: list["DiscussionView"]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class DiscussionView(BaseModel):
    id: str
    type: DiscussionType = "general"
    target_id: str | None = None
    title: str
    content: str
    author_id: str
    author_name: str
    pinned: bool = False
    likes: int = 0
    solution_category: SolutionCategory | None = None
    liked: bool = False
    bookmarked: bool = False
    replies: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DiscussionReactionResponse(BaseModel):
    discussion: DiscussionView
    action: Literal["liked", "unliked", "bookmarked", "unbookmarked"]
    changed: bool


class NotificationStreamItem(BaseModel):
    id: str
    title: str
    type: Literal["judge", "contest", "reply", "system", "assignment"]
    is_read: bool
    created_at: datetime


class NotificationStreamEvent(BaseModel):
    event: Literal["snapshot", "update", "heartbeat"] = "snapshot"
    unread_count: int = Field(ge=0)
    latest: NotificationStreamItem | None = None
    generated_at: datetime


class Notification(BaseModel):
    id: str
    user_id: str
    title: str
    content: str
    type: Literal["judge", "contest", "reply", "system", "assignment"] = "system"
    is_read: bool = False
    created_at: datetime


class OfflineResultItem(BaseModel):
    problem_id: str
    answers: dict[str, Any]
    practiced_at: datetime | None = None
    client_result_key: str | None = Field(default=None, max_length=128)
    pack_id: str | None = Field(default=None, max_length=128)
    source: dict[str, Any] = Field(default_factory=dict)

    @field_validator("client_result_key", mode="before")
    @classmethod
    def normalize_client_result_key(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class OfflineResultSyncRequest(BaseModel):
    results: list[OfflineResultItem]


class OfflinePackProblem(BaseModel):
    id: str
    title: str
    type: ProblemType
    difficulty: str
    tags: list[str]
    statement: str
    options: list[dict[str, str]] = Field(default_factory=list)
    blanks: list[dict[str, Any]] = Field(default_factory=list)
    judge_config: dict[str, Any] = Field(default_factory=dict)


class OfflinePackLifecycle(BaseModel):
    status: Literal["active", "expired", "download_limit_reached", "disabled", "unknown"] = "unknown"
    downloaded: int = 0
    max_downloads: int | None = None
    retention_days: int | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    problem_set_id: str | None = None
    problem_ids: list[str] = Field(default_factory=list)


class OfflinePackPayload(BaseModel):
    version: str
    pack_id: str
    generated_at: str
    expires_at: str
    signature_algorithm: Literal["hmac-sha256"] = "hmac-sha256"
    scope: Literal["objective-only"]
    source: dict[str, Any] = Field(default_factory=dict)
    lifecycle: OfflinePackLifecycle = Field(default_factory=OfflinePackLifecycle)
    problems: list[OfflinePackProblem]


class OfflinePackResponse(BaseModel):
    payload: OfflinePackPayload
    signature: str


class OfflineResultRejected(BaseModel):
    problem_id: str
    reason_code: str
    reason: str


class OfflinePackRecord(BaseModel):
    pack_id: str
    source: dict[str, Any] = Field(default_factory=dict)
    problem_set_id: str | None = None
    problem_ids: list[str] = Field(default_factory=list)
    generated_at: datetime
    expires_at: datetime
    ttl_hours: int | None = None
    retention_days: int | None = None
    max_downloads: int | None = None
    downloaded: int = 0
    status: Literal["active", "expired", "disabled", "download_limit_reached"] = "active"
    created_by: str
    created_at: datetime
    last_downloaded_at: datetime | None = None


class OfflinePackCreate(BaseModel):
    pack_id: str
    source: dict[str, Any] = Field(default_factory=dict)
    problem_set_id: str | None = None
    problem_ids: list[str] = Field(default_factory=list)
    generated_at: datetime
    expires_at: datetime
    ttl_hours: int | None = None
    retention_days: int | None = None
    max_downloads: int | None = None
    created_by: str
    created_at: datetime


class OfflinePackStatus(BaseModel):
    pack_id: str
    status: Literal["active", "expired", "disabled", "download_limit_reached", "unknown"]
    source: dict[str, Any] = Field(default_factory=dict)
    problem_set_id: str | None = None
    problem_ids: list[str] = Field(default_factory=list)
    generated_at: datetime | None = None
    expires_at: datetime | None = None
    ttl_hours: int | None = None
    retention_days: int | None = None
    max_downloads: int | None = None
    downloaded: int = 0
    last_downloaded_at: datetime | None = None


class OfflinePackStatusResponse(BaseModel):
    payload: OfflinePackStatus


class OfflineResultSyncResponse(BaseModel):
    synced: list[SubmissionReview]
    merged: list[SubmissionReview] = Field(default_factory=list)
    rejected: list[OfflineResultRejected]


class JudgeMonitorResponse(BaseModel):
    queue_depth: int
    queue: JudgeQueueSummary
    last_submissions: list[Submission]
    judge_nodes: list[JudgeNode]
    clarifications: list[Clarification]
    contests: list[Contest] = Field(default_factory=list)
    frozen_contests: list[Contest] = Field(default_factory=list)
    balloons: list[ContestBalloon] = Field(default_factory=list)


class ContestJudgeQueueSummary(BaseModel):
    backend: JudgeQueueBackend
    topic: str
    depth: int
    pending: int
    leased: int
    last_jobs: list[JudgeQueueJob] = Field(default_factory=list)


class ContestJudgeMonitorResponse(BaseModel):
    contest: ContestDetail
    queue_depth: int
    queue: ContestJudgeQueueSummary
    last_submissions: list[SubmissionReview]
    judge_nodes: list[JudgeNode]
    clarifications: list[Clarification]
    announcements: list[ContestAnnouncement] = Field(default_factory=list)
    balloons: list[ContestBalloon] = Field(default_factory=list)
    print_jobs: list[ContestPrintJobSummary] = Field(default_factory=list)


class SystemConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    site_name: str = "gayoj"
    registration_enabled: bool = True
    default_language: str = "cpp"
    judge_submit_rate_limit_per_minute: int = Field(default=10, ge=1)
    objective_submit_rate_limit_per_minute: int = Field(default=30, ge=1)
    password_min_length: int = Field(default=6, ge=1, le=128)
    password_require_letter: bool = True
    password_require_digit: bool = True
    login_max_failed_attempts: int = Field(default=5, ge=1, le=50)
    login_lockout_minutes: int = Field(default=15, ge=1, le=1440)
    maintenance_mode: bool = False


class SystemConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    site_name: str | None = None
    registration_enabled: bool | None = None
    default_language: str | None = None
    judge_submit_rate_limit_per_minute: int | None = Field(default=None, ge=1)
    objective_submit_rate_limit_per_minute: int | None = Field(default=None, ge=1)
    password_min_length: int | None = Field(default=None, ge=1, le=128)
    password_require_letter: bool | None = None
    password_require_digit: bool | None = None
    login_max_failed_attempts: int | None = Field(default=None, ge=1, le=50)
    login_lockout_minutes: int | None = Field(default=None, ge=1, le=1440)
    maintenance_mode: bool | None = None

