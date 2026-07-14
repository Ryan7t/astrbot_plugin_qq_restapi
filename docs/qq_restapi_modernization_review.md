# QQ REST API 插件现代化对比与实施记录

> 目的：记录 `qq_restapi` 插件与 `wanbot` 私有命令、ElainaBot_v2、AstrBot 本体及 QQ/AstrBot 官方规则的对比结论，并跟踪已经落地的现代化改造。
>
> 初始日期：2026-06-23；状态复核：2026-07-14

## 参考来源

- AstrBot 插件开发指南：<https://docs.astrbot.app/dev/star/plugin-new.html>
- AstrBot 处理消息事件：<https://docs.astrbot.app/dev/star/guides/listen-message-event>
- AstrBot 消息发送：<https://docs.astrbot.app/dev/star/guides/send-message>
- AstrBot 会话控制：<https://docs.astrbot.app/dev/star/guides/session-control>
- QQ 官方消息事件：<https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/send-receive/event.html>
- QQ 官方发送消息：<https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/send-receive/send.html>
- QQ 官方 Markdown 消息：<https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/type/markdown.html>
- QQ 官方消息按钮：<https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/trans/msg-btn.html>
- ElainaBot_v2 本地参考仓库：`D:\code\bot\ElainaBot_v2`
- AstrBot 本体本地代码：`D:\code\bot\AstrBotLauncher\AstrBot\astrbot`

说明：当前插件目录里的 `docs/astrbot_docs` 和 `docs/qq官方平台文档` 年久失修，后续判断应以以上官方链接和本地 AstrBot 实际代码为准。

## 当前已对齐的结论

当前插件不应该整体迁移到 ElainaBot_v2 架构。更合理的路线是：继续保持 AstrBot 平台适配器身份，只把 v2 中“更成熟的 QQ 传输、事件解析、发送细节”拆出来吸收。

本轮最初确定的三件事（现均已完成）：

1. 把 `wanbot` 里“优先 Markdown，失败后普通文本重试”的写法下沉到 `qq_restapi` 核心发送层。
2. 默认接入 `GROUP_MESSAGE_CREATE` 全量群消息：QQ 管理后台发来什么，插件就正常解析、提交给 AstrBot、并确保对话数据不遗漏。
3. 补齐自动事件日志分组开关，尤其是频道成员加入/删除/更新、频道/子频道、消息撤回等事件。

本轮初始范围明确不做（其中全量群回复策略后来作为第三阶段独立完成）：

- 不做群白名单。
- 不做群备注/群别名。
- 不做“仅记录插件日志且完全不进入 AstrBot”的全量群消息模式。
- 不做 `full_group_message.enabled` 这种插件侧开关。
- 不采用旧草案的 `at_self`、`log_only`、`all` 命名；第三阶段改为 `full_group_reply` 五种明确模式。
- 不在本阶段重构按钮消息整体体系。

## 第一阶段实现状态

> 更新时间：2026-06-23

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| Markdown 优先发送 | 已实现 | `QQRestAPISender.send_text_prefer_markdown()` 统一封装：先 `markdown.content`，失败后普通文本。 |
| 普通 `reply()` / `send()` | 已实现 | 默认走 Markdown 优先；显式 `use_markdown=False` 时仍强制纯文本。 |
| `send_by_session()` | 已实现 | WSS/Webhook 两个适配器都改为复用 Markdown 优先发送。 |
| 全量群消息解析 | 已实现 | 新增 `GROUP_MESSAGE_CREATE`，解析 `mentions`、`message_scene`、`is_at_self`、`is_at_all` 等字段。 |
| 全量群消息唤醒策略 | 第一阶段实现为 `framework_default` | 默认不伪造 @，不设置 `event.is_at_or_wake_command=True`，普通全量消息只进入插件 handler 写上下文，不触发默认 LLM 回复。第三阶段可通过 `full_group_reply.mode` 改变非 @ 回复策略。 |
| 全量群消息存储兜底 | 已实现 | 非 @、非 @全体、非唤醒词的全量群消息由插件消息事件 handler 补写一条 `user` 历史；明显会进入框架 LLM 的消息交给 AstrBot 自己保存，避免重复当前消息。 |
| Union OpenID 默认优先 | 已实现 | `use_union_id_for_group`、`use_union_id_for_channel` 默认改为 `true`；显式配置为 `false` 时仍尊重用户配置。 |
| 自动事件日志分组 | 已实现 | 补齐 `relation`、`group_setting`、`guild`、`channel`、`guild_member`、`message_delete` 等分组，`GUILD_MEMBER_UPDATE` 纳入 `guild_member`。 |
| 群成员入群事件 | 已实现 | 新增 `GROUP_MEMBER_ADD`、`GROUP_MEMBER_REMOVE` 解析；`group_member_add_message` 为空时只记录日志，配置后可发送普通群成员入群欢迎。 |
| 按钮发送/存储重构 | 未实现 | 仍按后续专项处理；当前仅保留既有按钮能力。 |

## 引用与 @ 发送人实现状态

> 更新时间：2026-06-24

详细兼容性说明见：[QQ Markdown、引用与 @ 兼容性说明](qq_markdown_quote_at_compatibility.md)。

AstrBot 本体的“回复时引用发送人消息”和“回复时 @ 发送人”是在结果装饰阶段处理的。非流式普通回复、非流式分段回复会进入该阶段；流式输出会跳过该阶段，因此流式回复不承诺引用/@，插件会继续输出 warning 提醒关闭流式。

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 非流式引用原消息 | 已实现 | `Reply` 组件会被转成 QQ `message_reference`。只要带引用，当前插件强制普通文本发送，避免 QQ 客户端重复渲染 `Markdown + message_reference`。 |
| 非流式分段回复引用 | 已实现 | AstrBot 分段回复只会把 `Reply`/`At` 放到第一段；因此只有第一段可能带引用。当前策略下第一段会普通文本发送，后续分段仍可 Markdown 优先。 |
| @ 发送人 | 已实现 | 不带引用时，`At` 渲染为 QQ 官方 `<qqbot-at-user id="" />` 并走 Markdown。 |
| 引用 + @ | 已实现取舍 | 优先保留引用，忽略 @，普通文本发送。这样避免 Markdown 正文重复，也避免普通文本里显示裸 ID。 |
| 流式输出引用/@ | 不支持 | 流式输出跳过结果装饰阶段，框架不会稳定插入 `Reply`/`At`。 |

