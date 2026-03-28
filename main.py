from __future__ import annotations

from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

_PLUGIN_ROOT = Path(__file__).resolve().parent
_PRIVATE_BOT_CANDIDATES = ("private_bot", "wanbot")
_PRIVATE_BOT_NAME = next(
    (
        name
        for name in _PRIVATE_BOT_CANDIDATES
        if (_PLUGIN_ROOT / name / "commands").exists()
    ),
    None,
)
_PRIVATE_BOT_ROOT = _PLUGIN_ROOT / _PRIVATE_BOT_NAME if _PRIVATE_BOT_NAME else None
_PRIVATE_BOT_INSTALLED = _PRIVATE_BOT_ROOT is not None
_PRIVATE_BOT_ERROR: Exception | None = None

if _PRIVATE_BOT_INSTALLED:
    try:
        if _PRIVATE_BOT_NAME == "wanbot":
            from .wanbot.commands.daily_fortune import (
                clear_daily_fortune_cache_impl,
                daily_fortune_impl,
            )
            from .wanbot.commands.help_card import help_card_impl
            from .wanbot.commands.latest_messages import latest_messages_impl
            from .wanbot.commands.markdown_template_test import (
                markdown_template_test_impl,
            )
            from .wanbot.commands.random_messages import random_messages_impl
            from .wanbot.commands.random_tree_holes import random_tree_holes_impl
            from .wanbot.commands.search_messages import search_messages_impl
            from .wanbot.commands.test_image import (
                test_image_impl,
                test_local_image_impl,
            )
            from .wanbot.commands.welcome_card_test import test_welcome_card_impl
        else:
            from .private_bot.commands.daily_fortune import (
                clear_daily_fortune_cache_impl,
                daily_fortune_impl,
            )
            from .private_bot.commands.help_card import help_card_impl
            from .private_bot.commands.latest_messages import latest_messages_impl
            from .private_bot.commands.markdown_template_test import (
                markdown_template_test_impl,
            )
            from .private_bot.commands.random_messages import random_messages_impl
            from .private_bot.commands.random_tree_holes import random_tree_holes_impl
            from .private_bot.commands.search_messages import search_messages_impl
            from .private_bot.commands.test_image import (
                test_image_impl,
                test_local_image_impl,
            )
            from .private_bot.commands.welcome_card_test import test_welcome_card_impl
    except Exception as exc:
        _PRIVATE_BOT_ERROR = exc


