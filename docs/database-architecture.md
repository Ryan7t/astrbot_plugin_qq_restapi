# QQ REST API 插件数据库架构设计（四表核心+日志表）

> **版本**: v2.1  
> **创建日期**: 2026-01-14  
> **状态**: 评审稿  
> **适用范围**: qq_restapi 插件业务层 SQLite 数据库  

---

## 1. 概述

### 1.1 文档目的
定义“四表核心 + 日志表”的数据库架构，用于支持平台四类场景（单聊/群聊/频道讨论组/频道私聊）的用户与场景数据存储，并保留频道体系元数据，为后续频道管理功能提供基础数据支撑。

### 1.2 适用范围
- 单聊（C2C）
- 群聊（Group）
- 频道讨论组（Channel）
- 频道私聊（Channel DM）

### 1.3 设计原则
| 原则 | 说明 |
|---|---|
| **简化优先** | 控制表数量，避免引入多余的中间表 |
| **四场景可区分** | 必须能明确区分四类场景的用户关系 |
| **Union OpenID 为主** | 跨场景统一身份，允许延迟补齐 |
| **只存当前状态** | 核心表不保存事件历史，仅维护最新快照 |
| **配置就地存储** | 频道配置放在频道表，减少额外表 |
| **日志独立** | 全量事件日志写入日志表，不影响核心表结构 |

---

## 2. 业务规则与约束

### 2.1 OpenID 类型差异
| 场景 | Union OpenID | Raw OpenID |
|---|---|---|
| 单聊 | 有 | = Union OpenID |
| 群聊 | 有 | = Union OpenID |
| 频道讨论组 | 自动事件可能无 Union OpenID | 有 |
| 频道私聊 | 自动事件可能无 Union OpenID | 有 |

**结论**: 频道场景必须允许 `union_openid` 为空，并在后续消息事件中补齐。

### 2.2 用户信息获取范围
| 场景 | 可获取信息 |
|---|---|
| 单聊/群聊 | 仅 Union OpenID |
| 频道讨论组/私聊 | Union OpenID、Raw OpenID、昵称、头像（按频道区分） |

### 2.3 频道体系结构
```
频道 (Guild)
├── 频道头像、名称、描述
├── 子频道 (Channel)
│   ├── 文字子频道 (type=0)
│   ├── 语音子频道 (type=2)
│   ├── 子频道分组 (type=4)
│   ├── 直播子频道 (type=10005)
│   ├── 应用子频道 (type=10006)
│   └── 论坛子频道 (type=10007)
└── 身份组 (Role)
    ├── 1: 全体成员（系统默认）
    ├── 2: 管理员（系统默认）
    ├── 4: 频道主/创建者（系统默认）
    ├── 5: 子频道管理员（系统默认）
    └── 自定义身份组...
```

### 2.4 权限与角色
- 成员对象中包含 `roles` 数组（角色 ID 列表）
- 本方案以 `roles_json` 原样保存角色数组
- 需要权限判断时，可直接解析 `roles_json`

### 2.5 频道私聊来源记录
- 只记录**当前来源频道**，不保留历史
- 字段存放于 `user_scene.source_guild_id/source_channel_id`

---

## 3. 架构总览

### 3.1 核心四表 + 日志表
| 表名 | 用途 |
|---|---|
| `user_identity` | Union OpenID 维度的全局用户表 |
| `user_scene` | 用户与场景关联 + 频道维度资料 |
| `guild` | 频道元数据 + 频道配置 |
| `channel` | 子频道元数据 |
| `event_log` | 全量事件日志（含自动事件） |

### 3.2 表关系图
```
         ┌────────────────────┐
         │   user_identity    │
         │  (union_openid PK) │
         └─────────┬──────────┘
                   │
                   ▼
         ┌────────────────────┐
         │     user_scene     │
         │  (场景/用户关系)    │
         └─────────┬──────────┘
                   │
                   ▼
         ┌────────────────────┐
         │       guild        │
         │    (频道元数据)     │
         └─────────┬──────────┘
                   │
                   ▼
         ┌────────────────────┐
         │      channel       │
         │   (子频道元数据)    │
         └────────────────────┘

         ┌────────────────────┐
         │     event_log      │
         │   (全量事件日志)    │
         └────────────────────┘
```

---

## 4. 表结构详细定义