简化后的发送策略：

| 消息链 | 当前处理 |
| --- | --- |
| 无引用、无 @ | Markdown 优先，失败后普通文本兜底。 |
| 只有 @ | Markdown + `<qqbot-at-user id="用户ID" />`。 |
| 只有引用 | 普通文本 + `message_reference`。 |
| 引用 + @ | 普通文本 + `message_reference`，忽略 @。 |

## 第二阶段实现状态

> 更新时间：2026-06-23

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| WSS/Webhook 共享分发入口 | 已实现 | 新增 `runtime/dispatch.py`，两个适配器收到 payload 后都走 `handle_qq_payload()`，统一解析、事件日志、自动事件、欢迎、去重和 `commit_event()`。 |
| 基础去重 | 已实现 | 按 `qq_event_id` 优先，其次按 `message_id + event_type + session_id` 去重；TTL 5 分钟，最多保留 4096 个 key。用于避免 WSS 重连、Webhook 重试或双入口误开时重复写入/重复触发。 |
| WSS READY/RESUMED 过滤 | 已实现 | Gateway 的 `READY` 只用于记录 `session_id`，`RESUMED` 只记录恢复成功，不再作为普通事件交给 AstrBot。 |
| WSS resume/reconnect | 已实现 | 收到 `INVALID_SESSION` 时遵循 QQ 返回的 `d` 判断是否可恢复；可恢复则保留 session/seq 走 resume，不可恢复则清空后重新 identify。`RECONNECT` 会主动重连。 |
| WSS 背压 | 已实现 | WSS 事件进入有界队列，默认最多等待 256 条；下游处理变慢时不再无限制创建任务，同时保持事件处理顺序。 |
| WSS/Webhook 提交一致性 | 已实现并经实机验证 | 两个入口都只把有效群/私聊消息提交给 AstrBot；生命周期、频道变更、审核、表态等系统事件由自动事件逻辑记录/处理，不再额外混入普通消息流水线。WSS 与 Webhook 两种接入模式均已完成实际运行验证。 |

## 几个容易混淆的词

| 说法 | 通俗解释 | 本次结论 |
| --- | --- | --- |
| Markdown 优先发送 | 机器人要发一段文字时，先按 QQ 原生 Markdown 发；如果 QQ 返回失败，再按普通文本发。 | 已放到核心发送层。 |
| 普通文本兜底 | Markdown 发不出去时，至少把同样内容作为普通文字发出去，不让用户收不到回复。 | 已实现。 |
| 按钮降级 | 如果“Markdown + 按钮”失败，先改成“Markdown 无按钮”；如果还失败，再普通文本。 | 后续按钮专项做；当前文档先记录原则。 |
| `prefer_markdown_for_text` | 这是之前草案里的配置名，意思只是“普通文字优先用 Markdown 发”。 | 不作为当前用户配置项。当前阶段直接默认启用 Markdown 优先发送。 |
| `dispatch_mode` | 之前草案里指“全量群消息收到后，插件再决定是只记日志、只处理 @、还是全部当作 @ 处理”。 | 当前阶段删除这个设计。后续可以作为可选增强重新加入。 |
| `at_self` | 全量群消息已经收到，但只有消息真的 @ 机器人时，才让它像普通 @ 消息一样触发回复。 | 当前阶段不做，后续可作为插件侧模式。 |
| `log_only` | 全量群消息只写插件日志/插件数据库，不进入 AstrBot 消息处理流水线，也不触发 LLM。 | 当前阶段不做，后续可作为插件侧模式。 |
| `all` / `all_as_at` | 收到的每一条全量群消息都当作 @ 机器人来处理，也就是都可能触发 AstrBot 默认 LLM 回复。 | 第三阶段已作为可选配置实现，默认不启用。 |

## “交给 AstrBot”到底是什么意思

这里之前写得不够清楚，需要拆成三层：

| 层级 | 通俗解释 | 会不会回复 |
| --- | --- | --- |
| 插件收到 QQ payload | WSS/Webhook 收到了 QQ 发来的原始事件。 | 不会，这时还只是原始数据。 |
| `commit_event(event)` 交给 AstrBot | 插件把解析好的 `QQRestAPIEvent` 放进 AstrBot 事件队列。之后会经过唤醒检查、白名单、会话状态、限流、插件处理、LLM、发送回复等流水线。 | 不一定。 |
| 当作 @ 消息处理 | 不只是进入队列，还要让这条群消息通过 AstrBot 的唤醒检查，效果接近用户真的 @ 了机器人。 | 通常会触发默认 LLM 回复，除非被其他配置或插件拦截。 |

本地 AstrBot 代码里，`commit_event()` 只是 `self._event_queue.put_nowait(event)`。进入队列之后，`WakingCheckStage` 会检查群消息是否满足以下条件之一：

- @ 了机器人；
- @ 全体且未被配置忽略；
- 引用了机器人的消息；
- 命中了唤醒词；
- 命中了某个插件 handler 的过滤条件；
- 私聊消息且未要求唤醒词。

所以，“交给 AstrBot”准确地说是“进入 AstrBot 消息处理流水线”，不等于“一定回复”。“全部当作 @ 消息进行处理和回复”更准确地说是 `all_as_at` 模式：全量群消息不只是进入流水线，还会被主动标记成已唤醒，从而走默认 LLM 回复逻辑。第三阶段已把它做成可选配置，默认仍然是 `normal`。

