# QQ REST API 插件自动事件说明

> 更新时间：2026-07-14
>
> 适用范围：`runtime/auto_events.py`、`runtime/dispatch.py`、`templates/registry.yaml` 与插件配置。

## 1. 关键结论

- 平台系统事件先由共享分发入口解析，再由自动事件逻辑消费，不进入普通指令/LLM 流水线。
- 自动事件默认会输出结构化日志，并写入插件自有 SQLite 事件日志；关闭对应日志分组时，这两项都会跳过。
- 当前有 5 类平台事件具备自动回复能力：机器人入群/退群、普通群成员加入、好友添加/删除。其中退群和删好友默认关闭，普通成员欢迎默认文本为空。
- `new_user_welcome` 是首次聊天欢迎逻辑，不是 QQ 平台事件，也不在 `AUTO_EVENT_MAP` 中。

## 2. 事件清单

### 2.1 可自动回复事件

| 平台事件 | 自动事件 key | 默认行为 | 插件配置 |
| --- | --- | --- | --- |
| `GROUP_ADD_ROBOT` | `group_add_robot` | 发送机器人入群欢迎 | `group_add_robot_message`，为空不发送 |
| `GROUP_DEL_ROBOT` | `group_del_robot` | 只记录，回复默认关闭 | `enable_group_remove_notice` |
| `GROUP_MEMBER_ADD` | `group_member_add` | 只记录，欢迎文本默认空 | `group_member_add_message`，为空不发送 |
| `FRIEND_ADD` | `friend_add` | 发送好友欢迎 | `friend_add_message`，为空不发送 |
| `FRIEND_DEL` | `friend_del` | 只记录，回复默认关闭 | `enable_friend_remove_notice` |

`group_member_add_message` 支持 `{user_id}`、`{member_openid}`、`{raw_user_id}`、`{union_openid}`、`{group_id}` 和 `{op_user_id}` 占位符。无法识别的占位符会原样保留。

### 2.2 仅日志/存储事件

| 分组 | 平台事件 |
| --- | --- |
| `relation` | `GROUP_ADD_ROBOT`、`GROUP_DEL_ROBOT`、`FRIEND_ADD`、`FRIEND_DEL` |
| `group_setting` | `GROUP_MSG_RECEIVE`、`GROUP_MSG_REJECT` |
| `group_member` | `GROUP_MEMBER_ADD`、`GROUP_MEMBER_REMOVE` |
| `guild` | `GUILD_CREATE`、`GUILD_UPDATE`、`GUILD_DELETE` |
| `channel` | `CHANNEL_CREATE`、`CHANNEL_UPDATE`、`CHANNEL_DELETE` |
| `guild_member` | `GUILD_MEMBER_ADD`、`GUILD_MEMBER_UPDATE`、`GUILD_MEMBER_REMOVE` |
| `message_delete` | `PUBLIC_MESSAGE_DELETE`、`DIRECT_MESSAGE_DELETE` |
| `reaction` | `MESSAGE_REACTION_ADD`、`MESSAGE_REACTION_REMOVE` |
| `audit` | `MESSAGE_AUDIT_PASS`、`MESSAGE_AUDIT_REJECT` |
| `forum` | `OPEN_FORUM_THREAD_CREATE/UPDATE/DELETE`、`OPEN_FORUM_POST_CREATE/DELETE`、`OPEN_FORUM_REPLY_CREATE/DELETE` |

表中的可回复事件也属于相应日志分组；自动回复开关与日志分组开关是两套独立判断。

### 2.3 暂未启用的映射

以下常量和解析准备仍保留，但没有加入 `AUTO_EVENT_MAP`：

- `SUBSCRIBE_MESSAGE_STATUS`
- `C2C_MSG_REJECT`、`C2C_MSG_RECEIVE`
- `AUDIO_START`、`AUDIO_FINISH`、`AUDIO_ON_MIC`、`AUDIO_OFF_MIC`
- `AUDIO_OR_LIVE_CHANNEL_MEMBER_ENTER`、`AUDIO_OR_LIVE_CHANNEL_MEMBER_EXIT`

