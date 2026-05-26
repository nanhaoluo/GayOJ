# P7-05 教练报表导出任务总结

## 完成内容

- 新增 `GET /api/v1/coach/reports/export`，支持 `csv` 和 `xlsx` 两种格式下载。
- 报表基于教练端既有聚合作用域生成，覆盖作业概览、学生画像汇总、标签掌握度、题型掌握度和活跃热力。
- CSV/XLSX 只包含脱敏统计字段，不输出提交源码、标准答案、客观题答案字段、`expected` 或 `judge_config`。
- 新增下载审计 `coach.report.export`，记录格式、作业数量和学生数量。
- 教练工作台新增报表导出入口，提供 CSV/XLSX 下载按钮、导出范围摘要、加载状态和移动端适配。
- OpenAPI 已刷新，导出路由声明 CSV 与 XLSX 二进制响应。

## 测试与验证

- `py -3.12 -m pytest apps/api/tests/test_p7_coach_reports.py -q`：4 passed。
- `py -3.12 -m pytest apps/api/tests/test_p1_backend_contract.py::test_openapi_business_routes_are_versioned_and_typed apps/api/tests/test_p7_coach_reports.py -q`：5 passed。
- `npm run check:api`：251 passed。
- `npm run build:web`：通过。
- `npm run check:openapi`：通过。
- `py -3.12 -m pytest apps/api/tests/test_p7_coach_reports.py apps/api/tests/test_p7_coach_profiles.py apps/api/tests/test_p7_coach_assignment_status.py apps/api/tests/test_p7_coach_similarity.py -q`：13 passed。

## 边界确认

- 没有新增或修改存储字段，不影响 `apps/api/storage/dev-db.json` 兼容性。
- 没有改变客观题、比赛、提交、离线训练既有权限边界。
- XLSX 由标准库生成最小 Office Open XML 包，不引入额外运行依赖。
- 报表导出依赖当前教练可见队伍、作业和学生聚合，非本人负责队伍和外部教练数据不会进入导出文件。

## 剩余风险

- XLSX 当前是轻量表格导出，未包含复杂样式、冻结窗格或公式；已通过 zip 结构和 XML 内容测试确认可打开基础结构。
- 前端下载行为已通过生产构建校验，未额外启动浏览器做点击式端到端下载验证。