二开注意：当前插件为了让非 @ 全量群消息也能写入上下文，注册了一个低优先级 handler，并使用自定义过滤器限定只命中 `qq_restapi` / `qq_restapi_webhook` 的 `GROUP_MESSAGE_CREATE`。AstrBot 的 `WakingCheckStage` 会因为“有 handler 命中”把 `event.is_wake` 置为 `True`，表示这条消息没有被门卫直接丢弃。但插件不会把 `event.is_at_or_wake_command` 置为 `True`。默认 LLM 回复链路主要看 `is_at_or_wake_command`，所以非 @ 全量消息仍不会触发默认回复。二开插件如果想判断“用户是否真的在叫机器人”，应优先看 `event.is_at_or_wake_command`，不要只看 `event.is_wake`。

## 最新规则对当前设计的影响

| 规则/能力 | 官方现状 | 对插件的影响 |
| --- | --- | --- |
| 自定义 Markdown | QQ 官方文档写明：2026/04/23 后，单聊、群聊自定义 Markdown 开放给所有机器人；频道场景仍可能有额外限制。 | 统一按“先 Markdown，失败再普通文本”处理。频道也不单独分支，因为普通文本兜底已经能覆盖失败场景。 |
| Markdown 模板消息 | 官方文档仍保留 `custom_template_id + params` 示例。 | 当前 `reply_markdown()`、`reply_markdown_aj()`、模板 registry 不能删，只是不再作为默认文本发送路径。 |
| 消息按钮 | 官方文档写明按钮挂在 Markdown 消息底部，单聊/群聊自定义按钮开放，频道仍可能有权限差异。 | 按钮不能当成普通 Markdown 直接合并处理。后续专项重构发送逻辑，当前阶段先不动按钮体系。 |
| 被动回复频控 | QQ 官方发送消息文档明确单聊、群聊被动回复有效时间和次数有限制。 | 核心发送层要继续保留 `msg_id`/`event_id`，并使用 `msg_seq` 避免重复回复。 |
| 主动推送 | QQ 官方发送消息页提示主动推送能力有严格限制。 | `send_by_session()` 可以走同一套 Markdown 优先发送，但不把主动推送包装成无限制能力。 |
| 全量群消息 | 群聊管理者可在 QQ 后台切换机器人接收模式。 | 插件端不提供开关或白名单；只要收到 `GROUP_MESSAGE_CREATE`，就按普通群消息进入 AstrBot 处理和存储链路。 |

## AstrBot 按钮存储核实结果

已经查看本地 AstrBot 本体代码，结论是：AstrBot 当前没有把 QQ 按钮作为通用消息组件存入对话历史。

| 核查点 | 本地代码现状 | 结论 |
| --- | --- | --- |
| 通用消息组件 | `astrbot/core/message/components.py` 的 `ComponentType` 有 `Plain`、`Image`、`At`、`Reply`、`Json`、`Unknown` 等，没有 `Button` 或 `Keyboard`。 | 按钮不是 AstrBot 通用 `MessageChain` 的一等组件。 |
| Markdown 标记 | `astrbot/core/message/message_event_result.py` 的 `MessageChain` 有 `use_markdown_`。 | AstrBot 能表达“这条回复尝试用 Markdown 发”，但不能表达“这条消息带哪些按钮”。 |
| QQ 官方发送侧 | `astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py` 的发送函数参数里有 `keyboard`，但它是 QQ 发送 payload 参数。 | 按钮存在于发送侧 payload，不进入通用聊天记录结构。 |
| QQ 官方接收侧 | 本体 QQ 官方适配器主要把文本、图片、语音、视频、文件转成 `MessageChain`。 | 没看到按钮结构被解析为历史组件。 |
| 当前插件按钮点击 | `runtime/message_parser.py` 里 `INTERACTION_CREATE` 会取 `button_data`，然后转成 `Plain(content)`。 | 用户点按钮后，按钮回调可以变成一段普通文本进入 AstrBot；但原始按钮结构本身不会作为按钮格式进入对话历史。 |
| 对话历史结构 | `astrbot/core/conversation_mgr.py` 主要保存 OpenAI 风格的 `role/content`。 | 历史里没有独立按钮 schema。 |

因此，后续如果要完整重构“Markdown 目标消息 + 按钮目标消息”的发送和存储，需要单独设计：

| 后续重构点 | 说明 |
| --- | --- |
| 发送侧 | 支持“Markdown + 按钮”失败后先降级为“Markdown 无按钮”，再降级为普通文本。 |
| 接收侧 | `INTERACTION_CREATE` 除了转成普通文本，也保留按钮 ID、按钮 data、用户 ID、场景、原消息 ID。 |
| 存储侧 | 后续必须能在聊天记录中看到“用户点了哪个按钮”。实现上需要额外存 metadata，或者新增类似 `ButtonInteraction` 的组件。 |
| 当前阶段 | 不做按钮存储结构重构，只记录这个结论，避免和 Markdown 优先发送混在一起。 |

## 当前插件、wanbot、v2 的具体对比

| 维度 | 当前 `qq_restapi` 插件 | `wanbot` 3cd7d78 | ElainaBot_v2 | 建议接入方式 |
| --- | --- | --- | --- | --- |
| 定位 | AstrBot 平台适配器插件，复用 AstrBot LLM、插件、会话管理。 | 私有业务命令包。 | 独立 QQ Bot 框架。 | 继续保持 AstrBot 适配器定位。 |
| WSS/Webhook | 已有 `qq_restapi` WSS 和 `qq_restapi_webhook` 两个适配器。 | 不处理传输层。 | WSS/Webhook 更完整，支持 ACK、恢复、背压等。 | 保留两个 AstrBot 适配器，但复用同一套事件处理函数。 |
| 默认文本发送 | LLM/streaming 结果已部分启用 Markdown 优先；普通 `reply()` 仍偏纯文本。 | 命令里手写“Markdown 失败后纯文本”。 | 发送器统一构造 payload。 | 把 `wanbot` 模式下沉到 `QQRestAPIEvent._send_text_reply()` 和 `send_by_session()`。 |
| Markdown 模板/AJ | 有 `reply_markdown()`、`reply_markdown_aj()`、template registry。 | 仍有部分旧模板命令。 | 更偏模板文件，不保留 AJ 一等接口。 | 保留当前模板/AJ API，标为显式高级能力。 |
| 按钮 | `QQRestAPISender.rows/button()` 可构建 keyboard；随 Markdown 一起发。 | 少量命令仍依赖模板按钮。 | `build_keyboard()` 更完整。 | 当前阶段不重构按钮；后续按“Markdown 有按钮 -> Markdown 无按钮 -> 普通文本”重构。 |
| 事件覆盖 | 当前解析事件很多：频道、子频道、论坛、审核、表态、音频、撤回等。 | 不处理平台事件。 | 全量群消息和分发更成熟。 | 保留当前插件事件覆盖优势；补齐 `GROUP_MESSAGE_CREATE`。 |
| 全量群消息 | 未明确支持 `GROUP_MESSAGE_CREATE` 常量和解析。 | 不处理。 | 支持 `GROUP_MESSAGE_CREATE`。 | 默认接入：收到就解析、记录身份、提交给 AstrBot。 |
| AstrBot 对话存储 | 非 LLM 回复时插件有 `_store_history_if_needed()`；LLM 场景由 AstrBot 内部保存。 | 业务命令只关心回复。 | 自己有日志库，不依赖 AstrBot。 | 全量群消息不能只写插件 event_log，要保证进入 AstrBot 对话历史链路。 |
| 自动事件日志开关 | 只有 `reaction`、`audit`、`forum` 分组。 | 不处理。 | 有自己的 lifecycle 日志。 | 补充分组：`guild`、`channel`、`guild_member`、`message_delete`、`group_setting` 等。 |

