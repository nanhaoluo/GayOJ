# gayoj MVP 架构说明

本实现按 `1.md` 的模块化单体思路落地，先保证核心训练闭环可运行。

## 分层

- `apps/web`：Vue 3 + TypeScript 单页工作台，对应展示层。
- `apps/api`：FastAPI 业务服务，对应用户、题库、提交、比赛、统计、权限和客观题评判。
- `tools/offline-cli`：客观题离线训练工具，只处理填空题、单选题和多选题。
- `deploy`：开发部署配置。

## 当前边界

- 代码题提交只写入在线评测队列状态，不在 API、Web 或 CLI 本地执行或本地判题。
- 客观题规则由服务端保存，普通题目详情不向选手返回 `judge_config`。
- 离线训练包包含授权客观题规则，并使用 HMAC 签名防篡改。
- 离线 CLI 可保存客观题练习结果，并通过 `/api/v1/offline-results/sync` 恢复联网后同步。
- 本地开发使用 JSON 文件持久化，文件位置为 `apps/api/storage/dev-db.json`。

## P1-01 仓储层

- `apps/api/app/db/repository.py` 定义 API 路由和认证模块使用的仓储协议。
- `apps/api/app/db/json_repository.py` 将现有 JSON `Store` 适配为仓储实现，供本地开发继续使用。
- `apps/api/app/db/get_repository()` 是 FastAPI 依赖入口，测试和后续数据库实现都应覆盖这个入口。
- P1-01 不改变 `apps/api/storage/dev-db.json` 的文件格式，现有开发数据继续兼容。
- 客观题 `judge_config` 仍只在管理端、服务端评判和授权离线包中出现；普通题面接口继续隔离答案。
- 代码题仍只进入在线评测队列路径，API、Web 和 CLI 不编译、不运行、不本地判题。

## P1-02 PostgreSQL 迁移

- `migrations/versions/0001_initial_schema.sql` 可初始化空 PostgreSQL 数据库。
- `schema_migrations` 记录已应用版本，迁移文件按四位版本号排序。
- `problems` 只保存普通题面公开字段；客观题判题规则保存在独立的 `problem_judge_config` 表。
- `scripts/db-migrate.ps1` 通过 `GAYOJ_DATABASE_URL` 和 `psql` 应用迁移。
- `scripts/check-migrations.py` 在无数据库环境下静态校验迁移结构和安全边界。
- 当前运行时仍使用 `apps/api/storage/dev-db.json`，P1-02 不改变 JSON 文件格式。

## P1-03 RBAC 表

- `migrations/versions/0002_rbac_tables.sql` 新增 `roles`、`permissions`、`role_permissions`、`user_roles`。
- 迁移会把旧 `users.role` 回填到 `user_roles`，同时保留 `users.role` 字段以兼容当前 JSON 开发模式。
- `role_permission_matrix` 视图提供数据库侧角色权限矩阵查询能力。
- `apps/api/app/rbac.py` 保存当前运行时角色权限矩阵，供 API 和迁移种子保持一致。
- `GET /api/v1/admin/rbac/matrix` 仅管理员可查询，不改变现有 `require_roles` 粗粒度权限校验。

## P1-04 核心业务表 JSON 导入

- 现有 `0001_initial_schema.sql` 已覆盖题库、提交、比赛、Clarification、题单、队伍、作业、讨论、通知和系统配置等核心表。
- `scripts/export-dev-db-sql.py` 将 `apps/api/storage/dev-db.json` 导出为幂等 PostgreSQL SQL，可在迁移后导入历史开发数据。
- 导入时公开题面字段进入 `problems`，客观题 `judge_config` 进入 `problem_judge_config`，避免普通题面数据携带答案。
- `submissions.source_code` 仅作为文本数据导入；脚本不连接评测队列、不编译、不运行用户代码。
- 运行时仍使用 JSON 仓储，P1-04 只补齐数据库迁移落地前的数据搬迁路径。

## P1-05 客观题判题配置隔离

