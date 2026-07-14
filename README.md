# QQ REST API 适配器

AstrBot 的 QQ 官方 REST API 平台适配器插件。不依赖 `botpy`（qq-botpy），直接通过 HTTP 调用 QQ 官方 REST API，提供更灵活的消息收发和事件处理能力。

## 与框架内置 QQ 适配器的区别

AstrBot 框架内置了基于 `botpy` SDK 的 `qq_official` / `qq_official_webhook` 适配器。本插件作为替代方案，有以下不同：

| 对比项 | 框架内置 (`qq_official`) | 本插件 (`qq_restapi`) |
|--------|------------------------|-----------------------|
| 依赖 | 依赖 `qq-botpy` SDK | 无 SDK 依赖，直接 HTTP 调用 |
| API 覆盖 | 受限于 SDK 已实现的接口 | 可调用任意 REST API |
| 事件类型 | 4 种消息事件 | 35+ 种事件（消息/关系/频道/表态/审核/论坛等） |
| 自动事件 | 不支持 | 入群/退群/好友/首次对话自动回复，19 种事件日志 |
| Markdown | 基础 Markdown 降级 | 原生 Markdown + QQ 模板 + AJ 万能模板 |
| 按钮面板 | 不支持 | 动态按钮构建，支持权限控制 |
| ARK 卡片 | 不支持 | 支持 Template 23/24/37 |
| 模板系统 | 无 | 多源注册、YAML/JSON、参数化渲染、热加载 |
| 数据库 | 无 | SQLite 事件日志 + 用户身份/场景追踪 |
| 业务扩展 | 需按框架插件机制扩展 | 可在插件内挂载私有扩展，当前兼容固定命令集 |

简单来说：如果只需要基础的消息收发，使用框架内置适配器即可；如果需要更丰富的消息类型、自动事件处理、模板系统或业务扩展能力，推荐使用本插件。

## 特性

- **双接入模式**：WebSocket Gateway（长连接推送）和 Webhook（HTTP 回调），按需选择
- **丰富的消息类型**：纯文本、原生 Markdown、QQ Markdown 模板、AJ 万能模板、ARK 卡片、图片、语音、视频、按钮面板
- **35+ 事件类型**：覆盖消息、群/好友关系、频道/子频道生命周期、成员变动、表态、审核、论坛等
- **自动事件处理**：入群欢迎、好友添加、首次对话欢迎等，支持配置文案和场景过滤
- **Markdown 模板系统**：多源注册、YAML/JSON 格式、`{{key}}` 参数化渲染、文件热加载
- **按钮/键盘构建**：动态按钮面板，支持管理员/指定用户/指定角色权限控制
- **数据持久化**：SQLite（WAL 模式），自动记录事件日志、用户身份、场景映射
- **私有扩展兼容**：可挂载 `private_bot/` 或 `wanbot/` 的既有业务命令和模板，不修改 AstrBot 框架

## 安装

将本仓库克隆到 AstrBot 的插件目录下：

```bash
cd <AstrBot安装目录>/data/plugins
git clone <本仓库地址> qq_restapi
```

重启 AstrBot 即可自动加载。

## 配置

在 AstrBot 管理面板中添加平台，选择 `qq_restapi`（WebSocket 模式）或 `qq_restapi_webhook`（Webhook 模式）。

### 必填项

| 配置项 | 说明 |
|--------|------|
| `appid` | QQ 机器人 AppID |
| `secret` | QQ 机器人密钥 |

