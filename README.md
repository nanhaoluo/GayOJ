# gayoj

## Backend tests

Install the API dependencies, then run the backend check:

```powershell
py -3.12 -m pip install -r apps/api/requirements.txt
npm run check:api
```

`npm run check:api` compiles `apps/api`, `apps/judge`, and `tools/offline-cli`, then runs `py -3.12 -m pytest`.
The pytest suite uses a temporary JSON store, so it does not modify `apps/api/storage/dev-db.json`.

## Frontend type checks

Run the Vue 3 + TypeScript type check with:

```powershell
npm run typecheck
```

This runs `vue-tsc` against `apps/web/tsconfig.json` without emitting build artifacts.

Check the Markdown/LaTeX problem statement renderer with:

```powershell
npm run smoke:web-renderer
```

The smoke renders headings, tables, fenced code blocks, inline/block KaTeX
formulas, and verifies raw HTML is escaped before it can appear in public
problem statements.

## API smoke test

Start the API service, then run the regression smoke script:

```powershell
npm run dev:api
npm run smoke:api
```

The script uses `http://127.0.0.1:8000/api/v1` by default. Override the target with:

```powershell
$env:GAYOJ_API_BASE="http://127.0.0.1:8000/api/v1"
$env:GAYOJ_HEALTH_URL="http://127.0.0.1:8000/health"
npm run smoke:api
```

It covers login, problem browsing, public problem-detail answer isolation, objective submission, code-submission queue flow, problem sets, notifications, and banned-account enforcement.

## Judge worker smoke test

P4-02 adds an independent judge worker entrypoint that can claim queued code submissions from the JSON development queue:

```powershell
npm run smoke:judge-worker
```

The smoke test uses a temporary JSON store, creates queued code submissions, runs `apps/judge/worker.py --once`, and verifies the default CLI path only moves a task to `judging`. It also exercises `JudgeWorker.execute_once(...)` with an injected sandbox executor to verify worker-side result writeback without requiring Docker. The claim event prints a redacted source reference only; it does not echo submitted code or the `source_code` storage field.

## Compiler configuration management

P4-04 exposes the enabled code-language table at:

```text
GET /api/v1/judge/languages
```

Administrators can inspect and update compiler presets through:

```text
GET /api/v1/admin/compiler-configs
PUT /api/v1/admin/compiler-configs/{code}
```

The Web admin console uses the same API to manage the seeded C/C++/Java/Python presets. Public problem detail responses still omit `judge_config`, and code submissions remain queue-only through the online judge path.

## Data repository layer

P1-01 introduces a repository boundary under `apps/api/app/db`:

- `repository.py` defines the API storage contract used by routes and auth.
- `json_repository.py` adapts the existing JSON file store for local development.
- `get_repository()` is the FastAPI dependency to override in tests or future database adapters.

The current implementation still persists to `apps/api/storage/dev-db.json` and does not change that file format. Existing development data remains compatible, while later PostgreSQL work can add a SQLAlchemy/SQLModel adapter behind the same contract.

## PostgreSQL migrations

P1-02 adds versioned PostgreSQL migrations in `migrations/versions`.

Check the migration files without a running database:

```powershell
npm run check:migrations
```

Apply migrations to an empty PostgreSQL database with `psql`:

```powershell
$env:GAYOJ_DATABASE_URL="postgresql://gayoj:gayoj@127.0.0.1:5432/gayoj"
npm run migrate:db
```

The first migration initializes the MVP tables and keeps objective `judge_config` in `problem_judge_config`, separate from the public `problems` table. Runtime still uses the JSON repository until a later database adapter is introduced.

P1-03 adds RBAC tables and a queryable role-permission matrix:

- `roles`
- `permissions`
- `role_permissions`
- `user_roles`
- `role_permission_matrix` view

Admins can inspect the current runtime matrix through:

```text
GET /api/v1/admin/rbac/matrix
```

The endpoint uses the same role matrix that seeds the PostgreSQL migration and does not expose objective answers or execute code submissions.