- JSON 开发存储新增顶层 `problem_judge_config`，与 PostgreSQL `problem_judge_config` 表保持同一边界。
- 旧版 `apps/api/storage/dev-db.json` 中嵌在 `problems[*].judge_config` 的规则会在读取时自动迁出，普通题目行写回后不再包含答案。
- 仓储层提供 `get_problem_judge_config()` / `set_problem_judge_config()`，服务端评判、管理端查看和签名离线包生成通过该接口读取规则。
- 普通题面、题单、比赛题目摘要继续只返回公开字段；CLI 仍只处理填空题、单选题、多选题。

## P1-06 Audit log persistence

- The JSON repository keeps audit events in the existing top-level `audit_logs` section and remains compatible with current `apps/api/storage/dev-db.json` snapshots.
- `GET /api/v1/admin/audit-logs` returns `{ items, total, limit, offset }` and supports `actor_id`, `action`, `resource`, `created_from`, `created_to`, `limit`, and `offset` query parameters.
- Failed login attempts are audited with `auth.login_failed` and never persist the submitted password.
- PostgreSQL migration `0003_audit_log_query_indexes.sql` adds actor/action/resource query indexes on the existing `audit_logs` table.
- The admin console uses the same API to filter and page audit records; ordinary problem detail APIs still do not expose objective `judge_config`, and code submissions remain on the online judge path.

## P02-01 权限码模型

- `apps/api/app/rbac.py` 是运行时权限码来源，角色只映射到权限集合，不再由路由散落硬编码角色白名单。
- `require_permissions()` 以 `problem:create`、`submission:read:all`、`submission:override`、`judge:monitor`、`audit:read`、`rbac:read`、`system:config` 等权限码保护 API。
- `GET /api/v1/auth/me` 和登录响应返回当前用户 `permissions`，供前端判断入口和后续管理 UI 使用。
- 资源归属仍在业务层校验，例如只有 `submission:read:own` 的用户只能读取自己的提交，题单编辑仍区分 owner 与 `problem_set:edit:all`。
- `0004_permission_code_enforcement.sql` 将 P02-01 新增权限码和授权关系补入 PostgreSQL；JSON 开发存储结构不变。
- 普通题面接口即使带管理角色登录也不返回 `judge_config`，客观题规则只在服务端判题和授权离线包内读取。

## P02-02 角色管理 UI

- 管理端页面在用户列表内提供角色选择与保存动作，角色来源于 `GET /api/v1/admin/rbac/matrix`。
- `PATCH /api/v1/admin/users/{user_id}/role` 使用 `user:role:update` 权限码保护，只允许具备权限的管理员分配角色。
- 角色更新仍写入 JSON 用户记录的 `role` 字段，不新增 JSON 存储结构；PostgreSQL 通过 `0006_role_management.sql` 补齐同名权限授权。
- 接口返回公开用户模型和派生 `permissions`，并写入 `user.role.update` 审计日志。
- 后端拒绝移除最后一个未禁用管理员，避免管理入口被全部锁死。
- 该 UI 只展示角色和权限矩阵，不展示客观题 `judge_config`，也不触发任何代码题本地执行。

## P2-03 Password policy and login logs
- Login now persists `failed_login_attempts`, `locked_until`, and `last_login_at` on the user record; existing JSON snapshots receive defaults on read.
- Repeated failed logins lock the account for the configured window and emit `auth.login_failed` plus `auth.login_locked` audit records without storing submitted passwords.
- Password policy settings live in `system_config`: `password_min_length`, `password_require_letter`, `password_require_digit`, `login_max_failed_attempts`, and `login_lockout_minutes`.
- Authenticated users can change their own password through `PUT /api/v1/users/me/password`; new passwords must satisfy the configured policy, and success/failure is audited.
- The admin Web console edits the same password policy and lockout settings, keeping P2 account-security controls on one surface.
- PostgreSQL migration `0005_auth_security_fields.sql` mirrors the JSON runtime fields and default policy keys.

## P2-04 用户资料与设置

- 当前登录用户通过 `GET /api/v1/users/me/profile` 读取个人资料，通过 `PATCH /api/v1/users/me/profile` 更新 `display_name`、`school`、`email`。
- `email` 属于当前用户私有资料，只在个人资料接口返回；`/api/v1/auth/me` 和用户列表仍返回公开用户模型。
- 前端 `/settings` 页面复用现有 Vue 3 工作台结构，保存资料后同步顶栏显示名，并提供当前用户改密入口。
- 更新写入 `user.profile.update` 审计日志，仅记录变更字段名，不写入密码或判题配置。
- 该任务复用现有 user 字段，不新增存储结构，兼容当前 `apps/api/storage/dev-db.json`。

