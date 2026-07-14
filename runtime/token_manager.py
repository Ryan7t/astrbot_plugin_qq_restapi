import asyncio
import time

from .httpx_pool import get_async_client


class TokenManagerError(RuntimeError):
    """QQ access token 获取或解析失败。"""


class TokenManager:
    """QQ Bot access_token 管理（基于 appid/secret，带缓存与自动刷新）。"""

    TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"

    def __init__(self, appid: str, secret: str):
        self.appid = appid
        self.secret = secret
        self._cached_token: str | None = None
        self._expires_at: float = 0
        self._refresh_lock = asyncio.Lock()

    async def get_token(self) -> str:
        """获取可用 token；过期则自动刷新。"""
        now = time.time()
        if self._cached_token and now < self._expires_at - 60:
            return self._cached_token

        async with self._refresh_lock:
            now = time.time()
            if self._cached_token and now < self._expires_at - 60:
                return self._cached_token
            return await self._refresh_unlocked()

    async def refresh(self) -> str:
        """强制刷新 token。"""
        async with self._refresh_lock:
            return await self._refresh_unlocked()

    async def _refresh_unlocked(self) -> str:
        if not self.appid or not self.secret:
            raise TokenManagerError("缺少 QQ 机器人 appid 或 secret")

        payload = {"appId": self.appid, "clientSecret": self.secret}
        try:
            client = await get_async_client()
            resp = await client.post(self.TOKEN_URL, json=payload, timeout=10)
        except Exception as exc:
            raise TokenManagerError(f"请求 QQ access token 失败: {exc}") from exc

        if resp.status_code != 200:
            body = getattr(resp, "text", "")
            raise TokenManagerError(
                f"请求 QQ access token 失败: HTTP {resp.status_code} {body[:200]}"
            )

        try:
            data = resp.json()
        except Exception as exc:
            raise TokenManagerError("QQ access token 响应不是有效 JSON") from exc

        if not isinstance(data, dict):
            raise TokenManagerError("QQ access token 响应格式无效")

        token = data.get("access_token")
        if not token:
            message = data.get("message") or data.get("msg") or "响应缺少 access_token"
            raise TokenManagerError(f"请求 QQ access token 失败: {message}")

        try:
            expires_in = max(1, int(data.get("expires_in", 7200)))
        except (TypeError, ValueError) as exc:
            raise TokenManagerError("QQ access token 响应的 expires_in 无效") from exc

        self._cached_token = str(token)
        self._expires_at = time.time() + expires_in
        return self._cached_token

    async def auth_headers(self) -> dict:
        token = await self.get_token()
        return {"Authorization": f"QQBot {token}", "Content-Type": "application/json"}
