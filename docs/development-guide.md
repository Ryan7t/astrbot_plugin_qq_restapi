# qq_restapi 开发指南

> 更新时间：2026-07-14
>
> 本文描述当前插件实现；插件始终作为 AstrBot 的平台适配器运行，不要求也不建议修改 AstrBot 框架源码。
>
> `metadata.yaml` 当前声明最低 AstrBot `4.22.0`；本轮自动化验证使用本地 AstrBot `4.26.4`。历史最低版本兼容性尚未重新逐版验证。

## 1. 项目结构与边界

```text
qq_restapi/
├── main.py                  # 插件入口、生命周期、全量群消息策略、私有扩展兼容注册
├── public_api.py            # 对外稳定接口，其他插件/私有扩展优先从这里导入
├── adapters/                # WebSocket、Webhook 与 AstrBot 平台适配器接线
├── runtime/                 # 分发、解析、发送、Token、模板、自动事件、回复策略
├── db/                      # 插件自有 SQLite 模型、仓储与服务
├── core/qq/                 # 复用 runtime 的公共 API 薄兼容层
├── utils/                   # 场景解析等公共工具
├── templates/               # 公共模板目录与 registry.yaml
├── docs/                    # 插件开发和行为说明
└── wanbot/                  # 可选私有扩展目录（不应被公开核心依赖）
```

职责原则：

- `adapters/` 只负责平台注册和传输接入。
- WSS 与 Webhook 收到 payload 后统一进入 `runtime/dispatch.py::handle_qq_payload()`。
- 事件解析、发送策略和业务判断放在 `runtime/`。
- 数据持久化只使用插件自己的 `db/`，数据库位于 AstrBot 提供的插件数据目录。
- 外部代码优先使用 `public_api.py`，避免依赖内部目录结构。
- 不通过修改 `astrbot/` 框架源码来实现插件功能。

## 2. 两种平台接入

AstrBot 平台面板中提供两个适配器：

| 平台名 | 接入方式 | 当前实现 |
| --- | --- | --- |
| `qq_restapi` | QQ Gateway WebSocket | 支持 identify、心跳、resume/reconnect、有界分发队列 |
| `qq_restapi_webhook` | AstrBot 统一 Webhook 入口 | 依赖 AstrBot 的 `FastAPIWebhookServer`，支持 QQ 验证回包与 Ed25519 签名校验 |

两个入口共用解析、去重、数据库记录、自动事件和 `commit_event()` 逻辑。Webhook 当前只支持 `unified_webhook_mode=true`；回调地址由 AstrBot 根据 `webhook_uuid` 展示和路由，不需要修改框架 Webhook 代码。

## 3. 配置来源

配置分为两层：

- 平台配置：由两个适配器的 `default_config_tmpl` 定义，例如 `appid`、`secret`、WSS 重连参数、Webhook UUID。
- 插件配置：由 `_conf_schema.json` 定义，例如 Union OpenID、自动欢迎、日志分组、全量群回复策略和模板配置。

`runtime/context.py::merge_plugin_config()` 会把插件配置合并到平台配置的有效副本中。新增插件配置时，应同步修改：

1. `_conf_schema.json`；
2. `runtime/context.py` 中的 `_PLUGIN_CONFIG_KEYS`；
3. `metadata.yaml` 中面向用户的默认值/说明（如该字段需要展示）；
4. README 或对应专题文档。

不要在文档或代码中写入真实 `appid`、`secret`、Webhook UUID 或私有后端地址。

## 4. 获取 QQ 凭据

插件或私有扩展应优先使用公共 API：

```python
from qq_restapi.public_api import get_app_credentials_from_plugin

appid, secret = get_app_credentials_from_plugin(self)
if not appid or not secret:
    # 当前没有可用的 QQ 平台配置
    ...
```

`public_api.resolve_qq_platform()` 会兼容查找 `qq_restapi`、`qq_restapi_webhook` 以及框架内置 QQ 平台。不要假设事件来自 `qq_official`，也不要直接读取适配器私有属性。

## 5. 消息接收链路

```text
QQ WSS / Webhook
  -> adapters/
  -> runtime/dispatch.py
  -> runtime/message_parser.py
  -> 插件 DB 记录与自动事件
  -> QQRestAPIEvent
  -> AstrBot commit_event()
```

系统事件由自动事件逻辑消费，不作为普通聊天消息提交给 AstrBot。群聊、单聊、频道讨论组和频道私信等有效消息会转换成 `QQRestAPIEvent`。

