from __future__ import annotations

import asyncio
import threading

import httpx

_MAX_CONNECTIONS = 100
_MAX_KEEPALIVE = 20
_KEEPALIVE_EXPIRY = 30.0
_DEFAULT_TIMEOUT = 20.0

_limits = httpx.Limits(
    max_connections=_MAX_CONNECTIONS,
    max_keepalive_connections=_MAX_KEEPALIVE,
    keepalive_expiry=_KEEPALIVE_EXPIRY,
)

_async_client: httpx.AsyncClient | None = None
_sync_client: httpx.Client | None = None
_async_lock = asyncio.Lock()
_sync_lock = threading.Lock()


async def get_async_client() -> httpx.AsyncClient:
    """获取全局 AsyncClient（连接池复用）。"""
    global _async_client
    async with _async_lock:
        if _async_client is None or _async_client.is_closed:
            _async_client = httpx.AsyncClient(
                timeout=_DEFAULT_TIMEOUT,
                limits=_limits,
            )
        return _async_client


def get_sync_client() -> httpx.Client:
    """获取全局同步 Client（连接池复用）。"""
    global _sync_client
    with _sync_lock:
        if _sync_client is None:
            _sync_client = httpx.Client(
                timeout=_DEFAULT_TIMEOUT,
                limits=_limits,
            )
        return _sync_client


async def aclose() -> None:
    """关闭连接池（可选调用）。"""
    global _async_client, _sync_client
    if _async_client and not _async_client.is_closed:
        await _async_client.aclose()
    _async_client = None
    if _sync_client:
        _sync_client.close()
    _sync_client = None