### 可选项（插件配置面板）

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `group_add_robot_message` | 入群欢迎消息（为空则不发送） | `欢迎加入，本机器人已入群～` |
| `group_member_add_message` | 普通群成员入群欢迎（为空则只记录，可用用户/群占位符） | 空 |
| `friend_add_message` | 好友添加欢迎消息（为空则不发送） | `你好，我是小万，欢迎添加好友～` |
| `new_user_welcome_message` | 首次对话欢迎消息（为空则不发送） | `欢迎第一次和我聊天～` |
| `enable_group_remove_notice` | 退群提示开关 | `false` |
| `enable_friend_remove_notice` | 删好友提示开关 | `false` |
| `use_union_id_for_group` | 群聊/单聊优先使用 Union OpenID | `true` |
| `use_union_id_for_channel` | 频道场景优先使用 Union OpenID | `true` |
| `markdown_aj_template_id` | AJ 万能模板 ID | 空 |
| `markdown_aj_keys` | AJ 万能模板参数键名（逗号分隔） | 空 |
| `bot_api_base_url` | 私有命令业务后端 API 地址 | 空 |
| `debug_event_log` | 输出事件类型、字段摘要和解析结果 | `false` |
| `auto_event_log_groups` | 自动事件日志/插件事件存储分组开关 | 10 个分组均为 `true` |
| `full_group_reply` | 全量群消息回复策略，默认非 @ 只入上下文 | `mode: normal` |

`full_group_reply` 支持 `normal`、`random_reply`、`all_as_at`、`smart_reply`、`smart_random`，完整参数见 [全量群消息回复模式说明](docs/full_group_reply_modes.md)。自动事件配置见 [自动事件说明](docs/auto_events_guide.md)。

### Webhook 模式额外配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `unified_webhook_mode` | 统一 Webhook 入口模式 | `true` |
| `webhook_uuid` | Webhook UUID（自动生成） | 空 |

当前 Webhook 适配器只支持统一入口模式。回调地址由 AstrBot 根据 `webhook_uuid` 展示和路由，插件复用框架的 `FastAPIWebhookServer`，不需要单独启动 Quart 服务。

平台配置模板中仍保留 `port`、`callback_server_host` 和 `path` 作为历史兼容字段；统一入口模式不会使用它们。

## 消息类型

| 类型 | 发送方式 | 适用场景 |
|------|----------|---------|
| 纯文本 | `yield event.plain_result(text)` | 所有场景 |
| 原生 Markdown | `await event.reply(content=md, use_markdown=True)` | 群/私聊/频道 |
| QQ Markdown 模板 | `await event.reply_markdown(template_id, params=...)` | 群/私聊/频道 |
| AJ 万能模板 | `await event.reply_markdown_aj(text)` | 群/私聊/频道 |
| ARK 卡片 | `await event.reply_ark(template_id=24, kv_data=[...])` | 群/私聊/频道 |
| 图片 | `await event.reply_image(url=...)` | 群/私聊 |
| 语音 | `await event.reply_voice(url=...)` | 群/私聊 |
| 视频 | `await event.reply_video(url=...)` | 群/私聊 |

> `event.reply()` / `event.reply_markdown()` 等方法是 `QQRestAPIEvent` 特有的，使用前需 `hasattr` 检查。

## 支持的事件类型

**消息事件**：群 AT 消息、全量群消息、C2C 私聊、频道 @消息、频道消息、频道私聊

**关系事件**：机器人入群/退群、好友添加/删除

**频道事件**：频道创建/更新/删除、子频道创建/更新/删除

**成员事件**：普通群成员加入/退出、频道成员加入/更新/移除

**互动事件**：消息表态添加/移除、消息审核通过/拒绝

**论坛事件**：帖子/回帖/评论的创建/更新/删除

**其他**：群消息接收/拒绝设置、消息撤回等

## 私有扩展目录

插件可以挂载私有目录来承载现有业务指令和模板，适合在开源核心能力之上叠加个性化功能。所有扩展仍通过 AstrBot 插件机制注册，不需要修改 AstrBot 框架源码。

当前实现只检测 `private_bot/` 和 `wanbot/` 两个候选目录；存在 `commands/` 子目录时，`main.py` 会加载代码中明确列出的既有命令模块，并将私有 `templates/` 注册为外部模板源。它不是扫描任意目录、任意 Python 文件的通用命令自动发现器。

```
qq_restapi/
├── ...                  ← 公开核心代码
└── private_bot/         ← 私有命令目录（.gitignore 已排除）
    ├── commands/        ← 业务指令实现
    ├── runtime/         ← 私有运行时（如业务 API 客户端）
    ├── core/            ← 私有 API 封装
    ├── templates/       ← 私有 Markdown 模板
    └── assets/          ← 静态素材
```