它们当前不会走自动事件回复/日志分组逻辑。

## 3. 处理流程

```text
WSS / Webhook payload
  -> parse_event()
  -> 去重与有效性检查
  -> 按日志分组决定是否写插件 DB
  -> handle_relation_event()
       -> 输出自动事件日志
       -> 系统事件直接消费
       -> 可回复事件按配置发送文本
  -> 非系统消息检查 new_user_welcome
  -> 有效聊天消息 commit_event() 给 AstrBot
```

自动回复文本使用 `send_text_prefer_markdown()`：先尝试 QQ 原生 Markdown，失败后发送普通文本。

## 4. 配置来源与优先级

### 4.1 `templates/registry.yaml`

注册表提供自动事件的基础默认值：

```yaml
auto_events:
  group_add_robot:
    enabled: true
    template: ""
    fallback_text: "欢迎加入，本机器人已入群～"
    log: true
```

| 字段 | 当前作用 |
| --- | --- |
| `enabled` | 控制使用注册表默认回复的事件是否启用；入群、成员欢迎、好友欢迎主要由插件文本是否为空决定 |
| `template` | 预留字段，当前自动回复未使用模板发送 |
| `fallback_text` | 退群、删好友等没有专用文本配置时的回复文本 |
| `log` | 单事件日志/存储开关 |
| `scenes` | 可选场景限制 |

### 4.2 插件配置

插件配置 schema 位于 `_conf_schema.json`，实际配置文件路径由 AstrBot 管理，不应在插件文档中假定固定文件名。

插件配置优先决定以下内容：

- `group_add_robot_message`
- `group_member_add_message`
- `friend_add_message`
- `new_user_welcome_message`
- `enable_group_remove_notice`
- `enable_friend_remove_notice`
- `auto_event_log_groups`

对 `group_add_robot`、`group_member_add`、`friend_add`，文本为空就不发送；`group_del_robot` 和 `friend_del` 还要求注册表事件已启用且对应布尔开关为 `true`。

### 4.3 日志分组

`auto_event_log_groups` 的 10 个分组默认都是 `true`。判断优先级为：

1. 插件配置中该分组的布尔值；
2. `templates/registry.yaml` 的分组 `log`；
3. 缺失时默认允许记录。

分组关闭后，事件仍会被接收和消费，但不会输出自动事件日志，也不会写入插件 `EventLog`。是否发送自动回复继续由事件自身配置决定。

## 5. `new_user_welcome`

`new_user_welcome` 在以下条件同时满足时触发：

- 当前消息不是 `AUTO_EVENT_MAP` 中的系统事件；
- 当前场景符合注册表 `scenes`，默认只包含 `group`；
- `new_user_welcome_message` 不为空；
- AstrBot 对话管理器中当前 `unified_msg_origin` 尚无 conversation；
- 同一事件尚未执行过首次用户检查。

未 @ 机器人的 `GROUP_MESSAGE_CREATE` 不触发首次欢迎。欢迎消息本身不会写入 AstrBot 对话历史，也不会替代随后正常提交的用户消息。

## 6. 插件数据库与 AstrBot 对话历史

需要区分两类存储：

- 插件 SQLite：`runtime/dispatch.py` 通过 `db/service.py` 记录事件、身份和场景信息，数据库位于 AstrBot 插件数据目录下的 `qq_restapi/qq_restapi.db`。
- AstrBot conversation：只有正常提交的聊天消息以及全量群消息上下文兜底会进入聊天上下文；系统自动事件不会作为聊天消息提交。

自动事件日志分组控制的是插件日志和插件数据库事件记录，不等同于 AstrBot 的对话历史开关。

## 7. 实现依据

- `runtime/dispatch.py`
- `runtime/auto_events.py`
- `runtime/message_parser.py`
- `db/database.py`
- `db/service.py`
- `templates/registry.yaml`
- `_conf_schema.json`