### 4.1 user_identity - 全局用户表
**用途**: 统一记录用户主身份（Union OpenID），并预留基础信息字段。

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| union_openid | TEXT | PK | Union OpenID，跨场景唯一标识 |
| qq_number | TEXT | NULL | QQ号（预留） |
| avatar | TEXT | NULL | 头像URL（预留） |
| nickname | TEXT | NULL | 昵称（预留） |
| created_at | INTEGER | NOT NULL | 创建时间（秒） |
| last_seen_at | INTEGER | NULL | 最近活跃时间（秒） |

---

### 4.2 user_scene - 场景与用户关系表
**用途**: 统一承载四类场景的用户关系，并存储频道维度的昵称、头像与角色信息。

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| scene_id | INTEGER | PK | 场景关系主键 |
| scene_type | TEXT | NOT NULL | 场景类型：`c2c`/`group`/`channel`/`channel_dm` |
| union_openid | TEXT | FK | Union OpenID（频道自动事件可为空） |
| raw_openid | TEXT | NOT NULL | Raw OpenID/场景内用户ID |
| group_id | TEXT | NULL | 群ID（群聊） |
| guild_id | TEXT | NULL | 频道ID（频道讨论组/私聊） |
| channel_id | TEXT | NULL | 子频道ID（频道讨论组） |
| dm_id | TEXT | NULL | 频道私聊会话ID（如有） |
| source_guild_id | TEXT | NULL | 频道私聊来源频道ID |
| source_channel_id | TEXT | NULL | 频道私聊来源子频道ID |
| source_updated_at | INTEGER | NULL | 来源更新时间（秒） |
| username | TEXT | NULL | 频道用户资料: 用户名 |
| avatar | TEXT | NULL | 频道用户资料: 头像URL |
| nick | TEXT | NULL | 频道用户资料: 昵称 |
| bot | INTEGER | NULL | 是否机器人(1/0) |
| union_user_account | TEXT | NULL | 关联互联用户信息 |
| roles_json | TEXT | NULL | 角色ID列表(JSON数组字符串) |
| first_seen_at | INTEGER | NOT NULL | 首次见到时间（秒） |
| last_seen_at | INTEGER | NOT NULL | 最近见到时间（秒） |
| last_event_type | TEXT | NULL | 最近事件类型 |

**roles_json 示例**:
```json
["1", "2", "custom_role_id_123"]
```

---

### 4.3 guild - 频道表
**用途**: 存储频道元数据与频道级配置。

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| guild_id | TEXT | PK | 频道ID |
| name | TEXT | NULL | 频道名称 |
| icon | TEXT | NULL | 频道头像地址 |
| owner_id | TEXT | NULL | 创建人用户ID |
| owner | INTEGER | NULL | 机器人是否为创建人(1/0) |
| member_count | INTEGER | NULL | 成员数 |
| max_members | INTEGER | NULL | 最大成员数 |
| description | TEXT | NULL | 频道描述 |
| joined_at | INTEGER | NULL | 加入时间（秒） |
| config_json | TEXT | NULL | 频道管理配置(JSON) |
| last_seen_at | INTEGER | NULL | 最近更新时间（秒） |

---

### 4.4 channel - 子频道表
**用途**: 存储子频道元数据。

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| channel_id | TEXT | PK | 子频道ID |
| guild_id | TEXT | NOT NULL | 频道ID |
| name | TEXT | NULL | 子频道名称 |
| type | INTEGER | NULL | 子频道类型 |
| sub_type | INTEGER | NULL | 子频道子类型 |
| position | INTEGER | NULL | 排序值 |
| parent_id | TEXT | NULL | 所属分组ID |
| owner_id | TEXT | NULL | 创建人ID |
| private_type | INTEGER | NULL | 子频道私密类型 |
| speak_permission | INTEGER | NULL | 子频道发言权限 |
| application_id | TEXT | NULL | 应用子频道类型 |
| permissions | TEXT | NULL | 机器人拥有的子频道权限(字符串) |
| config_json | TEXT | NULL | 子频道管理配置(JSON) |
| last_seen_at | INTEGER | NULL | 最近更新时间（秒） |

---

