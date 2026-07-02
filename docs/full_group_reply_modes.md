# 全量群消息回复模式说明

> 本文说明 `qq_restapi` 插件对 QQ `GROUP_MESSAGE_CREATE` 全量群消息的回复策略。
> 默认行为仍然是只入库、不主动回复，只有显式改配置后才会让非 @ 群消息触发 LLM。

## 一句话解释

QQ 后台开启全量群消息后，机器人会收到群里每一条普通消息。

本插件把这件事拆成两步：

1. 收到的群消息都尽量写入 AstrBot 当前群会话的 conversation，保证后续上下文完整。
2. 是否让机器人对“非 @ 消息”接话，由 `full_group_reply.mode` 决定。

这不是 QQ 主动推送。命中回复策略后，插件只是把当前事件交给 AstrBot 默认 LLM 回复流程，QQ 侧仍然使用这条消息事件的被动回复能力。

## 配置总览

配置位于插件配置里的 `full_group_reply`：

```yaml
full_group_reply:
  mode: normal
  random_probability: 0.05
  random_cooldown_seconds: 0
  smart_sample_probability: 0.2
  smart_cooldown_seconds: 60
  smart_judge_provider_id: ""
  smart_judge_timeout_seconds: 8.0
  smart_recent_context_messages: 20
  smart_judge_prompt: ""
  per_group_ordered_decision: true
  max_pending_per_group: 32
  debug_log: false
```

## mode 怎么选

| 模式 | 通俗解释 | 会不会调用判断模型 | 会不会每条都回复 |
| --- | --- | --- | --- |
| `normal` | 当前默认行为。非 @ 全量群消息只写入历史，不触发回复。 | 否 | 否 |
| `random_reply` | 不调用判断模型，只按概率决定是否接话。 | 否 | 否 |
| `all_as_at` | 非 @ 全量群消息全部进入默认 LLM 回复流程。 | 否 | 是 |
| `smart_reply` | 每条非 @ 全量群消息都调用判断模型，由模型决定是否值得接话。 | 是 | 否 |
| `smart_random` | 先按概率抽样，命中后才调用判断模型决定是否值得接话。 | 是 | 否 |

建议：

| 使用目标 | 推荐模式 |
| --- | --- |
| 只要完整上下文，不希望机器人插话 | `normal` |
| 想要低成本随机插话 | `random_reply` |
| 小群测试、希望每条都回复 | `all_as_at` |
| 想让机器人尽量认真判断每条消息 | `smart_reply` |
| 想让机器人低成本地“看情况接话” | `smart_random` |

## 入库和回复规则

| 当前消息结果 | 插件行为 |
| --- | --- |
| 非 @，且策略决定不回复 | 调用 `store_incoming_history_if_needed()`，只追加一条 user 历史。 |
| 非 @，且策略决定回复 | 不提前写入当前消息，直接让 AstrBot 默认 LLM 流程保存本轮 user + assistant，避免重复历史。 |
| @ 机器人、@ 全体、命中唤醒词 | 交给 AstrBot 原本唤醒逻辑处理；插件只补一个保底唤醒标记，避免全量事件里 @ 信息没有被框架识别。 |
| 判断模型失败、超时、输出不是 JSON | 当作不回复，只写入历史。 |

历史格式也分清楚：

| 场景 | 历史里的用户消息格式 |
| --- | --- |
| 普通全量消息只入库 | `[昵称/用户ID]: 内容` |
| `random_reply` / `smart_reply` / `smart_random` 命中回复 | `[昵称/用户ID]: 内容` |
| `all_as_at` 命中回复 | `[昵称/用户ID -> 机器人]: 内容` |
| 用户真实 @ 或唤醒机器人 | `[昵称/用户ID -> 机器人]: 内容` |

也就是说，`random_reply`、`smart_reply` 和 `smart_random` 不会把历史伪装成“用户真的 @ 了机器人”。它们只是让机器人在合适时机自然接话。

## 各配置项说明

