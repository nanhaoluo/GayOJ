# P8-02 题解系统增强总结

## 范围

- 为题解帖补充分类字段，支持 `general`、`tutorial`、`analysis`、`official`、`trick`。
- 为题解帖提供点赞、取消点赞、收藏、取消收藏接口。
- 讨论列表和详情统一返回脱敏视图，只暴露计数与当前用户状态，不暴露 `liked_by`、`bookmarked_by`。
- 前端讨论工作台支持题解分类筛选、发布分类、点赞和收藏状态回退。

## 安全与边界

- 题解反应接口复用讨论可见性校验，私有题目/比赛下的内容仍按资源归属与权限过滤。
- 非题解帖子调用点赞/收藏接口会被拒绝，避免把普通讨论扩展为未定义状态。
- SSE 通知只保留用户级摘要，不包含源码、答案、`judge_config`、反应用户列表等敏感字段。
- JSON 快照和 SQL 导入导出均补齐 `solution_category`、`liked_by`、`bookmarked_by`，兼容旧 `dev-db.json`。

## 验证

- `npm run check:api`：258 passed。
- `npm run build:web`：通过。
- `npm run check:openapi`：通过。
- `npm run check:migrations`：通过。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke-p8-social.ps1`：通过。

## 备注

- 新工作树需要本地复制被忽略的 `apps/api/storage/dev-db.json` 后才能跑完整 API 回归。
- 本次修正了两个 P6 比赛测试的固定日期假设，避免 2026-05-26 之后测试结果随时间漂移。
