"""
精简版 QQ Gateway WebSocket 客户端（基于 Elaina 思路移植），用于接收消息事件。
当前实现包含心跳、hello/dispatch 处理，提供回调接口；如需 resume/reconnect 可后续扩展。
"""

import asyncio
import json
import time
from typing import Awaitable, Callable, Optional

import websockets

from astrbot import logger

from ..runtime.token_manager import TokenManager
from ..runtime.httpx_pool import get_async_client

GatewayHandler = Callable[[dict], Awaitable[None]]


class QQGatewayClient:
    def __init__(
        self,
        token_manager: TokenManager,
        intents: int,
        on_dispatch: GatewayHandler,
        on_connect: Optional[GatewayHandler] = None,
        on_disconnect: Optional[GatewayHandler] = None,
        is_sandbox: bool = False,
    ):
        self.token_manager = token_manager
        self.intents = intents
        self.on_dispatch = on_dispatch
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.is_sandbox = bool(is_sandbox)
        self.ws = None
        self._heartbeat_interval = 45
        self._last_seq = None
        self._session_id = None
        self._stop = False

    async def _fetch_gateway_url(self) -> str:
        headers = await self.token_manager.auth_headers()
        client = await get_async_client()
        base = "https://sandbox.api.sgroup.qq.com" if self.is_sandbox else "https://api.sgroup.qq.com"
        resp = await client.get(f"{base}/gateway/bot", headers=headers, timeout=10)
        data = resp.json()
        return data.get("url")

    async def _send(self, payload: dict):
        if self.ws:
            await self.ws.send(json.dumps(payload))

    async def _send_heartbeat(self):
        await self._send({"op": 1, "d": self._last_seq})

    async def _identify(self):
        token = await self.token_manager.get_token()
        await self._send(
            {
                "op": 2,
                "d": {
                    "token": f"QQBot {token}",
                    "intents": self.intents,
                    "shard": [0, 1],
                    "properties": {"$os": "linux", "$browser": "qq-restapi", "$device": "qq-restapi"},
                },
            }
        )

    async def _resume(self):
        token = await self.token_manager.get_token()
        await self._send(
            {
                "op": 6,
                "d": {
                    "token": f"QQBot {token}",
                    "session_id": self._session_id,
                    "seq": self._last_seq,
                },
            }
        )

    async def run(self):
        retry_delay = 2
        while not self._stop:
            url = await self._fetch_gateway_url()
            if not url:
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)
                continue
            try:
                async with websockets.connect(url) as ws:
                    self.ws = ws
                    if self.on_connect:
                        await self.on_connect({"ts": time.time()})
                    heartbeat_task = None
                    async for message in ws:
                        try:
                            payload = json.loads(message)
                        except Exception:
                            continue
                        op = payload.get("op")
                        self._last_seq = payload.get("s") or self._last_seq
                        if op == 10:
                            self._heartbeat_interval = payload.get("d", {}).get("heartbeat_interval", 45000) / 1000
                            if heartbeat_task is None or heartbeat_task.done():
                                heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                            if self._session_id and self._last_seq:
                                await self._resume()
                            else:
                                await self._identify()
                        elif op == 0:
                            # dispatch
                            if payload.get("t") == "READY":
                                self._session_id = payload.get("d", {}).get("session_id")
                            if self.on_dispatch:
                                await self.on_dispatch(payload)
                        elif op == 7:
                            # reconnect
                            break
                        elif op == 9:
                            # invalid session
                            self._session_id = None
                            break
                        elif op == 11:
                            pass
                    if heartbeat_task:
                        heartbeat_task.cancel()
                    if self.on_disconnect:
                        await self.on_disconnect({"ts": time.time()})
            except Exception as exc:
                logger.warning(f"QQ gateway 连接异常: {exc}")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)

    async def _heartbeat_loop(self):
        while not self._stop and self.ws:
            await asyncio.sleep(self._heartbeat_interval)
            try:
                await self._send_heartbeat()
            except Exception:
                break
