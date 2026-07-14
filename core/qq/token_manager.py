from contextvars import ContextVar

from ...runtime.token_manager import TokenManager, TokenManagerError


_TOKEN_MANAGERS: dict[tuple[str, str], TokenManager] = {}
_LAST_ERROR: ContextVar[str] = ContextVar(
    "qq_restapi_legacy_token_error",
    default="",
)


def get_token_manager(appid: str, secret: str) -> TokenManager:
    """返回供旧公共 API 复用的 runtime TokenManager 实例。"""
    cache_key = (appid, secret)
    manager = _TOKEN_MANAGERS.get(cache_key)
    if manager is None:
        manager = TokenManager(appid, secret)
        _TOKEN_MANAGERS[cache_key] = manager
    return manager


async def get_access_token(appid: str, secret: str) -> str:
    """兼容旧接口，内部委托 runtime.TokenManager。"""
    if not appid or not secret:
        _LAST_ERROR.set("缺少 appid 或 secret")
        return ""

    try:
        token = await get_token_manager(appid, secret).get_token()
    except TokenManagerError as exc:
        _LAST_ERROR.set(str(exc))
        return ""

    _LAST_ERROR.set("")
    return token


def get_last_error() -> str:
    return _LAST_ERROR.get()
