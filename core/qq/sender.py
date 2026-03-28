import random
from typing import Iterable

from .token_manager import get_access_token, get_last_error
from ...runtime.httpx_pool import get_async_client


def build_markdown_params(keys: Iterable[str], values: Iterable[object]) -> list[dict]:
    params = []
    for key, value in zip(keys, values):
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            vals = [str(v) for v in value if v is not None]
        else:
            vals = [str(value)]
        if not vals:
            continue
        params.append({"key": key, "values": vals})
    return params


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
    token = await get_access_token(appid, secret)
    if not token:
        return 0, get_last_error()

    payload: dict = {
        "msg_type": 2,
        "msg_seq": random.randint(10000, 999999),
        "markdown": {"custom_template_id": template_id},
    }
    params = build_markdown_params(param_keys, param_values)
    if params:
        payload["markdown"]["params"] = params
    if msg_id:
        payload["msg_id"] = msg_id
    if keyboard_id:
        payload["keyboard"] = {"id": keyboard_id}

    headers = {
        "Authorization": f"QQBot {token}",
        "Content-Type": "application/json",
    }

    try:
        client = await get_async_client()
        resp = await client.post(api_url, headers=headers, json=payload, timeout=10.0)
    except Exception as exc:
        return 0, f"发送失败: {exc}"

    return resp.status_code, resp.text