## P2-05 Account ban enforcement

- `disabled` remains the storage-compatible account-ban flag on user records.
- `PATCH /api/v1/admin/users/{user_id}/ban?disabled=true|false` writes the flag and records `user.ban` / `user.unban` audit events with target metadata.
- Banning the last active administrator is rejected, matching role-change protection and preventing full admin lockout.
- Login rejects disabled users, and tokens issued before a ban are rejected by the shared authenticated-user dependency before protected handlers run.
- The protected chain includes code submission queue entry, objective submission, offline training-pack download, offline-result sync, notifications, discussions, coach/judge/admin operations, and `auth/me`.
- Public endpoints that do not require a user still omit objective `judge_config`; CLI remains objective-only and never executes code.

## P3-01 题目 CRUD 完整表单

- 新增 Web 路由 `/admin/problems`，面向具备题目管理权限的教练、裁判和管理员。
- 管理端 API 使用 `/api/v1/admin/problems` 命名空间，普通 `/api/v1/problems/*` 仍只返回公开题面字段。
- 管理端详情可读取和保存 `judge_config`，用于客观题答案配置和后续代码题在线 worker 配置；普通题面、题单和比赛详情继续不泄露答案。
- 表单支持代码题、填空题、单选题和多选题。后端对客观题答案、选项 Key、填空 Key 做结构校验。
- 删除题目采用 `visible=false` 软删除，不移除历史提交，也不要求迁移或重建 `apps/api/storage/dev-db.json`。
- 软删除后的题目不会出现在普通题库、题单、比赛详情、离线包或提交入口中；管理端仍可查看历史条目。
- 代码题保存的配置只作为在线评测 worker 元数据，API、Web 和 CLI 均不编译、不运行、不本地判题。

## P3-02 Markdown + LaTeX 题面渲染

- `ProblemStatementRenderer` 统一渲染公开题面、输入格式、输出格式和选择题选项内容。
- 渲染能力覆盖 Markdown 标题、列表、表格、代码块，以及 KaTeX 行内公式和块级公式。
- 原始 HTML 保持关闭并转义，外部链接自动加 `noopener` 等属性；普通题面接口仍不包含 `judge_config`。
- 本任务只调整前端展示和渲染 smoke test，不修改 API 存储结构，继续兼容 `apps/api/storage/dev-db.json`。

## P3-03 标签与知识点层级

- JSON 开发存储新增顶层 `tags` 标签树；旧 `apps/api/storage/dev-db.json` 若缺少该段，会在读取时由现有 `problems[*].tags` 自动补齐并去重。
- `GET /api/v1/tags` 返回公开知识点树，`GET/POST/PUT/DELETE /api/v1/admin/tags` 使用 `tag:manage` 权限管理层级、父级和排序。
- `GET /api/v1/problems` 支持重复 `tag=...` 和逗号分隔 `tags=...` 多标签 AND 筛选，普通题目摘要和详情仍不返回 `judge_config`。
- Web 题库页提供知识点树多选筛选，题目管理表单可从同一标签树选择标签，并新增 `/admin/tags` 管理页面。
- PostgreSQL 迁移 `0007_problem_tag_hierarchy.sql` 增加 `tags`、`problem_tags` 和 `tag:manage` 授权；JSON 导出脚本会把旧字符串标签转换为关系表数据。

## P3-04 代码题测试数据上传

- 管理端新增 `GET/POST /api/v1/admin/problems/{problem_id}/testdata` 和 `GET /api/v1/admin/problems/{problem_id}/testdata/download`，权限沿用题目编辑权限和所有权校验。
- 上传只接受 ZIP，校验路径穿越、加密条目、文件数量、压缩包大小、解压后总大小，以及至少一组 `.in/.out`、`.input/.ans` 等输入输出配对。
- JSON 开发存储新增顶层 `problem_test_data` 元数据段；旧 `apps/api/storage/dev-db.json` 缺少该段时自动补空对象，已有题目数据继续可读。
- ZIP 对象通过对象存储适配器保存：默认本地 `apps/api/storage/objects`，可配置为 MinIO；PostgreSQL 迁移 `0009_problem_test_data.sql` 固化对象引用和校验摘要元数据。
- 上传成功会更新代码题管理端 `judge_config.testdata_ref`，供在线 worker 后续读取；API/Web/CLI 均不编译、不运行、不本地判题，普通题面接口也不返回测试数据元数据。

