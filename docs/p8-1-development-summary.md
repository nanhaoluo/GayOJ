# P8-1 社交、通知与实时推送任务总结

## 完成内容

- 讨论列表改为分页响应，支持 `type`、`target_id`、`q`、`limit`、`offset` 查询。
- 讨论列表、详情和回复增加目标可见性控制：公开题目/公开比赛可见，私有题目和私有比赛只允许授权角色访问。
- 发布讨论时校验关联目标可见性，避免普通用户向不可见题目或比赛挂载讨论/题解。
- 新增 `GET /api/v1/notifications/stream` SSE 推送端点，按当前用户令牌只输出本人通知摘要、未读数和心跳事件。
- SSE 推送不输出通知正文、提交源码、标准答案、`expected` 或 `judge_config`。
- 讨论页新增筛选、搜索、分页、加载和空状态。
- 通知页新增实时连接状态、未读数、手动刷新、断线轮询回退和自动重连。
- OpenAPI 已刷新，包含讨论分页响应、输入校验和通知推送事件模型。

## 测试与验证

- `py -3.12 -m pytest apps/api/tests/test_p8_social_notifications.py -q`：4 passed。
- `npm run check:api`：255 passed。
- `npm run build:web`：通过。
- `npm run check:openapi`：通过。
- 推送/通知 smoke：登录、讨论分页查询、通知列表、SSE text/event-stream、推送脱敏检查通过。

## 边界确认

- 评论、题解、通知、推送均按当前权限与目标可见性做过滤。
- 实时推送仅输出通知摘要和未读数量，不泄露私有提交、答案或管理信息。
- 前端在 SSE 断线后会进入轮询回退，并定时尝试重连。
- 本任务没有新增持久化字段，不改变 `apps/api/storage/dev-db.json` 结构。

## 剩余风险

- 当前推送为 SSE 轻量实现，不是完整 WebSocket 通道；适合通知推送基础能力，后续 P8-05 可扩展评测状态、榜单和比赛广播。
- SSE 连接使用查询参数传递短期登录 token，以适配浏览器 `EventSource` 限制；生产环境建议结合 HTTPS、短 TTL 或专用一次性推送 token。
