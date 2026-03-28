import asyncio
import logging
from typing import Any, Optional

import quart
from cryptography.hazmat.primitives.asymmetric import ed25519

from astrbot import logger

# remove logger handler
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)


class QQRestAPIWebhookServer:
    """简易 QQ REST API Webhook 服务器，接收 QQ 推送并回调适配器."""

    def __init__(
        self,
        config: dict,
        handler,
    ):
        self.appid = config["appid"]
        self.secret = config["secret"]
        self.port = int(config.get("port", 6200))
        self.callback_server_host = config.get("callback_server_host", "0.0.0.0")
        self.path = config.get("path", "/qq-restapi-webhook/callback")
        self.handler = handler  # async function(payload: dict) -> None
        self.shutdown_event = asyncio.Event()

        self.server = quart.Quart(__name__)
        self.server.add_url_rule(self.path, view_func=self.callback, methods=["POST"])

    async def repeat_seed(self, bot_secret: str, target_size: int = 32) -> bytes:
        seed = bot_secret
        while len(seed) < target_size:
            seed *= 2
        return seed[:target_size].encode("utf-8")

    async def webhook_validation(self, validation_payload: dict):
        """处理 QQ 官方 webhook 验证回包."""
        seed = await self.repeat_seed(self.secret)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
        msg = validation_payload.get("event_ts", "") + validation_payload.get("plain_token", "")
        signature = private_key.sign(msg.encode()).hex()
        return {"plain_token": validation_payload.get("plain_token"), "signature": signature}

    async def callback(self):
        return await self.handle_callback(quart.request)

    async def handle_callback(self, request: Any):
        try:
            payload: dict = await request.json
        except Exception:
            return {"error": "invalid json"}, 400

        logger.debug(f"收到 qq_restapi_webhook 回调: {payload}")

        op = payload.get("op")
        data = payload.get("d", {})
        if op == 13:
            # 官方验证
            return await self.webhook_validation(data)

        # 普通事件，交给适配器处理
        try:
            await self.handler(payload)
        except Exception as exc:
            logger.warning(f"处理 qq_restapi_webhook 事件异常: {exc}", exc_info=True)
        return {"code": 0}

    async def start(self):
        logger.info(f"启动 QQ REST API webhook 适配器: {self.callback_server_host}:{self.port}{self.path}")
        await self.server.run_task(
            host=self.callback_server_host,
            port=self.port,
            shutdown_trigger=self.shutdown_trigger,
        )

    async def shutdown_trigger(self):
        await self.shutdown_event.wait()