建议将私有目录作为独立私有 Git 仓库管理。只有依赖私有后端的命令才需要配置 `bot_api_base_url`。

## 指令开发

本插件公开核心主要提供平台适配器能力；仓库中的可选私有目录可能包含本地业务指令。新增通用指令时，仍应使用 AstrBot 提供的命令装饰器显式注册。

指令实现可按 async generator 拆分，例如在私有扩展的 `commands/` 目录下创建独立文件：

```python
# commands/my_command.py
async def my_command_impl(plugin, event):
    try:
        # 你的业务逻辑
        yield event.plain_result("回复内容")
    finally:
        event.stop_event()
```

然后在插件类中注册：

```python
@filter.command("我的指令")
async def my_command(self, event: AstrMessageEvent):
    async for result in my_command_impl(self, event):
        yield result
```

更多消息类型（Markdown、ARK 卡片、图片、按钮等）的用法参见上方「消息类型」章节和 `docs/` 目录下的开发文档。

## 项目结构

```
main.py                  ← 插件入口：注册、初始化、指令定义
├── public_api.py        ← 公共 API 表面（外部应通过此模块访问内部功能）
├── adapters/            ← 平台适配器
│   ├── qq_restapi_adapter.py         WebSocket Gateway 适配器
│   ├── qq_restapi_webhook_adapter.py Webhook 适配器
│   ├── qq_restapi_webhook_server.py  Webhook 回调处理（FastAPIWebhookServer + Ed25519 验签）
│   └── ws_client.py                  WebSocket 客户端（心跳/identify/resume）
├── core/qq/             ← 复用 runtime 的公共 API 薄兼容层
├── runtime/             ← 运行时核心（事件解析、消息发送、Token 管理、模板系统）
├── db/                  ← 插件自有数据库层（SQLModel + SQLite WAL）
├── utils/               ← 工具（场景识别）
├── templates/           ← Markdown 模板文件 + registry.yaml
└── docs/                ← 开发文档
```

## 自动化测试

测试不连接真实 QQ，也不启动 AstrBot 服务，但需要使用 AstrBot 项目的虚拟环境以取得框架依赖：

```powershell
$env:PYTHONPATH="<AstrBot根目录>;<AstrBot根目录>\data\plugins"
<AstrBot根目录>\venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

## 设计参考与致谢

本插件始终定位为 AstrBot 的 QQ 官方平台适配器：QQ 侧的 WebSocket/Webhook 接入、事件解析和 REST API 发送由插件负责；消息事件流水线、插件调度、会话与对话管理、上下文存储、LLM 调用等能力继续复用 AstrBot，不将其改造成一套独立机器人框架。

本项目早期首先参考了 [ElainaBot v1](https://github.com/ElainaCore/ElainaBot) 的 QQ 官方接口封装与机器人功能设计；在后续传输层和发送层的现代化过程中，又参考了 [ElainaBot v2](https://github.com/ElainaCore/ElainaBot_v2) 的部分封装体系和实现思路，包括：

- QQ 官方 WebSocket/Webhook 双接入的组织方式；
- Gateway 心跳、重连、Resume 和有界分发队列；
- 事件解析、发送 payload 与 Token 管理的分层；
- Markdown、媒体消息和按钮构造等 QQ 官方能力的接口设计。

本项目没有整体迁移 ElainaBot v1/v2 的独立框架、插件市场、Web 管理面板或存储体系，而是选择性吸收适合平台适配器的实现经验，并保持对 AstrBot 事件、会话和插件生态的依赖。按钮发送降级与交互记录等能力仍属于后续专项，不代表当前已经完整迁移参考项目的按钮体系。

感谢 ElainaBot v1 与 ElainaBot v2 项目提供的开源实现与设计参考。

## 开源协议

本项目采用 [LGPL-3.0](LICENSE)（GNU Lesser General Public License v3）协议。

- 如果你修改了适配器本身的代码并分发，需要将修改部分同样开源
- 基于适配器开发的私有指令（如 `private_bot/` 目录）属于独立的上层应用，不受此约束
- 允许商业使用