## P3-05 题目版本控制

- JSON 开发存储新增顶层 `problem_versions`，旧 `apps/api/storage/dev-db.json` 会在读取时补空数组，现有题目和判题配置无需手工迁移。
- 每次管理端编辑、下线或回滚题目前，API 都会保存当前题目的完整管理快照；快照包含 `judge_config`，只通过管理端版本接口返回。
- 管理端新增 `GET /api/v1/admin/problems/{problem_id}/versions` 和 `POST /api/v1/admin/problems/{problem_id}/versions/{version_id}/restore`，权限沿用题目编辑权限和所有权校验。
- `/admin/problems` 页面显示版本历史并支持回滚。回滚前会再次归档当前状态，因此误回滚也可继续恢复。
- PostgreSQL 迁移 `0008_problem_versions.sql` 增加 `problem_versions` 表；普通 `problems` 表仍不存放 `judge_config`。

## P3-06 导入导出

- 管理端新增 `GET /api/v1/admin/problems/export` 和 `POST /api/v1/admin/problems/import`，格式覆盖 Hydro JSON、QDU JSON 和 FPS XML。
- 导出遵循题目编辑权限：教练只能导出自己的题目，裁判和管理员可导出全部或按 `ids` 指定题目。
- 导入先解析并复用 `ProblemCreate` 题型校验，整批通过后才一次性写入 JSON 存储；任一题无效时不会留下半批题目或半批 `problem_judge_config`。
- 冲突策略支持新建副本、覆盖同号和跳过同号；覆盖前仍校验题目所有权，并归档旧版本。
- 导入导出包属于管理端资料，可包含 `judge_config`；普通题面、题单、比赛详情和 CLI 仍不返回客观题答案。
- 代码题导入的评测配置只保存为在线 worker 元数据，API/Web/CLI 均不编译、不运行、不本地判题。

## P4-01 提交队列抽象

- 代码题提交会同时写入 `submissions` 和顶层 `judge_queue_jobs` 队列任务；任务只包含 `submission_id`、`problem_id`、`language`、`source_ref`、源码 SHA-256、资源限制和 `testdata_ref`。
- 队列任务不复制 `source_code`，worker 只能通过提交记录引用读取源码；普通题面接口仍不返回 `judge_config`。
- JSON 开发存储对旧快照做读时迁移：缺少 `judge_queue_jobs` 时，会为已有 `queued`/`judging` 代码提交派生队列任务并回填 `queue_job_id`、`queued_at`。
- 后续 PostgreSQL 队列迁移会固化同名表和调度索引；JSON 导出脚本保持提交源码只作为文本数据导出，不触发本地执行。
- `GAYOJ_JUDGE_QUEUE_BACKEND=json` 是本地默认；`redis`/`kafka` 作为可选发布适配入口，发布失败时 API 返回 503，并回滚本地提交与队列任务元数据，避免假入队。

## P4-02 judge worker 服务

- 新增 `apps/judge/worker.py` 作为独立 judge worker 队列入口，运行时通过仓储接口访问 JSON 开发队列，不嵌入 API 进程。
- worker 会注册或更新自己的 `judge_nodes` 心跳，并按语言过滤领取 `judge_queue_jobs.status=pending` 的代码提交。
- 默认 `--once` 路径领取成功后只把提交状态更新为 `judging`，返回 `submission_id`、`problem_id`、`language`、`source_ref`、资源限制和 `testdata_ref` 这类任务元数据。
- worker 输出和普通 API 响应都不返回用户源代码全文或客观题 `judge_config`；代码题配置仅用于生成 worker 任务元数据。
- 显式使用 `--execute` 时，worker 会在独立进程内调用 worker 侧 Docker 沙箱执行链路并回写最终结果；API、Web、离线 CLI 仍不编译、不运行、不本地判分。
- JSON 存储结构保持兼容：旧 `submissions` 队列状态读时迁入 `judge_queue_jobs`，不要求删除或重建 `apps/api/storage/dev-db.json`。

