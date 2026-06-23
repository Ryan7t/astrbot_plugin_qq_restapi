"""
精简版 QQ Gateway WebSocket 客户端（基于 Elaina 思路移植），用于接收消息事件。
包含心跳、resume/reconnect、READY/RESUMED 管理事件过滤，以及有界队列背压。
"""

import asyncio
import contextlib
import json
import time
from typing import Awaitable, Callable, Optional

import websockets

from astrbot import logger

from ..runtime.token_manager import TokenManager
from ..runtime.httpx_pool import get_async_client

GatewayHandler = Callable[[dict], Awaitable[None]]

_OP_DISPATCH = 0
_OP_HEARTBEAT = 1
_OP_IDENTIFY = 2
_OP_RESUME = 6
_OP_RECONNECT = 7
_OP_INVALID_SESSION = 9
_OP_HELLO = 10
_OP_HEARTBEAT_ACK = 11
_MAX_PENDING_DISPATCHES = 256


class QQGatewayClient:
    def __init__(
        self,
        token_manager: TokenManager,
        intents: int,
        on_dispatch: GatewayHandler,
        on_connect: Optional[GatewayHandler] = None,
        on_disconnect: Optional[GatewayHandler] = None,
        is_sandbox: bool = False,
        reconnect_interval: int = 5,
        max_reconnects: int = -1,
        max_pending_dispatches: int = _MAX_PENDING_DISPATCHES,
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
        self._reconnect_interval = max(1, int(reconnect_interval or 5))
        self._max_reconnects = int(max_reconnects or -1)
        self._reconnect_count = 0
        self._dispatch_queue: asyncio.Queue[dict] = asyncio.Queue(
            maxsize=max(1, int(max_pending_dispatches or _MAX_PENDING_DISPATCHES))
        )
        self._dispatch_worker_task: asyncio.Task | None = None

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
        await self._send({"op": _OP_HEARTBEAT, "d": self._last_seq})

    async def _identify(self):
        token = await self.token_manager.get_token()
        await self._send(
            {
                "op": _OP_IDENTIFY,
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
                "op": _OP_RESUME,
                "d": {
                    "token": f"QQBot {token}",
                    "session_id": self._session_id,
                    "seq": self._last_seq,
                },
            }
        )

    async def close(self):
        self._stop = True
        if self._dispatch_worker_task and not self._dispatch_worker_task.done():
            self._dispatch_worker_task.cancel()
        if self.ws:
            with contextlib.suppress(Exception):
                await self.ws.close()

    async def run(self):
        self._ensure_dispatch_worker()
        while not self._stop:
            try:
                url = await self._fetch_gateway_url()
                if not url:
                    raise RuntimeError("获取 QQ Gateway 地址失败")
                heartbeat_task = None
                async with websockets.connect(url) as ws:
                    try:
                        self.ws = ws
                        self._reconnect_count = 0
                        if self.on_connect:
                            await self.on_connect({"ts": time.time()})
                        async for message in ws:
                            try:
                                payload = json.loads(message)
                            except Exception:
                                continue
                            op = payload.get("op")
                            if payload.get("s") is not None:
                                self._last_seq = payload.get("s")
                            if op == _OP_HELLO:
                                self._heartbeat_interval = payload.get("d", {}).get("heartbeat_interval", 45000) / 1000
                                if heartbeat_task is None or heartbeat_task.done():
                                    heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                                if self._session_id and self._last_seq is not None:
                                    await self._resume()
                                else:
                                    await self._identify()
                            elif op == _OP_DISPATCH:
                                event_type = payload.get("t")
                                if event_type == "READY":
                                    self._session_id = payload.get("d", {}).get("session_id")
                                    logger.info("qq_restapi gateway ready: session=%s", self._session_id)
                                    continue
                                if event_type == "RESUMED":
                                    logger.info("qq_restapi gateway resumed")
                                    continue
                                await self._queue_dispatch(payload)
                            elif op == _OP_RECONNECT:
                                logger.info("qq_restapi gateway requested reconnect")
                                break
                            elif op == _OP_INVALID_SESSION:
                                resumable = bool(payload.get("d")) and bool(self._session_id)
                                if resumable:
                                    logger.warning("qq_restapi gateway session invalid but resumable")
                                else:
                                    logger.warning("qq_restapi gateway session invalid, identifying again")
                                    self._session_id = None
                                    self._last_seq = None
                                await asyncio.sleep(3)
                                break
                            elif op == _OP_HEARTBEAT_ACK:
                                pass
                    finally:
                        if heartbeat_task:
                            heartbeat_task.cancel()
                        if self.on_disconnect:
                            await self.on_disconnect({"ts": time.time()})
                        self.ws = None
                if not self._stop:
                    await asyncio.sleep(self._reconnect_interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"QQ gateway 连接异常: {exc}")
                self._reconnect_count += 1
                if 0 < self._max_reconnects <= self._reconnect_count:
                    logger.error("QQ gateway 达到最大重连次数: %s", self._max_reconnects)
                    break
                await asyncio.sleep(self._reconnect_interval)
        await self.close()

    def _ensure_dispatch_worker(self):
        if self._dispatch_worker_task is None or self._dispatch_worker_task.done():
            self._dispatch_worker_task = asyncio.create_task(self._dispatch_worker())

    async def _queue_dispatch(self, payload: dict):
        if self.on_dispatch is None:
            return
        if self._dispatch_queue.full():
            logger.warning(
                "qq_restapi gateway 事件队列已满，等待下游处理: pending=%s",
                self._dispatch_queue.qsize(),
            )
        await self._dispatch_queue.put(payload)

    async def _dispatch_worker(self):
        while not self._stop:
            try:
                payload = await self._dispatch_queue.get()
            except asyncio.CancelledError:
                break
            try:
                if self.on_dispatch:
                    await self.on_dispatch(payload)
            except Exception as exc:
                logger.warning("QQ gateway 事件分发异常: %s", exc, exc_info=True)
            finally:
                self._dispatch_queue.task_done()

    async def _heartbeat_loop(self):
        while not self._stop and self.ws:
            await asyncio.sleep(self._heartbeat_interval)
            try:
                await self._send_heartbeat()
            except Exception:
                break
