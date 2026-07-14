import asyncio
import json
from binascii import Error as BinasciiError
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from astrbot import logger
from astrbot.core.platform.webhook_server import FastAPIWebhookServer


_SIGNATURE_HEADER = "X-Signature-Ed25519"
_SIGNATURE_TIMESTAMP_HEADER = "X-Signature-Timestamp"
_ED25519_SEED_SIZE = 32
_ED25519_SIGNATURE_SIZE = 64


def _build_ed25519_seed(secret: str) -> bytes:
    if not secret:
        raise ValueError("QQ REST API bot secret is empty.")

    seed = secret.encode("utf-8")
    while len(seed) < _ED25519_SEED_SIZE:
        seed *= 2
    return seed[:_ED25519_SEED_SIZE]


def _verify_qq_webhook_signature(
    secret: str,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
) -> bool:
    if not timestamp or not signature:
        return False

    try:
        signature_buffer = bytes.fromhex(signature)
    except (BinasciiError, ValueError):
        return False

    if (
        len(signature_buffer) != _ED25519_SIGNATURE_SIZE
        or signature_buffer[63] & 224 != 0
    ):
        return False

    try:
        seed = _build_ed25519_seed(secret)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
        public_key = private_key.public_key()
        public_key.verify(signature_buffer, timestamp.encode("utf-8") + body)
    except (InvalidSignature, ValueError):
        return False
    return True


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

        self.server = FastAPIWebhookServer("qq-restapi-webhook")
        self.server.add_url_rule(
            self.path,
            view_func=self.callback,
            methods=["GET", "POST"],
        )

    async def webhook_validation(self, validation_payload: dict):
        """处理 QQ 官方 webhook 验证回包."""
        seed = _build_ed25519_seed(self.secret)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
        msg = validation_payload.get("event_ts", "") + validation_payload.get(
            "plain_token",
            "",
        )
        signature = private_key.sign(msg.encode()).hex()
        return {
            "plain_token": validation_payload.get("plain_token"),
            "signature": signature,
        }

    async def callback(self, request: Any):
        return await self.handle_callback(request)

    async def handle_callback(self, request: Any):
        method = str(getattr(request, "method", "POST")).upper()
        if method == "GET":
            return {"code": 0, "message": "qq_restapi webhook endpoint"}, 200
        if method != "POST":
            return {"error": "method not allowed"}, 405

        try:
            body = await request.get_data()
        except Exception as exc:
            logger.warning(f"读取 qq_restapi_webhook 回调 body 失败: {exc}", exc_info=True)
            return {"error": "invalid body"}, 400

        if not body:
            logger.warning("qq_restapi_webhook 回调 body 为空")
            return {"error": "empty body"}, 400

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("qq_restapi_webhook 回调 body 不是有效 JSON")
            return {"error": "invalid json"}, 400

        if not isinstance(payload, dict):
            logger.warning("qq_restapi_webhook 回调 JSON 顶层不是对象")
            return {"error": "invalid json"}, 400

        logger.debug(f"收到 qq_restapi_webhook 回调: {payload}")

        op = payload.get("op")
        if op == 13:
            data = payload.get("d")
            if not isinstance(data, dict):
                return {"error": "invalid validation payload"}, 400
            return await self.webhook_validation(data)

        if not _verify_qq_webhook_signature(
            self.secret,
            request.headers.get(_SIGNATURE_TIMESTAMP_HEADER),
            request.headers.get(_SIGNATURE_HEADER),
            body,
        ):
            logger.warning("qq_restapi_webhook 签名校验失败")
            return {"error": "invalid signature"}, 401

        # 普通事件，交给适配器处理
        try:
            await self.handler(payload)
        except Exception as exc:
            logger.warning(f"处理 qq_restapi_webhook 事件异常: {exc}", exc_info=True)
        return {"code": 0}

    async def start(self):
        logger.info(
            "启动 QQ REST API webhook 适配器: %s:%s%s",
            self.callback_server_host,
            self.port,
            self.path,
        )
        await self.server.run_task(
            host=self.callback_server_host,
            port=self.port,
            shutdown_trigger=self.shutdown_trigger,
        )

    async def shutdown_trigger(self):
        await self.shutdown_event.wait()