### 4.5 event_log - 全量事件日志表
**用途**: 记录所有事件日志（包含自动事件），用于审计与排障。

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| log_id | INTEGER | PK | 日志主键 |
| log_level | TEXT | NOT NULL | 日志级别：`info`/`warn`/`error` |
| event_kind | TEXT | NOT NULL | 事件类别：`message`/`auto`/`system` |
| event_type | TEXT | NULL | 事件类型（如 `GUILD_MEMBER_ADD`） |
| scene_type | TEXT | NULL | 场景类型：`c2c`/`group`/`channel`/`channel_dm`/`guild` |
| union_openid | TEXT | NULL | Union OpenID |
| raw_openid | TEXT | NULL | Raw OpenID |
| group_id | TEXT | NULL | 群ID |
| guild_id | TEXT | NULL | 频道ID |
| channel_id | TEXT | NULL | 子频道ID |
| message_id | TEXT | NULL | 消息ID |
| event_id | TEXT | NULL | 事件ID |
| payload_json | TEXT | NULL | 原始事件数据(JSON字符串) |
| created_at | INTEGER | NOT NULL | 发生时间（秒） |

---

## 5. 数据流与处理逻辑

### 5.1 单聊场景 (C2C)
```
用户发送消息
  └─ 获取 Union OpenID
     ├─ user_identity upsert
     └─ user_scene upsert (scene_type=c2c)
```

### 5.2 群聊场景 (Group)
```
用户发送消息
  └─ 获取 Union OpenID
     ├─ user_identity upsert
     └─ user_scene upsert (scene_type=group + group_id)
```

### 5.3 频道讨论组 (Channel)
```
自动事件: 仅 Raw OpenID
  └─ user_scene upsert (union_openid=NULL)

用户发消息: Union OpenID + Raw OpenID
  ├─ user_identity upsert
  └─ user_scene 回填 union_openid + 频道资料 + roles_json
```

### 5.4 频道私聊 (Channel DM)
```
用户发送私聊
  ├─ user_identity upsert
  ├─ user_scene upsert (scene_type=channel_dm + guild_id)
  └─ 更新 source_guild_id/source_channel_id
```

### 5.5 日志写入（全部事件）
```
事件进入适配器
  └─ 写入 event_log（自动事件/消息事件/系统事件）
```

---

## 6. 索引设计

| 表 | 索引 | 用途 |
|---|---|---|
| user_scene | 唯一索引（按场景类型） | 保证同场景唯一 |
| user_scene | idx_user_scene_union | 按 Union OpenID 查询 |
| channel | idx_channel_guild | 按频道查询子频道 |
| event_log | idx_event_log_time | 按时间范围查询 |
| event_log | idx_event_log_type | 按事件类型查询 |
| event_log | idx_event_log_scene | 按场景类型查询 |
| event_log | idx_event_log_guild | 按频道查询日志 |
| event_log | idx_event_log_union | 按用户查询日志 |

---

## 7. 不存储的数据说明
| 数据类型 | 管理方式 |
|---|---|
| 对话/消息记录 | AstrBot 框架对话管理模块 |
| 群聊详细信息 | 官方 API 无法获取，不存储 |

---

## 8. 完整建表 SQL（带中文注释）

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS user_identity (
    union_openid TEXT PRIMARY KEY, -- Union OpenID，跨场景统一用户ID
    qq_number TEXT, -- QQ号(预留)
    avatar TEXT, -- 头像URL(预留)
    nickname TEXT, -- 昵称(预留)
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')), -- 创建时间(秒)
    last_seen_at INTEGER -- 最近活跃时间(秒)
);

