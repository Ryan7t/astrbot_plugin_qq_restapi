import time

from ...runtime.httpx_pool import get_async_client

TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
REFRESH_BUFFER = 60

_TOKEN_CACHE = {"token": "", "expire": 0}
_LAST_ERROR = ""


async def get_access_token(appid: str, secret: str) -> str:
    global _LAST_ERROR

    if not appid or not secret:
        _LAST_ERROR = "缺少 appid 或 secret"
        return ""

    now = time.time()
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["expire"] > now + REFRESH_BUFFER:
        return _TOKEN_CACHE["token"]

    try:
        client = await get_async_client()
        resp = await client.post(
            TOKEN_URL,
            json={"appId": appid, "clientSecret": secret},
            timeout=10.0,
        )
    except Exception as exc:
        _LAST_ERROR = f"获取 token 失败: {exc}"
        return ""

    if resp.status_code != 200:
        _LAST_ERROR = f"获取 token 失败: HTTP {resp.status_code} {resp.text}"
        return ""

    try:
        data = resp.json()
    except ValueError:
        _LAST_ERROR = f"获取 token 失败: 响应不是 JSON - {resp.text}"
        return ""

    token = data.get("access_token")
    if not token:
        _LAST_ERROR = f"获取 token 失败: {data}"
        return ""

    expires = int(data.get("expires_in", 7000))
    _TOKEN_CACHE["token"] = token
    _TOKEN_CACHE["expire"] = now + expires
    _LAST_ERROR = ""
    return token


def get_last_error() -> str:
    return _LAST_ERROR
