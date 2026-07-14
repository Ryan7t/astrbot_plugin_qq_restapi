from typing import Iterable

from ...runtime.sender import (
    QQRestAPISender,
    build_markdown_params as _build_markdown_params,
)
from .token_manager import get_access_token, get_last_error, get_token_manager


def build_markdown_params(
    keys: Iterable[str],
    values: Iterable[object],
) -> list[dict]:
    """保留旧公共签名，参数转换由 runtime 统一实现。"""
    return _build_markdown_params(keys, values)


async def send_markdown_template(
    api_url: str,
    appid: str,
    secret: str,
    template_id: str,
    param_keys: Iterable[str],
    param_values: Iterable[object],
    *,
    msg_id: str | None = None,
    keyboard_id: str | None = None,
) -> tuple[int, str]:
    """保留旧公共 API，内部委托 runtime sender 并转换回二元组。"""
    token = await get_access_token(appid, secret)
    if not token:
        return 0, get_last_error()

    sender = QQRestAPISender(
        appid,
        secret,
        get_token_manager(appid, secret),
    )
    result = await sender.send_markdown_template_url(
        api_url,
        template_id,
        build_markdown_params(param_keys, param_values),
        msg_id=msg_id,
        keyboard=keyboard_id,
    )
    if result.transport_error:
        return 0, f"发送失败: {result.transport_error}"
    return int(result.http_status), str(result.raw or "")