| 配置 | 生效模式 | 含义 | 默认值 |
| --- | --- | --- | --- |
| `mode` | 全部 | 全量群消息回复模式。 | `normal` |
| `random_probability` | `random_reply` | 每条非 @ 全量消息直接触发回复的概率，范围 0.0-1.0。 | `0.05` |
| `random_cooldown_seconds` | `random_reply` | 同一个群随机回复命中后，多少秒内不再随机回复。`0` 表示不冷却。 | `0` |
| `smart_sample_probability` | `smart_random` | 进入判断模型前的抽样概率。`smart_reply` 不使用此项。 | `0.2` |
| `smart_cooldown_seconds` | `smart_reply` / `smart_random` | 判断为需要回复并触发后，同一个群多少秒内不再智能接话。`0` 表示不冷却。`smart_reply` 冷却期仍会调用判断模型，但会抑制最终回复。 | `60` |
| `smart_judge_provider_id` | `smart_reply` / `smart_random` | 判断模型使用的 Provider ID。为空时使用当前会话默认聊天模型。 | `""` |
| `smart_judge_timeout_seconds` | `smart_reply` / `smart_random` | 判断模型最多等待多久。超时后只入库。 | `8.0` |
| `smart_recent_context_messages` | `smart_reply` / `smart_random` | 仅用于判断模型，读取当前 conversation 最近多少条历史作为“是否接话”的判断上下文；不影响正式 LLM 回复时的上下文条数。`0` 表示判断模型只看当前消息。 | `20` |
| `smart_judge_prompt` | `smart_reply` / `smart_random` | 自定义判断模型系统提示词。留空使用插件内置保守提示词。 | `""` |
| `per_group_ordered_decision` | `random_reply` / `smart_reply` / `smart_random` / `all_as_at` | 同一个群内按收到顺序执行抽样和判断，降低后发消息先判断完成的概率。 | `true` |
| `max_pending_per_group` | 同上 | 同一个群等待判断的消息上限。超过后新消息只入库。`0` 表示不限制。 | `32` |
| `debug_log` | `smart_reply` / `smart_random` | 输出判断模型的简短原始结果，便于调试。 | `false` |

## 智能判断模式的区别

`smart_reply` 和 `smart_random` 都只让判断模型决定“要不要回复”，不生成正式回复。

| 模式 | 判断模型调用时机 | 适合场景 |
| --- | --- | --- |
| `smart_reply` | 每条非 @ 全量群消息都会调用判断模型。 | 小群、低消息量群、希望判断尽量完整。 |
| `smart_random` | 先用 `smart_sample_probability` 抽样，抽中后才调用判断模型。 | 活跃群、希望控制模型调用成本。 |

## smart_random 的工作方式

`smart_random` 是两段式：

1. 先用 `smart_sample_probability` 做低成本抽样，挡掉大部分消息。
2. 抽样命中后，调用判断模型，只判断“要不要回复”，不生成正式回复。
3. 判断为需要回复后，再交给 AstrBot 默认 LLM 流程，用完整上下文生成正式回复。

判断模型期望输出：

```json
{"should_reply": true, "reason": "用户在问机器人"}
```

只认 `should_reply`。解析失败、字段缺失、非 JSON、超时都按 `false` 处理。

## 和 AstrBot 内置主动回复的关系

AstrBot 本体的“群聊上下文感知 -> 主动回复”可以证明 QQ 被动回复链路能用，但不建议和本插件的 `full_group_reply` 同时开启。

原因很简单：AstrBot 内置主动回复不了解 `qq_restapi` 的全量群消息入库兜底，容易出现同一条消息一份由内置主动回复保存、一份由插件全量入库保存的重复历史。

推荐做法：

| 功能 | 建议 |
| --- | --- |
| AstrBot “启用群聊上下文感知” | 关闭，避免 `<system_reminder>` 和插件持久化上下文重复。 |
| AstrBot “主动回复” | 不建议和 `full_group_reply` 同时使用。 |
| `qq_restapi.full_group_reply` | 使用本文这套模式控制非 @ 全量消息是否回复。 |

## 注意事项

- 插件不会尝试识别“其他机器人发出的消息”。QQ 全量群消息里不能稳定判断发言者是不是机器人。
- `all_as_at` 会让每条非 @ 全量群消息都触发回复，适合小群或短时间测试，不建议直接用于活跃大群。
- `smart_reply` 会对每条非 @ 全量群消息调用判断模型，适合小群或低消息量群。
- `smart_random` 会额外消耗判断模型调用。可以调低 `smart_sample_probability`，或调高 `smart_cooldown_seconds` 控制成本。
- 同群顺序判断只负责抽样和判断阶段尽量按顺序；正式 LLM 回复仍交给 AstrBot 会话锁串行处理。
- 按钮消息点击记录、Markdown + 按钮发送降级重构不属于本文功能范围，后续单独处理。