CREATE TABLE IF NOT EXISTS user_scene (
    scene_id INTEGER PRIMARY KEY AUTOINCREMENT, -- 场景关系主键
    scene_type TEXT NOT NULL CHECK (scene_type IN ('c2c','group','channel','channel_dm')), -- 场景类型
    union_openid TEXT, -- Union OpenID(可为空)
    raw_openid TEXT NOT NULL, -- Raw OpenID/场景内用户ID
    group_id TEXT, -- 群ID(群聊)
    guild_id TEXT, -- 频道ID(频道讨论组/私聊)
    channel_id TEXT, -- 子频道ID(频道讨论组)
    dm_id TEXT, -- 频道私聊会话ID(如有)
    source_guild_id TEXT, -- 私聊来源频道ID
    source_channel_id TEXT, -- 私聊来源子频道ID
    source_updated_at INTEGER, -- 来源更新时间(秒)
    username TEXT, -- 频道用户资料: 用户名
    avatar TEXT, -- 频道用户资料: 头像URL
    nick TEXT, -- 频道用户资料: 昵称
    bot INTEGER, -- 是否机器人(1/0)
    union_user_account TEXT, -- 关联互联用户信息
    roles_json TEXT, -- 角色ID列表(JSON数组字符串)
    first_seen_at INTEGER NOT NULL DEFAULT (strftime('%s','now')), -- 首次见到时间(秒)
    last_seen_at INTEGER NOT NULL DEFAULT (strftime('%s','now')), -- 最近见到时间(秒)
    last_event_type TEXT, -- 最近事件类型
    FOREIGN KEY (union_openid) REFERENCES user_identity(union_openid)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_scene_c2c
    ON user_scene(scene_type, raw_openid)
    WHERE scene_type='c2c';

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_scene_group
    ON user_scene(scene_type, raw_openid, group_id)
    WHERE scene_type='group';

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_scene_channel
    ON user_scene(scene_type, raw_openid, guild_id, channel_id)
    WHERE scene_type='channel';

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_scene_channel_dm
    ON user_scene(scene_type, raw_openid, guild_id)
    WHERE scene_type='channel_dm';

CREATE INDEX IF NOT EXISTS idx_user_scene_union ON user_scene(union_openid);
CREATE INDEX IF NOT EXISTS idx_user_scene_group ON user_scene(group_id);
CREATE INDEX IF NOT EXISTS idx_user_scene_guild ON user_scene(guild_id);
CREATE INDEX IF NOT EXISTS idx_user_scene_channel ON user_scene(channel_id);

CREATE TABLE IF NOT EXISTS guild (
    guild_id TEXT PRIMARY KEY, -- 频道ID
    name TEXT, -- 频道名称
    icon TEXT, -- 频道头像地址
    owner_id TEXT, -- 创建人用户ID
    owner INTEGER, -- 机器人是否为创建人(1/0)
    member_count INTEGER, -- 成员数
    max_members INTEGER, -- 最大成员数
    description TEXT, -- 频道描述
    joined_at INTEGER, -- 加入时间(秒)
    config_json TEXT, -- 频道管理配置(JSON)
    last_seen_at INTEGER -- 最近更新时间(秒)
);

CREATE TABLE IF NOT EXISTS channel (
    channel_id TEXT PRIMARY KEY, -- 子频道ID
    guild_id TEXT NOT NULL, -- 频道ID
    name TEXT, -- 子频道名称
    type INTEGER, -- 子频道类型
    sub_type INTEGER, -- 子频道子类型
    position INTEGER, -- 排序值
    parent_id TEXT, -- 所属分组ID
    owner_id TEXT, -- 创建人ID
    private_type INTEGER, -- 子频道私密类型
    speak_permission INTEGER, -- 子频道发言权限
    application_id TEXT, -- 应用子频道类型
    permissions TEXT, -- 机器人拥有的子频道权限(字符串)
    config_json TEXT, -- 子频道管理配置(JSON)
    last_seen_at INTEGER, -- 最近更新时间(秒)
    FOREIGN KEY (guild_id) REFERENCES guild(guild_id)
);

CREATE INDEX IF NOT EXISTS idx_channel_guild ON channel(guild_id);

CREATE TABLE IF NOT EXISTS event_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT, -- 日志主键
    log_level TEXT NOT NULL, -- 日志级别: info/warn/error
    event_kind TEXT NOT NULL, -- 事件类别: message/auto/system
    event_type TEXT, -- 事件类型(如 GUILD_MEMBER_ADD)
    scene_type TEXT, -- 场景类型
    union_openid TEXT, -- Union OpenID
    raw_openid TEXT, -- Raw OpenID
    group_id TEXT, -- 群ID
    guild_id TEXT, -- 频道ID
    channel_id TEXT, -- 子频道ID
    message_id TEXT, -- 消息ID
    event_id TEXT, -- 事件ID
    payload_json TEXT, -- 原始事件数据(JSON字符串)
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')) -- 发生时间(秒)
);

CREATE INDEX IF NOT EXISTS idx_event_log_time ON event_log(created_at);
CREATE INDEX IF NOT EXISTS idx_event_log_type ON event_log(event_type);
CREATE INDEX IF NOT EXISTS idx_event_log_scene ON event_log(scene_type);
CREATE INDEX IF NOT EXISTS idx_event_log_guild ON event_log(guild_id);
CREATE INDEX IF NOT EXISTS idx_event_log_union ON event_log(union_openid);
```

---

## 9. 参考来源
- `docs/qq官方平台文档/openapi/user/model.md`
- `docs/qq官方平台文档/openapi/member/model.md`
- `docs/qq官方平台文档/server-inter/channel/manage/guild/model.md`
- `docs/qq官方平台文档/server-inter/channel/manage/channel/model.md`
- `docs/qq官方平台文档/server-inter/channel/role/member/role_model.md`