## Markdown 优先发送应如何下沉

### 当前问题

现在业务命令如果想要漂亮排版，需要自己写两份发送逻辑：

```python
message_id = await event.reply(content=markdown_text, use_markdown=True)
if not message_id:
    await event.reply(content=plain_text)
```

这会导致：

- 每个命令重复实现降级逻辑；
- LLM 回复和普通插件回复行为不一致；
- 如果未来错误码、按钮降级策略变化，需要改很多业务命令；
- 私有命令包和公共适配器耦合过深。

### 当前阶段的核心行为

| 场景 | 第一选择 | 失败后 |
| --- | --- | --- |
| 普通文字，无按钮 | `msg_type=2` + `markdown.content` | `msg_type=0` + `content` |
| LLM/streaming 文字 | `msg_type=2` + `markdown.content` | `msg_type=0` + `content` |
| 频道文字 | 同样先 Markdown | 失败后普通文本，不单独做频道特殊分支 |
| 显式 `use_markdown=False` | 纯文本 | 不再 Markdown |
| 显式 `reply_markdown()` | Markdown 模板 | 不自动改成 AJ 或普通 Markdown |
| 显式 `reply_markdown_aj()` | AJ 模板 | 不自动改成普通 Markdown |
| 图片/语音/视频/ARK | 原逻辑 | 不纳入 Markdown 优先 |

当前阶段不新增复杂用户配置。简单说：普通文字默认先按 Markdown 发，失败就按普通文字发。

### 按钮相关先记录原则

按钮不在当前优化阶段内，但未来重构发送逻辑时按这个顺序降级：

1. `Markdown + 按钮`
2. `Markdown 无按钮`
3. `普通文本`

也就是说，按钮失败时第一降级不是直接纯文本，而是先保留 Markdown 排版、去掉按钮。

### 可复用当前已有代码

当前 `runtime/sender.py` 已有：

- `send_markdown_content()`
- `send_plain()`
- `send_text_prefer_markdown()`
- `should_downgrade_markdown_to_plain()`
- `_MARKDOWN_FALLBACK_ERROR_CODES`

当前 `runtime/qq_restapi_event.py` 已有：

- `_send_text_reply()`
- `_should_prefer_markdown_for_default_send()`
- streaming Markdown 安全切分
- `_qq_restapi_force_plain_send` 临时开关

因此这不是推倒重写，而是把“触发 Markdown 优先”的条件从“主要 LLM 结果”扩大为“核心文本发送默认行为”。第一阶段已经按这个方向落地。

## 全量群消息如何适配 AstrBot

### 关键口径

全量群消息是否推送由群聊管理者在 QQ 机器人管理后台配置。插件端不提供“只听 @/全量”的接收开关、群白名单或完全绕过 AstrBot 的仅日志模式；收到消息后的主动回复行为由 `full_group_reply` 控制。

插件要做的是：

1. WSS/Webhook 收到 `GROUP_MESSAGE_CREATE`。
2. 解析成和普通群消息一致的 `AstrBotMessage`。
3. 使用稳定的群会话 ID，让它复用同一个 AstrBot 群会话。
4. 使用跨场景用户身份 ID 记录发送者。
5. 正常 `commit_event()` 给 AstrBot。
6. 确保 AstrBot 对话数据能记录这些消息，不因为事件类型不同而遗漏。

第一阶段已经确认选择 `framework_default`：只接入、提交、写入上下文，不强制每条全量群消息唤醒回复。第三阶段保留这个默认行为，并新增 `full_group_reply.mode` 作为可选回复策略。

### 接入行为

| 情况 | 插件行为 |
| --- | --- |
| QQ 后台配置为仅 @ | 插件会收到 `GROUP_AT_MESSAGE_CREATE`，按当前群 @ 消息处理。 |
| QQ 后台切换为全量群消息 | 插件会收到 `GROUP_MESSAGE_CREATE`，按普通群消息处理。 |
| 后台从仅 @ 切到全量 | 插件无需改配置，事件类型变化后仍正常解析和写入。 |
| 后台从全量切回仅 @ | 插件无需改配置，收不到的消息自然不会处理。 |
| 群消息没有 @ 机器人 | 如果 QQ 后台已经发给插件，就正常进入 AstrBot 事件链路；默认 `normal` 只补写上下文，其他 `full_group_reply` 模式可主动触发回复。 |

### 不再使用这些配置

| 旧草案配置 | 处理 |
| --- | --- |
| `full_group_message.enabled` | 删除。是否接收由 QQ 后台决定。 |
| `full_group_message.dispatch_mode` | 删除。第三阶段改用更明确的 `full_group_reply.mode`。 |
| `full_group_message.group_whitelist` | 删除。不做群白名单。 |
| `ignore_at_other_bot` / `ignore_at_other_user` | 当前阶段不做。 |
| `ignore_bot_sender` | 当前阶段不做。 |