## P4-03 Docker 沙箱最小实现

- `apps/judge/gayoj_judge/sandbox.py` 新增 worker 侧 Docker 沙箱执行器，API、Web、离线 CLI 不调用该执行器。
- 执行器把用户源码写入临时目录并挂载到容器 `/work`，结束后清理临时目录，用户代码不写入仓库目录。
- Docker 命令默认包含 `--network none`、内存/交换区限制、`--pids-limit`、只读根文件系统、`--cap-drop ALL`、`no-new-privileges`、非 root UID 和容器内 `timeout`。
- `deploy/Dockerfile.judge-runner` 提供 Ubuntu 24.04 runner 镜像基线，包含 gcc/g++、Python 3 和 OpenJDK 21。
- `npm run smoke:judge-sandbox` 默认 dry-run 验证沙箱命令结构；显式设置 `GAYOJ_JUDGE_RUN_DOCKER_SMOKE=1` 后才运行真实 Docker smoke。
- 该任务不新增存储字段，不改普通题面接口，也不改变客观题离线 CLI 的题型边界。

## P4-04 编译器配置管理

- `GET /api/v1/judge/languages` 返回当前启用的代码语言清单，仅包含 `c`、`cpp`、`java`、`python` 的公开元数据。
- `GET /api/v1/admin/compiler-configs` 和 `PUT /api/v1/admin/compiler-configs/{code}` 由管理员维护底层编译器版本、命令模板、启用状态和排序。
- Web 管理端使用同一接口控制默认语言和启用状态；禁用语言后，公开语言表会即时收缩，代码提交也会在提交入口被拒绝。
- 普通题面接口继续不返回 `judge_config`，编译器管理只调整语言可用性和 worker 元数据，不在 API/Web/CLI 中执行代码。

## P4-05 测试点执行与结果聚合

- 新增 `apps/judge/gayoj_judge` 作为独立 judge worker 侧模块，API 仍只负责把代码题提交写入 `queued` 状态。
- worker 通过注入的 `SandboxExecutor` 执行编译与测试点运行，聚合 `accepted`、`wrong_answer`、`compile_error`、`time_limit_exceeded`、`memory_limit_exceeded`、`runtime_error` 等状态。
- 每个测试点回写结构化详情，包括用例编号、分值、耗时、内存、退出码、用户输出预览和错误信息；不会回写隐藏输入或期望输出预览，最终状态与总分写回提交记录。
- 若提交存在 `queue_job_id`，worker 会把对应队列任务标记为 `completed`；沙箱或 worker 系统错误会标记为 `failed` 并保留通用错误摘要，避免任务长期停留在 `leased`。
- 代码题隐藏测试点只从管理端保存的 `judge_config.test_cases` 或 worker 可用的评测元数据读取；普通题面、题单、比赛和离线 CLI 仍不泄露或处理这些规则。
- 当前实现固定 worker 聚合与回写契约，并提供 `DockerSandboxPointExecutor` 适配 Docker 沙箱执行器；生产级语言版本策略和 Redis/Kafka worker 消费仍需后续任务继续完善。

## P4-06 评测节点心跳与调度

- 新增 `POST /api/v1/judge/nodes/heartbeat`，由 judge worker 使用 `X-Judge-Node-Token` 上报节点 ID、语言、负载、队列深度和运行状态。
- `judge_nodes` 仍保持 JSON 兼容结构；旧节点缺字段时会在读取时补齐，超过心跳 TTL 的 `online`/`draining` 节点会在管理端和裁判端显示为 `offline`。
- 新增 `POST /api/v1/judge/nodes/{node_id}/claim`，只允许在线节点领取自己支持语言的 pending 代码队列任务，并将任务标记为 `leased`、提交标记为 `judging`。
- 新增 `PATCH /api/v1/admin/judge-nodes/{node_id}`，管理员可把节点切换为 `online`、`draining` 或 `offline`，操作写入审计日志。
- 裁判端显示队列 backend/topic、pending/leased 任务和节点心跳；管理端显示节点语言、负载、心跳时间和状态操作。
- P4-06 只完成调度和状态流转，不编译、不运行、不本地判题；普通题面接口继续不返回 `judge_config`，离线 CLI 仍只处理客观题。

