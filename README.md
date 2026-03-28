# QQ REST API 适配器

AstrBot 的 QQ 官方 REST API 平台插件。

## 特性

- 不依赖 `botpy`，直接使用 QQ 官方 REST API
- 提供 `qq_restapi` 与 `qq_restapi_webhook` 平台适配器
- 支持图片、语音、视频、Markdown 等消息类型
- 保留自动事件、事件日志、数据库与模板历史摘要能力
- 支持在仓内挂载私有命令目录

## 说明

- 默认公开部分是平台核心能力。
- 开源仓文档约定默认私有目录名为 `private_bot/`。
- 如果目录下存在 `private_bot/` 或自定义目录（例如 `wanbot/`），插件会自动加载其中的命令、素材、业务模板与业务 API 客户端。
- 建议将该私有目录作为独立私有 Git 仓库管理，并在公开仓 `.gitignore` 中忽略。

## 配置

在 AstrBot 管理面板中添加平台，选择 `qq_restapi` 或 `qq_restapi_webhook`。

如果启用了 `private_bot/` 中的业务命令，还需要配置 `bot_api_base_url`。