P1-04 adds a repeatable export path for importing the current JSON snapshot into
the migrated PostgreSQL schema:

```powershell
npm run export:dev-db-sql -- --input apps/api/storage/dev-db.json --output runtime-logs/dev-db-import.sql
```

Apply the generated SQL after `npm run migrate:db`:

```powershell
psql $env:GAYOJ_DATABASE_URL -v ON_ERROR_STOP=1 -f runtime-logs/dev-db-import.sql
```

The generated SQL writes public problem fields to `problems`, objective
rules to `problem_judge_config`, and submission `source_code` as text data
only. It does not compile, run, or judge submitted code.

P1-05 applies the same judge-config isolation to the JSON development store.
Existing snapshots with `judge_config` embedded in `problems` are migrated on
read into top-level `problem_judge_config`, while public problem rows are kept
answer-free. API routes that need rules use the repository methods
`get_problem_judge_config()` / `set_problem_judge_config()`; ordinary problem
detail responses still omit `judge_config`, and authorized offline packs remain
signed objective-only payloads.

P1-06 persists and exposes audit logs through an admin-only query API:

```text
GET /api/v1/admin/audit-logs
```

Supported filters are `actor_id`, `action`, `resource`, `created_from`,
`created_to`, `limit`, and `offset`. The JSON development store keeps the
existing top-level `audit_logs` section, and PostgreSQL migration `0003` adds
query indexes for the same access pattern. Failed login attempts are audited
without storing submitted passwords.

## P02-01 Permission-code enforcement

P02-01 makes permission codes the runtime authorization model. Login and
`GET /api/v1/auth/me` return the user's granted `permissions`, derived from the
role-permission matrix in `apps/api/app/rbac.py`.

Protected APIs now use permission dependencies such as `problem:create`,
`submission:read:all`, `submission:override`, `judge:monitor`, `audit:read`,
`rbac:read`, and `system:config` instead of hard-coded role lists. Resource
ownership checks still apply where needed, so a user with only
`submission:read:own` cannot read another user's submission.

PostgreSQL migration `0004_permission_code_enforcement.sql` extends the seeded
permission grants for the same model. The JSON development store format is
unchanged and remains compatible with `apps/api/storage/dev-db.json`.

Ordinary problem-detail responses do not include `judge_config`, even for
manager roles. Objective judging rules remain available only to server-side
judging and authorized objective-only offline training packs.

## P02-02 Role management UI

Admins can assign platform roles from the Web admin console and through:

```text
PATCH /api/v1/admin/users/{user_id}/role
```

The endpoint requires `user:role:update`, returns the updated public user with
derived `permissions`, audits changes as `user.role.update`, and rejects changes
that would remove the last active administrator. JSON development storage still
uses the existing `users[*].role` field, so current `apps/api/storage/dev-db.json`
snapshots remain compatible.

The admin page also shows the RBAC matrix from `GET /api/v1/admin/rbac/matrix`.
This UI only manages roles and permissions; it does not expose objective
`judge_config` and does not run or judge code submissions locally.

## P2-03 Password policy and login logs

P2-03 adds persistent login security state to user records:
`failed_login_attempts`, `locked_until`, `last_login_at`, and
`password_changed_at`. Existing JSON snapshots are migrated on read.

Repeated failed logins are audited as `auth.login_failed`; once the configured
threshold is reached, the account is temporarily locked and an
`auth.login_locked` event is recorded. Audit metadata includes the username,
client host, user agent, failure reason, and counter state, but never stores the
submitted password.

Password and lockout defaults live in `/api/v1/system/config`:
`password_min_length`, `password_require_letter`, `password_require_digit`,
`login_max_failed_attempts`, and `login_lockout_minutes`. Authenticated users
can change their own password from `/settings` or through:

```text
PUT /api/v1/users/me/password
```

PostgreSQL migration `0005_auth_security_fields.sql` mirrors the JSON runtime
fields and seeds the same default policy keys.

