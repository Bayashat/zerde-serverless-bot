# 设计文档：封禁统计功能（Issue #31）

**日期：** 2026-04-05
**状态：** 已批准

---

## 背景

现有 DynamoDB 统计表（`stats`）已记录 `total_joins` 和 `verified_users`。Issue #31 要求：每次通过投票封禁用户时记录到统计表，并在 `/stats` 命令中展示封禁总数。

---

## 架构

无需新增 DynamoDB 表或更改表结构。现有 `_increment()` 方法使用 `if_not_exists`，可自动为已有 item 创建新字段 `total_bans`。

数据流：
1. 投票达到封禁阈值 → `_finalize_ban()` 调用 `kick_chat_member`
2. 封禁成功后 → 调用 `stats_repo.increment_total_bans(chat_id)`
3. 管理员执行 `/stats` → `get_stats()` 返回包含 `total_bans` 的数据
4. `handle_stats()` 将封禁数展示在消息中

---

## 变更范围

### 1. `src/bot/services/repositories/stats.py`
- 新增 `increment_total_bans(chat_id)` 方法，复用 `_increment()` 模式
- `get_stats()` 返回值新增 `total_bans` 字段（默认 0）

### 2. `src/bot/services/handlers/voteban.py`
- `_finalize_ban()` 中，`kick_chat_member` 成功执行后，调用 `ctx.stats_repo.increment_total_bans(ctx.chat_id)`
- 需判断 `ctx.stats_repo` 不为 None（与现有 `ctx.vote_repo` 的判断模式一致）

### 3. `src/bot/services/handlers/commands.py`
- `handle_stats()` 从 `stats` 中读取 `total_bans`
- 传入 `stats_message` 翻译模板

### 4. `src/bot/core/translations.py`
- `stats_message`（en、kk）新增封禁用户一行：
  - EN: `🔨 <b>Banned by vote:</b> {banned} users`
  - KK: `🔨 <b>Дауыспен бандалғандар:</b> {banned} қолданушы`

---

## 错误处理

`increment_total_bans()` 内部已有 `try/except ClientError`（复用 `_increment`），封禁操作本身不受统计失败影响（统计调用在封禁消息发送之后）。

---

## 测试要点

- `_finalize_ban` 调用 `stats_repo.increment_total_bans`
- `get_stats` 返回 `total_bans` 字段
- `handle_stats` 消息包含封禁数
- `stats_repo` 为 None 时不抛异常
