# P6-12 比赛提交与状态视图修补总结

## 完成内容

- 比赛题目引用支持真实 `problem_id` 与比赛 `problem_key` 双入口；比赛题面、提交、Clarification、打印和赛后重测都会先映射到当前比赛内题目，再做资源归属校验。
- 比赛提交状态视图继续按比赛维度过滤；普通选手只能看自己的提交和源码，裁判/管理员可看全量提交、队伍汇总和状态详情。
- 提交、Clarification、打印单、气球、榜单和裁判工作台响应优先展示比赛题号与展示题名，存储层仍保留真实题目 ID，避免跨比赛串题。
- 比赛题面响应保持 `response_model_exclude_none=True`，普通比赛题面不暴露 `judge_config`。
- 代码打印仍只读取已提交源码或本次请求源码，不编译、不执行、不调用本地判题。
- 前端比赛首页、题面页、提交状态页、Clarification、气球台、裁判组和榜单展示均承接比赛题号、展示题名与分值；外榜、实时外榜、滚榜、裁判组、打印台、气球台和提交状态页继续使用纯净布局。
- OpenAPI 已刷新，补齐 Clarification 与 ContestBalloon 的 `problem_key` 响应字段。

## 验证

- `py -3.12 -m pytest apps/api/tests/test_p6_contest_boundaries.py::test_contest_problem_aliases_drive_submit_clarification_print_and_rejudge apps/api/tests/test_p6_contest_boundaries.py::test_contest_submit_routes_keep_code_queue_only_and_objective_scored -q`：2 passed。
- `py -3.12 -m pytest apps/api/tests/test_p6_contest_boundaries.py -q`：功能分支 55 passed；合并 main 后 58 passed。
- `npm run check:api`：273 passed。
- `npm run build:web`：通过。
- `npm run check:openapi`：通过。

## 合并说明

- 本次从 `codex/p6-12-contest-status-fix-20260526` 合并入 `main`。
- 合并时 `apps/api/app/main.py` 与主线报名名单/参赛名单逻辑有冲突；最终保留主线正式赛名单校验，同时引入 p6-12 的比赛题号映射、展示题名和 Clarification 响应增强。
- 合并后修正 `GET /api/v1/contests/{contest_id}` 的裁判视图，使裁判/管理员在封榜后仍能看到完整 ProblemSummary，公开视图继续按封榜过滤。

## 边界确认

- 比赛题面、提交、Clarification、打印、封榜榜单、重测都经过权限校验和比赛资源归属校验。
- 普通提交接口仍不能携带 `contest_id` 伪装比赛提交。
- 私有赛、名单赛和队伍赛仍依赖 `ensure_contest_access` 与参赛名单判断。
- 气球和 Clarification 的展示题号来自当前比赛编排，不从用户输入直接透传。

## 剩余风险

- 比赛题目展示标题和分值已接入 API/Web，但没有单独做可视化截图验收。
- 打印台仍是轻量工作流，未接入真实打印设备队列或回执。
- 本次未修改迁移和 worker，因此未跑 `npm run check:migrations` 或 worker smoke。