The admin Web console exposes the same password policy and lockout fields, so
P2 account-security behavior is managed from the same surface as roles and bans.

## P2-04 User profile settings

Authenticated users can manage their own profile through:

```text
GET /api/v1/users/me/profile
PATCH /api/v1/users/me/profile
```

The Web route `/settings` updates `display_name`, `school`, `email`, and the
current user's password. The private `email` field is returned only by the
profile endpoint; `/api/v1/auth/me` and public/admin user lists keep the public
user shape. Updates are audited as `user.profile.update` and reuse existing user
fields, so the JSON development store remains compatible with current
`apps/api/storage/dev-db.json` snapshots.

## P2-05 Account ban enforcement

Admins can ban or unban users through:

```text
PATCH /api/v1/admin/users/{user_id}/ban?disabled=true|false
```

Disabled users cannot log in. Tokens issued before the ban are rejected by the
shared authenticated-user dependency before submissions, offline-pack download,
offline-result sync, notifications, discussions, or other protected actions can
run. The API also rejects banning the last active administrator. Public problem
pages still stay answer-free and code submissions remain on the online judge
queue path; the API, Web, and CLI do not execute or locally judge code.

## P3-01 Problem CRUD management

Problem managers can use the Web route:

```text
/admin/problems
```

The page calls the management-only API surface:

```text
GET    /api/v1/admin/problems
POST   /api/v1/admin/problems
GET    /api/v1/admin/problems/{problem_id}
PUT    /api/v1/admin/problems/{problem_id}
DELETE /api/v1/admin/problems/{problem_id}
```

Coaches can create and edit their own problems; judges and admins can manage all
problems. The form supports code, blank, single-choice, and multiple-choice
problem types. Deleting a problem is a soft delete through `visible=false`, so
existing submissions and historical JSON data remain compatible.

Objective `judge_config` is returned only by the management endpoints and the
authorized signed offline pack. Ordinary problem detail, problem-set, and contest
responses still omit answers. Code problems continue to be submitted only to the
online judge queue path and are not executed by API, Web, or CLI.

## P3-02 Markdown and LaTeX rendering

Problem detail pages render public `statement`, `input_format`, `output_format`,
and choice-option text through a shared Markdown renderer. The renderer supports
tables, fenced code blocks with highlighting, inline math such as `$a_i$`, and
display math with `$$...$$` or `\[...\]`.

Raw HTML remains disabled and escaped, so ordinary problem-detail content cannot
inject scripts. This is a frontend-only rendering change: the API response shape
and `judge_config` isolation are unchanged.

## P3-03 Tags and knowledge hierarchy

The public tag tree is available at:

```text
GET /api/v1/tags
```

Problem managers can use `/admin/tags` or the management API to create, update,
and delete unused knowledge tags:

```text
GET    /api/v1/admin/tags
POST   /api/v1/admin/tags
PUT    /api/v1/admin/tags/{tag_id}
DELETE /api/v1/admin/tags/{tag_id}
```

`GET /api/v1/problems` supports multi-tag AND filters with repeated `tag`
parameters or comma-separated `tags`. Existing JSON snapshots remain compatible:
missing top-level `tags` are backfilled from `problems[*].tags` on read. Public
problem responses still omit `judge_config`, and code submissions stay queue-only.

## P3-04 Code test data upload

Problem managers can upload and download code-problem test data from the same
`/admin/problems` Web surface:

```text
GET  /api/v1/admin/problems/{problem_id}/testdata
POST /api/v1/admin/problems/{problem_id}/testdata
GET  /api/v1/admin/problems/{problem_id}/testdata/download
```

Uploads must be ZIP archives with at least one matching input/output pair such
as `1.in` and `1.out`. The API rejects path traversal, encrypted entries,
oversized archives, and ZIPs without case pairs. Metadata is stored in
`problem_test_data`, and the archive bytes are written through the object storage
adapter: local files by default, with a MinIO-compatible backend available by
configuration.

