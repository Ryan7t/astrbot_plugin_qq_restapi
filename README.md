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
| 图片床 | 不支持 | QQ 官方图床 + Bilibili 图床 |
| 模板系统 | 无 | 多源注册、YAML/JSON、参数化渲染、热加载 |
| 数据库 | 无 | SQLite 事件日志 + 用户身份/场景追踪 |
| 业务扩展 | 需修改框架代码 | 支持挂载私有命令目录，独立管理 |

简单来说：如果只需要基础的消息收发，使用框架内置适配器即可；如果需要更丰富的消息类型、自动事件处理、模板系统或业务扩展能力，推荐使用本插件。

## 特性

- **双接入模式**：WebSocket Gateway（长连接推送）和 Webhook（HTTP 回调），按需选择
- **丰富的消息类型**：纯文本、原生 Markdown、QQ Markdown 模板、AJ 万能模板、ARK 卡片、图片、语音、视频、按钮面板
- **35+ 事件类型**：覆盖消息、群/好友关系、频道/子频道生命周期、成员变动、表态、审核、论坛等
- **自动事件处理**：入群欢迎、好友添加、首次对话欢迎等，支持配置文案和场景过滤
- **Markdown 模板系统**：多源注册、YAML/JSON 格式、`{{key}}` 参数化渲染、文件热加载
- **按钮/键盘构建**：动态按钮面板，支持管理员/指定用户/指定角色权限控制
- **图片床**：QQ 官方子频道图床 + Bilibili 图床双通道
- **数据持久化**：SQLite（WAL 模式），自动记录事件日志、用户身份、场景映射
- **私有命令目录**：支持挂载独立的业务命令包，不影响公开仓库代码

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
| `friend_add_message` | 好友添加欢迎消息（为空则不发送） | `你好，我是小万，欢迎添加好友～` |
| `new_user_welcome_message` | 首次对话欢迎消息（为空则不发送） | `欢迎第一次和我聊天～` |
| `enable_group_remove_notice` | 退群提示开关 | `false` |
| `enable_friend_remove_notice` | 删好友提示开关 | `false` |
| `use_union_id_for_group` | 群聊/单聊优先使用 Union OpenID | `false` |
| `use_union_id_for_channel` | 频道场景优先使用 Union OpenID | `false` |
| `markdown_aj_template_id` | AJ 万能模板 ID | 空 |
| `markdown_aj_keys` | AJ 万能模板参数键名（逗号分隔） | 空 |
| `image_bed_channel_id` | QQ 图床子频道 ID | 空 |
| `bilibili_image_bed_config` | Bilibili 图床配置（enabled/csrf_token/sessdata） | 空 |
| `bot_api_base_url` | 私有命令业务后端 API 地址 | 空 |
| `debug_event_log` | 输出原始事件调试日志 | `false` |

### Webhook 模式额外配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `unified_webhook_mode` | 统一 Webhook 入口模式 | `true` |
| `webhook_uuid` | Webhook UUID（自动生成） | 空 |
| `port` | 独立服务器端口 | `6200` |
| `callback_server_host` | 监听地址 | `0.0.0.0` |

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

**消息事件**：群 AT 消息、C2C 私聊、频道 @消息、频道消息、频道私聊

**关系事件**：机器人入群/退群、好友添加/删除

**频道事件**：频道创建/更新/删除、子频道创建/更新/删除

**成员事件**：频道成员加入/移除

**互动事件**：消息表态添加/移除、消息审核通过/拒绝

**论坛事件**：帖子/回帖/评论的创建/更新/删除

**其他**：群消息接收/拒绝设置、消息撤回等

## 私有命令目录

插件支持挂载私有命令目录来扩展业务指令，适合在开源核心能力之上叠加个性化功能。

插件启动时自动检测目录下的 `private_bot/` 或自定义目录名（如 `wanbot/`），若存在且包含 `commands/` 子目录，则自动加载其中的指令、模板和素材。

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

建议将私有目录作为独立私有 Git 仓库管理。如启用了其中的业务命令，需配置 `bot_api_base_url`。

## 指令开发

本插件提供的是平台适配器核心能力，不包含具体的业务指令。你可以根据自己的需求自行开发指令，也可以借助 AI 大模型（如 Claude、ChatGPT 等）辅助生成指令代码。

指令遵循 async generator 模式，在 `commands/` 目录下创建独立文件：

```python
# commands/my_command.py
async def my_command_impl(plugin, event):
    try:
        # 你的业务逻辑
        yield event.plain_result("回复内容")
    finally:
        event.stop_event()
```

然后在 `main.py` 中注册：

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
│   ├── qq_restapi_webhook_server.py  Webhook HTTP 服务器（Quart + Ed25519 验签）
│   └── ws_client.py                  WebSocket 客户端（心跳/identify/resume）
├── core/qq/             ← QQ API 封装（无状态工具层）
├── runtime/             ← 运行时核心（事件解析、消息发送、Token 管理、模板系统）
├── db/                  ← 数据库层（SQLModel + SQLite WAL）
├── utils/               ← 工具（场景识别）
├── templates/           ← Markdown 模板文件 + registry.yaml
└── docs/                ← 开发文档
```

## 开源协议

本项目采用 [LGPL-3.0](LICENSE)（GNU Lesser General Public License v3）协议。

- 如果你修改了适配器本身的代码并分发，需要将修改部分同样开源
- 基于适配器开发的私有指令（如 `private_bot/` 目录）属于独立的上层应用，不受此约束
- 允许商业使用
