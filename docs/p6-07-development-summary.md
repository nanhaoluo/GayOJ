# P6-07 赛后重测/Hacking 修补总结

## 完成内容

- 新增比赛级 `ContestRejudgeRequest`，支持按 `submission_ids`、`problem_id` 和 `statuses` 限定赛后重测范围。
- 比赛重测严格校验当前比赛、当前题集和筛选条件；赛外、题外、缺失或状态不匹配提交只进入 `skipped`，不会入在线评测队列。
- 重测仍只对代码提交执行重新入队，API 不编译、不运行、不本地判题；客观题提交会以清晰原因跳过。
- 比赛级汇总审计继续使用 `contest.rejudge`，单条赛内入队审计改为 `contest.submission.rejudge`，避免审计统计混淆。
- 重测后刷新受影响用户/题目的气球记录，手动 override 后也会同步刷新 ACM 气球状态。
- 裁判组纯净页移除跨功能跳转，仅保留目标内容、返回和刷新，外榜、实时外榜、滚榜、打印台、气球台等纯净页边界保持一致。
- OpenAPI 已刷新，`POST /api/v1/contests/{contest_id}/rejudge` 请求体更新为 `ContestRejudgeRequest`。

## 验证

- `py -3.12 -m pytest apps/api/tests/test_p6_contest_boundaries.py -q`：46 passed。
- `npm run check:api`：264 passed。
- `npm run build:web`：通过。
- `npm run check:openapi`：通过。

## 边界确认

- 比赛题面、提交、Clarification、打印、封榜、重测继续走现有认证、权限和资源归属校验。
- 代码打印只返回已提交源码或本次请求源码文本，不执行用户代码。
- 普通题面和比赛题面响应不新增 `judge_config` 字段。
- 训练赛和正式赛共用同一比赛提交、重测、封榜、榜单、气球和裁判监控路径。

## 剩余风险

- 本次没有新增真实 worker 执行链路；重测结果重新排名依赖后续 judge worker 回写新评测结果。
- 在独立 worktree 跑完整 API 回归时，需要本地存在被忽略的 `apps/api/storage/dev-db.json` 种子文件；该文件仍不提交。
