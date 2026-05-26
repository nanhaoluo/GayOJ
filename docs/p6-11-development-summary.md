# P6-11 比赛题号映射修补总结

## 完成内容

- 比赛题号解析支持比赛内 `problem_key` 和原题 ID 双路输入，比赛题面、提交、Clarification、打印、重测筛选均按比赛编排做资源归属校验。
- 比赛题面、Clarification、打印单、气球、榜单、裁判监控等响应补齐或优先使用 `problem_key`、`display_title`、`score`，避免前端在比赛上下文里回退到原题 ID 展示。
- 裁判监控 `last_submissions` 契约新增比赛题号字段，按比赛编排替换展示标题和分值，保证训练赛与正式赛的裁判视图一致。
- 前端比赛首页、题面页、提交入口、Clarification、打印台、气球台、裁判台、榜单等页面统一使用比赛题号和展示标题，同时继续兼容原题 ID。
- 比赛编排管理表单补齐展示标题、分值、语言限制等字段，避免只覆盖管理后台以外的学生和裁判流程。
- 外榜、实时外榜、裁判组、打印台、气球台、滚榜等单页继续通过 `meta.pure` 使用纯净布局，只展示目标内容、返回按钮和必要目标操作。
- 普通题面响应继续不暴露 `judge_config`；比赛题面也不新增判题配置泄露面。
- 代码打印链路只读取已提交源码或本次请求源码文本，不编译、不运行、不调用本地判题。
- `api/openapi.json` 已随路由和响应模型刷新，前后端类型契约保持一致。

## 验证

功能分支验证：

- `py -3.12 -m pytest apps/api/tests/test_p6_contest_boundaries.py`：55 passed。
- `npm run typecheck`：通过。
- `npm run build:web`：通过。
- `npm run check:openapi`：通过。
- `npm run check:api`：273 passed。

合入 `main` 后复验：

- `npm run typecheck`：通过。
- `npm run build:web`：通过。
- `npm run check:openapi`：通过。
- `py -3.12 -m pytest apps/api/tests/test_p6_contest_boundaries.py`：61 passed。
- `npm run check:api`：279 passed。

## 边界确认

- 比赛题面、提交、Clarification、打印、封榜、重测均保留权限校验和比赛资源归属校验。
- 训练赛和正式赛共用比赛题号映射、提交、Clarification、打印、气球、裁判监控和榜单展示链路。
- 学生只能访问自己有资格参加的比赛资源，裁判和管理员操作仍限定在目标比赛内。
- 普通题面不暴露 `judge_config` 字段，比赛相关响应只返回展示和判题结果所需字段。
- 纯净页不进入全站 `AppShell`，避免外榜、裁判组、打印台、气球台、滚榜等现场页面混入非目标导航。

## 合并记录

- 功能分支：`codex/p6-11-contest-system-fix-20260526`。
- 关键提交：`656f91d`、`3b657b1`、`5ec561c`。
- 主线合并提交：`f2723b0 merge(p6-11): 任务id：p6-11 合并比赛题号映射修补-2026-05-26 20:11:30 +08:00`。

## 剩余风险

- `apps/api/storage/dev-db.json` 是被 `.gitignore` 忽略的本地测试种子；独立 worktree 跑完整 API 回归时需要本地存在该种子文件，但它未纳入提交。
- 真实现场打印机、打印机回执和物理打印失败重试仍未接入；当前代码打印只生成和处理打印单。
- 本轮验证覆盖 API、OpenAPI、TypeScript 和生产构建，未执行浏览器人工 E2E 或现场硬件联调。
