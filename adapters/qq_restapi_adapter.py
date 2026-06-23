import asyncio
from typing import cast

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.platform import MessageType, Platform, PlatformMetadata
from astrbot.core.platform.astr_message_event import MessageSesion

from astrbot.api.platform import register_platform_adapter
from astrbot.core.platform.register import platform_cls_map, platform_registry

from ..runtime.dispatch import handle_qq_payload
from ..runtime.sender import QQRestAPISender
from ..runtime import merge_plugin_config
from ..runtime.token_manager import TokenManager
from .ws_client import QQGatewayClient

# 兼容热重载：若已注册则先移除旧注册，避免冲突
if "qq_restapi" in platform_cls_map:
    platform_cls_map.pop("qq_restapi", None)
    platform_registry[:] = [pm for pm in platform_registry if pm.name != "qq_restapi"]


@register_platform_adapter(
    "qq_restapi",
    "QQ 官方 REST API 适配器（无需 botpy）",
    default_config_tmpl={
        "appid": "your_appid",
        "secret": "your_secret",
        "is_sandbox": False,
        "intent_mask": None,
        "reconnect_interval": 5,
        "max_reconnects": -1,
        "max_pending_dispatches": 256,
    },
    support_streaming_message=False,
)
class QQRestAPIPlatformAdapter(Platform):
    def __init__(self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue) -> None:
        super().__init__(platform_config, event_queue)
        # 若 mode 指定为 webhook，则不启用 gateway 适配器
        if platform_config.get("mode") == "webhook":
            raise RuntimeError("当前配置为 webhook 模式，请启用 qq_restapi_webhook 适配器")
        self.appid = platform_config["appid"]
        self.secret = platform_config["secret"]
        self.is_sandbox = platform_config.get("is_sandbox", False)
        intents = platform_config.get("intent_mask")
        # Elaina 默认开启群/私聊/interaction/audit 等
        default_intents = (1 << 0) | (1 << 10) | (1 << 12) | (1 << 26) | (1 << 27) | (1 << 25)
        self.intents = intents if intents is not None else default_intents
        self.token_mgr = TokenManager(self.appid, self.secret)
        self.sender = QQRestAPISender(self.appid, self.secret, self.token_mgr, is_sandbox=self.is_sandbox)
        self.gateway = QQGatewayClient(
            token_manager=self.token_mgr,
            intents=self.intents,
            on_dispatch=self._on_dispatch,
            on_connect=self._on_connect,
            on_disconnect=self._on_disconnect,
            is_sandbox=self.is_sandbox,
            reconnect_interval=platform_config.get("reconnect_interval", 5),
            max_reconnects=platform_config.get("max_reconnects", -1),
            max_pending_dispatches=platform_config.get("max_pending_dispatches", 256),
        )

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="qq_restapi",
            description="QQ 官方 REST API 适配器（无需 botpy）",
            id=cast(str, self.config.get("id")),
        )

    async def run(self):
        await self.gateway.run()

    async def terminate(self):
        await self.gateway.close()
        logger.info("qq_restapi adapter stopped")

    async def send_by_session(self, session: MessageSesion, message_chain: MessageChain):
        """主动消息发送（通过 session 发送已知会话）。"""
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

    async def _on_connect(self, _):
        logger.info("qq_restapi gateway connected")

    async def _on_disconnect(self, _):
        logger.warning("qq_restapi gateway disconnected")

    def _effective_config(self) -> dict:
        return merge_plugin_config(self.config)

    async def _on_dispatch(self, payload: dict):
        effective_cfg = self._effective_config()
        await handle_qq_payload(
            payload,
            source="wss",
            meta=self.meta(),
            sender=self.sender,
            effective_config=effective_cfg,
            commit_event=self.commit_event,
        )
