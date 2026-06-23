# QQ REST API 插件自动事件说明文档

> **版本**: v1.0  
> **创建日期**: 2026-01-14  
> **状态**: 评审稿  
> **适用范围**: qq_restapi 插件自动事件与新用户欢迎逻辑  

---

## 1. 概述

### 1.1 文档目的
本文档用于清晰说明 qq_restapi 插件内的“自动事件”现状，包括事件清单、默认行为、处理流程与配置方式，方便开发、测试与运营统一理解。

### 1.2 适用范围
- 自动事件处理逻辑（`runtime/auto_events.py`）
- 自动事件配置（`templates/registry.yaml`）
- 插件开关配置（插件配置项）

### 1.3 关键结论
- 自动事件并不存历史，仅在触发时执行**日志记录**或**可选回复**。
- 默认仅有 **5 个事件**具备“自动回复”能力，其余事件仅记录日志。
- `new_user_welcome` 是一条**首次聊天欢迎逻辑**，不是平台系统事件。

---

## 2. 自动事件总览

### 2.1 事件分类
自动事件分为以下类别：
- 群聊关系事件（机器人入群/退群、群消息设置、普通群成员加入/退出）
- 单聊关系事件（好友添加/删除）
- 频道/子频道事件（创建/更新/删除）
- 频道成员事件（加入/更新/退出）
- 表态与审核事件
- 论坛事件
- 消息撤回事件

### 2.2 事件清单（按类别划分）

#### 2.2.1 表态事件
| 平台事件类型 | 自动事件 key | 默认行为 |
|---|---|---|
| `MESSAGE_REACTION_ADD` | `message_reaction_add` | 仅日志 |
| `MESSAGE_REACTION_REMOVE` | `message_reaction_remove` | 仅日志 |

#### 2.2.2 审核事件
| 平台事件类型 | 自动事件 key | 默认行为 |
|---|---|---|
| `MESSAGE_AUDIT_PASS` | `message_audit_pass` | 仅日志 |
| `MESSAGE_AUDIT_REJECT` | `message_audit_reject` | 仅日志 |

#### 2.2.3 论坛事件
| 平台事件类型 | 自动事件 key | 默认行为 |
|---|---|---|
| `OPEN_FORUM_THREAD_CREATE` | `open_forum_thread_create` | 仅日志 |
| `OPEN_FORUM_THREAD_UPDATE` | `open_forum_thread_update` | 仅日志 |
| `OPEN_FORUM_THREAD_DELETE` | `open_forum_thread_delete` | 仅日志 |
| `OPEN_FORUM_POST_CREATE` | `open_forum_post_create` | 仅日志 |
| `OPEN_FORUM_POST_DELETE` | `open_forum_post_delete` | 仅日志 |
| `OPEN_FORUM_REPLY_CREATE` | `open_forum_reply_create` | 仅日志 |
| `OPEN_FORUM_REPLY_DELETE` | `open_forum_reply_delete` | 仅日志 |

#### 2.2.4 其他事件
| 平台事件类型 | 自动事件 key | 默认行为 |
|---|---|---|
| `GROUP_ADD_ROBOT` | `group_add_robot` | 可自动回复 |
| `GROUP_DEL_ROBOT` | `group_del_robot` | 可自动回复 |
| `GROUP_MSG_RECEIVE` | `group_msg_receive` | 仅日志 |
| `GROUP_MSG_REJECT` | `group_msg_reject` | 仅日志 |
| `GROUP_MEMBER_ADD` | `group_member_add` | 可自动回复 |
| `GROUP_MEMBER_REMOVE` | `group_member_remove` | 仅日志 |
| `FRIEND_ADD` | `friend_add` | 可自动回复 |
| `FRIEND_DEL` | `friend_del` | 可自动回复 |
| `GUILD_CREATE` | `guild_create` | 仅日志 |
| `GUILD_UPDATE` | `guild_update` | 仅日志 |
| `GUILD_DELETE` | `guild_delete` | 仅日志 |
| `CHANNEL_CREATE` | `channel_create` | 仅日志 |
| `CHANNEL_UPDATE` | `channel_update` | 仅日志 |
| `CHANNEL_DELETE` | `channel_delete` | 仅日志 |
| `GUILD_MEMBER_ADD` | `guild_member_add` | 仅日志 |
| `GUILD_MEMBER_UPDATE` | `guild_member_update` | 仅日志 |
| `GUILD_MEMBER_REMOVE` | `guild_member_remove` | 仅日志 |
| `PUBLIC_MESSAGE_DELETE` | `channel_message_delete` | 仅日志 |
| `DIRECT_MESSAGE_DELETE` | `channel_dm_message_delete` | 仅日志 |

### 2.3 暂时禁用事件（代码注释保留）
以下事件已在代码中标注为“暂时禁用”，不会进入自动事件映射：
- `SUBSCRIBE_MESSAGE_STATUS`（订阅状态）
- `C2C_MSG_REJECT` / `C2C_MSG_RECEIVE`
- `AUDIO_START` / `AUDIO_FINISH` / `AUDIO_ON_MIC` / `AUDIO_OFF_MIC`
- `AUDIO_OR_LIVE_CHANNEL_MEMBER_ENTER` / `AUDIO_OR_LIVE_CHANNEL_MEMBER_EXIT`