The upload path only stores test data and updates code-problem worker metadata
such as `testdata_ref`. It does not compile, run, or judge submitted code. Public
problem detail responses still omit both `judge_config` and test-data metadata.

## P3-05 Problem version control

Problem edits now archive the previous management snapshot before it is changed:

```text
GET  /api/v1/admin/problems/{problem_id}/versions
POST /api/v1/admin/problems/{problem_id}/versions/{version_id}/restore
```

The Web route `/admin/problems` shows version history and lets authorized problem
managers roll a problem back. Version snapshots are management-only records; they
may include objective `judge_config`, but ordinary problem detail, problem-set,
contest, and CLI payloads remain answer-free. Restoring a version archives the
current state first, so rollback actions are themselves reversible.

## P3-06 Problem import and export

Problem managers can move batches through the management-only package APIs:

```text
GET  /api/v1/admin/problems/export?format=hydro|qdu|fps&ids=P1003,P1004
POST /api/v1/admin/problems/import
```

Exports support Hydro-style JSON, QDU-style JSON, and FPS XML. Imports validate
the whole batch before writing; if any item is invalid, no problem rows or
`problem_judge_config` entries are committed. Duplicate IDs can be imported as
new copies, overwritten when the user can edit the target problem, or skipped.

These packages are management artifacts and may contain objective
`judge_config`. Ordinary problem detail, problem-set, contest, and CLI payloads
continue to omit it. Code-problem package data is stored only as online worker
metadata; API, Web, and CLI still do not compile, run, or locally judge code.

## P4-01 Judge queue abstraction

Code submissions now create a `judge_queue_jobs` task alongside the `queued`
submission. The task protocol stores `submission_id`, `problem_id`, `language`,
`source_ref`, `source_sha256`, resource limits, and `testdata_ref`; it does not
copy submitted source into the queue payload. Old JSON snapshots are migrated on
read by deriving queue jobs for existing queued or judging code submissions.

The default local backend is `json`. `GAYOJ_JUDGE_QUEUE_BACKEND=redis|kafka`
selects the optional publishing adapters while preserving the same repository
metadata for monitor and worker compatibility. Missing or unavailable external
brokers fail the code-submit request with 503 instead of silently pretending the
job was published; the API also rolls back the local submission and queue-job
metadata, or restores the previous submission/job when a rejudge enqueue fails.

## P4-02 Judge worker service

`apps/judge/worker.py` is the queue-facing worker entrypoint. It registers a
judge node heartbeat, leases a pending JSON queue job for a supported language,
and moves the matching code submission from `queued` to `judging`.

By default this entrypoint is claim-only: it returns task metadata such as
`source_ref`, limits, and `testdata_ref`, but it does not compile, run, or
locally judge user code. Starting it with `--execute` runs the claimed task
through the worker-side Docker sandbox and writes the final result back to the
submission and queue job. Existing `apps/api/storage/dev-db.json` snapshots
remain compatible because the implementation reuses `submissions`,
`judge_queue_jobs`, and `judge_nodes`.

## P4-03 Docker sandbox executor

`apps/judge/gayoj_judge/sandbox.py` provides the worker-side Docker executor for
code submissions. It writes source only into a temporary directory, runs compile
and test commands through `docker run`, and enforces the minimum sandbox
contract: `--network none`, memory/swap limits, process limit, read-only root
filesystem, dropped capabilities, `no-new-privileges`, non-root UID, and a
container-side timeout.

Build the runner image with:

```powershell
npm run build:judge-runner
```

Run the sandbox smoke in dry-run mode with:

```powershell
npm run smoke:judge-sandbox
```

Dry-run validates the Docker command contract without executing user code or
requiring Docker on the host. Set `GAYOJ_JUDGE_RUN_DOCKER_SMOKE=1` to execute a
small Python case inside Docker after the runner image has been built.

## P4-05 Judge worker result aggregation

