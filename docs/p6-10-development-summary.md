# P6-10 比赛访问控制修补总结

## 完成内容

- 比赛模型新增 `access_mode`，覆盖 `open`、`password`、`invite`、`team`、`manual` 五类门禁。
- 口令赛和邀请码赛新增 `/api/v1/contests/{contest_id}/access` 解锁接口，服务端只保存 `access_code_hash`，列表、详情和管理响应不回传明文口令或哈希。
- 队伍赛和白名单赛新增 `team_ids`、`participant_user_ids`、`access_unlocked_user_ids` 存储字段，并与 P6-09 的 `participation_mode`、报名名单、锁榜名单并存。
- 学生访问统一拆成门禁校验和参赛校验：详情页可用于公开报名入口，题面、提交、Clarification、打印、封榜视图、重测相关资源继续要求完整授权。
- 打印接口先做比赛访问与源码归属校验，再读取已提交源码或本次请求源码文本；缺失提交不会向未授权用户泄露 404 探测信号。
- 普通题面和比赛题面响应继续剔除 `judge_config`，普通用户不能从题面接口看到判题配置字段。
- 外榜、实时外榜、滚榜等公开榜单只暴露 `public + open access + open participation` 的比赛，私有门禁比赛不会进入公开榜单。
- 前端比赛首页加入口令/邀请码解锁流程，比赛管理页支持同时配置参赛方式和访问模式。
- SQL 迁移顺延为 `0018_contest_access_control.sql`，避免覆盖已有 P6-09 `0017_contest_roster_fields.sql`。

## 验证

- `py -3.12 -m pytest apps/api/tests/test_p6_contest_boundaries.py -q`：59 passed。
- `npm run export:openapi`：通过，已刷新 `api/openapi.json`。
- `npm run check:openapi`：通过。
- `npm run check:migrations`：通过，18 个迁移文件通过检查。
- `npm run typecheck`：通过。
- `npm run build:web`：通过。
- `npm run check:api`：277 passed。

最终合入 `main` 后复验：

- `py -3.12 -m pytest apps/api/tests/test_p6_contest_boundaries.py -q`：61 passed。
- `npm run check:openapi`：通过。
- `npm run check:migrations`：通过。
- `npm run typecheck`：通过。
- `npm run build:web`：通过。
- `npm run check:api`：279 passed。

## 边界确认

- 比赛题面、提交、Clarification、打印、封榜、重测均保留权限校验和比赛资源归属校验。
- 代码打印不执行用户代码，只处理提交源码或请求源码文本。
- 公开报名赛允许学生进入详情报名，但报名前不能读取题面、提交、提问或打印。
- 私有队伍赛、白名单赛不在普通学生列表中公开，资源访问仍按队伍/白名单授权放行。
- 训练赛和正式赛共用访问控制、报名控制、榜单和运维路径，没有只覆盖管理后台。

## 剩余风险

- 口令/邀请码目前使用单一访问码哈希，尚未实现多邀请码、邀请码失效时间和批量导入。
- 访问解锁记录保存在当前轻量存储模型中，后续接入正式数据库时需要继续保持哈希字段和迁移默认值兼容。
