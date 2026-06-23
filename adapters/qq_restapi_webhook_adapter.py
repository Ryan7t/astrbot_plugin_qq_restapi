import asyncio
import uuid
from typing import cast

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.platform import MessageType, Platform, PlatformMetadata
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.api.platform import register_platform_adapter
from astrbot.core.utils.webhook_utils import log_webhook_info
from astrbot.core.platform.register import platform_cls_map, platform_registry

from ..runtime.dispatch import handle_qq_payload
from ..runtime.sender import QQRestAPISender
from ..runtime.token_manager import TokenManager
from ..runtime import merge_plugin_config
from .qq_restapi_webhook_server import QQRestAPIWebhookServer

# 兼容热重载：若已注册则先移除旧注册，避免冲突
if "qq_restapi_webhook" in platform_cls_map:
    platform_cls_map.pop("qq_restapi_webhook", None)
    platform_registry[:] = [
        pm for pm in platform_registry if pm.name != "qq_restapi_webhook"
    ]


@register_platform_adapter(
    "qq_restapi_webhook",
    "QQ 官方 REST API 适配器（Webhook）",
    default_config_tmpl={
        "appid": "your_appid",
        "secret": "your_secret",
        "is_sandbox": False,
        "port": 6200,
        "callback_server_host": "0.0.0.0",
        "path": "/qq-restapi-webhook/callback",
        "unified_webhook_mode": True,
        "webhook_uuid": "",
    },
    support_streaming_message=False,
)
class QQRestAPIWebhookPlatformAdapter(Platform):
    """Webhook 方式接收 QQ 事件，复用 sender/token/parser。"""

    def __init__(self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue) -> None:
        super().__init__(platform_config, event_queue)
        self.appid = platform_config["appid"]
        self.secret = platform_config["secret"]
        self.token_mgr = TokenManager(self.appid, self.secret)
        self.is_sandbox = platform_config.get("is_sandbox", False)
        self.sender = QQRestAPISender(self.appid, self.secret, self.token_mgr, is_sandbox=self.is_sandbox)
        self.unified_webhook_mode = platform_config.get("unified_webhook_mode", False)
        self.server = QQRestAPIWebhookServer(platform_config, self._handle_incoming)

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="qq_restapi_webhook",
            description="QQ 官方 REST API 适配器（Webhook）",
            id=cast(str, self.config.get("id")),
        )

    async def run(self):
        webhook_uuid = self.config.get("webhook_uuid")
        if not self.unified_webhook_mode:
            raise RuntimeError("仅支持统一 Webhook 模式，请设置 unified_webhook_mode=true")
        if not webhook_uuid:
            webhook_uuid = uuid.uuid4().hex[:16]
            self.config["webhook_uuid"] = webhook_uuid
        log_webhook_info(f"{self.meta().id}(QQ REST API Webhook)", webhook_uuid)
        await self.server.shutdown_event.wait()  # 挂起等待 terminate

    async def terminate(self):
        self.server.shutdown_event.set()
        logger.info("qq_restapi_webhook adapter stopped")

    async def send_by_session(self, session: MessageSesion, message_chain: MessageChain):
        if not session.session_id:
            return
        if session.message_type == MessageType.FRIEND_MESSAGE:
            if str(session.session_id).isdigit():
                target = {"scene": "channel_dm", "guild_id": session.session_id}
            else:
                target = {"scene": "c2c", "user_id": session.session_id}
        else:
            if str(session.session_id).isdigit():
                target = {"scene": "channel", "channel_id": session.session_id}
            else:
                target = {"scene": "group", "group_id": session.session_id}
        await self.sender.send_text_prefer_markdown(
            target=target,
            content=message_chain.get_plain_text(),
        )

    async def webhook_callback(self, request):
        """统一 Webhook 入口使用，框架会将 /api/platform/webhook/<uuid> 的请求转到这里。"""
        return await self.server.handle_callback(request)

    def _effective_config(self) -> dict:
        return merge_plugin_config(self.config)

    async def _handle_incoming(self, payload: dict):
        effective_cfg = self._effective_config()
        await handle_qq_payload(
            payload,
            source="webhook",
            meta=self.meta(),
            sender=self.sender,
            effective_config=effective_cfg,
            commit_event=self.commit_event,
        )