`apps/judge/gayoj_judge` contains the worker-side test-point runner contract for
code submissions. The API still only creates `queued` code submissions and queue
jobs; a separate judge worker calls `judge_submission(...)`, runs an injected
sandbox executor, aggregates per-test-point details, and writes back
`AC/WA/CE/TLE/MLE/RE` style statuses. Worker-side failures are converted into
structured `system_error` results so leased jobs do not stay stuck indefinitely.

The worker accepts hidden test cases from management-only code `judge_config`
through `test_cases` (falling back to public samples for local smoke tests). It
does not expose `judge_config` through ordinary problem APIs, and public
submission details do not include hidden input or expected-output previews. The
`DockerSandboxPointExecutor` adapter can feed the existing Docker sandbox into
the P4-05 aggregator; production-grade language-version policy and external
Redis/Kafka worker consumption remain separate integration work.

## P4-06 Judge node heartbeat and scheduling

Judge workers register and refresh node state through:

```text
POST /api/v1/judge/nodes/heartbeat
POST /api/v1/judge/nodes/{node_id}/claim
PATCH /api/v1/admin/judge-nodes/{node_id}
```

Heartbeat requests are authenticated with `X-Judge-Node-Token`, update
`judge_nodes` with supported languages, queue depth, load, and heartbeat time,
and automatically report stale online/draining nodes as `offline` after the
configured TTL. The claim endpoint leases a pending code queue job to an online
node that supports the submission language, moves the submission to `judging`,
and leaves `judged_at` plus test details empty until the separate worker writes
the real result.

The judge console now shows queue backend/depth/pending/leased jobs, and the
admin console shows node heartbeat, load, language support, and status controls.
These APIs only schedule work; they do not compile, run, or locally judge user
code in the API, Web, or offline CLI.

## P4-07 Manual and batch rejudge

Judges and admins can requeue code submissions without running user code in the
API process:

```text
POST /api/v1/judge/submissions/{submission_id}/rejudge
POST /api/v1/judge/submissions/rejudge
```

The single-submission endpoint resets a code submission to `queued`, clears old
judge details, creates a fresh `judge_queue_jobs` entry, audits the action, and
notifies the submitter. The batch endpoint accepts explicit `submission_ids` or
filters such as `problem_id`, `contest_id`, and `statuses`; non-code or missing
submissions are reported as skipped instead of being judged locally.

The Web submissions page exposes the same controls to users with
`submission:override`. Rejudge only places work back on the online judge queue;
API, Web, and the offline CLI still do not compile, run, or locally judge code.

## P5-01 Objective rule tests

The objective rule regression suite lives in
`apps/api/tests/test_p5_objective_rules.py`. It covers blank, single-choice, and
multiple-choice scoring and compares `apps/api/app/services.py::judge_objective`
with `tools/offline-cli/gayoj_offline.py::judge` for the same answer payloads.
It also keeps the explicit code-problem boundary: API objective rules reject
code problems, and the offline CLI remains objective-only.

## P5-02 Blank rule enhancements

Blank problems can now set per-blank rules inside management-only
`judge_config.blank_rules`. Supported `match` values are `exact`, `regex`, and
`numeric`; numeric rules may set a non-negative `tolerance`. The API rule engine
and offline CLI share the same behavior, while ordinary problem detail responses
still omit `judge_config`.

## P5-03 Problem-set offline packages

Students can download an objective-only offline package for a specific public
problem set from `GET /api/v1/problem-sets/{problem_set_id}/offline-package`.
The package keeps the existing signed offline-pack format, filters out code
problems, and includes `judge_config` only inside the authorized offline payload.
The offline CLI supports both `download --problem-set-id <id>` and
`pull-set <id>` for this flow.

## P5-04 Offline package expiry and signature checks

Offline packages now include `signature_algorithm: hmac-sha256` and an
`expires_at` timestamp. The signature covers the full payload, including the
expiry metadata, so changing problem content, answers, or expiry invalidates the
package. The offline CLI verifies the HMAC signature and rejects expired packs
before any local objective practice starts.