## P4-07 手动重测与批量重测

- 新增 `POST /api/v1/judge/submissions/{submission_id}/rejudge`，裁判或管理员可将单个代码提交重新置为 `queued`。
- 新增 `POST /api/v1/judge/submissions/rejudge`，支持按 `submission_ids`、`problem_id`、`contest_id` 和 `statuses` 批量筛选重测；缺失记录和非代码题会返回 skipped。
- 重测会清空旧测试点详情和 `judged_at`，生成新的 `judge_queue_jobs` 记录，写入审计日志，并通知提交者。
- Web 提交列表对具备 `submission:override` 权限的用户显示单条和批量重测入口；普通选手只看到自己的提交记录。
- API 与 Web 仅重置状态并入队，不编译、不运行、不本地判题；客观题 `judge_config` 隔离和离线 CLI 客观题边界不变。

## P5-01 客观题规则引擎单测

- 新增 `apps/api/tests/test_p5_objective_rules.py`，覆盖填空题、单选题和多选题的当前规则。
- 单测使用同一组题目、`judge_config` 和答案同时调用 API 侧 `judge_objective()` 与离线 CLI `judge()`，确保在线提交与 CLI 本地训练判分一致。
- 规则覆盖大小写敏感、空白保留/归一、多答案填空、单选精确匹配、多选顺序无关和漏选/多选错误。
- 代码题继续被客观题规则路径拒绝；CLI 仍只处理填空题、单选题和多选题。

## P5-02 填空题规则增强

- 填空题 `judge_config` 新增可选的 `blank_rules` 映射，每个空位可配置 `match: exact | regex | numeric`。
- `exact` 继续复用既有答案列表、大小写和空白设置；`regex` 使用完整匹配并复用大小写/空白设置；`numeric` 使用浮点数比较并支持非负 `tolerance`。
- API 侧 `judge_objective()` 与离线 CLI `judge()` 使用同一规则语义；管理端保存时校验正则和数值误差配置。
- `blank_rules` 仍属于管理端和授权离线包中的 `judge_config`，普通题面接口、题单和比赛详情不返回该字段。

## P5-03 题单离线包下载

- 新增 `GET /api/v1/problem-sets/{problem_set_id}/offline-package`，学生可按公开题单下载签名客观题离线包。
- 题单包沿用全局离线包格式与签名算法，但只取该题单中的可见题目，并在打包时过滤代码题。
- 普通题单列表和题单详情仍只返回题目摘要，不返回 `judge_config`；授权离线包 payload 内保留客观题判题配置供 CLI 本地训练。
- 离线 CLI 新增 `pull-set <id>`，也支持 `download --problem-set-id <id>`；本地判题仍只接受填空题、单选题和多选题。

## P5-04 离线包有效期与签名

- 离线包 payload 新增 `signature_algorithm: hmac-sha256` 与 `expires_at`，默认有效期由 `GAYOJ_OFFLINE_PACK_TTL_HOURS` 控制。
- HMAC 签名覆盖完整 payload，题面、答案、`judge_config`、有效期或签名算法任一字段被篡改都会导致 CLI 拒绝加载。
- 离线 CLI 在练习前先校验签名算法、HMAC 签名和过期时间；过期包必须重新下载。
- 该机制只保护授权客观题离线训练包，不改变代码题在线队列/worker 评测边界。

## 迁移到完整版本

1. 增加 SQLAlchemy/SQLModel 或等价数据库仓储实现，替换当前 JSON 仓储适配器。
2. 增加数据库仓储的读写适配，让 API smoke test 可在 PostgreSQL 模式下通过。
3. 将当前 JSON 入队状态替换为 Redis/Kafka 队列生产者。
4. 新增独立 judge worker，通过 Docker/nsjail/gVisor 执行代码题。
5. 前端接入 Monaco Editor、WebSocket 排行榜和更完整的管理表单。
6. 将审计日志、提交日志和统计报表接入 ClickHouse/Prometheus。

