# P7-04 教练防抄袭辅助入口任务总结

任务时间：2026-05-26

## 完成内容

- 新增 `GET /api/v1/coach/similarity`，面向教练端提供相似提交列表。
- 相似度计算只在服务端把已提交源码作为文本做 token 重叠分析，不编译、不运行、不评判用户代码。
- 数据范围收口到教练负责队伍中的学生，以及教练负责作业题单中的代码题。
- 支持按题目、比赛和阈值筛选；越权题目和越权比赛返回明确拒绝。
- 返回内容只包含学生、队伍、题目、比赛、语言、提交时间、提交 ID、相似度和共享 token 数等元数据。
- 教练端工作台新增“防抄袭辅助”面板，提供筛选控件、候选统计和相似提交列表，移动端单列展示。
- 刷新 OpenAPI 契约，新增相似提交相关响应模型。

## 权限与安全边界

- 未登录用户访问相似提交接口返回 `401`。
- 无 `analytics:read` 权限的普通学生访问返回 `403`。
- `problem_id` 不在教练负责作业题目范围内时返回 `403 Problem is outside coach scope`。
- `contest_id` 不存在返回 `404 Contest not found`。
- 私有比赛仍按比赛管理、裁判监控或 Clarification 全量读取权限校验。
- 响应不包含 `source_code`、客观题答案、评测详情里的 `expected` 或 `judge_config`。

## 验证结果

- `npm run check:api`：247 passed。
- `npm run build:web`：通过。
- `npm run check:openapi`：通过。
- `py -3.12 -m pytest apps/api/tests/test_p7_coach_similarity.py apps/api/tests/test_p7_coach_profiles.py apps/api/tests/test_p7_coach_assignment_status.py -q`：9 passed。

## 剩余风险

- 当前相似度算法是轻量 token 集合重叠，适合作为教练复核入口，不等同于正式查重判定。
- 目前不展示源码对比视图，后续若增加源码查看必须继续复用提交源码权限和脱敏边界。
