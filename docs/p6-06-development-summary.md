# P6-06 比赛系统修补总结

## 完成内容

- 比赛打印从一次性返回源码升级为持久化打印单，支持创建、列表、详情读取和状态更新。
- 打印单只读取已提交源码或本次请求源码；API 不编译、不运行、不本地判题，审计日志只记录来源、题目、语言、行数和 `source_sha256`。
- 比赛打印、比赛提交、Clarification、封榜榜单、重测和气球记录继续走权限校验与比赛资源归属校验。
- 普通提交接口禁止携带 `contest_id`，避免普通训练提交伪装成比赛提交。
- 裁判监控增加 `print_jobs`，打印台纯净页接入打印单列表、源码预览、已打印和取消状态处理。
- 外榜、实时外榜、滚榜、裁判组、打印台、气球台等目标页保持纯净布局，只呈现目标内容和返回/必要操作按钮。
- OpenAPI 已刷新，覆盖打印单列表、详情、状态更新和裁判监控字段。

## 验证

- `py -3.12 -m pytest apps/api/tests/test_p6_contest_boundaries.py apps/api/tests/test_p4_result_aggregation.py -q`：63 passed。
- `npm run build:web`：通过。
- `npm run typecheck`：通过。
- `npm run check:openapi`：通过。
- `npm run check:migrations`：通过。
- `npm run check:api`：272 passed。

## 边界确认

- 普通题面和比赛题面响应未暴露 `judge_config`。
- 代码打印不执行用户代码，只处理提交源码或请求源码文本。
- 学生只能查看自己的打印单；裁判/管理员可处理比赛内打印单。
- 私有比赛打印仍受比赛访问与提交归属限制。
- 比赛重测只作用于当前比赛、当前题集和选定筛选范围内的代码提交。

## 剩余风险

- 打印单状态仍是轻量内置工作流，未接入真实打印机队列或打印机回执。
- 独立 worktree 跑完整 API 回归时需要本地存在被 `.gitignore` 忽略的 `apps/api/storage/dev-db.json` 验证种子；该文件不提交。
