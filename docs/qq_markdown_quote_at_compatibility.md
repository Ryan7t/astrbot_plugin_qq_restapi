# QQ Markdown、引用与 @ 兼容性说明

> 更新时间：2026-06-24  
> 适用范围：`qq_restapi` / `qq_restapi_webhook` 平台适配器

本文档记录 `qq_restapi` 在 QQ 官方机器人接口下，对 **Markdown 消息**、**引用原消息**、**@ 发送人**、**分段回复**、**流式回复** 的实测结论与当前实现策略。  
这部分非常容易被误判：日志和 AstrBot 对话数据可能完全正常，但 QQ 客户端最终显示会重复、裸露 ID，或者无法解析 @。

## 一句话结论

当前 QQ 客户端表现下：

```text
Markdown 可以正常 @。
message_reference 可以正常引用。
但 Markdown + message_reference 不能稳定共存，会导致 QQ 客户端重复显示正文。
```

因此当前插件采用硬规则：

| 场景 | 发送策略 |
| --- | --- |
| 无引用、无 @ | Markdown 优先，失败后普通文本兜底 |
| 只有 @ | Markdown + 官方 `<qqbot-at-user id="..." />` |
| 只有引用 | 普通文本 + `message_reference` |
| 引用 + @ | 普通文本 + `message_reference`，忽略 @ |
| 流式输出 | 不承诺引用/@，打印 warning 提醒关闭流式 |

## 官方文档背景

相关官方文档：

- Markdown 消息：<https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/type/markdown.html>
- 文本交互/@：<https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/trans/text-chain.html>
- 发送/接收消息：<https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/send-receive/send.html>

官方文本交互文档说明：群聊、文字子频道中，含有文本文字的消息类型，包括文本、图文、Markdown，都支持 @ 能力。当前推荐格式是：

```text
<qqbot-at-user id="" />
```

旧格式：

```text
<@userid>
<@!userid>
```

在部分场景仍可能可用，但不作为当前插件的正式发送格式。

## 实测矩阵

开发阶段临时加入过 `测试MarkdownAt` 指令进行真实 QQ 客户端发包验证。该调试指令已从正式代码移除，仅保留测试结论。

| 编号 | 发送类型 | @ 写法 | 是否带引用 | QQ 客户端结果 |
| --- | --- | --- | --- | --- |
| P0 | 普通文本 | `<qqbot-at-user id="id" />` | 是 | 引用成功，但 @ 不解析，只显示原始标签/ID |
| P1 | 普通文本 | `<@id>` | 是 | 引用成功，但 @ 不解析，只显示原始 ID |
| P2 | 普通文本 | `<@!id>` | 是 | 引用成功，但 @ 不解析，只显示原始 ID |
| M1 | Markdown | `<qqbot-at-user id="id" />` 前置 | 否 | @ 正常，QQ 显示蓝色 @ |
| M2 | Markdown | `<qqbot-at-user id="id" />` 中置 | 否 | @ 正常，QQ 显示蓝色 @ |
| M3 | Markdown | `<@id>` | 否 | @ 正常，QQ 显示蓝色 @ |
| M4 | Markdown | `<@!id>` | 否 | @ 正常，QQ 显示蓝色 @ |
| Q1 | Markdown | `<qqbot-at-user id="id" />` | 是 | 正文重复 |
| Q2 | Markdown | `<@id>` | 是 | 正文重复 |
| Q3 | Markdown | `<@!id>` | 是 | 正文重复 |
| R1 | Markdown | 无 @ | 是 | 正文重复 |

关键结论：

- `@` 本身不是问题，Markdown 内 @ 可以正常解析。
- `message_reference` 本身不是问题，普通文本引用可以正常显示。
- 真正有问题的是 `Markdown + message_reference`。
- 分段回复只让问题看起来像“第一段重复”，因为 AstrBot 只把引用放在第一段。

## 为什么日志和数据库没有重复

出现重复时，AstrBot 日志和对话数据库通常只会看到一份内容，例如：

```text
Prepare to send - 用户/ID: [引用消息]
回复内容
```

数据库里也只有一条 assistant 回复。

但 QQ 客户端显示时可能变成：

```text
回复内容 回复内容
```

这说明重复不是：

- AstrBot 构造了两条回复；
- 插件发了两次；
- 对话数据库重复写入；
- 分段回复重复切片。

而是 QQ 客户端或 QQ 官方接口在渲染 `msg_type=2` 的 Markdown 消息并附带 `message_reference` 时，把正文展示了两遍。

## 分段回复的关系

AstrBot 的非流式分段回复逻辑会把 `Reply` 和 `At` 作为头部组件，只放到第一段：

```text
第一段：Reply / At + 第一段文本
第二段：第二段文本
第三段：第三段文本
```

所以当开启引用时：

- 第一段带 `message_reference`；
- 第二段、第三段不带 `message_reference`；
- 只有第一段重复，后续分段正常。

这容易误判为“分段回复导致重复”。  
实际根因仍然是第一段包含 `Markdown + message_reference`。

