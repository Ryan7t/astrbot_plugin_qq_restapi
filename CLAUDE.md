# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

AstrBot 的 QQ 官方 REST API 平台适配器插件。不依赖 botpy 库，直接使用 QQ 官方 REST API 进行消息收发。支持 WebSocket Gateway 和 Webhook 两种接入模式。

**重要约束**：本项目是插件代码，严禁修改 AstrBot 框架代码。所有变更仅限于本插件目录内。

## 验证命令

```bash
# 语法检查（无框架依赖时的基本验证）
python3 -c "import ast; ast.parse(open('main.py').read())"

# 批量检查所有 Python 文件
find . -name '*.py' -exec python3 -c "import ast; ast.parse(open('{}').read()); print('{} OK')" \;

# 验证 JSON 配置格式
python3 -c "import json; json.load(open('_conf_schema.json')); print('OK')"
```

无独立的 lint/test/build 流程。插件直接由 AstrBot 框架加载运行，验证需启动 AstrBot 实例。

## 架构

### 分层结构

```
main.py                  ← 插件入口：注册、初始化、指令定义
├── public_api.py        ← 稳定公共 API 表面（commands/ 和外部应通过此模块访问内部功能）
├── adapters/            ← 平台适配器
│   ├── qq_restapi_adapter.py         WebSocket Gateway 适配器
│   ├── qq_restapi_webhook_adapter.py Webhook 适配器
│   ├── qq_restapi_webhook_server.py  Webhook HTTP 服务器（Quart + Ed25519 验签）
│   └── ws_client.py                  QQ Gateway WebSocket 客户端（心跳/identify/resume）
├── core/                ← QQ 平台 API 封装（无状态工具层）
│   └── qq/
│       ├── sender.py       Markdown 模板参数构建 + 直接发送
│       └── token_manager.py 函数式 token 获取（独立于适配器，供 core 层使用）
├── runtime/             ← 运行时核心（有状态，依赖全局上下文）
│   ├── context.py          全局上下文单例（Context/Config/DB）
│   ├── sender.py           QQRestAPISender 类（文本/Markdown/图片/媒体/语音/视频）
│   ├── token_manager.py    TokenManager 类（适配器级，带缓存的 token 管理）
│   ├── qq_restapi_event.py QQRestAPIEvent（AstrMessageEvent 实现，reply/reply_markdown 等）
│   ├── message_parser.py   QQ 事件类型常量 + 事件解析
│   ├── auto_events.py      自动事件处理（入群/好友/表态等）
│   ├── db_service.py       DB 服务定位器（懒加载 QQRestAPIService 单例）
│   ├── httpx_pool.py       全局 httpx 连接池
│   ├── template_registry.py / template_store.py  Markdown 模板系统
│   └── last_message_cache.py
├── db/                  ← 数据库层（SQLModel + SQLite WAL）
├── utils/               ← 工具（场景识别 scene.py）
├── templates/           ← Markdown 模板文件 + registry.yaml
├── wanbot/              ← 私有命令目录（.gitignore 排除，独立管理）
│   ├── commands/           业务指令实现
│   ├── runtime/            私有运行时（bot_api_client.py、httpx_pool.py 等）
│   ├── core/qq/            私有 QQ API 封装（sender.py）
│   ├── templates/          私有模板
│   └── assets/             静态素材
└── docs/                ← 开发文档 + QQ 官方平台文档
```

### 核心模式

**插件注册**：`@register("qq_restapi", ...)` + 继承 `Star`

**全局上下文注入**：`runtime/context.py` 维护全局单例，通过 `set_context()` / `get_context()` 等函数访问。`_PLUGIN_CONFIG_KEYS` 集合控制哪些配置项被合并。新增配置必须同时修改 `_PLUGIN_CONFIG_KEYS` 和 `_conf_schema.json`。

**指令注册**：`@filter.command("指令名")` 装饰器。