### 当前支持的全量群消息模式

第三阶段已提供 `full_group_reply.mode`，默认仍然是只入库不主动回复：

| 模式 | 行为 | 适合场景 |
| --- | --- | --- |
| `normal` | 收到全量群消息后正常 `commit_event()` 并写入上下文；非 @ 不主动触发默认 LLM。 | 默认采用。 |
| `random_reply` | 非 @ 全量群消息按概率触发 AstrBot 默认 LLM 回复。 | 低成本随机接话。 |
| `smart_reply` | 每条非 @ 全量群消息都调用判断模型，由模型决定是否自然接话。 | 小群或低消息量群，希望尽量完整判断。 |
| `smart_random` | 先抽样，再让判断模型决定是否自然接话。 | 活跃群里控制模型调用成本。 |
| `all_as_at` | 每条收到的全量群消息都会尝试触发 AstrBot 默认 LLM 回复。 | 小群测试或希望机器人参与全部对话。 |

默认仍采用 `normal`，也就是原来的 `framework_default` 行为。如果启用 `all_as_at`，插件会把非 @ 全量群消息主动标记成已唤醒，让它进入 AstrBot 默认 LLM 回复流程；这不同于仅仅 `commit_event()`。

### 第三阶段：全量群消息回复模式（已实现）

> 这一段是第三阶段开发规格与实现说明。目标是让全量群消息不只是“能入库”，还可以按配置决定是否主动参与群聊。实现时仍然只改 `qq_restapi` 插件，不修改 AstrBot 本体。详细配置和使用规则见：[全量群消息回复模式说明](full_group_reply_modes.md)。

当前已新增一个明确的全量群消息回复模式配置，例如：

```yaml
full_group_reply:
  mode: normal
  random_probability: 0.05
  random_cooldown_seconds: 0
  smart_sample_probability: 0.2
  smart_cooldown_seconds: 60
  smart_judge_provider_id: ""
  smart_judge_timeout_seconds: 8
  smart_recent_context_messages: 20
  smart_judge_prompt: ""
  per_group_ordered_decision: true
  max_pending_per_group: 32
```

配置含义如下：

| 配置 | 通俗解释 | 建议默认值 |
| --- | --- | --- |
| `mode` | 全量群消息回复模式。 | `normal` |
| `random_probability` | `random_reply` 模式下，每条非 @ 全量群消息直接随机触发回复的概率。 | `0.05` |
| `random_cooldown_seconds` | `random_reply` 命中一次回复后，同一个群多少秒内不再随机回复。 | `0` |
| `smart_sample_probability` | `smart_random` 模式下，先用这个概率筛掉大部分消息，命中的消息才调用判断模型。`smart_reply` 不使用此项。 | `0.2` |
| `smart_cooldown_seconds` | 同一个群内智能回复命中后，冷却多少秒不再主动回复，避免连续插话。`0` 表示不冷却。`smart_reply` 冷却期仍会调用判断模型，但会抑制最终回复。 | `60` |
| `smart_judge_provider_id` | 判断模型使用的 Provider ID。为空时使用当前会话默认 provider。 | `""` |
| `smart_judge_timeout_seconds` | 判断模型超时时间。超时按“不回复”处理。 | `8` |
| `smart_recent_context_messages` | 仅用于判断模型，最多读取当前 conversation 最近多少条历史作为“是否接话”的判断上下文；不影响正式 LLM 回复时的上下文条数。 | `20` |
| `smart_judge_prompt` | 自定义判断模型系统提示词。留空使用插件内置保守提示词。 | `""` |
| `per_group_ordered_decision` | 同一个群内按收到消息顺序处理抽样和判断，降低后发消息先判断完成的概率。 | `true` |
| `max_pending_per_group` | 单个群的待判断上限。超过后新消息直接只入库。 | `32` |

`mode` 的具体行为：

| 模式 | 行为 | 是否调用判断模型 | 是否每条都回复 |
| --- | --- | --- | --- |
| `normal` | 当前行为。非 @ 全量群消息只写入 AstrBot 对话历史，不触发 LLM 回复。 | 否 | 否 |
| `random_reply` | 非 @ 全量群消息先按 `random_probability` 抽样，命中后交给 AstrBot 正常 LLM 回复流程；未命中只入库。 | 否 | 否 |
| `all_as_at` | 非 @ 全量群消息全部当作“需要回复”的消息交给 AstrBot 正常 LLM 回复流程。 | 否 | 是 |
| `smart_reply` | 每条非 @ 全量群消息都调用判断模型。判断模型只决定“要不要回复”，不生成正式回复。判断为需要回复后，再交给 AstrBot 正常 LLM 回复流程。 | 是 | 否 |
| `smart_random` | 先做基础概率抽样和冷却检查，命中后调用一个轻量判断模型。判断模型只决定“要不要回复”，不生成正式回复。判断为需要回复后，再交给 AstrBot 正常 LLM 回复流程。 | 是 | 否 |

不要实现 `ignore_bot_sender` 或“忽略其他机器人消息”。QQ 全量群消息里不能稳定判断发言者是不是机器人，即使部分 payload 偶尔带类似字段，也不应作为核心逻辑依赖。

#### 回复和入库规则

这一阶段最重要的是避免同一条消息重复进入 conversation。当前按下面规则实现：

| 结果 | 处理 |
| --- | --- |
| 不回复 | 调用当前已有的 `store_incoming_history_if_needed()`，只补写一条 `user` 历史。 |
| 要回复 | 不提前写入这条 `user` 历史，直接触发 AstrBot 正常 LLM 流程；由 AstrBot 保存本轮 `user + assistant`。 |
| 判断模型调用失败/超时 | 按“不回复”处理，只入库，不发消息。 |
| Markdown 发送失败 | 沿用当前核心发送层：Markdown 优先，失败后普通文本兜底。 |

也就是说，`random_reply`、`all_as_at`、`smart_reply`、`smart_random` 命中回复时，都应该让“当前这条消息”只进入一次历史。不要先把它作为普通全量群消息写入，再让 AstrBot LLM 流程把它作为 prompt 保存一遍。

