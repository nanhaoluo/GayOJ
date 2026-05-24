# gayoj PostgreSQL Migrations

P1-02 adds versioned PostgreSQL migrations while keeping the current JSON
repository as the local runtime source of truth.

## Run

Set a PostgreSQL connection string, then apply migrations in order:

```powershell
$env:GAYOJ_DATABASE_URL="postgresql://gayoj:gayoj@127.0.0.1:5432/gayoj"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/db-migrate.ps1
```

The migration files are idempotent: each file creates objects with
`IF NOT EXISTS` and records its version in `schema_migrations`.

## Scope

- `migrations/versions/0001_initial_schema.sql` initializes an empty gayoj
  PostgreSQL database with the MVP tables.
- Public problem fields live in `problems`.
- Objective answer rules live in `problem_judge_config`, not in the public
  problem table.
- Code submission source may be stored as submission data, but migrations do
  not compile or run user code.
- Existing `apps/api/storage/dev-db.json` is unchanged and remains compatible.

## P1-03 RBAC

`0002_rbac_tables.sql` adds:

- `roles`
- `permissions`
- `role_permissions`
- `user_roles`
- `role_permission_matrix`

The migration seeds the four MVP roles (`student`, `coach`, `judge`, `admin`),
the documented permission codes, and backfills `user_roles` from the legacy
`users.role` column. The legacy column is intentionally kept until the runtime
database adapter and role assignment flows are implemented.

## P1-04 JSON snapshot import

After running the schema migrations, export the current development JSON
snapshot to PostgreSQL SQL:

```powershell
npm run export:dev-db-sql -- --input apps/api/storage/dev-db.json --output runtime-logs/dev-db-import.sql
```

Then apply it with `psql`:

```powershell
psql $env:GAYOJ_DATABASE_URL -v ON_ERROR_STOP=1 -f runtime-logs/dev-db-import.sql
```

The export is idempotent and targets the existing core business tables:

- `users` plus `user_roles`
- `problems` and `problem_judge_config`
- `contests`, `submissions`, and `clarifications`
- judge nodes, audit logs, problem sets, teams, assignments, discussions,
  notifications, and system configuration

The generated SQL keeps objective judge rules out of `problems`. Submission
`source_code` is copied as text data only; the export script never executes,
compiles, or judges submitted code.

## P1-05 judge-config isolation in JSON mode

The local JSON repository now mirrors the database boundary:

- Public problem rows are stored without `judge_config`.
- Objective and code judge rules are stored under top-level
  `problem_judge_config`.
- Existing JSON files with embedded `problems[*].judge_config` are migrated
  automatically on read.
- The SQL export reads both the new isolated section and legacy embedded
  values, so historical snapshots remain importable.

## P1-06 audit log persistence

`0003_audit_log_query_indexes.sql` adds indexes for the admin audit-log query
API on the existing `audit_logs` table:

- `actor_id, created_at`
- `action, created_at`
- `resource, created_at`

The JSON development store keeps audit events in `audit_logs`, and the SQL
export continues to import that section into PostgreSQL. The API exposes the
logs only through `GET /api/v1/admin/audit-logs`, guarded by the admin role.

## P2-03 authentication security

`0005_auth_security_fields.sql` adds login security state to `users`:

- `failed_login_attempts`
- `locked_until`
- `last_login_at`
- `password_changed_at`

It also seeds password-policy and lockout defaults into `system_config`. The
runtime JSON repository migrates missing fields on read, and the SQL export
preserves those fields when importing a development snapshot.