关闭分段回复后，如果仍使用 `Markdown + message_reference`，整条回复也会重复。这已经在实测中确认。

## 流式回复的关系

流式回复是另一条独立问题线。

AstrBot 流式输出会跳过结果装饰阶段，因此框架不会稳定插入：

- `Reply`；
- `At`；
- 非流式分段回复头部。

所以当前插件在 `send_streaming()` 中会打印 warning，提醒用户关闭流式输出，才能正确使用引用、@ 和非流式分段回复。

这和 `Markdown + message_reference` 的客户端重复问题不同。  
简单说：

| 问题 | 根因 |
| --- | --- |
| 流式下没有引用/@ | AstrBot 流式跳过结果装饰阶段 |
| 非流式引用时正文重复 | QQ 客户端对 `Markdown + message_reference` 渲染异常 |

## 当前实现策略

当前实现位于：

- `runtime/qq_restapi_event.py`
- `runtime/sender.py`

### 1. 无引用、无 @

继续走 Markdown 优先：

```text
msg_type = 2
markdown.content = 回复内容
```

如果 QQ 返回 Markdown 发送失败，再回退普通文本。

### 2. 只有 @

使用 Markdown，并把 AstrBot 的 `At` 组件渲染为官方推荐格式：

```text
<qqbot-at-user id="用户ID" />
```

这是当前最稳定的 @ 显示方式。QQ 客户端会显示蓝色 @。

### 3. 只有引用

强制普通文本：

```text
msg_type = 0
content = 回复内容
message_reference = {...}
```

这样可以避免 `Markdown + message_reference` 导致正文重复。

### 4. 引用 + @

当前优先引用，忽略 @：

```text
msg_type = 0
content = 回复内容
message_reference = {...}
```

不把 @ 塞进普通文本，因为实测普通文本中的三种 @ 写法都不会解析成蓝色 @，只会显示原始 ID 或标签文本。

不发送两条消息，因为：

- 会占用 QQ 被动回复次数；
- 群聊体验更吵；
- 分段回复时更容易触发频控；
- 发送顺序和失败重试会变复杂。

## 代码实现要点

### `Reply` 转 `message_reference`

`QQRestAPIEvent.send()` 会从 AstrBot 消息链中提取 `Reply` 组件，并转成 QQ payload 的：

```json
{
  "message_reference": {
    "message_id": "REFIDX_xxx",
    "ignore_get_message_error": true
  }
}
```

引用 ID 优先级：

| 来源 | 说明 |
| --- | --- |
| `Reply.id` 已经是 `REFIDX...` | 直接使用 |
| 当前事件 `qq_message_reference_id` | 来自 `message_scene.ext` 中的 `msg_idx`，更适合全量群消息引用 |
| 兜底普通消息 ID | 仅在没有 `REFIDX` 时使用 |

### `At` 转 Markdown @

没有引用时，`At` 会被转换为：

```text
<qqbot-at-user id="用户ID" />
```

`AtAll` / `qq="all"` 会被转换为：

```text
<qqbot-at-everyone />
```

注意：`@ 全体成员` 仅部分场景可用，并且需要机器人具备相应权限。

### 引用时禁用 Markdown

一旦本次发送包含 `message_reference`，插件会强制：

```python
prefer_markdown = False
```

也就是说，引用回复不再走 Markdown 优先，而是直接普通文本发送。

这是当前避免 QQ 客户端正文重复的核心规则。

## 常见误区

### 误区一：这是分段回复的问题

不是。  
分段只是让引用只出现在第一段，所以重复只出现在第一段。

### 误区二：这是 @ 导致的

不是。  
无 @、只有引用时也会重复；Markdown 不带引用时 @ 可以正常显示。

### 误区三：这是 AstrBot 重复写入上下文

不是。  
日志和对话数据库都只有一份内容。重复发生在 QQ 客户端展示层。

### 误区四：普通文本也能稳定 @

实测不是。  
普通文本带引用时，`<qqbot-at-user id="">`、`<@id>`、`<@!id>` 都无法渲染成真正的蓝色 @。

### 误区五：发两条消息就能完美解决

技术上可以一条引用、一条 @，但不推荐作为默认实现。  
QQ 被动回复有次数限制，且群聊体验较差。

## 回归测试建议

后续如果 QQ 官方客户端或接口行为发生变化，可以重新验证以下组合：

| 测试项 | 预期 |
| --- | --- |
| Markdown + 官方 @，无引用 | 应显示蓝色 @ |
| 普通文本 + message_reference，无 @ | 应引用成功且正文不重复 |
| Markdown + message_reference，无 @ | 当前会重复；如果未来不重复，可重新评估引用是否继续禁用 Markdown |
| Markdown + message_reference + 官方 @ | 当前会重复；如果未来不重复，可支持引用和 @ 同时保留 |
| 普通文本 + message_reference + 官方 @ | 当前 @ 不解析；如果未来解析，可考虑普通文本引用同时保留 @ |

回归测试时要看 QQ 手机客户端最终显示，而不只看 AstrBot 日志。日志正常不代表客户端渲染正常。

