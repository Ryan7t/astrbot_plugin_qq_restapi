# QQ 用户身份标识说明（Union OpenID / Raw OpenID）

## 1. 为什么需要说明
在 QQ 官方平台中，同一个用户在不同场景（单聊、群聊、频道）会出现不同的 ID。  
如果不区分，会导致“同一用户被当成多个用户”，后续用户系统/权限系统会混乱。

本插件统一输出两个字段：
- **Union OpenID**：跨场景统一身份（建议作为“用户主 ID”）
- **Raw OpenID**：频道场景的原始用户 ID（用于频道相关接口或 @）

## 2. 字段定义
**Union OpenID**  
- 用途：统一身份识别（跨群聊/单聊/频道场景一致）  
- 特点：同一用户在不同场景保持一致  
- 建议：作为数据库“用户主键”

**Raw OpenID**  
- 用途：频道场景中真实的用户 ID（比如频道内 @、部分频道接口参数）  
- 特点：在频道场景中与 Union OpenID 不同；在群聊/单聊场景一般与 Union OpenID 相同  
- 建议：用于频道业务时使用，作为“场景内用户标识”

## 3. 四个场景的差异（核心结论）

| 场景 | Union OpenID | Raw OpenID | 说明 |
|------|-------------|------------|------|
| 单聊 (C2C) | 有 | = Union OpenID | 二者一致 |
| 群聊 | 有 | = Union OpenID | 二者一致 |
| 频道讨论组（文字子频道） | 有 | 与 Union 不同 | Raw OpenID 是频道用户 ID |
| 频道私聊 | 有 | 与 Union 不同 | Raw OpenID 是频道用户 ID |

## 4. 日志输出规则（本插件）
- **群聊/单聊**：只打印 `Union OpenID`  
- **频道讨论组/频道私聊**：打印 `Union OpenID` + `Raw OpenID`
 - **频道成员相关系统事件**：可能不会携带 `Union OpenID`，此时日志会显示 `Union OpenID=无`，但仍会输出 `Raw OpenID` 供排查

示例：
```
自动事件：group_add_robot 场景/scene=群聊/group Union OpenID=xxx 群ID=xxx 频道ID=无 子频道ID=无
自动事件：friend_add 场景/scene=单聊/c2c Union OpenID=xxx 群ID=无 频道ID=无 子频道ID=无
自动事件：... 场景/scene=频道讨论组/channel Union OpenID=xxx Raw OpenID=yyy 频道ID=zzz 子频道ID=aaa
```

## 5. 存储建议（最佳实践）
**建议同时存储 Union OpenID 与 Raw OpenID**，理由：
- Union OpenID 用于“统一用户身份”
- Raw OpenID 用于“频道场景的真实操作”

推荐字段（最小集合）：
- `union_openid`（主身份 ID）
- `raw_openid`（频道场景 ID，群/单聊可与 union 同值）
- `scene`（group / c2c / channel / channel_dm）
- `guild_id`（频道 ID，可空）
- `channel_id`（子频道 ID，可空）
- `last_seen_at`

如果暂时只存一个字段：  
- **只存 Union OpenID** 可满足大多数“用户系统”需求，但未来做频道功能时可能需要补 raw_openid。  

## 6. 自动事件里补齐 Union OpenID 的两种方案
背景：频道成员事件（如 `GUILD_MEMBER_ADD/REMOVE/UPDATE`）的事件体通常 **不包含** `union_openid`，只能拿到 `user.id`（即 Raw OpenID）。

### 方案A：消息事件缓存映射（轻量推荐）
思路：当用户在频道里发过消息时，消息事件里会带 `Union OpenID` + `Raw OpenID`。  
我们在内存中建立映射表 `raw_openid -> union_openid`，自动事件触发时用它补齐。

优点：
- 不额外请求接口，性能稳定
- 实现简单，风险小

缺点：
- 新成员从未发言时，无法补齐

适用：
- 日常日志与用户识别场景，已经足够

### 方案B：主动查询成员接口（更完整）
思路：自动事件触发后，调用官方接口：  
`GET /guilds/{guild_id}/members/{user_id}` 获取 `union_openid`，再缓存下来。

优点：
- 更完整，新成员未发言也能补齐

缺点：
- 需要权限、额外请求量，必须做缓存/限流

适用：
- 对“统一身份补齐”要求极高的业务

### 推荐做法
默认优先使用方案A；如后续业务确实需要完整数据，再新增开关启用方案B。