@register("qq_restapi", "YourName", "QQ 官方 REST API 平台适配器", "0.1.0")
class QQRestApiPlugin(Star):
    """QQ REST API 平台适配器插件。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        from .runtime import set_context, set_plugin_config, set_plugin_db
        from .db import QQRestAPIDatabase

        if _PRIVATE_BOT_ERROR is not None:
            raise RuntimeError(
                f"检测到 private_bot 目录但加载失败: {_PRIVATE_BOT_ERROR}"
            ) from _PRIVATE_BOT_ERROR

        set_context(context)
        set_plugin_config(config)
        self.config = config
        self.db = QQRestAPIDatabase()
        set_plugin_db(self.db)

        from .adapters.qq_restapi_adapter import QQRestAPIPlatformAdapter  # noqa: F401
        from .adapters.qq_restapi_webhook_adapter import (  # noqa: F401
            QQRestAPIWebhookPlatformAdapter,
        )

        self._private_template_source_key: str | None = None
        if _PRIVATE_BOT_INSTALLED:
            self._private_template_source_key = self._register_private_template_source()

    def _register_private_template_source(self) -> str:
        from .public_api import register_external_template_source

        assert _PRIVATE_BOT_ROOT is not None
        template_dir = _PRIVATE_BOT_ROOT / "templates"
        registry_path = template_dir / "registry.yaml"
        source_key = register_external_template_source(
            template_dir=template_dir,
            registry_path=registry_path,
            source_name=f"qq_restapi_{_PRIVATE_BOT_NAME}",
        )
        logger.info(
            "qq_restapi 私有命令目录已加载: %s，模板源=%s",
            _PRIVATE_BOT_NAME,
            source_key,
        )
        return source_key

    def _get_app_credentials(self):
        from .public_api import get_app_credentials_from_plugin

        return get_app_credentials_from_plugin(self)

    def get_app_credentials(self):
        return self._get_app_credentials()

    async def initialize(self):
        try:
            await self.db.initialize()
            logger.info(f"QQ REST API 插件数据库已初始化: {self.db.db_path}")
        except Exception:
            logger.exception("QQ REST API 插件数据库初始化失败")
            raise

    async def terminate(self):
        db = getattr(self, "db", None)
        if db:
            try:
                await db.close()
                logger.info("QQ REST API 插件数据库已关闭")
            except Exception:
                logger.exception("QQ REST API 插件数据库关闭失败")

    if _PRIVATE_BOT_INSTALLED and _PRIVATE_BOT_ERROR is None:
        @filter.command("helloworld")
        async def helloworld(self, event: AstrMessageEvent):
            user_name = event.get_sender_name()
            message_str = event.message_str
            message_chain = event.get_messages()
            logger.info(message_chain)
            yield event.plain_result(f"Hello, {user_name}, 你发了 {message_str}!")

        @filter.command("测试欢迎卡片")
        async def test_welcome_card(self, event: AstrMessageEvent):
            async for result in test_welcome_card_impl(self, event):
                yield result

        @filter.command("测试图片")
        async def test_image(self, event: AstrMessageEvent):
            async for result in test_image_impl(self, event):
                yield result

        @filter.command("测试本地图片")
        async def test_local_image(self, event: AstrMessageEvent):
            async for result in test_local_image_impl(self, event):
                yield result

        @filter.command("今日运势")
        async def daily_fortune(self, event: AstrMessageEvent):
            async for result in daily_fortune_impl(self, event):
                yield result

        @filter.command("清理今日运势缓存")
        async def clear_daily_fortune_cache(
            self, event: AstrMessageEvent, mode: str = "today"
        ):
            async for result in clear_daily_fortune_cache_impl(
                self, event, mode=mode
            ):
                yield result

        @filter.command("帮助")
        async def help_card(self, event: AstrMessageEvent):
            async for result in help_card_impl(self, event):
                yield result

        @filter.command("测试模板")
        async def markdown_template_test(self, event: AstrMessageEvent):
            async for result in markdown_template_test_impl(self, event):
                yield result

        @filter.command("搜索留言")
        async def search_messages(self, event: AstrMessageEvent):
            async for result in search_messages_impl(self, event):
                yield result

        @filter.command("随机留言")
        async def random_messages(self, event: AstrMessageEvent):
            async for result in random_messages_impl(self, event):
                yield result

        @filter.command("最新留言")
        async def latest_messages(self, event: AstrMessageEvent):
            async for result in latest_messages_impl(self, event):
                yield result

        @filter.command("随机树洞")
        async def random_tree_holes(self, event: AstrMessageEvent):
            async for result in random_tree_holes_impl(self, event):
                yield result

        @filter.command("当前场景")
        async def current_scene(self, event: AstrMessageEvent):
            from .public_api import resolve_scene

            context = resolve_scene(self, event)
            message_obj = getattr(event, "message_obj", None)
            session_id = getattr(message_obj, "session_id", None)
            platform_id = ""
            try:
                platform_id = event.get_platform_id() or ""
            except Exception:
                platform_id = ""

            def render(value):
                if value is None or value == "":
                    return "无"
                return str(value)

            fields = [
                ("解析错误", context.error),
                ("场景", context.scene_type),
                ("平台", context.platform_name),
                ("平台ID", platform_id),
                ("用户ID", context.user_id),
                ("会话ID", session_id),
                ("消息ID", context.message_id),
                ("群ID", context.group_id),
                ("频道ID", context.guild_id),
                ("子频道ID", context.channel_id),
                ("频道私聊ID", context.dm_id),
                ("来源频道ID", context.source_guild_id),
                ("来源子频道ID", context.source_channel_id),
                ("Union OpenID", getattr(message_obj, "qq_union_openid", None)),
                ("Raw OpenID", getattr(message_obj, "qq_raw_user_id", None)),
            ]

            lines = ["当前场景信息："]
            lines.extend(f"{label}: {render(value)}" for label, value in fields)
            yield event.plain_result("\n".join(lines))

        ENABLE_RECALL_COMMAND = False
        if ENABLE_RECALL_COMMAND:
            @filter.command("撤回上一条消息")
            async def recall_last_message(self, event: AstrMessageEvent):
                from .public_api import get_last_message_id

                if not hasattr(event, "recall_message"):
                    yield event.plain_result("当前平台不支持撤回消息。")
                    return
                origin = getattr(event, "unified_msg_origin", None)
                message_id = get_last_message_id(origin)
                if not message_id:
                    yield event.plain_result("未找到上一条机器人消息 ID。")
                    return
                try:
                    resp = await event.recall_message(message_id)
                    status = None
                    if isinstance(resp, dict):
                        status = resp.get("status_code")
                        data = resp.get("data") or {}
                        code = data.get("code") if isinstance(data, dict) else None
                        message = (
                            data.get("message") if isinstance(data, dict) else None
                        )
                        if status in (200, 204):
                            yield event.plain_result(f"撤回成功：{message_id}")
                            return
                        detail = f"HTTP {status}" if status else "未知错误"
                        if code or message:
                            detail = (
                                f"{detail} / code={code} / message={message}"
                            )
                        yield event.plain_result(f"撤回失败：{detail}")
                        return
                    yield event.plain_result(f"已尝试撤回上一条消息：{message_id}")
                except Exception as exc:
                    yield event.plain_result(f"撤回失败：{exc}")
