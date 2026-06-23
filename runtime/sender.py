import base64
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Optional, Sequence, Tuple

from astrbot import logger

from .token_manager import TokenManager
from .httpx_pool import get_async_client

_DEFAULT_API_BASE = "https://api.sgroup.qq.com"
_SANDBOX_API_BASE = "https://sandbox.api.sgroup.qq.com"
_IGNORE_ERROR_CODES = {11293, 40054002, 40054003}
_TOKEN_EXPIRED_CODE = 11244
_MARKDOWN_FALLBACK_ERROR_CODES = {
    50037,
    50041,
    50042,
    50054,
    50055,
    50056,
    50057,
    304036,
}
_NON_DOWNGRADE_HTTP_STATUSES = {401, 403, 404, 405, 429}

_MARKDOWN_PATTERNS = [
    re.compile(r"(!?\[.*?\])(\s*\(.*?\))"),
    re.compile(r"(\[.*?\])(\[.*?\])"),
    re.compile(r"(\*)([^*]+?\*)"),
    re.compile(r"(`)([^`]+?`)"),
    re.compile(r"(_)([^_]*?_)"),
    re.compile(r"(``)(`)")
]


def _msg_seq() -> int:
    return random.randint(10000, 999999)


@dataclass
class SendResult:
    ok: bool
    http_status: int = 0
    data: Any = None
    raw: str = ""
    code: int | str | None = None
    message: str | None = None
    transport_error: str | None = None
    ignored: bool = False

    @property
    def normalized_code(self) -> int | None:
        if self.code is None:
            return None
        try:
            return int(self.code)
        except (TypeError, ValueError):
            return None

    @property
    def message_id(self) -> str | None:
        if not isinstance(self.data, dict):
            return None
        message_id = (
            self.data.get("id")
            or self.data.get("msg_id")
            or self.data.get("message_id")
        )
        if message_id is None or message_id == "":
            return None
        return str(message_id)


