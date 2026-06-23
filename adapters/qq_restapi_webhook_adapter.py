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

from ..runtime.message_parser import parse_event
from ..runtime.qq_restapi_event import QQRestAPIEvent
from ..runtime.auto_events import (
    AUTO_EVENT_MAP,
    auto_event_storage_enabled,
    handle_new_user_welcome,
    handle_relation_event,
)
from ..runtime.db_service import get_db_service
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
        raw_t = payload.get("t") or payload.get("event_type") or payload.get("eventType") or payload.get("type")
        data = payload.get("d") if isinstance(payload.get("d"), dict) else {}
        d_keys = ",".join(sorted(data.keys())) if data else "-"
        effective_cfg = self._effective_config()
        if effective_cfg.get("debug_event_log", False):
            logger.debug(
                "[qq_restapi][debug] webhook收到事件: op=%s t=%s d_keys=%s",
                payload.get("op"),
                raw_t,
                d_keys,
            )
        abm = parse_event(
            payload,
            bot_id=None,
            use_union_id_for_group=effective_cfg.get("use_union_id_for_group", True),
            use_union_id_for_channel=effective_cfg.get("use_union_id_for_channel", True),
        )
        if effective_cfg.get("debug_event_log", False):
            logger.debug(
                "[qq_restapi][debug] webhook解析结果: t=%s scene=%s session_id=%s guild=%s channel=%s user=%s union=%s raw=%s",
                getattr(abm, "qq_event_type", None),
                getattr(abm, "qq_scene", None),
                getattr(abm, "session_id", None),
                getattr(abm, "guild_id", None),
                getattr(abm, "channel_id", None),
                getattr(getattr(abm, "sender", None), "user_id", None),
                getattr(abm, "qq_union_openid", None),
                getattr(abm, "qq_raw_user_id", None),
            )
        if getattr(abm, "qq_ignore", False):
            return
        session_id = abm.session_id
        if not session_id:
            session_id = (
                getattr(abm, "group_id", None)
                or getattr(abm, "channel_id", None)
                or getattr(abm, "guild_id", None)
                or getattr(getattr(abm, "sender", None), "user_id", None)
                or ""
            )
            if session_id:
                abm.session_id = session_id
        if not session_id and abm.type in {MessageType.GROUP_MESSAGE, MessageType.FRIEND_MESSAGE}:
            return
        event = QQRestAPIEvent(
            abm.message_str,
            abm,
            self.meta(),
            session_id,
            self.sender,
            effective_cfg,
        )
        db_service = get_db_service()
        if db_service:
            event_type = getattr(abm, "qq_event_type", None)
            if auto_event_storage_enabled(event_type):
                event_kind = "auto" if event_type in AUTO_EVENT_MAP else "message"
                if event_kind == "message" and abm.type not in (
                    MessageType.GROUP_MESSAGE,
                    MessageType.FRIEND_MESSAGE,
                ):
                    event_kind = "system"
                await db_service.record_event(event, event_kind=event_kind)
        if await handle_relation_event(event):
            return
        await handle_new_user_welcome(event)
        self.commit_event(event)
