from __future__ import annotations

import json
import hashlib
import copy
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .config import JUDGE_NODE_HEARTBEAT_TTL_SECONDS
from .models import (
    Assignment,
    AuditLog,
    Clarification,
    CompilerConfig,
    Contest,
    DEFAULT_STUDENT_SCHOOL,
    Discussion,
    JudgeQueueJob,
    JudgeNode,
    OfflinePackRecord,
    Notification,
    Problem,
    ProblemTestData,
    ProblemVersion,
    ProblemSet,
    Submission,
    Tag,
    Team,
    User,
)


ROOT = Path(__file__).resolve().parents[1]
STORAGE_PATH = ROOT / "storage" / "dev-db.json"
LANGUAGE_CODES = ("c", "cpp", "java", "python")
DEMO_USERNAMES = {"alice", "coach", "judge", "admin"}
LEGACY_DEFAULT_STUDENT_SCHOOLS = {"gayoj Training Team"}
LEGACY_DEMO_PASSWORD_HASHES = {
    "pbkdf2_sha256$gayoj-demo-salt$c1570f6999257d09d37c38805485340bf93efbe239c3003df724aee4e0a11e14",
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    if not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return None


def _seed_password() -> str:
    salt = "gayoj-demo-salt"
    digest = hashlib.pbkdf2_hmac("sha256", "gayoj123".encode(), salt.encode(), 120_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def _split_problem_dump(problem: Problem) -> tuple[dict[str, Any], dict[str, Any]]:
    item = problem.model_dump(mode="json")
    judge_config = item.pop("judge_config", {})
    return item, judge_config


def _default_offline_enabled(problem_type: str | None = None) -> bool:
    return problem_type != "code"


def _normalize_offline_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    normalized: dict[str, Any] = {}
    ttl_hours = value.get("ttl_hours")
    if ttl_hours is not None:
        try:
            ttl = int(ttl_hours)
        except (TypeError, ValueError):
            ttl = 0
        if 1 <= ttl <= 24 * 365:
            normalized["ttl_hours"] = ttl
        else:
            normalized["ttl_hours"] = None
    else:
        normalized["ttl_hours"] = None
    normalized["answer_visibility"] = value.get("answer_visibility") if value.get("answer_visibility") in {"full", "none"} else "full"
    normalized["sync_mode"] = value.get("sync_mode") if value.get("sync_mode") in {"allow", "disabled"} else "allow"
    max_downloads = value.get("max_downloads")
    if max_downloads is None:
        normalized["max_downloads"] = None
    else:
        try:
            max_value = int(max_downloads)
        except (TypeError, ValueError):
            max_value = 0
        normalized["max_downloads"] = max_value if max_value > 0 else None
    retention_days = value.get("retention_days", 30)
    try:
        retention = int(retention_days)
    except (TypeError, ValueError):
        retention = 30
    normalized["retention_days"] = retention if retention > 0 else 30
    return normalized


def _clean_tag_name(value: Any) -> str:
    return str(value or "").strip()


def _tag_slug(name: str) -> str:
    return "-".join(name.lower().replace("，", " ").replace(",", " ").split())


def _next_tag_id(items: list[dict[str, Any]]) -> str:
    numeric_ids = [
        int(str(item.get("id", ""))[3:])
        for item in items
        if str(item.get("id", "")).startswith("TAG") and str(item.get("id", ""))[3:].isdigit()
    ]
    return f"TAG{max(numeric_ids, default=1000) + 1}"


def _dedupe_text(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean_tag_name(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _tag_item(
    tag_id: str,
    name: str,
    created_at: datetime,
    *,
    parent_id: str | None = None,
    sort_order: int = 0,
) -> dict[str, Any]:
    return {
        "id": tag_id,
        "name": name,
        "slug": _tag_slug(name),
        "parent_id": parent_id,
        "sort_order": sort_order,
        "created_at": created_at.isoformat(),
    }


def _seed_tags(created: datetime) -> list[dict[str, Any]]:
    return [
        _tag_item("TAG1001", "算法", created, sort_order=0),
        _tag_item("TAG1002", "基础算法", created, parent_id="TAG1001", sort_order=10),
        _tag_item("TAG1003", "语法", created, parent_id="TAG1002", sort_order=10),
        _tag_item("TAG1004", "输入输出", created, parent_id="TAG1002", sort_order=20),
        _tag_item("TAG1005", "算法思想", created, parent_id="TAG1002", sort_order=30),
        _tag_item("TAG1006", "二分", created, parent_id="TAG1002", sort_order=40),
        _tag_item("TAG1007", "图论", created, parent_id="TAG1001", sort_order=20),
        _tag_item("TAG1008", "数学", created, parent_id="TAG1001", sort_order=30),
        _tag_item("TAG1009", "组合数学", created, parent_id="TAG1008", sort_order=10),
        _tag_item("TAG1010", "系统", created, sort_order=90),
        _tag_item("TAG1011", "系统安全", created, parent_id="TAG1010", sort_order=10),
        _tag_item("TAG1012", "在线评测", created, parent_id="TAG1010", sort_order=20),
    ]


def _seed_compiler_configs(updated_at: datetime) -> list[dict[str, Any]]:
    stamp = updated_at.isoformat()
    return [
        {
            "code": "c",
            "display_name": "C",
            "version": "GCC 14.2 / C17",
            "source_extension": ".c",
            "compile_command": [
                "gcc",
                "-std=c17",
                "-O2",
                "-Wall",
                "-Wextra",
                "-DONLINE_JUDGE",
                "-static",
                "-Wl,--no-relax",
                "-Wl,--no-pie",
                "-mcmodel=medium",
                "-o",
                "Main",
                "Main.c",
            ],
            "run_command": ["./Main"],
            "enabled": True,
            "sort_order": 10,
            "updated_at": stamp,
        },
        {
            "code": "cpp",
            "display_name": "C++17",
            "version": "GCC 14.2 / C++17",
            "source_extension": ".cpp",
            "compile_command": [
                "g++",
                "-std=c++17",
                "-O2",
                "-Wall",
                "-Wextra",
                "-DONLINE_JUDGE",
                "-static",
                "-Wl,--no-relax",
                "-Wl,--no-pie",
                "-mcmodel=medium",
                "-o",
                "Main",
                "Main.cpp",
            ],
            "run_command": ["./Main"],
            "enabled": True,
            "sort_order": 20,
            "updated_at": stamp,
        },
        {
            "code": "java",
            "display_name": "Java",
            "version": "OpenJDK 21",
            "source_extension": ".java",
            "compile_command": ["javac", "-J-Xms1024M", "-J-Xmx1024M", "-J-Xss64M", "-encoding", "UTF-8", "Main.java"],
            "run_command": ["java", "-Dfile.encoding=UTF-8", "-XX:+UseSerialGC", "-Xss64M", "-cp", ".", "Main"],
            "enabled": True,
            "sort_order": 30,
            "updated_at": stamp,
        },
        {
            "code": "python",
            "display_name": "Python",
            "version": "Python 3.12",
            "source_extension": ".py",
            "compile_command": ["python3", "-m", "py_compile", "Main.py"],
            "run_command": ["python3", "Main.py"],
            "enabled": True,
            "sort_order": 40,
            "updated_at": stamp,
        },
    ]


def seed_data() -> dict[str, Any]:
    created = now()
    password = _seed_password()
    users = [
        User(
            id="u-student",
            username="alice",
            display_name="Alice Chen",
            role="student",
            school=DEFAULT_STUDENT_SCHOOL,
            rating=1580,
            solved=1,
            email="alice@example.com",
            password_hash=password,
        ),
        User(
            id="u-coach",
            username="coach",
            display_name="Coach Lin",
            role="coach",
            school="gayoj Training Team",
            rating=1800,
            solved=12,
            email="coach@example.com",
            password_hash=password,
        ),
        User(
            id="u-judge",
            username="judge",
            display_name="Judge Wu",
            role="judge",
            school="gayoj Committee",
            rating=1900,
            solved=25,
            email="judge@example.com",
            password_hash=password,
        ),
        User(
            id="u-admin",
            username="admin",
            display_name="Admin",
            role="admin",
            school="gayoj Ops",
            rating=2100,
            solved=36,
            email="admin@example.com",
            password_hash=password,
        ),
    ]
    problems = [
        Problem(
            id="P1001",
            title="A+B Problem",
            type="code",
            difficulty="入门",
            tags=["语法", "输入输出"],
            statement="给定两个整数 a 和 b，输出它们的和。本题用于验证在线代码提交、排队和结果回写流程。",
            input_format="一行两个整数 a, b。",
            output_format="输出一个整数，表示 a + b。",
            samples=[{"input": "1 2", "output": "3"}, {"input": "100 250", "output": "350"}],
            time_limit_ms=1000,
            memory_limit_mb=128,
            author_id="u-admin",
            offline_enabled=False,
            judge_config={"mode": "standard", "tests": 12, "simulator_hint": "source must contain addition"},
            created_at=created,
        ),
        Problem(
            id="P1002",
            title="完全图边数",
            type="blank",
            difficulty="基础",
            tags=["组合数学", "图论"],
            statement="含 n 个不同顶点的无向完全图共有多少条边？请填写关于 n 的表达式。",
            blanks=[{"key": "edge_formula", "label": "边数公式", "score": 100}],
            author_id="u-coach",
            offline_enabled=True,
            judge_config={
                "case_sensitive": False,
                "trim_space": True,
                "answers": {"edge_formula": ["n(n-1)/2", "n*(n-1)/2", "n(n - 1)/2"]},
                "scores": {"edge_formula": 100},
            },
            created_at=created,
        ),
        Problem(
            id="P1003",
            title="二分查找适用条件",
            type="single_choice",
            difficulty="基础",
            tags=["算法思想", "二分"],
            statement="以下哪一项是二分查找正确使用的必要条件？",
            options=[
                {"key": "A", "text": "数组元素必须全部为正数"},
                {"key": "B", "text": "搜索空间具有有序性或单调性"},
                {"key": "C", "text": "只能使用递归实现"},
                {"key": "D", "text": "时间复杂度必须为 O(n)"},
            ],
            author_id="u-coach",
            offline_enabled=True,
            judge_config={"answer": "B", "score": 100},
            created_at=created,
        ),
        Problem(
            id="P1004",
            title="代码沙箱安全策略",
            type="multiple_choice",
            difficulty="提高",
            tags=["系统安全", "在线评测"],
            statement="下列哪些措施属于在线代码评测沙箱的常见安全策略？",
            options=[
                {"key": "A", "text": "限制 CPU 时间、内存和进程数量"},
                {"key": "B", "text": "允许评测程序访问公网以便下载依赖"},
                {"key": "C", "text": "禁用网络并使用系统调用白名单"},
                {"key": "D", "text": "将用户代码直接在 API 服务器进程内执行"},
            ],
            author_id="u-judge",
            offline_enabled=True,
            judge_config={"answer": ["A", "C"], "score": 100},
            created_at=created,
        ),
    ]
    contest = Contest(
        id="C1001",
        title="gayoj Spring Training Round",
        rule="ACM",
        start_at=created - timedelta(hours=1),
        end_at=created + timedelta(hours=4),
        problem_ids=["P1001", "P1002", "P1003"],
        status="running",
    )
    nodes = [
        JudgeNode(
            id="node-1",
            name="sandbox-a",
            status="online",
            languages=["cpp", "c", "java", "python"],
            queue_depth=1,
            load=0.34,
            last_heartbeat=created,
        ),
        JudgeNode(
            id="node-2",
            name="sandbox-b",
            status="draining",
            languages=["python"],
            queue_depth=0,
            load=0.12,
            last_heartbeat=created,
        ),
    ]
    problem_sets = [
        ProblemSet(
            id="PS1001",
            title="基础语法与数学热身",
            description="面向新选手的第一组训练，覆盖代码提交、组合数学和二分查找概念。",
            type="set",
            visibility="public",
            problem_ids=["P1001", "P1002", "P1003"],
            owner_id="u-coach",
            offline_enabled=True,
            created_at=created,
            updated_at=created,
        ),
        ProblemSet(
            id="PS1002",
            title="OJ 系统安全测验",
            description="用于课堂讨论在线评测沙箱、安全边界和客观题判分规则。",
            type="assignment",
            visibility="public",
            problem_ids=["P1004"],
            owner_id="u-coach",
            offline_enabled=True,
            due_at=created + timedelta(days=7),
            created_at=created,
            updated_at=created,
        ),
    ]
    teams = [
        Team(
            id="T1001",
            name="gayoj Training Team",
            description="默认训练班级，用于演示教练端班级与作业管理。",
            invite_code="GAYOJ2026",
            owner_id="u-coach",
            member_ids=["u-student"],
            created_at=created,
        )
    ]
    assignments = [
        Assignment(
            id="A1001",
            title="二分与组合数学基础训练",
            description="完成题单 PS1001，重点理解表达式填空和二分条件。",
            problem_set_id="PS1001",
            team_id="T1001",
            due_at=created + timedelta(days=10),
            created_by="u-coach",
            created_at=created,
        )
    ]
    discussions = [
        Discussion(
            id="D1001",
            type="problem",
            target_id="P1003",
            title="二分查找为什么要求单调性？",
            content="可以把二分理解为每次丢弃一半候选区间，因此判定条件必须能把搜索空间稳定分成两侧。",
            author_id="u-coach",
            author_name="Coach Lin",
            pinned=True,
            likes=3,
            created_at=created,
            updated_at=created,
        ),
        Discussion(
            id="D1002",
            type="solution",
            target_id="P1001",
            title="A+B Problem 题解",
            content="本题的关键是正确读取两个整数并输出它们的和。注意换行和整数范围。",
            author_id="u-student",
            author_name="Alice Chen",
            likes=1,
            created_at=created,
            updated_at=created,
        ),
    ]
    notifications = [
        Notification(
            id="N1001",
            user_id="u-student",
            title="训练作业已发布",
            content="教练发布了「二分与组合数学基础训练」，请在截止时间前完成。",
            type="assignment",
            created_at=created,
        ),
        Notification(
            id="N1002",
            user_id="u-student",
            title="比赛提醒",
            content="gayoj Spring Training Round 正在进行中。",
            type="contest",
            created_at=created,
        ),
    ]
    problem_items: list[dict[str, Any]] = []
    problem_judge_config: dict[str, dict[str, Any]] = {}
    for problem in problems:
        item, config = _split_problem_dump(problem)
        problem_items.append(item)
        problem_judge_config[problem.id] = config

    return {
        "users": [u.model_dump(mode="json") for u in users],
        "problems": problem_items,
        "problem_judge_config": problem_judge_config,
        "problem_test_data": {},
        "problem_versions": [],
        "tags": _seed_tags(created),
        "submissions": [],
        "judge_queue_jobs": [],
        "contests": [contest.model_dump(mode="json")],
        "clarifications": [],
        "contest_balloons": [],
        "judge_nodes": [n.model_dump(mode="json") for n in nodes],
        "compiler_configs": _seed_compiler_configs(created),
        "audit_logs": [],
        "offline_packs": [],
        "problem_sets": [p.model_dump(mode="json") for p in problem_sets],
        "teams": [t.model_dump(mode="json") for t in teams],
        "assignments": [a.model_dump(mode="json") for a in assignments],
        "discussions": [d.model_dump(mode="json") for d in discussions],
        "notifications": [n.model_dump(mode="json") for n in notifications],
        "system_config": {
            "site_name": "gayoj",
            "registration_enabled": True,
            "default_language": "cpp",
            "judge_submit_rate_limit_per_minute": 10,
            "objective_submit_rate_limit_per_minute": 30,
            "password_min_length": 6,
            "password_require_letter": True,
            "password_require_digit": True,
            "login_max_failed_attempts": 5,
            "login_lockout_minutes": 15,
            "maintenance_mode": False,
        },
    }


class Store:
    """In-memory domain store base.

    Runtime persistence is implemented by app.db.SnapshotRepository through the
    database layer in apps/api/storage. STORAGE_PATH remains only as the legacy
    seed snapshot location for compatibility imports.
    """

    def __init__(self, path: Path = STORAGE_PATH):
        self.path = path
        self._lock = threading.RLock()
        self._data = seed_data()

    def _read(self) -> dict[str, Any]:
        with self._lock:
            data = copy.deepcopy(self._data)
            data, changed = self._normalize_data(data)
            if changed:
                self._write(data)
            return data

    def _write(self, data: dict[str, Any]) -> None:
        with self._lock:
            self._data = copy.deepcopy(data)

    def _normalize_data(self, data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        changed = False
        seeded = seed_data()
        for key, value in seeded.items():
            if key == "problem_judge_config":
                continue
            if key not in data:
                data[key] = value
                changed = True
        for user in data.get("users", []):
            if "password_hash" not in user:
                user["password_hash"] = _seed_password()
                changed = True
            elif user.get("username") in DEMO_USERNAMES and user.get("password_hash") in LEGACY_DEMO_PASSWORD_HASHES:
                user["password_hash"] = _seed_password()
                changed = True
            for key, default in {
                "failed_login_attempts": 0,
                "locked_until": None,
                "last_login_at": None,
                "password_changed_at": None,
            }.items():
                if key not in user:
                    user[key] = default
                    changed = True
            if user.get("role") == "student" and (
                not str(user.get("school", "")).strip()
                or str(user.get("school", "")).strip() in LEGACY_DEFAULT_STUDENT_SCHOOLS
            ):
                user["school"] = DEFAULT_STUDENT_SCHOOL
                changed = True
        if self._migrate_system_config(data, seeded["system_config"]):
            changed = True
        if self._migrate_problem_judge_config(data):
            changed = True
        if self._migrate_offline_policy(data):
            changed = True
        if self._migrate_tags(data, seeded["tags"]):
            changed = True
        if self._migrate_compiler_configs(data, seeded["compiler_configs"]):
            changed = True
        if self._migrate_judge_nodes(data):
            changed = True
        if self._migrate_judge_queue_jobs(data):
            changed = True
        if self._migrate_offline_packs(data):
            changed = True
        return data, changed

    def _migrate_system_config(self, data: dict[str, Any], defaults: dict[str, Any]) -> bool:
        config = data.get("system_config")
        if not isinstance(config, dict):
            data["system_config"] = copy.deepcopy(defaults)
            return True
        changed = False
        for key, value in defaults.items():
            if key not in config:
                config[key] = copy.deepcopy(value)
                changed = True
        return changed

    def _migrate_compiler_configs(self, data: dict[str, Any], defaults: list[dict[str, Any]]) -> bool:
        raw_configs = data.get("compiler_configs")
        if not isinstance(raw_configs, list):
            data["compiler_configs"] = copy.deepcopy(defaults)
            return True

        raw_by_code = {
            str(item.get("code", "")).strip().lower(): item
            for item in raw_configs
            if isinstance(item, dict)
        }
        normalized: list[dict[str, Any]] = []
        changed = False
        for default in defaults:
            code = default["code"]
            source = raw_by_code.get(code)
            if source is None:
                normalized.append(copy.deepcopy(default))
                changed = True
                continue

            item = copy.deepcopy(default)
            for key in ["display_name", "version", "source_extension"]:
                value = str(source.get(key, item[key]) or "").strip()
                item[key] = value or item[key]
            for key in ["compile_command", "run_command"]:
                value = source.get(key, item[key])
                if isinstance(value, list):
                    item[key] = [str(part).strip() for part in value if str(part).strip()]
            item["enabled"] = bool(source.get("enabled", item["enabled"]))
            try:
                item["sort_order"] = int(source.get("sort_order", item["sort_order"]))
            except (TypeError, ValueError):
                item["sort_order"] = default["sort_order"]
            item["updated_at"] = source.get("updated_at") or item["updated_at"]
            normalized.append(item)

        if set(raw_by_code) - set(LANGUAGE_CODES):
            changed = True
        if normalized != raw_configs:
            changed = True
        data["compiler_configs"] = normalized
        return changed

    def _migrate_problem_judge_config(self, data: dict[str, Any]) -> bool:
        changed = False
        configs = data.get("problem_judge_config")
        if not isinstance(configs, dict):
            configs = {}
            data["problem_judge_config"] = configs
            changed = True

        for problem in data.get("problems", []):
            if not isinstance(problem, dict):
                continue
            problem_id = problem.get("id")
            if not problem_id:
                continue
            embedded = problem.pop("judge_config", None)
            if embedded is not None:
                changed = True
                if problem_id not in configs:
                    configs[problem_id] = embedded
            if problem_id not in configs:
                configs[problem_id] = {}
                changed = True

        return changed

    def _migrate_offline_policy(self, data: dict[str, Any]) -> bool:
        changed = False
        for problem in data.get("problems", []):
            if not isinstance(problem, dict):
                continue
            problem_type = str(problem.get("type") or problem.get("problem_type") or "")
            if "offline_enabled" not in problem:
                problem["offline_enabled"] = _default_offline_enabled(problem_type)
                changed = True
            if not isinstance(problem.get("offline_enabled"), bool):
                problem["offline_enabled"] = bool(problem.get("offline_enabled"))
                changed = True
            policy = _normalize_offline_policy(problem.get("offline_policy"))
            if problem.get("offline_policy") != policy:
                problem["offline_policy"] = policy
                changed = True

        for problem_set in data.get("problem_sets", []):
            if not isinstance(problem_set, dict):
                continue
            if "offline_enabled" not in problem_set:
                problem_set["offline_enabled"] = True
                changed = True
            if not isinstance(problem_set.get("offline_enabled"), bool):
                problem_set["offline_enabled"] = bool(problem_set.get("offline_enabled"))
                changed = True
            policy = _normalize_offline_policy(problem_set.get("offline_policy"))
            if problem_set.get("offline_policy") != policy:
                problem_set["offline_policy"] = policy
                changed = True

        return changed

    def _migrate_judge_nodes(self, data: dict[str, Any]) -> bool:
        changed = False
        raw_nodes = data.get("judge_nodes")
        if not isinstance(raw_nodes, list):
            raw_nodes = []
            changed = True

        normalized: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        current = now()
        ttl = max(1, JUDGE_NODE_HEARTBEAT_TTL_SECONDS)
        for raw in raw_nodes:
            if not isinstance(raw, dict):
                changed = True
                continue
            node = dict(raw)
            node_id = str(node.get("id") or node.get("name") or "").strip()
            if not node_id or node_id in seen_ids:
                changed = True
                continue
            seen_ids.add(node_id)
            languages = [
                language
                for language in JudgeNode.normalize_languages(node.get("languages", []))
                if language in LANGUAGE_CODES
            ]
            try:
                queue_depth = max(0, int(node.get("queue_depth", 0) or 0))
            except (TypeError, ValueError):
                queue_depth = 0
                changed = True
            try:
                load = max(0.0, float(node.get("load", 0) or 0))
            except (TypeError, ValueError):
                load = 0.0
                changed = True
            heartbeat = _parse_datetime(node.get("last_heartbeat")) or current
            status = node.get("status") if node.get("status") in {"online", "offline", "draining"} else "offline"
            if status in {"online", "draining"} and current - heartbeat > timedelta(seconds=ttl):
                status = "offline"
            normalized_node = {
                "id": node_id,
                "name": str(node.get("name") or node_id).strip() or node_id,
                "status": status,
                "languages": languages,
                "queue_depth": queue_depth,
                "load": load,
                "last_heartbeat": heartbeat.isoformat(),
            }
            if normalized_node != raw:
                changed = True
            normalized.append(normalized_node)

        if normalized != raw_nodes:
            changed = True
        data["judge_nodes"] = normalized
        return changed

    def _migrate_judge_queue_jobs(self, data: dict[str, Any]) -> bool:
        changed = False
        jobs = data.get("judge_queue_jobs")
        if not isinstance(jobs, list):
            jobs = []
            data["judge_queue_jobs"] = jobs
            changed = True

        submissions = {
            str(item.get("id")): item
            for item in data.get("submissions", [])
            if isinstance(item, dict) and item.get("id")
        }
        problems = {
            str(item.get("id")): item
            for item in data.get("problems", [])
            if isinstance(item, dict) and item.get("id")
        }
        configs = data.get("problem_judge_config", {}) if isinstance(data.get("problem_judge_config"), dict) else {}
        known_job_ids: set[str] = set()
        queued_submission_ids: set[str] = set()
        normalized_jobs: list[dict[str, Any]] = []
        now_iso = now().isoformat()

        for raw_job in jobs:
            if not isinstance(raw_job, dict):
                changed = True
                continue
            job = dict(raw_job)
            job.pop("source_code", None)
            submission_id = str(job.get("submission_id") or "")
            submission = submissions.get(submission_id)
            if not submission:
                changed = True
                continue
            problem_id = str(job.get("problem_id") or submission.get("problem_id") or "")
            problem = problems.get(problem_id, {})
            config = configs.get(problem_id, {}) if isinstance(configs.get(problem_id, {}), dict) else {}
            source = str(submission.get("source_code") or "")
            job_id = str(job.get("id") or submission.get("queue_job_id") or f"JQ-{submission_id}")
            if job_id in known_job_ids:
                job_id = f"JQ-{uuid4().hex[:12]}"
                changed = True
            job.update(
                {
                    "id": job_id,
                    "submission_id": submission_id,
                    "problem_id": problem_id,
                    "user_id": str(job.get("user_id") or submission.get("user_id") or ""),
                    "contest_id": job.get("contest_id", submission.get("contest_id")),
                    "language": str(job.get("language") or submission.get("language") or ""),
                    "source_ref": str(job.get("source_ref") or f"submission:{submission_id}:source_code"),
                    "source_sha256": str(
                        job.get("source_sha256") or hashlib.sha256(source.encode("utf-8")).hexdigest()
                    ),
                    "limits": job.get("limits")
                    if isinstance(job.get("limits"), dict)
                    else {
                        "time_limit_ms": problem.get("time_limit_ms"),
                        "memory_limit_mb": problem.get("memory_limit_mb"),
                    },
                    "testdata_ref": job.get("testdata_ref")
                    or config.get("testdata_ref")
                    or config.get("dataset_ref")
                    or f"problem:{problem_id}:testdata",
                    "priority": int(job.get("priority", 10 if submission.get("contest_id") else 0) or 0),
                    "status": job.get("status") if job.get("status") in {"pending", "leased", "completed", "failed"} else "pending",
                    "backend": job.get("backend") if job.get("backend") in {"json", "redis", "kafka"} else "json",
                    "assigned_node_id": job.get("assigned_node_id"),
                    "attempts": int(job.get("attempts", 0) or 0),
                    "last_error": str(job.get("last_error") or ""),
                    "created_at": job.get("created_at") or submission.get("queued_at") or submission.get("created_at") or now_iso,
                    "leased_at": job.get("leased_at"),
                    "completed_at": job.get("completed_at"),
                }
            )
            if raw_job != job:
                changed = True
            known_job_ids.add(job_id)
            queued_submission_ids.add(submission_id)
            if not submission.get("queue_job_id"):
                submission["queue_job_id"] = job_id
                changed = True
            if not submission.get("queued_at"):
                submission["queued_at"] = job["created_at"]
                changed = True
            normalized_jobs.append(job)

        for submission_id, submission in submissions.items():
            if submission_id in queued_submission_ids:
                continue
            if submission.get("problem_type") != "code" or submission.get("status") not in {"queued", "judging"}:
                continue
            job_id = str(submission.get("queue_job_id") or f"JQ-{submission_id}")
            if job_id in known_job_ids:
                job_id = f"JQ-{uuid4().hex[:12]}"
            problem_id = str(submission.get("problem_id") or "")
            problem = problems.get(problem_id, {})
            config = configs.get(problem_id, {}) if isinstance(configs.get(problem_id, {}), dict) else {}
            source = str(submission.get("source_code") or "")
            created_at = submission.get("queued_at") or submission.get("created_at") or now_iso
            submission["queue_job_id"] = job_id
            submission["queued_at"] = created_at
            normalized_jobs.append(
                {
                    "id": job_id,
                    "submission_id": submission_id,
                    "problem_id": problem_id,
                    "user_id": str(submission.get("user_id") or ""),
                    "contest_id": submission.get("contest_id"),
                    "language": str(submission.get("language") or ""),
                    "source_ref": f"submission:{submission_id}:source_code",
                    "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                    "limits": {
                        "time_limit_ms": problem.get("time_limit_ms"),
                        "memory_limit_mb": problem.get("memory_limit_mb"),
                    },
                    "testdata_ref": config.get("testdata_ref") or config.get("dataset_ref") or f"problem:{problem_id}:testdata",
                    "priority": 10 if submission.get("contest_id") else 0,
                    "status": "leased" if submission.get("status") == "judging" else "pending",
                    "backend": "json",
                    "assigned_node_id": None,
                    "attempts": 0,
                    "last_error": "",
                    "created_at": created_at,
                    "leased_at": None,
                    "completed_at": None,
                }
            )
            known_job_ids.add(job_id)
            changed = True

        if normalized_jobs != jobs:
            data["judge_queue_jobs"] = normalized_jobs
            changed = True
        return changed

    def _migrate_offline_packs(self, data: dict[str, Any]) -> bool:
        packs = data.get("offline_packs")
        if not isinstance(packs, list):
            data["offline_packs"] = []
            return True
        changed = False
        normalized: list[dict[str, Any]] = []
        for item in packs:
            if not isinstance(item, dict) or not item.get("pack_id"):
                changed = True
                continue
            record = {
                "pack_id": str(item.get("pack_id")),
                "source": item.get("source") if isinstance(item.get("source"), dict) else {},
                "problem_set_id": item.get("problem_set_id"),
                "problem_ids": [str(pid) for pid in item.get("problem_ids", []) if str(pid).strip()],
                "generated_at": item.get("generated_at") or now().isoformat(),
                "expires_at": item.get("expires_at") or now().isoformat(),
                "ttl_hours": item.get("ttl_hours"),
                "retention_days": item.get("retention_days"),
                "max_downloads": item.get("max_downloads"),
                "downloaded": max(0, int(item.get("downloaded", 0) or 0)),
                "status": item.get("status") if item.get("status") in {"active", "expired", "disabled", "download_limit_reached"} else "active",
                "created_by": str(item.get("created_by") or "system"),
                "created_at": item.get("created_at") or now().isoformat(),
                "last_downloaded_at": item.get("last_downloaded_at"),
            }
            normalized.append(record)
        if normalized != packs:
            data["offline_packs"] = normalized
            changed = True
        return changed

    def _migrate_tags(self, data: dict[str, Any], defaults: list[dict[str, Any]]) -> bool:
        changed = False
        raw_tags = data.get("tags")
        if not isinstance(raw_tags, list):
            raw_tags = []
            changed = True
        elif raw_tags and not any(isinstance(item, dict) and item.get("id") for item in raw_tags):
            raw_tags = [*_seed_tags(now()), *raw_tags]
            changed = True

        normalized: list[dict[str, Any]] = []
        names: set[str] = set()
        ids: set[str] = set()
        now_iso = now().isoformat()

        for raw in raw_tags:
            if isinstance(raw, str):
                item = {"name": raw}
            elif isinstance(raw, dict):
                item = dict(raw)
            else:
                changed = True
                continue

            name = _clean_tag_name(item.get("name"))
            if not name or name in names:
                changed = True
                continue
            tag_id = str(item.get("id") or "").strip()
            if not tag_id or tag_id in ids:
                tag_id = _next_tag_id(normalized)
                changed = True
            parent_id = str(item.get("parent_id") or "").strip() or None
            try:
                sort_order = int(item.get("sort_order", 0))
            except (TypeError, ValueError):
                sort_order = 0
                changed = True
            tag = {
                "id": tag_id,
                "name": name,
                "slug": _clean_tag_name(item.get("slug")) or _tag_slug(name),
                "parent_id": parent_id,
                "sort_order": sort_order,
                "created_at": item.get("created_at") or now_iso,
            }
            normalized.append(tag)
            ids.add(tag_id)
            names.add(name)

        for default in defaults:
            name = _clean_tag_name(default.get("name"))
            tag_id = str(default.get("id") or "").strip()
            if not name or name in names or tag_id in ids:
                continue
            normalized.append(copy.deepcopy(default))
            ids.add(tag_id)
            names.add(name)
            changed = True

        valid_ids = {item["id"] for item in normalized}
        for item in normalized:
            if item["parent_id"] and item["parent_id"] not in valid_ids:
                item["parent_id"] = None
                changed = True

        for problem in data.get("problems", []):
            if not isinstance(problem, dict):
                continue
            problem_tags = _dedupe_text(problem.get("tags", []))
            if problem_tags != problem.get("tags", []):
                problem["tags"] = problem_tags
                changed = True
            for name in problem_tags:
                if name not in names:
                    tag = _tag_item(_next_tag_id(normalized), name, now())
                    normalized.append(tag)
                    names.add(name)
                    changed = True

        if normalized != raw_tags:
            changed = True
        data["tags"] = normalized
        return changed

    def _ensure_problem_tags(self, data: dict[str, Any], problem_tags: list[str]) -> None:
        existing_names = {
            tag.get("name")
            for tag in data.get("tags", [])
            if isinstance(tag, dict) and _clean_tag_name(tag.get("name"))
        }
        for name in _dedupe_text(problem_tags):
            if name in existing_names:
                continue
            tag = _tag_item(_next_tag_id(data.setdefault("tags", [])), name, now())
            data["tags"].append(tag)
            existing_names.add(name)

    def _write(self, data: dict[str, Any]) -> None:
        with self._lock:
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_users(self) -> list[User]:
        return [User(**item) for item in self._read()["users"]]

    def get_user(self, user_id: str) -> User | None:
        return next((u for u in self.list_users() if u.id == user_id), None)

    def get_user_by_username(self, username: str) -> User | None:
        return next((u for u in self.list_users() if u.username == username), None)

    def update_user(self, user: User) -> User:
        data = self._read()
        data["users"] = [user.model_dump(mode="json") if item["id"] == user.id else item for item in data["users"]]
        self._write(data)
        return user

    def list_problems(self) -> list[Problem]:
        return [Problem(**item) for item in self._read()["problems"]]

    def get_problem(self, problem_id: str) -> Problem | None:
        return next((p for p in self.list_problems() if p.id == problem_id), None)

    def add_problem(self, problem: Problem) -> Problem:
        data = self._read()
        item, judge_config = _split_problem_dump(problem)
        item["tags"] = _dedupe_text(item.get("tags", []))
        self._ensure_problem_tags(data, item["tags"])
        data["problems"].append(item)
        data.setdefault("problem_judge_config", {})[problem.id] = judge_config
        self._write(data)
        return problem

    def update_problem(self, problem: Problem) -> Problem:
        data = self._read()
        item, judge_config = _split_problem_dump(problem)
        item["tags"] = _dedupe_text(item.get("tags", []))
        self._ensure_problem_tags(data, item["tags"])
        updated = False
        data["problems"] = [
            item if existing.get("id") == problem.id else existing
            for existing in data["problems"]
        ]
        updated = any(existing.get("id") == problem.id for existing in data["problems"])
        if not updated:
            data["problems"].append(item)
        data.setdefault("problem_judge_config", {})[problem.id] = judge_config
        self._write(data)
        return problem

    def upsert_problems(
        self,
        problems: list[Problem],
        *,
        version_snapshots: list[tuple[Problem, str, str]] | None = None,
    ) -> list[Problem]:
        data = self._read()
        problem_rows = list(data.get("problems", []))
        judge_configs = data.setdefault("problem_judge_config", {})
        versions = data.setdefault("problem_versions", [])
        index_by_id = {
            str(item.get("id")): index
            for index, item in enumerate(problem_rows)
            if isinstance(item, dict) and item.get("id")
        }
        for snapshot, saved_by, action in version_snapshots or []:
            current_versions = [item for item in versions if item.get("problem_id") == snapshot.id]
            next_version = max((int(item.get("version", 0)) for item in current_versions), default=0) + 1
            copy_snapshot = snapshot.model_copy(deep=True)
            copy_snapshot.judge_config = copy.deepcopy(
                copy_snapshot.judge_config or judge_configs.get(snapshot.id, {})
            )
            versions.insert(
                0,
                ProblemVersion(
                    id=f"PV{uuid4().hex[:12].upper()}",
                    problem_id=snapshot.id,
                    version=next_version,
                    saved_by=saved_by,
                    action=action,
                    saved_at=now(),
                    snapshot=copy_snapshot,
                ).model_dump(mode="json"),
            )
        for problem in problems:
            item, judge_config = _split_problem_dump(problem)
            item["tags"] = _dedupe_text(item.get("tags", []))
            self._ensure_problem_tags(data, item["tags"])
            if problem.id in index_by_id:
                problem_rows[index_by_id[problem.id]] = item
            else:
                index_by_id[problem.id] = len(problem_rows)
                problem_rows.append(item)
            judge_configs[problem.id] = judge_config
        data["problems"] = problem_rows
        self._write(data)
        return problems

    def delete_problem(self, problem_id: str) -> Problem | None:
        problem = self.get_problem(problem_id)
        if not problem:
            return None
        problem.judge_config = self.get_problem_judge_config(problem.id)
        problem.visible = False
        return self.update_problem(problem)

    def list_problem_versions(self, problem_id: str) -> list[ProblemVersion]:
        versions = [
            ProblemVersion(**item)
            for item in self._read().get("problem_versions", [])
            if item.get("problem_id") == problem_id
        ]
        return sorted(versions, key=lambda item: item.version, reverse=True)

    def get_problem_version(self, problem_id: str, version_id: str) -> ProblemVersion | None:
        return next(
            (
                version
                for version in self.list_problem_versions(problem_id)
                if version.id == version_id
            ),
            None,
        )

    def add_problem_version(self, problem: Problem, saved_by: str, action: str = "update") -> ProblemVersion:
        data = self._read()
        versions = data.setdefault("problem_versions", [])
        current_versions = [item for item in versions if item.get("problem_id") == problem.id]
        next_version = max((int(item.get("version", 0)) for item in current_versions), default=0) + 1
        snapshot = problem.model_copy(deep=True)
        snapshot.judge_config = copy.deepcopy(
            snapshot.judge_config or data.get("problem_judge_config", {}).get(problem.id, {})
        )
        version = ProblemVersion(
            id=f"PV{uuid4().hex[:12].upper()}",
            problem_id=problem.id,
            version=next_version,
            saved_by=saved_by,
            action=action,
            saved_at=now(),
            snapshot=snapshot,
        )
        versions.insert(0, version.model_dump(mode="json"))
        self._write(data)
        return version

    def restore_problem_version(self, problem_id: str, version_id: str) -> Problem | None:
        data = self._read()
        raw_version = next(
            (
                item
                for item in data.get("problem_versions", [])
                if item.get("problem_id") == problem_id and item.get("id") == version_id
            ),
            None,
        )
        if raw_version is None:
            return None
        snapshot = ProblemVersion(**raw_version).snapshot.model_copy(deep=True)
        snapshot.id = problem_id
        item, judge_config = _split_problem_dump(snapshot)
        data["problems"] = [
            item if existing.get("id") == problem_id else existing
            for existing in data.get("problems", [])
        ]
        updated = any(existing.get("id") == problem_id for existing in data["problems"])
        if not updated:
            data["problems"].append(item)
        data.setdefault("problem_judge_config", {})[problem_id] = judge_config
        self._write(data)
        return snapshot

    def get_problem_judge_config(self, problem_id: str) -> dict[str, Any]:
        data = self._read()
        config = data.get("problem_judge_config", {}).get(problem_id, {})
        return copy.deepcopy(config) if isinstance(config, dict) else {}

    def set_problem_judge_config(self, problem_id: str, judge_config: dict[str, Any]) -> None:
        data = self._read()
        data.setdefault("problem_judge_config", {})[problem_id] = copy.deepcopy(judge_config)
        self._write(data)

    def get_problem_test_data(self, problem_id: str) -> ProblemTestData | None:
        data = self._read()
        raw = data.get("problem_test_data", {}).get(problem_id)
        if not isinstance(raw, dict):
            return None
        return ProblemTestData(**raw)

    def set_problem_test_data(self, metadata: ProblemTestData) -> ProblemTestData:
        data = self._read()
        data.setdefault("problem_test_data", {})[metadata.problem_id] = metadata.model_dump(mode="json")
        self._write(data)
        return metadata

    def list_compiler_configs(self) -> list[CompilerConfig]:
        configs = [CompilerConfig(**item) for item in self._read()["compiler_configs"]]
        return sorted(configs, key=lambda item: (item.sort_order, item.code))

    def get_compiler_config(self, code: str) -> CompilerConfig | None:
        normalized = code.strip().lower()
        return next((config for config in self.list_compiler_configs() if config.code == normalized), None)

    def update_compiler_config(self, compiler_config: CompilerConfig) -> CompilerConfig:
        data = self._read()
        item = compiler_config.model_dump(mode="json")
        updated = False
        configs = []
        for existing in data.get("compiler_configs", []):
            if existing.get("code") == compiler_config.code:
                configs.append(item)
                updated = True
            else:
                configs.append(existing)
        if not updated:
            configs.append(item)
        data["compiler_configs"] = configs
        self._write(data)
        return compiler_config

    def list_tags(self) -> list[Tag]:
        return [Tag(**item) for item in self._read()["tags"]]

    def get_tag(self, tag_id: str) -> Tag | None:
        return next((tag for tag in self.list_tags() if tag.id == tag_id), None)

    def add_tag(self, tag: Tag) -> Tag:
        data = self._read()
        data.setdefault("tags", []).append(tag.model_dump(mode="json"))
        self._write(data)
        return tag

    def update_tag(self, tag: Tag) -> Tag:
        data = self._read()
        old_name = ""
        for item in data.get("tags", []):
            if item.get("id") == tag.id:
                old_name = _clean_tag_name(item.get("name"))
                break
        new_name = _clean_tag_name(tag.name)
        data["tags"] = [
            tag.model_dump(mode="json") if item.get("id") == tag.id else item
            for item in data.get("tags", [])
        ]
        if old_name and old_name != new_name:
            for problem in data.get("problems", []):
                if not isinstance(problem, dict):
                    continue
                problem["tags"] = _dedupe_text([new_name if name == old_name else name for name in problem.get("tags", [])])
        self._write(data)
        return tag

    def delete_tag(self, tag_id: str) -> Tag | None:
        data = self._read()
        deleted: Tag | None = None
        remaining = []
        for item in data.get("tags", []):
            if item.get("id") == tag_id:
                deleted = Tag(**item)
            else:
                remaining.append(item)
        if not deleted:
            return None
        data["tags"] = remaining
        self._write(data)
        return deleted

    def list_submissions(self) -> list[Submission]:
        return [Submission(**item) for item in self._read()["submissions"]]

    def get_submission(self, submission_id: str) -> Submission | None:
        return next((s for s in self.list_submissions() if s.id == submission_id), None)

    def add_submission(self, submission: Submission) -> Submission:
        data = self._read()
        data["submissions"].insert(0, submission.model_dump(mode="json"))
        self._write(data)
        return submission

    def update_submission(self, submission: Submission) -> Submission:
        data = self._read()
        data["submissions"] = [
            submission.model_dump(mode="json") if item["id"] == submission.id else item
            for item in data["submissions"]
        ]
        self._write(data)
        return submission

    def delete_submission(self, submission_id: str) -> None:
        data = self._read()
        data["submissions"] = [
            item
            for item in data.get("submissions", [])
            if item.get("id") != submission_id
        ]
        self._write(data)

    def list_judge_queue_jobs(self) -> list[JudgeQueueJob]:
        return [JudgeQueueJob(**item) for item in self._read().get("judge_queue_jobs", [])]

    def get_judge_queue_job(self, job_id: str) -> JudgeQueueJob | None:
        return next((job for job in self.list_judge_queue_jobs() if job.id == job_id), None)

    def add_judge_queue_job(self, job: JudgeQueueJob) -> JudgeQueueJob:
        data = self._read()
        jobs = data.setdefault("judge_queue_jobs", [])
        for index, item in enumerate(jobs):
            if item.get("id") == job.id or item.get("submission_id") == job.submission_id:
                jobs[index] = job.model_dump(mode="json")
                self._write(data)
                return job
        jobs.append(job.model_dump(mode="json"))
        self._write(data)
        return job

    def update_judge_queue_job(self, job: JudgeQueueJob) -> JudgeQueueJob:
        data = self._read()
        data["judge_queue_jobs"] = [
            job.model_dump(mode="json") if item.get("id") == job.id else item
            for item in data.get("judge_queue_jobs", [])
        ]
        self._write(data)
        return job

    def delete_judge_queue_job(self, job_id: str) -> None:
        data = self._read()
        data["judge_queue_jobs"] = [
            item
            for item in data.get("judge_queue_jobs", [])
            if item.get("id") != job_id
        ]
        self._write(data)

    def claim_next_judge_queue_job(self, *, node_id: str) -> tuple[JudgeQueueJob, Submission] | None:
        with self._lock:
            data = self._read()
            node = next((item for item in data.get("judge_nodes", []) if item.get("id") == node_id), None)
            if not node or node.get("status") != "online":
                return None
            supported_languages = set(JudgeNode.normalize_languages(node.get("languages", [])))
            enabled_languages = {
                str(config.get("code", "")).strip().lower()
                for config in data.get("compiler_configs", [])
                if isinstance(config, dict) and config.get("enabled", True)
            }
            submissions = data.get("submissions", [])
            pending_jobs = [
                job
                for job in data.get("judge_queue_jobs", [])
                if job.get("status") == "pending"
                and str(job.get("language") or "").lower() in enabled_languages
                and (not supported_languages or str(job.get("language") or "").lower() in supported_languages)
            ]
            pending_jobs.sort(
                key=lambda job: (
                    -int(job.get("priority", 0) or 0),
                    str(job.get("created_at", "")),
                    str(job.get("id", "")),
                )
            )
            for job in pending_jobs:
                submission = next(
                    (item for item in submissions if item.get("id") == job.get("submission_id")),
                    None,
                )
                if not submission:
                    continue
                if submission.get("status") != "queued" or submission.get("problem_type") != "code":
                    continue
                current = now().isoformat()
                submission["status"] = "judging"
                submission["message"] = f"已调度至评测节点 {node_id}，等待沙箱执行。"
                submission["judged_at"] = None
                submission.setdefault("details", [])
                submission["queue_job_id"] = job.get("id")
                if not submission.get("queued_at"):
                    submission["queued_at"] = job.get("created_at") or current
                job["status"] = "leased"
                job["assigned_node_id"] = node_id
                job["leased_at"] = current
                job["attempts"] = int(job.get("attempts", 0) or 0) + 1
                node["queue_depth"] = max(0, int(node.get("queue_depth", 0) or 0)) + 1
                self._write(data)
                return JudgeQueueJob(**job), Submission(**submission)
        return None

    def claim_next_code_submission(self, *, worker_id: str, languages: list[str]) -> Submission | None:
        supported_languages = {language.strip().lower() for language in languages if language.strip()}
        with self._lock:
            data = self._read()
            enabled_languages = {
                str(config.get("code", "")).strip().lower()
                for config in data.get("compiler_configs", [])
                if isinstance(config, dict) and config.get("enabled", True)
            }
            submissions = data.get("submissions", [])
            pending_jobs = [
                (index, job)
                for index, job in enumerate(data.get("judge_queue_jobs", []))
                if job.get("status") == "pending"
                and str(job.get("language") or "").lower() in enabled_languages
                and (not supported_languages or str(job.get("language") or "").lower() in supported_languages)
            ]
            pending_jobs.sort(
                key=lambda pair: (
                    -int(pair[1].get("priority", 0) or 0),
                    str(pair[1].get("created_at", "")),
                )
            )
            for _, job in pending_jobs:
                item = next((submission for submission in submissions if submission.get("id") == job.get("submission_id")), None)
                if not item:
                    continue
                if item.get("status") != "queued":
                    continue
                if item.get("problem_type") != "code":
                    continue
                item["status"] = "judging"
                item["message"] = f"已由评测 worker {worker_id} 拉取，等待沙箱执行。"
                item["judged_at"] = None
                item.setdefault("details", [])
                item["queue_job_id"] = job.get("id")
                job["status"] = "leased"
                job["assigned_node_id"] = worker_id
                job["leased_at"] = now().isoformat()
                job["attempts"] = int(job.get("attempts", 0) or 0) + 1
                self._write(data)
                return Submission(**item)

            for item in reversed(data["submissions"]):
                if item.get("status") != "queued":
                    continue
                if item.get("problem_type") != "code":
                    continue
                item_language = str(item.get("language") or "").lower()
                if item_language not in enabled_languages:
                    continue
                if supported_languages and item_language not in supported_languages:
                    continue
                queue_job_id = item.get("queue_job_id")
                if queue_job_id and any(
                    job.get("id") == queue_job_id and job.get("status") != "pending"
                    for job in data.get("judge_queue_jobs", [])
                ):
                    continue
                item["status"] = "judging"
                item["message"] = f"已由评测 worker {worker_id} 拉取，等待沙箱执行。"
                item["judged_at"] = None
                item.setdefault("details", [])
                for job in data.get("judge_queue_jobs", []):
                    if job.get("submission_id") == item.get("id") or job.get("id") == item.get("queue_job_id"):
                        item["queue_job_id"] = job.get("id")
                        job["status"] = "leased"
                        job["assigned_node_id"] = worker_id
                        job["leased_at"] = now().isoformat()
                        job["attempts"] = int(job.get("attempts", 0) or 0) + 1
                        break
                self._write(data)
                return Submission(**item)
        return None

    def list_contests(self) -> list[Contest]:
        return [Contest(**item) for item in self._read()["contests"]]

    def get_contest(self, contest_id: str) -> Contest | None:
        return next((c for c in self.list_contests() if c.id == contest_id), None)

    def add_contest(self, contest: Contest) -> Contest:
        data = self._read()
        data["contests"].insert(0, contest.model_dump(mode="json"))
        self._write(data)
        return contest

    def update_contest(self, contest: Contest) -> Contest:
        data = self._read()
        data["contests"] = [
            contest.model_dump(mode="json") if item.get("id") == contest.id else item
            for item in data["contests"]
        ]
        self._write(data)
        return contest

    def list_clarifications(self) -> list[Clarification]:
        return [Clarification(**item) for item in self._read()["clarifications"]]

    def get_clarification(self, clarification_id: str) -> Clarification | None:
        return next((c for c in self.list_clarifications() if c.id == clarification_id), None)

    def add_clarification(self, clarification: Clarification) -> Clarification:
        data = self._read()
        data["clarifications"].insert(0, clarification.model_dump(mode="json"))
        self._write(data)
        return clarification

    def update_clarification(self, clarification: Clarification) -> Clarification:
        data = self._read()
        data["clarifications"] = [
            clarification.model_dump(mode="json") if item["id"] == clarification.id else item
            for item in data["clarifications"]
        ]
        self._write(data)
        return clarification

    def list_contest_balloons(self, contest_id: str | None = None) -> list[dict[str, Any]]:
        balloons = [dict(item) for item in self._read().get("contest_balloons", [])]
        if contest_id:
            balloons = [item for item in balloons if str(item.get("contest_id") or "") == contest_id]
        return balloons

    def upsert_contest_balloon(self, balloon: dict[str, Any]) -> dict[str, Any]:
        data = self._read()
        balloons = [
            item
            for item in data.get("contest_balloons", [])
            if not (
                str(item.get("contest_id") or "") == str(balloon.get("contest_id") or "")
                and str(item.get("user_id") or "") == str(balloon.get("user_id") or "")
                and str(item.get("problem_id") or "") == str(balloon.get("problem_id") or "")
            )
        ]
        balloons.append(dict(balloon))
        data["contest_balloons"] = balloons
        self._write(data)
        return dict(balloon)

    def delete_contest_balloon(self, contest_id: str, user_id: str, problem_id: str) -> None:
        data = self._read()
        data["contest_balloons"] = [
            item
            for item in data.get("contest_balloons", [])
            if not (
                str(item.get("contest_id") or "") == str(contest_id or "")
                and str(item.get("user_id") or "") == str(user_id or "")
                and str(item.get("problem_id") or "") == str(problem_id or "")
            )
        ]
        self._write(data)

    def list_judge_nodes(self) -> list[JudgeNode]:
        return [JudgeNode(**item) for item in self._read()["judge_nodes"]]

    def update_judge_node(self, judge_node: JudgeNode) -> JudgeNode:
        data = self._read()
        item = judge_node.model_dump(mode="json")
        updated = False
        nodes = []
        for existing in data["judge_nodes"]:
            if existing.get("id") == judge_node.id:
                nodes.append(item)
                updated = True
            else:
                nodes.append(existing)
        if not updated:
            nodes.append(item)
        data["judge_nodes"] = nodes
        self._write(data)
        return judge_node

    def list_audit_logs(
        self,
        *,
        actor_id: str | None = None,
        action: str | None = None,
        resource: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        logs = [AuditLog(**item) for item in self._read()["audit_logs"]]
        logs.sort(key=lambda item: _as_utc(item.created_at) or item.created_at, reverse=True)
        created_from = _as_utc(created_from)
        created_to = _as_utc(created_to)
        if actor_id:
            logs = [item for item in logs if item.actor_id == actor_id]
        if action:
            logs = [item for item in logs if item.action == action]
        if resource:
            logs = [item for item in logs if resource in item.resource]
        if created_from:
            logs = [item for item in logs if (_as_utc(item.created_at) or item.created_at) >= created_from]
        if created_to:
            logs = [item for item in logs if (_as_utc(item.created_at) or item.created_at) <= created_to]
        total = len(logs)
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        return logs[offset : offset + limit], total

    def list_problem_sets(self) -> list[ProblemSet]:
        return [ProblemSet(**item) for item in self._read()["problem_sets"]]

    def get_problem_set(self, problem_set_id: str) -> ProblemSet | None:
        return next((p for p in self.list_problem_sets() if p.id == problem_set_id), None)

    def add_problem_set(self, problem_set: ProblemSet) -> ProblemSet:
        data = self._read()
        data["problem_sets"].insert(0, problem_set.model_dump(mode="json"))
        self._write(data)
        return problem_set

    def update_problem_set(self, problem_set: ProblemSet) -> ProblemSet:
        data = self._read()
        data["problem_sets"] = [
            problem_set.model_dump(mode="json") if item["id"] == problem_set.id else item
            for item in data["problem_sets"]
        ]
        self._write(data)
        return problem_set

    def list_assignments(self) -> list[Assignment]:
        return [Assignment(**item) for item in self._read()["assignments"]]

    def add_assignment(self, assignment: Assignment) -> Assignment:
        data = self._read()
        data["assignments"].insert(0, assignment.model_dump(mode="json"))
        self._write(data)
        return assignment

    def list_teams(self) -> list[Team]:
        return [Team(**item) for item in self._read()["teams"]]

    def add_team(self, team: Team) -> Team:
        data = self._read()
        data["teams"].insert(0, team.model_dump(mode="json"))
        self._write(data)
        return team

    def list_discussions(self) -> list[Discussion]:
        return [Discussion(**item) for item in self._read()["discussions"]]

    def get_discussion(self, discussion_id: str) -> Discussion | None:
        return next((d for d in self.list_discussions() if d.id == discussion_id), None)

    def add_discussion(self, discussion: Discussion) -> Discussion:
        data = self._read()
        data["discussions"].insert(0, discussion.model_dump(mode="json"))
        self._write(data)
        return discussion

    def update_discussion(self, discussion: Discussion) -> Discussion:
        data = self._read()
        data["discussions"] = [
            discussion.model_dump(mode="json") if item["id"] == discussion.id else item
            for item in data["discussions"]
        ]
        self._write(data)
        return discussion

    def list_notifications(self, user_id: str) -> list[Notification]:
        return [Notification(**item) for item in self._read()["notifications"] if item["user_id"] == user_id]

    def add_notification(self, notification: Notification) -> Notification:
        data = self._read()
        data["notifications"].insert(0, notification.model_dump(mode="json"))
        self._write(data)
        return notification

    def mark_notification_read(self, notification_id: str, user_id: str) -> Notification | None:
        data = self._read()
        target: Notification | None = None
        for item in data["notifications"]:
            if item["id"] == notification_id and item["user_id"] == user_id:
                item["is_read"] = True
                target = Notification(**item)
                break
        self._write(data)
        return target

    def get_system_config(self) -> dict[str, Any]:
        return self._read()["system_config"]

    def update_system_config(self, config: dict[str, Any]) -> dict[str, Any]:
        data = self._read()
        data["system_config"] = {**data.get("system_config", {}), **config}
        self._write(data)
        return data["system_config"]

    def add_audit(
        self,
        actor_id: str | None,
        action: str,
        resource: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        data = self._read()
        data["audit_logs"].insert(
            0,
            AuditLog(
                id=f"log-{uuid4().hex[:10]}",
                actor_id=actor_id,
                action=action,
                resource=resource,
                created_at=now(),
                metadata=metadata or {},
            ).model_dump(mode="json"),
        )
        self._write(data)

    def list_offline_packs(self) -> list[OfflinePackRecord]:
        return [OfflinePackRecord(**item) for item in self._read().get("offline_packs", [])]

    def get_offline_pack(self, pack_id: str) -> OfflinePackRecord | None:
        return next((item for item in self.list_offline_packs() if item.pack_id == pack_id), None)

    def add_offline_pack(self, pack: OfflinePackRecord) -> OfflinePackRecord:
        data = self._read()
        packs = data.setdefault("offline_packs", [])
        packs = [item for item in packs if item.get("pack_id") != pack.pack_id]
        packs.append(pack.model_dump(mode="json"))
        data["offline_packs"] = packs
        self._write(data)
        return pack

    def update_offline_pack(self, pack: OfflinePackRecord) -> OfflinePackRecord:
        return self.add_offline_pack(pack)


_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store