class QQRestAPISender:
    """封装 QQ 官方 REST API 发送逻辑（对齐 Elaina 能力）。"""

    def __init__(self, appid: str, secret: str, token_manager: TokenManager, is_sandbox: bool = False):
        self.appid = appid
        self.secret = secret
        self.token_manager = token_manager
        self.is_sandbox = bool(is_sandbox)
        self.api_base = _SANDBOX_API_BASE if self.is_sandbox else _DEFAULT_API_BASE

    async def _post(self, endpoint: str, payload: dict, retry: int = 1) -> SendResult:
        headers = await self.token_manager.auth_headers()
        client = await get_async_client()
        resp = await client.post(
            f"{self.api_base}{endpoint}",
            json=payload,
            headers=headers,
            timeout=20,
        )

        raw_text = resp.text
        try:
            data = resp.json()
        except Exception:
            logger.warning(
                "QQ REST API 返回无效 JSON: endpoint=%s, status=%s, body=%s",
                endpoint,
                resp.status_code,
                raw_text[:200],
            )
            return SendResult(
                ok=False,
                http_status=resp.status_code,
                raw=raw_text,
                code=-1,
                message="invalid json",
            )

        if isinstance(data, dict) and "code" in data and "message" in data:
            code = data.get("code")
            message = str(data.get("message"))
            if code in _IGNORE_ERROR_CODES:
                return SendResult(
                    ok=False,
                    http_status=resp.status_code,
                    data=data,
                    raw=raw_text,
                    code=code,
                    message=message,
                    ignored=True,
                )
            if code == _TOKEN_EXPIRED_CODE and retry > 0:
                await self.token_manager.refresh()
                return await self._post(endpoint, payload, retry=retry - 1)
            logger.warning("QQ REST API 发送失败: code=%s, message=%s", code, message)
            return SendResult(
                ok=False,
                http_status=resp.status_code,
                data=data,
                raw=raw_text,
                code=code,
                message=message,
            )

        ok = 200 <= resp.status_code < 300
        if not ok:
            logger.warning(
                "QQ REST API 发送失败: status=%s, body=%s",
                resp.status_code,
                raw_text[:200],
            )
        return SendResult(
            ok=ok,
            http_status=resp.status_code,
            data=data,
            raw=raw_text,
        )

    def should_downgrade_markdown_to_plain(self, result: SendResult | None) -> bool:
        if result is None:
            return False
        if result.ok:
            return False
        if result.ignored or result.transport_error:
            return False
        if result.http_status in _NON_DOWNGRADE_HTTP_STATUSES or result.http_status >= 500:
            return False
        code = result.normalized_code
        if code == _TOKEN_EXPIRED_CODE:
            return False
        if code in _MARKDOWN_FALLBACK_ERROR_CODES:
            return True
        return 400 <= result.http_status < 500

    @staticmethod
    def _build_endpoint(target: dict) -> Tuple[str, bool]:
        """根据场景构造 endpoint。返回 (endpoint, allow_keyboard)"""
        scene = target.get("scene")
        if scene == "channel_dm":
            return f"/dms/{target['guild_id']}/messages", False
        if scene == "channel":
            return f"/channels/{target['channel_id']}/messages", True
        if scene == "group":
            return f"/v2/groups/{target['group_id']}/messages", True
        if scene == "c2c":
            return f"/v2/users/{target['user_id']}/messages", True

        if target.get("guild_id"):
            return f"/dms/{target['guild_id']}/messages", False
        if target.get("channel_id"):
            return f"/channels/{target['channel_id']}/messages", True
        if target.get("group_id"):
            return f"/v2/groups/{target['group_id']}/messages", True
        if target.get("user_id"):
            return f"/v2/users/{target['user_id']}/messages", True
        raise ValueError("缺少发送目标 ID")

    @staticmethod
    def _build_recall_endpoint(target: dict, message_id: str) -> str:
        scene = target.get("scene")
        if scene == "channel_dm":
            return f"/dms/{target['guild_id']}/messages/{message_id}?hidetip=false"
        if scene == "channel":
            return f"/channels/{target['channel_id']}/messages/{message_id}?hidetip=false"
        if scene == "group":
            return f"/v2/groups/{target['group_id']}/messages/{message_id}"
        if scene == "c2c":
            return f"/v2/users/{target['user_id']}/messages/{message_id}"
        if target.get("guild_id"):
            return f"/dms/{target['guild_id']}/messages/{message_id}?hidetip=false"
        if target.get("channel_id"):
            return f"/channels/{target['channel_id']}/messages/{message_id}?hidetip=false"
        if target.get("group_id"):
            return f"/v2/groups/{target['group_id']}/messages/{message_id}"
        if target.get("user_id"):
            return f"/v2/users/{target['user_id']}/messages/{message_id}"
        raise ValueError("缺少撤回目标 ID")

    @staticmethod
    def _apply_ids(payload: dict, msg_id: Optional[str], event_id: Optional[str]):
        if msg_id:
            payload["msg_id"] = msg_id
        if event_id:
            payload["event_id"] = event_id
        return payload

    @staticmethod
    def _apply_message_reference(payload: dict, message_reference: Optional[dict]):
        if message_reference:
            payload["message_reference"] = message_reference
        return payload

    @staticmethod
    def _process_button_parameter(button_param):
        if not button_param:
            return None
        if isinstance(button_param, str):
            return {"id": str(button_param)}
        if isinstance(button_param, dict):
            return button_param
        return None

    def rows(self, buttons):
        if not isinstance(buttons, list):
            buttons = [buttons]
        result = []
        for button in buttons:
            button_obj = {
                "id": button.get("id", str(_msg_seq())),
                "render_data": {
                    "label": button.get("text", button.get("link", "")),
                    "visited_label": button.get("show", button.get("text", button.get("link", ""))),
                    "style": button.get("style", 0),
                },
                "action": {
                    "type": 0 if "link" in button else button.get("type", 2),
                    "data": button.get("data", button.get("link", button.get("text", ""))),
                    "unsupport_tips": button.get("tips", "."),
                    "permission": {"type": 2},
                },
            }
            if button.get("enter"):
                button_obj["action"]["enter"] = True
            if button.get("reply"):
                button_obj["action"]["reply"] = True
            if button.get("admin"):
                button_obj["action"]["permission"]["type"] = 1
            if button.get("list"):
                button_obj["action"]["permission"]["type"] = 0
                button_obj["action"]["permission"]["specify_user_ids"] = button["list"]
            if button.get("role"):
                button_obj["action"]["permission"]["type"] = 3
                button_obj["action"]["permission"]["specify_role_ids"] = button["role"]
            if button.get("limit"):
                button_obj["action"]["click_limit"] = button["limit"]
            result.append(button_obj)
        return {"buttons": result}

    def button(self, rows=None):
        return {"content": {"rows": rows or []}}

    def _split_markdown_to_params(self, text: str, keys: Sequence[str] | str):
        text = text.replace("\n", "\r")
        delimiter = str(time.time()).replace(".", "")

        for pattern in _MARKDOWN_PATTERNS:
            text = pattern.sub(lambda m: delimiter.join(m.groups()), text)

        parts = text.split(delimiter) if delimiter in text else [text]
        if isinstance(keys, str):
            keys_list = [k.strip() for k in keys.split(",")] if "," in keys else list(keys)
        else:
            keys_list = list(keys)
        params = [{"key": keys_list[i], "values": [parts[i]]} for i in range(min(len(parts), len(keys_list)))]
        for i in range(len(params), len(keys_list)):
            params.append({"key": keys_list[i], "values": ["\u200B"]})
        return params

    async def send_plain(
        self,
        target: dict,
        content: str,
        msg_id: Optional[str] = None,
        event_id: Optional[str] = None,
        message_reference: Optional[dict] = None,
    ):
        endpoint, _ = self._build_endpoint(target)
        payload = {"msg_type": 0, "msg_seq": _msg_seq(), "content": content or ""}
        self._apply_ids(payload, msg_id, event_id)
        self._apply_message_reference(payload, message_reference)
        return await self._post(endpoint, payload)

    async def send_text_prefer_markdown(
        self,
        target: dict,
        content: str,
        msg_id: Optional[str] = None,
        event_id: Optional[str] = None,
        keyboard: Optional[dict] = None,
        hide_avatar_and_center: bool = False,
        prefer_markdown: bool = True,
        allow_markdown_fallback: bool = True,
        message_reference: Optional[dict] = None,
    ):
        if not prefer_markdown:
            return await self.send_plain(
                target=target,
                content=content,
                msg_id=msg_id,
                event_id=event_id,
                message_reference=message_reference,
            )

        send_result = await self.send_markdown_content(
            target=target,
            content=content or "\u200B",
            msg_id=msg_id,
            keyboard=keyboard,
            hide_avatar_and_center=hide_avatar_and_center,
            event_id=event_id,
            message_reference=message_reference,
        )
        if allow_markdown_fallback and self.should_downgrade_markdown_to_plain(send_result):
            if isinstance(send_result, SendResult):
                logger.info(
                    "[qq_restapi] 原生 Markdown 发送失败，回退纯文本: scene=%s status=%s code=%s message=%s",
                    target.get("scene"),
                    send_result.http_status,
                    send_result.code,
                    send_result.message or "-",
                )
            return await self.send_plain(
                target=target,
                content=content,
                msg_id=msg_id,
                event_id=event_id,
                message_reference=message_reference,
            )
        return send_result

    async def send_markdown_content(
        self,
        target: dict,
        content: str,
        msg_id: Optional[str] = None,
        keyboard: Optional[dict] = None,
        hide_avatar_and_center: bool = False,
        event_id: Optional[str] = None,
        message_reference: Optional[dict] = None,
    ):
        endpoint, allow_keyboard = self._build_endpoint(target)
        payload = {"msg_type": 2, "msg_seq": _msg_seq(), "markdown": {"content": content}}
        if hide_avatar_and_center:
            payload["markdown"].setdefault("style", {})["layout"] = "hide_avatar_and_center"
        self._apply_ids(payload, msg_id, event_id)
        self._apply_message_reference(payload, message_reference)
        if keyboard and allow_keyboard:
            payload["keyboard"] = self._process_button_parameter(keyboard) or keyboard
        return await self._post(endpoint, payload)

    async def send_markdown_template(
        self,
        target: dict,
        template_id: str,
        params: Sequence[dict],
        msg_id: Optional[str] = None,
        keyboard: Optional[dict] = None,
        hide_avatar_and_center: bool = False,
        event_id: Optional[str] = None,
        message_reference: Optional[dict] = None,
    ):
        endpoint, allow_keyboard = self._build_endpoint(target)
        payload = {
            "msg_type": 2,
            "msg_seq": _msg_seq(),
            "markdown": {"custom_template_id": template_id, "params": list(params)},
        }
        if hide_avatar_and_center:
            payload["markdown"].setdefault("style", {})["layout"] = "hide_avatar_and_center"
        self._apply_ids(payload, msg_id, event_id)
        self._apply_message_reference(payload, message_reference)
        if keyboard and allow_keyboard:
            payload["keyboard"] = self._process_button_parameter(keyboard) or keyboard
        return await self._post(endpoint, payload)

    async def send_markdown_aj(
        self,
        target: dict,
        template_id: str,
        keys: Sequence[str],
        text: str,
        msg_id: Optional[str] = None,
        keyboard: Optional[dict] = None,
        hide_avatar_and_center: bool = False,
        event_id: Optional[str] = None,
        message_reference: Optional[dict] = None,
    ):
        params = self._split_markdown_to_params(text, keys)
        payload = {
            "msg_type": 2,
            "msg_seq": _msg_seq(),
            "markdown": {"custom_template_id": template_id, "params": params},
        }
        if hide_avatar_and_center:
            payload["markdown"].setdefault("style", {})["layout"] = "hide_avatar_and_center"
        self._apply_ids(payload, msg_id, event_id)
        self._apply_message_reference(payload, message_reference)
        endpoint, allow_keyboard = self._build_endpoint(target)
        if keyboard and allow_keyboard:
            payload["keyboard"] = self._process_button_parameter(keyboard) or keyboard
        return await self._post(endpoint, payload)

    async def send_ark(
        self,
        target: dict,
        template_id: int,
        kv_data: Sequence[dict],
        content: str = "",
        msg_id: Optional[str] = None,
        event_id: Optional[str] = None,
        message_reference: Optional[dict] = None,
    ):
        endpoint, _ = self._build_endpoint(target)
        payload = {
            "msg_type": 3,
            "msg_seq": _msg_seq(),
            "content": content or "",
            "ark": {"template_id": template_id, "kv": list(kv_data)},
        }
        self._apply_ids(payload, msg_id, event_id)
        self._apply_message_reference(payload, message_reference)
        return await self._post(endpoint, payload)

    async def upload_media(self, target: dict, file_bytes: bytes, file_type: int) -> Optional[str]:
        if target.get("scene") == "group":
            endpoint = f"/v2/groups/{target['group_id']}/files"
        elif target.get("scene") == "c2c":
            endpoint = f"/v2/users/{target['user_id']}/files"
        else:
            # 频道与频道私聊暂不支持该上传方式
            return None
        payload = {
            "srv_send_msg": False,
            "file_type": file_type,
            "file_data": base64.b64encode(file_bytes).decode(),
        }
        resp = await self._post(endpoint, payload)
        if isinstance(resp.data, dict):
            return resp.data.get("file_info")
        return None

    async def upload_media_url(self, target: dict, file_url: str, file_type: int) -> Optional[str]:
        if not file_url:
            return None
        if target.get("scene") == "group":
            group_id = target.get("group_id")
            if not group_id:
                return None
            endpoint = f"/v2/groups/{group_id}/files"
        elif target.get("scene") == "c2c":
            user_id = target.get("user_id")
            if not user_id:
                return None
            endpoint = f"/v2/users/{user_id}/files"
        else:
            return None
        payload = {
            "srv_send_msg": False,
            "file_type": file_type,
            "url": file_url,
        }
        resp = await self._post(endpoint, payload)
        if isinstance(resp.data, dict):
            return resp.data.get("file_info")
        return None

    async def send_image_url(
        self,
        target: dict,
        image_url: str,
        content: str = "",
        msg_id: Optional[str] = None,
        event_id: Optional[str] = None,
        message_reference: Optional[dict] = None,
    ):
        if not image_url:
            return None
        scene = target.get("scene")
        if scene in ("group", "c2c"):
            file_info = await self.upload_media_url(target, image_url, file_type=1)
            if not file_info:
                logger.warning("媒体上传失败，未获取 file_info")
                return None
            endpoint, _ = self._build_endpoint(target)
            payload = {
                "msg_type": 7,
                "msg_seq": _msg_seq(),
                "content": content or "",
                "media": {"file_info": file_info},
            }
            self._apply_ids(payload, msg_id, event_id)
            self._apply_message_reference(payload, message_reference)
            return await self._post(endpoint, payload)
        endpoint, _ = self._build_endpoint(target)
        payload = {"content": content or "", "image": image_url}
        self._apply_ids(payload, msg_id, event_id)
        self._apply_message_reference(payload, message_reference)
        return await self._post(endpoint, payload)

    async def send_media(
        self,
        target: dict,
        file_bytes: bytes,
        file_type: int,
        content: str = "",
        msg_id: Optional[str] = None,
        event_id: Optional[str] = None,
        message_reference: Optional[dict] = None,
    ):
        file_info = await self.upload_media(target, file_bytes, file_type)
        if not file_info:
            logger.warning("媒体上传失败，未获取 file_info")
            return None
        endpoint, _ = self._build_endpoint(target)
        payload = {
            "msg_type": 7,
            "msg_seq": _msg_seq(),
            "content": content or "",
            "media": {"file_info": file_info},
        }
        self._apply_ids(payload, msg_id, event_id)
        self._apply_message_reference(payload, message_reference)
        return await self._post(endpoint, payload)

    async def send_media_file_info(
        self,
        target: dict,
        file_info: str,
        content: str = "",
        msg_id: Optional[str] = None,
        event_id: Optional[str] = None,
        message_reference: Optional[dict] = None,
    ):
        if not file_info:
            return None
        endpoint, _ = self._build_endpoint(target)
        payload = {
            "msg_type": 7,
            "msg_seq": _msg_seq(),
            "content": content or "",
            "media": {"file_info": file_info},
        }
        self._apply_ids(payload, msg_id, event_id)
        self._apply_message_reference(payload, message_reference)
        return await self._post(endpoint, payload)

    async def recall_message(self, target: dict, message_id: str):
        if not message_id:
            return None
        endpoint = self._build_recall_endpoint(target, message_id)
        headers = await self.token_manager.auth_headers()
        client = await get_async_client()
        resp = await client.delete(f"{self.api_base}{endpoint}", headers=headers, timeout=15)
        try:
            data = resp.json()
        except Exception:
            data = None
        if resp.status_code not in (200, 204):
            logger.warning(
                "QQ REST API 撤回失败: status=%s, body=%s",
                resp.status_code,
                resp.text,
            )
        return {"status_code": resp.status_code, "data": data, "raw": resp.text}
