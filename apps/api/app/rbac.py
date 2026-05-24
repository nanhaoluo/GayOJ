from __future__ import annotations

from typing import TypedDict

from .models import Role


class PermissionDef(TypedDict):
    code: str
    description: str
    category: str


class RoleDef(TypedDict):
    code: Role
    name: str
    description: str


ROLES: list[RoleDef] = [
    {"code": "student", "name": "Student", "description": "Only participant role for contests, submissions, and training"},
    {"code": "coach", "name": "Coach", "description": "Manage training content, teams, and assignments without participating"},
    {"code": "judge", "name": "Judge", "description": "Monitor contests and override judging outcomes without participating"},
    {"code": "admin", "name": "Admin + Judge", "description": "Operate the instance with merged judge authority"},
]

PERMISSIONS: list[PermissionDef] = [
    {"code": "problem:read", "description": "Browse public problems", "category": "problem"},
    {"code": "problem:create", "description": "Create problems", "category": "problem"},
    {"code": "problem:edit:own", "description": "Edit own problems", "category": "problem"},
    {"code": "problem:edit:all", "description": "Edit all problems", "category": "problem"},
    {"code": "tag:manage", "description": "Manage problem tags and knowledge hierarchy", "category": "problem"},
    {"code": "problem_set:create", "description": "Create problem sets and exams", "category": "problem_set"},
    {"code": "problem_set:edit:own", "description": "Edit owned problem sets and exams", "category": "problem_set"},
    {"code": "problem_set:edit:all", "description": "Edit all problem sets and exams", "category": "problem_set"},
    {"code": "submission:create", "description": "Submit code or objective answers", "category": "submission"},
    {"code": "submission:read:own", "description": "Read own submissions", "category": "submission"},
    {"code": "submission:read:all", "description": "Read all submissions", "category": "submission"},
    {"code": "submission:override", "description": "Manually override submission results", "category": "submission"},
    {"code": "training:offline", "description": "Download objective-only offline training packs", "category": "training"},
    {"code": "contest:join", "description": "Join public contests", "category": "contest"},
    {"code": "contest:manage", "description": "Create and manage contests", "category": "contest"},
    {"code": "clarification:create", "description": "Ask contest clarifications", "category": "contest"},
    {"code": "clarification:read:all", "description": "Read all contest clarifications", "category": "contest"},
    {"code": "clarification:reply", "description": "Reply to contest clarifications", "category": "contest"},
    {"code": "team:manage", "description": "Manage teams and assignments", "category": "team"},
    {"code": "assignment:manage", "description": "Create and manage assignments", "category": "team"},
    {"code": "analytics:read", "description": "Read coach analytics", "category": "analytics"},
    {"code": "discussion:write", "description": "Create discussion posts and replies", "category": "discussion"},
    {"code": "notification:read", "description": "Read own notifications", "category": "notification"},
    {"code": "judge:monitor", "description": "Read judge queue monitor", "category": "judge"},
    {"code": "judge_node:manage", "description": "Manage judge nodes", "category": "judge"},
    {"code": "user:read", "description": "Read user administration lists", "category": "user"},
    {"code": "user:ban", "description": "Ban or unban users", "category": "user"},
    {"code": "user:role:update", "description": "Assign platform roles to users", "category": "user"},
    {"code": "audit:read", "description": "Read audit logs", "category": "system"},
    {"code": "rbac:read", "description": "Read RBAC permission matrix", "category": "system"},
    {"code": "system:config", "description": "Read and update system configuration", "category": "system"},
    {"code": "backup:manage", "description": "Run backup and restore operations", "category": "system"},
]

_PERMISSION_CODES = {permission["code"] for permission in PERMISSIONS}

ROLE_PERMISSIONS: dict[Role, set[str]] = {
    "student": {
        "problem:read",
        "submission:create",
        "submission:read:own",
        "training:offline",
        "contest:join",
        "clarification:create",
        "discussion:write",
        "notification:read",
    },
    "coach": {
        "problem:read",
        "submission:read:own",
        "submission:read:all",
        "problem:create",
        "problem:edit:own",
        "tag:manage",
        "problem_set:create",
        "problem_set:edit:own",
        "contest:manage",
        "team:manage",
        "assignment:manage",
        "analytics:read",
        "discussion:write",
        "notification:read",
    },
    "judge": {
        "problem:read",
        "submission:read:own",
        "submission:read:all",
        "problem:create",
        "problem:edit:own",
        "problem:edit:all",
        "tag:manage",
        "problem_set:create",
        "problem_set:edit:own",
        "contest:manage",
        "submission:override",
        "clarification:read:all",
        "clarification:reply",
        "discussion:write",
        "notification:read",
        "judge:monitor",
    },
    "admin": {
        permission["code"]
        for permission in PERMISSIONS
        if permission["code"] not in {"submission:create", "training:offline", "contest:join", "clarification:create"}
    },
}


def _validate_role_permissions() -> None:
    for role, permissions in ROLE_PERMISSIONS.items():
        unknown = permissions - _PERMISSION_CODES
        if unknown:
            raise RuntimeError(f"Unknown permissions for {role}: {sorted(unknown)}")


_validate_role_permissions()


def permission_codes_for_role(role: Role) -> list[str]:
    return [permission["code"] for permission in PERMISSIONS if permission["code"] in ROLE_PERMISSIONS[role]]


def role_has_permission(role: Role, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def role_has_permissions(role: Role, permissions: tuple[str, ...]) -> bool:
    allowed = ROLE_PERMISSIONS.get(role, set())
    return all(permission in allowed for permission in permissions)


def role_permission_matrix() -> dict[str, object]:
    permission_codes = [permission["code"] for permission in PERMISSIONS]
    role_rows = []
    matrix: dict[str, dict[str, bool]] = {}

    for role in ROLES:
        role_code = role["code"]
        allowed = ROLE_PERMISSIONS[role_code]
        matrix[role_code] = {permission: permission in allowed for permission in permission_codes}
        role_rows.append(
            {
                **role,
                "permissions": permission_codes_for_role(role_code),
            }
        )

    return {
        "roles": role_rows,
        "permissions": PERMISSIONS,
        "matrix": matrix,
    }