## P5-05 Offline result sync idempotency

Offline practice results now carry a stable `client_result_key`. The API stores
that key as `submission.offline_result_key`; resubmitting the same local result
returns it in `merged` instead of creating another submission. If the same key is
sent with different problem data or answers, the row is rejected as a conflict.
Legacy result files without a key are still accepted through a deterministic
fallback key derived from problem id, answers, and `practiced_at`.

## OpenAPI export

Export the current FastAPI schema to `api/openapi.json`:

```powershell
npm run export:openapi
```

Check that the committed export still matches the live FastAPI app schema:

```powershell
npm run check:openapi
```

The API service also exposes the same schema at `http://127.0.0.1:8000/api/openapi.json`.

## Environment configuration

Create a local environment file from the checked-in example:

```powershell
Copy-Item .env.example .env
```

Local npm scripts read the same variable names used by Docker Compose. Useful keys:

| Variable | Default | Purpose |
| --- | --- | --- |
| `GAYOJ_API_HOST` | `127.0.0.1` | Local FastAPI bind host |
| `GAYOJ_API_PORT` | `8000` | Local FastAPI port |
| `GAYOJ_WEB_HOST` | `127.0.0.1` | Local Vite bind host |
| `GAYOJ_WEB_PORT` | `5173` | Local Vite dev port |
| `VITE_DEV_PROXY_TARGET` | `http://127.0.0.1:8000` | Vite dev proxy target |
| `VITE_API_BASE_URL` | `/api/v1` | Browser API base path |
| `GAYOJ_SECRET_KEY` | dev placeholder | API token signing key |
| `GAYOJ_OFFLINE_PACK_SECRET` | dev placeholder | Offline objective-pack signing key |
| `GAYOJ_OFFLINE_PACK_TTL_HOURS` | `168` | Signed offline-pack lifetime |
| `GAYOJ_API_CORS_ORIGINS` | local web origins | Comma-separated CORS allowlist |
| `GAYOJ_JUDGE_QUEUE_BACKEND` | `json` | Judge queue backend selector: `json`, `redis`, or `kafka` |
| `GAYOJ_JUDGE_QUEUE_TOPIC` | `gayoj.judge.submissions` | Redis list name or Kafka topic for code judge jobs |
| `GAYOJ_REDIS_URL` | empty | Optional Redis URL when using the Redis queue backend |
| `GAYOJ_KAFKA_BOOTSTRAP_SERVERS` | empty | Optional Kafka bootstrap servers when using the Kafka queue backend |
| `GAYOJ_OBJECT_STORAGE_BACKEND` | `local` | Test-data object storage backend: `local` or `minio` |
| `GAYOJ_OBJECT_STORAGE_BUCKET` | `gayoj-testdata` | Bucket name for code test-data ZIP objects |
| `GAYOJ_LOCAL_OBJECT_STORAGE_DIR` | `apps/api/storage/objects` | Local object directory when using the local backend |
| `GAYOJ_MINIO_ENDPOINT` | `127.0.0.1:9000` | MinIO endpoint when using the MinIO backend |
| `GAYOJ_MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key for local development |
| `GAYOJ_MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key for local development |
| `GAYOJ_MINIO_SECURE` | `false` | Use HTTPS for MinIO connections |
| `GAYOJ_TESTDATA_MAX_ARCHIVE_MB` | `50` | Maximum uploaded ZIP size |
| `GAYOJ_TESTDATA_MAX_UNCOMPRESSED_MB` | `200` | Maximum total uncompressed ZIP size |
| `GAYOJ_TESTDATA_MAX_FILES` | `1000` | Maximum number of files inside a test-data ZIP |
| `GAYOJ_DATABASE_URL` | local postgres URL | Target used by migration scripts |
| `GAYOJ_COMPOSE_API_PORT` | `8000` | Docker Compose API host port |
| `GAYOJ_COMPOSE_WEB_PORT` | `8080` | Docker Compose web host port |