`GROUP_MESSAGE_CREATE` 是全量群消息事件。默认 `full_group_reply.mode=normal` 时，非 @ 消息提交给 AstrBot 并由插件补写对话上下文，但不强制唤醒 LLM；其他模式见 [全量群消息回复模式说明](full_group_reply_modes.md)。

## 6. 消息发送

普通 AstrBot 回复仍可使用：

```python
yield event.plain_result("文本")
yield event.image_result("https://example.com/image.png")
```

当事件是本适配器的 `QQRestAPIEvent` 时，还可以调用 QQ 专用接口：

```python
if hasattr(event, "reply_markdown"):
    await event.reply(content="## Markdown", use_markdown=True)
    await event.reply_markdown("模板 ID", params={"key": "value"})
    await event.reply_ark(template_id=24, kv_data=[])
    await event.reply_image(url="https://example.com/image.png")
```

当前普通文本发送策略是 Markdown 优先、普通文本兜底。带 `Reply` 引用时会强制使用普通文本加 QQ `message_reference`；按钮仍使用现有 keyboard 能力，尚未实现“有按钮失败后去按钮再重试”的专项降级。

## 7. 模板与公共 API

公共模板注册表位于 `templates/registry.yaml`。模板加载由 `runtime/template_registry.py` 和 `runtime/template_store.py` 负责，支持外部模板源注册。

外部扩展可使用：

```python
from qq_restapi.public_api import (
    register_external_template_source,
    unregister_external_template_source,
)
```

同一进程内复用 HTTP 客户端、解析场景或查询模板时，也应从 `public_api.py` 导入对应函数。

需要注意两层 API：两个平台适配器和 `QQRestAPIEvent` 直接使用 `runtime/token_manager.py`、`runtime/sender.py`；`public_api.send_markdown_template()` 为兼容既有私有扩展，保留“指定完整 API URL 并返回 `(status_code, response_text)`”的旧签名。`core/qq/` 当前只是参数与返回值适配层，Token 获取、HTTP 发送、错误解析和 Token 失效重试均复用 `runtime/`。新代码仍应优先使用事件对象或平台 sender。

## 8. 自动事件与数据库

自动事件映射位于 `runtime/auto_events.py`，详细行为见 [自动事件说明](auto_events_guide.md)。自动事件可以：

- 写入插件自有事件日志；
- 按日志分组开关跳过日志和对应数据库事件记录；
- 对机器人入群、普通成员入群、好友添加等事件发送可配置欢迎文本；
- 消费系统事件，避免其进入普通指令/LLM 流水线。

插件数据库由 `db/database.py` 创建，默认文件为 AstrBot 插件数据目录下的 `qq_restapi/qq_restapi.db`。初始化当前使用 SQLModel metadata `create_all()`，只创建缺失表，不修改 AstrBot 自身数据库，也没有独立的 schema 迁移框架。

## 9. 私有扩展现状

当前 `main.py` 只兼容两个候选目录名：`private_bot/` 和 `wanbot/`。检测条件是目录下存在 `commands/`，随后代码会固定导入已知命令模块，并注册对应的 `@filter.command` handler；这不是任意文件的通用自动发现。

私有模板目录会作为外部模板源注册。公开核心不得反向依赖 `wanbot/` 的业务逻辑。新增普通业务命令时，可靠方式仍是在插件类中显式使用 AstrBot 的 `@filter.command` 注册；若未来实现通用发现，应在本插件内设计声明式注册协议，而不是修改 AstrBot 框架加载器。

## 10. 最小验证

测试需要使用 AstrBot 项目的虚拟环境，以便加载框架依赖；它不会启动 AstrBot 服务，也不会连接真实 QQ：

```powershell
$env:PYTHONPATH="<AstrBot根目录>;<AstrBot根目录>\data\plugins"
<AstrBot根目录>\venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

配置 schema 可单独验证：

```powershell
<AstrBot根目录>\venv\Scripts\python.exe -B -c "import json; json.load(open('_conf_schema.json', encoding='utf-8')); print('OK')"
```

当前测试覆盖 Webhook 签名、分发去重、发送降级、全量群回复辅助逻辑和 Token 刷新。触及真实事件字段、QQ API 行为或框架生命周期时，仍应在 AstrBot 中分别验证 WSS 与 Webhook 平台。
