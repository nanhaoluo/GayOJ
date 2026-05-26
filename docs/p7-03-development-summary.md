# P7-03 教练端学生能力画像总结

## 任务范围

- 完成教练端学生能力画像：标签掌握度、题型掌握度、最近活跃热力图。
- 画像数据只从当前教练负责队伍、班级、作业相关学生提交中聚合。
- 前端教练页改为可扫描的工作台视图，兼顾移动端布局。

## 主要变更

- 后端新增 `StudentAbilityProfile`、`TagMastery`、`ProblemTypeMastery`、`ActivityHeatmapCell` 等响应模型。
- `/api/v1/coach/analytics` 返回作业状态、学生画像、标签掌握度、题型掌握度和活跃热力图。
- 聚合逻辑集中在 `apps/api/app/services.py`，只输出计数、通过率、解题数、日期活跃等脱敏指标。
- 教练页新增作业状态卡、学生画像卡、标签掌握度卡和活跃热力图。
- OpenAPI 已刷新，新增字段纳入接口契约。

## 安全边界

- 教练只能看到自己拥有队伍中的学生和相关作业数据。
- 画像和报表数据不返回提交源码、客观题 answers、逐项 expected 或 `judge_config`。
- 作业创建校验目标队伍归属，拒绝跨教练队伍发布作业。
- 未改变客观题、比赛、提交的既有权限入口。

## 验证

- `npm run check:api`
- `npm run build:web`
- `npm run check:openapi`
- `py -3.12 -m pytest apps/api/tests/test_p7_coach_profiles.py -q`