**凭证获取**：`plugin._get_app_credentials()` → `public_api.get_app_credentials_from_plugin()` → 从已注册的 QQ 平台实例提取 appid/secret。

### public_api.py — 公共 API 入口

所有 commands 和外部模块应通过 `public_api.py` 访问插件内部功能，而非直接 import runtime 子模块。它统一导出：场景识别（`resolve_scene`）、模板操作、凭证获取、httpx 连接池、最后消息 ID 等。

### 私有命令目录机制

`main.py` 在启动时按优先级检测 `private_bot/` 或 `wanbot/` 目录。若存在且包含 `commands/` 子目录，则动态导入其中的指令实现。私有目录拥有独立的 `runtime/`、`core/`、`templates/` 等子结构，通过 `register_external_template_source()` 注册私有模板源。

`.gitignore` 已排除 `private_bot/` 和 `wanbot/`，建议作为独立私有仓库管理。

### Token 管理（两套实现）

| 位置 | 类型 | 用途 |
|------|------|------|
| `runtime/token_manager.py` | `TokenManager` 类 | 适配器使用，实例级缓存 |
| `core/qq/token_manager.py` | `get_access_token()` 函数 | core 层直接 API 调用，模块级缓存 |

两者独立，各自维护 token 缓存。适配器内的 `QQRestAPISender` 和 `QQGatewayClient` 使用前者。

### 指令实现约定

指令实现在 `commands/` 下独立文件中，遵循 async generator 模式：

```python
# commands/xxx.py
async def xxx_impl(plugin, event: AstrMessageEvent):
    try:
        # 业务逻辑...
        yield event.plain_result("文本回复")
        # 或 await event.reply(content=markdown, use_markdown=True)
    finally:
        event.stop_event()

# main.py 中注册
@filter.command("指令名")
async def xxx(self, event: AstrMessageEvent):
    async for result in xxx_impl(self, event):
        yield result
```

**关键注意**：`event.message_str` 包含完整消息文本（含命令名本身），解析参数时必须先去掉命令名前缀。

### 消息发送方式

| 方式 | 用法 | msg_type |
|------|------|----------|
| 纯文本 | `yield event.plain_result(text)` | 0 |
| 原生 Markdown | `await event.reply(content=md, use_markdown=True)` | 2 |
| QQ Markdown 模板 | `await event.reply_markdown(template_id, params=...)` | 2 |
| 图片 | `await event.reply(media=...)` | 7 |

`event.reply()` 和 `event.reply_markdown()` 是 `QQRestAPIEvent` 特有方法，使用前需 `hasattr` 检查。

### HTTP 请求

所有 HTTP 请求复用 `runtime/httpx_pool.get_async_client()` 全局连接池，不要创建新的 httpx 客户端实例。`wanbot/runtime/httpx_pool.py` 为私有目录提供独立连接池。

### 适配器热重载

适配器在注册前会清理 `platform_cls_map` 和 `platform_registry` 中的旧注册，避免插件重载时重复注册。修改适配器时需保留此机制。

### 数据库

SQLModel + SQLite（WAL 模式）。表定义在 `db/models.py`，数据操作在 `db/repository.py`，业务逻辑在 `db/service.py`。`QQRestAPIDatabase` 在 `initialize()` 时自动建表。运行时通过 `runtime/db_service.py` 的 `get_db_service()` 懒加载获取服务实例。

### WebSocket 适配器连接流程

`QQRestAPIPlatformAdapter` → `QQGatewayClient`（`ws_client.py`）→ QQ Gateway。客户端处理 hello(op=10) → identify(op=2) / resume(op=6) → dispatch(op=0) 事件循环，含自动心跳和指数退避重连。

### Webhook 适配器连接流程

`QQRestAPIWebhookPlatformAdapter` → `QQRestAPIWebhookServer`（Quart 应用）→ 接收 QQ 回调。支持 Ed25519 签名验证和统一 Webhook 入口模式（`unified_webhook_mode`）。