#### 智能判断模型的边界

`smart_reply` / `smart_random` 里的判断模型只负责判断，不负责生成最终回复。它的调用不应该写入 AstrBot conversation，也不应该触发消息发送。

两种智能模式的区别：

| 模式 | 判断模型调用时机 | 成本特点 |
| --- | --- | --- |
| `smart_reply` | 每条非 @ 全量群消息都会调用判断模型。 | 调用最多，判断最完整。 |
| `smart_random` | 先按 `smart_sample_probability` 抽样，抽中后才调用判断模型。 | 调用更少，适合活跃群。 |

判断模型输入建议包含：

- 当前群会话最近若干条 conversation 历史；
- 当前这条群消息，保留 `[昵称/用户ID]: 内容` 格式；
- 简短系统提示词，要求输出严格 JSON。

判断模型输出建议只接受类似结构：

```json
{"should_reply": true, "reason": "用户在询问机器人相关问题"}
```

解析失败、字段缺失、非 JSON、超时，都按 `{"should_reply": false}` 处理。

判断模型的系统提示词不要写“你正在随机回应这条消息”。更准确的目标是：判断当前机器人是否应该自然接话。正式回复仍交给 AstrBot 的正常 LLM 流程，使用完整上下文生成。

#### 顺序和并发

本地 AstrBot 的事件总线会给每条消息创建独立异步任务，所以多条群消息可能同时进入插件 handler。正式 LLM 回复阶段有 AstrBot 会话锁，通常能让同一个 `unified_msg_origin` 的 LLM 请求串行执行；但判断模型如果并发调用，完成顺序仍可能乱。

因此当前在插件侧按群维护一个轻量顺序判断锁：

1. 同一个群内，按收到消息顺序执行“抽样/冷却/判断/是否触发回复”。
2. 如果某条消息判断为不回复，立即入库并处理下一条。
3. 如果某条消息判断为回复，插件只打唤醒标记；正式 LLM 回复继续交给 AstrBot 默认流程和会话锁处理。
4. 待判断数量超过 `max_pending_per_group` 时，不阻塞 WSS/Webhook 入口，新消息直接只入库并记录 warning。

#### 不直接复用 AstrBot 内置“主动回复”

AstrBot 本体的“群聊上下文感知 -> 主动回复”目前主要是按概率随机触发 `event.request_llm()`。它可以临时测试 QQ 被动回复链路，但不建议作为 `qq_restapi` 的最终全量群随机回复实现，原因是：

- 它不了解当前插件的全量群消息入库兜底，容易造成同一条消息重复写入 conversation。
- 它只能做概率随机，不能做“是否自然接话”的判断。
- 它和 `provider_ltm_settings.group_icl_enable` 属于同一套内置群聊上下文能力，容易再次引入 `<system_reminder>` 注入混淆。

当前已由 `qq_restapi` 插件自己控制 `normal`、`random_reply`、`all_as_at`、`smart_reply`、`smart_random` 五种模式。

### 建议解析字段

在 `parse_event()` 中新增 `GROUP_MESSAGE_CREATE` 解析，输出 AstrBot 需要的字段：

| 字段 | 用途 |
| --- | --- |
| `abm.qq_event_type = "GROUP_MESSAGE_CREATE"` | 标明这是全量群消息。 |
| `abm.type = MessageType.GROUP_MESSAGE` | 让 AstrBot 当作群消息处理。 |
| `abm.qq_scene = "group"` | 复用现有群聊发送目标。 |
| `abm.group_id = group_openid/group_id` | 群会话 ID，必须和群 @ 消息保持一致。 |
| `abm.session_id = abm.group_id` | AstrBot 会话 ID。 |
| `abm.sender.user_id = union_openid/uuid 优先` | 群内用户身份优先使用跨场景稳定 ID。 |
| `abm.qq_union_openid = union_openid/uuid` | 跨频道、群聊、单聊尽量一致的用户身份。 |
| `abm.qq_raw_user_id = member_openid` | 保留群内 openid，方便发送、排查、兼容。 |
| `abm.qq_is_full_group_message = True` | 区分群 @ 事件和全量群事件。 |
| `abm.message_id` | 被动回复、去重、记录历史时需要。 |

这里的重点是：群内用户身份不要只用 `member_openid`。`openid` 更偏单个场景，跨场景识别应优先使用当前插件已经支持的 `union_openid`/uuid 类字段。

当前插件已经有相关基础：

- `_conf_schema.json` 有 `use_union_id_for_group`、`use_union_id_for_channel`。
- `runtime/message_parser.py` 有 `_swap_ids()`。
- `db/models.py` 的 `UserIdentity` 以 `union_openid` 作为主键。
- `db/service.py` 会把 `qq_union_openid`、`qq_raw_user_id`、`sender.user_id` 合并进用户身份和场景表。

### 会话 ID 和对话 ID 不要混淆

这里的“复用同一个 AstrBot 群会话”，不是让插件自己创建或管理 AstrBot 的 conversation id。

AstrBot 的关系大致是：

| 名称 | 来源 | 作用 |
| --- | --- | --- |
| `session_id` | 平台适配器提供。群聊里应该稳定使用 QQ 群 ID。 | 标识“这是哪个群/哪个私聊”。 |
| `unified_msg_origin` | AstrBot 用 `platform_id:message_type:session_id` 拼出来。 | 标识一个平台会话，例如某个 QQ 群。 |
| `conversation id` / `cid` | AstrBot `conversation_manager` 自动生成。 | 标识这个会话下当前使用的具体对话记录。 |

所以全量群消息适配时不要重复造一套对话 ID。插件只需要保证 `session_id` 和普通群 @ 消息一致，后续 conversation id 继续交给 AstrBot 自己生成和复用。

### 和 AstrBot 对话存储的配合

当前阶段目标不是只写插件自己的 `event_log`，而是让全量群消息能成为 AstrBot LLM 上下文的一部分。