For a local PowerShell session, dot-source the loader before starting services if you changed `.env`:

```powershell
. .\scripts\load-env.ps1
npm run dev:api
npm run dev:web
```

For Docker Compose, use the same `.env` file:

```powershell
docker compose --env-file .env -f deploy/docker-compose.yml up --build
```

Compose exposes API at `http://127.0.0.1:${GAYOJ_COMPOSE_API_PORT}` and Web at `http://127.0.0.1:${GAYOJ_COMPOSE_WEB_PORT}`.

## Phase 0 summary

The Phase 0 development summary is tracked in [`docs/p0-development-summary.md`](docs/p0-development-summary.md). It records the P0-01 to P0-05 deliverables, required verification commands, hard security boundaries, and the Ubuntu 24.04 judge-worker compiler/runtime specification for future real online judging work.

基于 `1.md` 落地的 Online Judge MVP。当前版本实现了可运行的 Web 工作台、FastAPI 后端、客观题规则评判、代码题在线评测队列入队、多角色入口和客观题离线训练 CLI。

## 已实现范围

- 用户登录与 RBAC 演示角色：选手、教练、裁判、管理员
- 题库浏览、题目详情、代码题提交、填空题/选择题即时判分
- 提交记录、比赛列表、实时排行榜、全局排行榜
- 教练端训练分析、裁判端提交流与节点监控、管理端用户/节点/审计日志
- 客观题离线训练包下载、签名校验、本地答题与判分
- FastAPI Swagger 文档：`/api/docs`

代码题不会在本机执行用户代码，也不会由 API 进程本地判题。MVP 当前只负责把代码提交写入在线评测队列状态，后续由 P4 的真实 judge worker 回写结果，符合设计文档中“CLI 不执行代码题、本地不判代码题”的边界。

## 本地启动

安装前端依赖：

```powershell
npm install
```

安装后端依赖：

```powershell
py -3.12 -m pip install -r apps/api/requirements.txt
```

启动 API：

```powershell
npm run dev:api
```

另开一个终端启动 Web：

```powershell
npm run dev:web
```

访问：

- Web：`http://127.0.0.1:5173`
- API：`http://127.0.0.1:8000`
- Swagger：`http://127.0.0.1:8000/api/docs`

演示账号密码均为 `gayoj123`：

| 用户名 | 角色 |
| --- | --- |
| `alice` | 选手 |
| `coach` | 教练 |
| `judge` | 裁判 |
| `admin` | 管理员 |

## 离线客观题训练

登录并获取 token：

```powershell
py -3.12 tools/offline-cli/gayoj_offline.py login -u alice -p gayoj123
```

下载离线包：

```powershell
$env:GAYOJ_TOKEN="<上一步输出的 token>"
py -3.12 tools/offline-cli/gayoj_offline.py download -o offline-pack.json
```

按题单下载离线包：

```powershell
py -3.12 tools/offline-cli/gayoj_offline.py pull-set PS1001 -o ps1001-pack.json
```

本地答题：

```powershell
py -3.12 tools/offline-cli/gayoj_offline.py practice offline-pack.json
```

恢复联网后同步本地练习结果：

```powershell
py -3.12 tools/offline-cli/gayoj_offline.py sync-results offline-results.json
```

## 工程结构

```text
apps/
  api/             FastAPI 后端
  judge/           独立代码评测 worker 与 Docker 沙箱执行器
  web/             Vue 3 + TypeScript 前端
tools/
  offline-cli/     客观题离线训练 CLI
deploy/            Docker 与 Compose 配置
docs/              架构与后续路线说明
```

## 后续扩展

- 将文件存储替换为 PostgreSQL 迁移与仓储层
- 接入 Redis 队列，把代码题提交转交真实沙箱评测节点
- 引入 Monaco Editor、WebSocket 排行榜推送和 Prometheus 指标
- 完成题目 CRUD 表单、比赛创建、Clarification 和重测流程

