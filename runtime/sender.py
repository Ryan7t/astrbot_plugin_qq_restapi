import base64
import random
import re
import time
from typing import Optional, Sequence, Tuple

from astrbot import logger

from .token_manager import TokenManager
from .httpx_pool import get_async_client

_DEFAULT_API_BASE = "https://api.sgroup.qq.com"
_SANDBOX_API_BASE = "https://sandbox.api.sgroup.qq.com"
_IGNORE_ERROR_CODES = {11293, 40054002, 40054003}
_TOKEN_EXPIRED_CODE = 11244

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


class QQRestAPISender:
    """封装 QQ 官方 REST API 发送逻辑（对齐 Elaina 能力）。"""

    def __init__(self, appid: str, secret: str, token_manager: TokenManager, is_sandbox: bool = False):
        self.appid = appid
        self.secret = secret
        self.token_manager = token_manager
        self.is_sandbox = bool(is_sandbox)
        self.api_base = _SANDBOX_API_BASE if self.is_sandbox else _DEFAULT_API_BASE

    async def _post(self, endpoint: str, payload: dict, retry: int = 1) -> dict | None:
        headers = await self.token_manager.auth_headers()
        client = await get_async_client()
        resp = await client.post(
            f"{self.api_base}{endpoint}",
            json=payload,
            headers=headers,
            timeout=20,
        )
        try:
            data = resp.json()
        except Exception:
            return {"code": -1, "message": "invalid json", "raw": resp.text}

        if isinstance(data, dict) and "code" in data and "message" in data:
            code = data.get("code")
            if code in _IGNORE_ERROR_CODES:
                return None
            if code == _TOKEN_EXPIRED_CODE and retry > 0:
                await self.token_manager.refresh()
                return await self._post(endpoint, payload, retry=retry - 1)
            logger.warning(f"QQ REST API 发送失败: code={code}, message={data.get('message')}")
            return data
        return data

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

    async def send_plain(self, target: dict, content: str, msg_id: Optional[str] = None, event_id: Optional[str] = None):
        endpoint, _ = self._build_endpoint(target)
        payload = {"msg_type": 0, "msg_seq": _msg_seq(), "content": content or ""}
        self._apply_ids(payload, msg_id, event_id)
        return await self._post(endpoint, payload)

    async def send_markdown_content(
        self,
        target: dict,
        content: str,
        msg_id: Optional[str] = None,
        keyboard: Optional[dict] = None,
        hide_avatar_and_center: bool = False,
        event_id: Optional[str] = None,
    ):
        endpoint, allow_keyboard = self._build_endpoint(target)
        payload = {"msg_type": 2, "msg_seq": _msg_seq(), "markdown": {"content": content}}
        if hide_avatar_and_center:
            payload["markdown"].setdefault("style", {})["layout"] = "hide_avatar_and_center"
        self._apply_ids(payload, msg_id, event_id)
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
    ):
        endpoint, _ = self._build_endpoint(target)
        payload = {
            "msg_type": 3,
            "msg_seq": _msg_seq(),
            "content": content or "",
            "ark": {"template_id": template_id, "kv": list(kv_data)},
        }
        self._apply_ids(payload, msg_id, event_id)
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
        if isinstance(resp, dict):
            return resp.get("file_info")
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
        if isinstance(resp, dict):
            return resp.get("file_info")
        return None

    async def send_image_url(
        self,
        target: dict,
        image_url: str,
        content: str = "",
        msg_id: Optional[str] = None,
        event_id: Optional[str] = None,
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
            return await self._post(endpoint, payload)
        endpoint, _ = self._build_endpoint(target)
        payload = {"content": content or "", "image": image_url}
        self._apply_ids(payload, msg_id, event_id)
        return await self._post(endpoint, payload)

    async def send_media(
        self,
        target: dict,
        file_bytes: bytes,
        file_type: int,
        content: str = "",
        msg_id: Optional[str] = None,
        event_id: Optional[str] = None,
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
        return await self._post(endpoint, payload)

    async def send_media_file_info(
        self,
        target: dict,
        file_info: str,
        content: str = "",
        msg_id: Optional[str] = None,
        event_id: Optional[str] = None,
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