| 项目 | 当前阶段要求 |
| --- | --- |
| 事件进入 AstrBot | `GROUP_MESSAGE_CREATE` 必须和普通群消息一样 `commit_event(event)`。 |
| 会话 ID | 使用群 ID 作为 `session_id`，保证同一个群的上下文在同一个会话里。 |
| 用户身份 | `sender.user_id` 优先使用跨场景 ID，raw openid 只作为保留字段。 |
| 对话历史 | 不能只依赖插件 `event_log`。实现时要核实 AstrBot 是否会在该路径自动写入 conversation；如果不会，需要补一个安全的 user-message 写入路径。 |
| 去重 | 使用 `message_id`/`event_id` 避免同一条 WSS/Webhook 重复写入。 |

需要注意：本地 AstrBot 代码里，conversation 历史主要是 OpenAI 风格的 `role/content`。LLM 流程会保存完整上下文；当前插件的 `_store_history_if_needed()` 也会在非 LLM 回复时补写 user/assistant pair。

`framework_default` 下不会强制唤醒回复，所以未 @、未命中唤醒词的全量群消息原本可能会被 AstrBot 的 `WakingCheckStage` 提前停止。第一阶段已经补了“存储兜底”：插件注册低优先级群消息 handler，让这类普通全量群消息进入 AstrBot 插件处理阶段，再补写一条 `user` 历史，保证它进入当前群会话的 conversation。明显会由框架自然唤醒的消息，例如 @ 机器人、@ 全体、命中唤醒词，仍交给 AstrBot LLM 流程自己保存，避免同一条当前消息在上下文里出现两次。

也就是说：只补记录，不补唤醒。

补充：如果 AstrBot 本体的 `provider_ltm_settings.group_icl_enable` 已开启，AstrBot 内置 `group_chat_context.py` 会把“上次回复之后的群聊消息”作为 `<system_reminder>...BEGIN CONTEXT...END CONTEXT...</system_reminder>` 注入下一次 LLM 请求。这个内容的昵称来自 `event.message_obj.sender.nickname`，也就是当前插件从 QQ `author.username` 解析出来的昵称；时间是 AstrBot 本地记录时间。当前插件不会自动改 AstrBot 配置，也不会跳过自己的上下文写入。为了避免普通全量消息刷屏，插件只会在群聊 @/唤醒进入 LLM 请求时输出强提醒日志，并且同一条事件最多提醒一次；下一次 @/唤醒仍会再次提醒。建议用户在 AstrBot Web 面板关闭“群聊上下文感知(原聊天记忆增强)”，避免 `<system_reminder>` 和 qq_restapi 持久化上下文同时出现。

插件写入群聊上下文时会带上用户标识，格式类似：

```text
[昵称/用户ID]: 消息内容
[昵称/用户ID -> 机器人平台名]: @ 或唤醒机器人后进入 LLM 的消息内容
```

这样 conversation 中能看出是哪位群成员说的话。

### 群成员入群事件

`group_add_robot_message` 和 `group_member_add_message` 是两个不同配置：

| 配置 | 对应事件 | 通俗解释 |
| --- | --- | --- |
| `group_add_robot_message` | `GROUP_ADD_ROBOT` | 机器人自己被拉进某个群时发送。 |
| `group_member_add_message` | `GROUP_MEMBER_ADD` | 群里有普通成员加入时发送。为空则只记录日志，不自动欢迎。 |

v2 中有 `GROUP_MEMBER_ADD` / `GROUP_MEMBER_REMOVE` 解析和生命周期处理；当前插件已接入同类事件，并把 `GROUP_MEMBER_REMOVE` 作为日志事件处理。

## WSS/Webhook 同步支持

当前必须保留两个平台适配器：

- `qq_restapi`：WebSocket Gateway。
- `qq_restapi_webhook`：Webhook 回调入口。

之前说的“抽一个共享入口”不是把两个适配器合并成一个，也不是改变 AstrBot WebUI 里选择 WSS/Webhook 的方式。

它的意思只是：两个适配器收到 payload 之后，调用同一段 Python 处理逻辑，避免以后 WSS 支持了某个事件、Webhook 忘了支持，或者两边写入历史的行为不一致。

建议结构：

```text
adapters/qq_restapi_adapter.py
adapters/qq_restapi_webhook_adapter.py
  -> runtime/dispatch.py::handle_qq_payload(payload, sender, meta, config, source)
      -> parse_event()
      -> record_event()
      -> auto_events
      -> commit_event()
      -> conversation storage guard
```

通俗讲：入口仍然是两个门，但进门以后走同一条走廊。

## 自动事件日志分组补齐

旧配置只有：

```yaml
auto_event_log_groups:
  reaction:
    log: true
  audit:
    log: true
  forum:
    log: true
```

导致频道成员、频道/子频道、消息撤回、群通知设置等日志无法按组关闭。第一阶段已补齐以下分组：

建议分组：

| 分组 | 包含事件 | 默认 |
| --- | --- | --- |
| `relation` | `GROUP_ADD_ROBOT`、`GROUP_DEL_ROBOT`、`FRIEND_ADD`、`FRIEND_DEL` | true |
| `group_setting` | `GROUP_MSG_RECEIVE`、`GROUP_MSG_REJECT` | true |
| `guild` | `GUILD_CREATE`、`GUILD_UPDATE`、`GUILD_DELETE` | true |
| `channel` | `CHANNEL_CREATE`、`CHANNEL_UPDATE`、`CHANNEL_DELETE` | true |
| `guild_member` | `GUILD_MEMBER_ADD`、`GUILD_MEMBER_UPDATE`、`GUILD_MEMBER_REMOVE` | true |
| `reaction` | `MESSAGE_REACTION_ADD`、`MESSAGE_REACTION_REMOVE` | true |
| `audit` | `MESSAGE_AUDIT_PASS`、`MESSAGE_AUDIT_REJECT` | true |
| `forum` | `OPEN_FORUM_*` | true |
| `message_delete` | `PUBLIC_MESSAGE_DELETE`、`DIRECT_MESSAGE_DELETE` | true |
| `subscribe` | `SUBSCRIBE_MESSAGE_STATUS`、`C2C_MSG_RECEIVE`、`C2C_MSG_REJECT` | false，待验证 |
| `audio` | `AUDIO_*` | false，待验证 |

