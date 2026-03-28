import time
from typing import Optional

from .httpx_pool import get_async_client

class TokenManager:
    """QQ Bot access_token 管理（基于 appid/secret，带缓存与自动刷新）。"""

    TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"

    def __init__(self, appid: str, secret: str):
        self.appid = appid
        self.secret = secret
        self._cached_token: Optional[str] = None
        self._expires_at: float = 0

    async def get_token(self) -> Optional[str]:
        """获取可用 token；过期则自动刷新。"""
        now = time.time()
        if self._cached_token and now < self._expires_at - 60:
            return self._cached_token
        return await self._refresh()

    async def refresh(self) -> Optional[str]:
        """强制刷新 token。"""
        return await self._refresh()

    async def _refresh(self) -> Optional[str]:
        payload = {"appId": self.appid, "clientSecret": self.secret}
        client = await get_async_client()
        resp = await client.post(self.TOKEN_URL, json=payload, timeout=10)
        data = resp.json()
        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 7200))
        if token:
            self._cached_token = token
            self._expires_at = time.time() + expires_in
        return token

    async def auth_headers(self) -> dict:
        token = await self.get_token()
        return {"Authorization": f"QQBot {token}", "Content-Type": "application/json"}