---

## 3. 自动事件处理流程

### 3.1 处理流程图
```
收到事件
  └─ 判断是否在 AUTO_EVENT_MAP
     ├─ 否 -> 进入普通消息/其他流程
     └─ 是 -> 读取 auto_events 配置
           ├─ 记录日志
           ├─ 若为“仅日志”事件 -> 结束
           └─ 若为“可回复”事件:
                ├─ 场景过滤 (scenes)
                ├─ 启用校验 (enabled)
                ├─ 插件配置消息内容检查（为空则不发送）
                └─ 发送自动回复
```

### 3.2 “仅日志”与“可回复”的区别
- **仅日志**: 事件触发后仅记录日志，不会发送任何消息。
- **可回复**: 事件满足配置与开关条件时，会发送 `fallback_text` 文案。

当前**可回复**事件只有 4 个：
- `group_add_robot`
- `group_del_robot`
- `friend_add`
- `friend_del`

---

## 4. 配置说明

### 4.1 auto_events 配置（registry.yaml）
路径: `templates/registry.yaml`

配置结构示例：
```yaml
auto_events:
  group_add_robot:
    enabled: true
    template: ""
    fallback_text: "欢迎加入，本机器人已入群～"
    log: true
```

字段说明：
| 字段 | 说明 |
|---|---|
| enabled | 是否启用此自动事件 |
| template | 预留字段（当前未使用） |
| fallback_text | 自动回复文本 |
| log | 是否记录日志 |
| scenes | 可选，限制触发场景 |

### 4.2 插件配置消息（Plugin Config）
插件配置路径: `data/config/qq_restapi_config.json`  
Schema 路径: `qq_restapi/_conf_schema.json`

与以下自动事件直接相关：
| 自动事件 key | 插件配置字段 | 说明 |
|---|---|---|
| group_add_robot | group_add_robot_message | 机器人自己被拉进群时的欢迎 |
| group_member_add | group_member_add_message | 普通群成员加入群聊时的欢迎 |
| group_del_robot | enable_group_remove_notice | 机器人退群通知 |
| friend_add | friend_add_message | 好友添加欢迎 |
| friend_del | enable_friend_remove_notice | 好友删除通知 |

说明：
- 对 `group_add_robot` / `group_member_add` / `friend_add`：插件配置消息不为空才发送。
- `group_add_robot_message` 和 `group_member_add_message` 是两类事件：前者是机器人自己进群，后者是群里有普通用户进群。
- 其他事件仍遵循 `enabled=true` + 对应开关为 `true` 的规则。

### 4.3 日志分组开关（auto_event_log_groups）
插件配置路径: `data/config/qq_restapi_config.json`  
Schema 路径: `qq_restapi/_conf_schema.json`

说明：
- 插件配置优先级最高
- 若插件配置缺失该字段，则回退读取 `templates/registry.yaml` 中的默认值

配置结构示例：
```json
{
  "auto_event_log_groups": {
    "relation": true,
    "group_setting": true,
    "group_member": true,
    "guild": true,
    "channel": true,
    "guild_member": true,
    "message_delete": true,
    "reaction": true,
    "audit": true,
    "forum": true
  }
}
```

字段说明：
| 字段 | 说明 |
|---|---|
| relation | 机器人入群/退群、好友添加/删除日志分组 |
| group_setting | 群消息接收/拒收设置日志分组 |
| group_member | 普通群成员加入、退出日志分组 |
| guild | 频道创建、更新、删除日志分组 |
| channel | 子频道创建、更新、删除日志分组 |
| guild_member | 频道成员加入、更新、删除日志分组 |
| message_delete | 频道消息撤回、频道私信撤回日志分组 |
| reaction | 表态事件日志分组 |
| audit | 审核事件日志分组 |
| forum | 论坛事件日志分组 |

说明：
- 分组 `false` 时，该分组内事件将不输出日志。
- 分组配置缺失时，默认记录日志。

---

## 5. new_user_welcome 说明

### 5.1 定义
`new_user_welcome` 是“首次聊天欢迎逻辑”，不是平台事件，不在 `AUTO_EVENT_MAP` 中。

### 5.2 触发条件
以下条件全部满足时才触发：
- 当前事件 **不是**自动事件（即不在 `AUTO_EVENT_MAP`）
- 通过对话管理器判断该用户**没有历史会话**
- 插件配置 `new_user_welcome_message` 不为空

### 5.3 行为特点
- 发送 `fallback_text` 欢迎文案
- **不写入对话历史**（避免覆盖真实对话）
- 支持 `scenes` 限制触发场景（默认示例为 `group`）

---

## 6. 日志输出规则

日志字段会包含以下关键信息：
- `Union OpenID` / `Raw OpenID`
- 操作人 ID（如有）
- 群ID / 频道ID / 子频道ID
- 特殊事件补充信息（如撤回消息ID、审核ID、表态emoji_id等）

频道相关事件在日志中会同时打印 Union/Raw OpenID（若可用）。

---

## 7. 参考来源
- `runtime/auto_events.py`
- `runtime/message_parser.py`
- `templates/registry.yaml`