关于 `GUILD_MEMBER_UPDATE`：当前插件已经定义常量，也在解析层有相关处理，第一阶段已纳入 `runtime/auto_events.py` 事件映射和 `guild_member` 日志分组。如果官方实际推送该事件，就能被日志开关控制；如果官方不推送，也不会产生额外副作用。

已同步修改：

- `runtime/auto_events.py`：`_resolve_event_group()` 和事件映射。
- `templates/registry.yaml`：默认分组配置。
- `_conf_schema.json`：插件面板配置。
- `runtime/context.py`：确保 `auto_event_log_groups` 合并。
- `docs/auto_events_guide.md`：补文档。

## 发送接口变化对比

| 能力 | 当前插件 | v2 | 建议 |
| --- | --- | --- | --- |
| `event.reply(text)` | 已默认 Markdown 优先、普通文本兜底；显式 `use_markdown=False` 时纯文本。 | 有，按配置默认 Markdown。 | 当前插件已完成下沉。 |
| `reply_markdown(template_id, params)` | 有。 | 无同名一等接口。 | 保留。 |
| `reply_markdown_aj(text)` | 有。 | 无。 | 保留但不作为默认发送路径。 |
| `reply_image/voice/video` | 有。 | 有。 | 暂不动。 |
| `reply_file` | 当前缺少一等接口。 | 有。 | 可作为后续增强，不是第一优先级。 |
| `reply_ark` | 有。 | 有。 | 保留。 |
| `send_by_session` | WSS/Webhook 均已复用 Markdown 优先发送。 | v2 有 `send_to_*`。 | 已完成。 |
| `message_reference_id` | 已接入 AstrBot `Reply` -> QQ `message_reference` 的发送路径。 | v2 支持。 | 当前优先使用 `message_scene.ext` 中的 `msg_idx`/`REFIDX`，再兜底普通消息 ID。 |
| `prompt_buttons/font_size` | 当前不完整。 | v2 有。 | 后续按钮专项处理。 |

## 事件覆盖变化对比

| 事件类别 | 当前插件 | v2 | 建议 |
| --- | --- | --- | --- |
| 单聊 `C2C_MESSAGE_CREATE` | 支持。 | 支持。 | 保留。 |
| 群 @ `GROUP_AT_MESSAGE_CREATE` | 支持。 | 支持。 | 保留。 |
| 群全量 `GROUP_MESSAGE_CREATE` | 已支持解析、提交、上下文写入与五种回复模式。 | 支持。 | 已完成。 |
| 频道 @ `AT_MESSAGE_CREATE` | 支持。 | 支持。 | 保留。 |
| 频道消息 `MESSAGE_CREATE` | 当前作为频道消息支持。 | 支持。 | 保留。 |
| 频道私信 `DIRECT_MESSAGE_CREATE` | 支持。 | 支持。 | 保留。 |
| 交互 `INTERACTION_CREATE` | 支持按钮点击转普通文本。 | 有 ACK 机制。 | 当前不重构按钮存储；后续专项处理。 |
| 群/好友关系 | 支持。 | 支持。 | 保留。 |
| 频道/子频道生命周期 | 当前覆盖更广。 | v2 较少。 | 保留当前优势。 |
| 频道成员 add/update/remove | add/update/remove 已进入自动事件，并放进 `guild_member` 日志分组。 | v2 主要覆盖 add/remove。 | 已补齐日志分组；是否进一步做业务响应，后续再讨论。 |
| 审核/表态/论坛/音频/订阅 | 当前覆盖更多。 | v2 不完整。 | 保留当前优势，但加日志开关。 |

## 建议实施顺序

### 第一阶段：当前优化

1. 已改 `QQRestAPIEvent._send_text_reply()`：普通文本默认先 Markdown，失败再普通文本。
2. 已改两个适配器的 `send_by_session()`：主动/延迟发送也复用同一文本发送策略。
3. 已新增 `GROUP_MESSAGE_CREATE` 常量和解析。
4. 已让 WSS/Webhook 收到 `GROUP_MESSAGE_CREATE` 后默认 `commit_event()`，不加白名单、不加插件侧 enabled，也不强制唤醒。
5. 已补未唤醒全量群消息的最小安全写入路径：通过插件消息事件 handler 写入上下文，保证普通全量群消息不遗漏。
6. 已补齐 `auto_event_log_groups` 分组，尤其 `guild_member`。

### 第二阶段：传输一致性

1. 已抽 `runtime/dispatch.py`，让 WSS/Webhook 共用事件处理逻辑。
2. 已加入基本去重：`message_id`/`event_id` + TTL。
3. 已从 v2 借鉴 WSS reconnect/resume 和事件处理背压；当前实现使用有界队列保持事件顺序。

### 后续阶段：按钮专项（未实现）

1. 重构“Markdown + 按钮”的发送降级：有按钮失败先去按钮，保留 Markdown。
2. 设计按钮点击的存储形态：至少保留 button id/data、用户、场景、原消息 ID。
3. 在“不修改 AstrBot 框架源码”的边界下，优先评估只在插件 DB 中保存按钮交互 metadata；只有框架未来提供正式扩展点时再考虑通用组件方案。

### 暂时搁置

- 群备注/群别名。
- v2 Web 面板。
- v2 插件系统。
- 大规模主动推送能力。
- 完整 OneBot 适配。

## 已确认决策

当前阶段收到 `GROUP_MESSAGE_CREATE` 后，采用 A 方案：

```text
只接入、提交、写入上下文，不强制每条都唤醒回复。
```

也就是：

- 不把每条全量群消息伪装成 @ 机器人。
- 不主动设置 `event.is_at_or_wake_command = True`。
- 不绕过 AstrBot 的唤醒词、@、插件命令等原生判断。
- 需要确保收到的全量群消息能正确进入上下文/对话数据。

“全部当作 @ 消息处理和回复”已作为 `full_group_reply.mode=all_as_at` 的可选模式实现，默认不启用。
