import asyncio
import base64
import hashlib
import re
import time
from typing import Any, Sequence

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, ResultContentType
from astrbot.api.message_components import At, Image, Plain, Record, Video
from astrbot.core.utils.io import download_image_by_url
from astrbot.core.utils.tencent_record_helper import audio_to_tencent_silk_base64
from astrbot.core.agent.message import UserMessageSegment, AssistantMessageSegment
from astrbot.core.star.context import Context as StarContext

from .message_parser import (
    CHANNEL_DIRECT_MESSAGE,
    CHANNEL_MESSAGE,
    CHANNEL_MESSAGE_CREATE,
    DIRECT_MESSAGE,
    FRIEND_ADD,
    GROUP_ADD_ROBOT,
    GROUP_MESSAGE,
    INTERACTION,
)
from .sender import QQRestAPISender, SendResult
from .context import get_context
from .httpx_pool import get_async_client, get_sync_client
from .last_message_cache import set_last_message_id
from .template_store import (
    build_meta_line,
    extract_params,
    get_template_body,
    normalize_keyboard_meta,
    render_template,
)
from .template_registry import resolve_template_id

_MSG_TYPES_NEED_MSG_ID = {
    GROUP_MESSAGE,
    DIRECT_MESSAGE,
    CHANNEL_MESSAGE,
    CHANNEL_MESSAGE_CREATE,
    CHANNEL_DIRECT_MESSAGE,
}
_MSG_TYPES_NEED_EVENT_ID = {INTERACTION, GROUP_ADD_ROBOT}
_MSG_TYPES_NEED_EVENT_PREFIX = {GROUP_ADD_ROBOT, FRIEND_ADD}
_EVENT_PREFIX_MAP = {GROUP_ADD_ROBOT: "ROBOT_ADD", FRIEND_ADD: "FRIEND_ADD"}
_STREAMING_SPLIT_CHARS = "。？！…"


def _count_same_char_run(text: str, start: int) -> int:
    char = text[start]
    end = start + 1
    while end < len(text) and text[end] == char:
        end += 1
    return end - start


def _can_open_markdown_span(text: str, start: int, run_len: int, marker: str) -> bool:
    next_char = text[start + run_len] if start + run_len < len(text) else ""
    prev_char = text[start - 1] if start > 0 else ""
    if marker == "_" and prev_char.isalnum() and next_char.isalnum():
        return False
    return bool(next_char) and not next_char.isspace()


def _can_close_markdown_span(text: str, start: int, run_len: int, marker: str) -> bool:
    prev_char = text[start - 1] if start > 0 else ""
    next_char = text[start + run_len] if start + run_len < len(text) else ""
    if marker == "_" and prev_char.isalnum() and next_char.isalnum():
        return False
    return bool(prev_char) and not prev_char.isspace()


def _advance_markdown_span_state(is_open: bool, can_open: bool, can_close: bool) -> bool:
    if is_open and can_close:
        return False
    if not is_open and can_open:
        return True
    return is_open


def _find_safe_streaming_split_index(text: str) -> int | None:
    strike_open = False
    strong_star_open = False
    emphasis_star_open = False
    strong_underscore_open = False
    emphasis_underscore_open = False
    link_text_depth = 0
    link_dest_depth = 0
    pending_link_dest = False
    fenced_code_ticks = 0
    inline_code_ticks = 0
    escaped = False
    i = 0

    while i < len(text):
        ch = text[i]

        if escaped:
            escaped = False
            i += 1
            continue
        if ch == "\\":
            escaped = True
            i += 1
            continue

        if fenced_code_ticks:
            if ch == "`":
                run_len = _count_same_char_run(text, i)
                if run_len >= fenced_code_ticks:
                    i += fenced_code_ticks
                    fenced_code_ticks = 0
                    continue
            i += 1
            continue

        if inline_code_ticks:
            if ch == "`":
                run_len = _count_same_char_run(text, i)
                if run_len >= inline_code_ticks:
                    delim_len = inline_code_ticks
                    inline_code_ticks = 0
                    i += delim_len
                    continue
            i += 1
            continue

        if ch == "`":
            run_len = _count_same_char_run(text, i)
            if run_len >= 3:
                fenced_code_ticks = run_len
            else:
                inline_code_ticks = run_len
            i += run_len
            continue

        if pending_link_dest:
            if ch.isspace():
                i += 1
                continue
            if ch == "(":
                link_dest_depth = 1
                pending_link_dest = False
                i += 1
                continue
            pending_link_dest = False

        if link_dest_depth > 0:
            if ch == "(":
                link_dest_depth += 1
            elif ch == ")":
                link_dest_depth -= 1
            i += 1
            continue

        if ch == "[":
            link_text_depth += 1
            i += 1
            continue
        if ch == "]" and link_text_depth > 0:
            link_text_depth -= 1
            if link_text_depth == 0:
                pending_link_dest = True
            i += 1
            continue
        if link_text_depth > 0:
            i += 1
            continue

        if ch in {"*", "_", "~"}:
            run_len = _count_same_char_run(text, i)
            can_open = _can_open_markdown_span(text, i, run_len, ch)
            can_close = _can_close_markdown_span(text, i, run_len, ch)

            if ch == "~":
                for _ in range(run_len // 2):
                    strike_open = _advance_markdown_span_state(
                        strike_open, can_open, can_close
                    )
                i += run_len
                continue

            if ch == "*":
                for _ in range(run_len // 2):
                    strong_star_open = _advance_markdown_span_state(
                        strong_star_open, can_open, can_close
                    )
                if run_len % 2:
                    emphasis_star_open = _advance_markdown_span_state(
                        emphasis_star_open, can_open, can_close
                    )
                i += run_len
                continue

            for _ in range(run_len // 2):
                strong_underscore_open = _advance_markdown_span_state(
                    strong_underscore_open, can_open, can_close
                )
            if run_len % 2:
                emphasis_underscore_open = _advance_markdown_span_state(
                    emphasis_underscore_open, can_open, can_close
                )
            i += run_len
            continue

        if (
            ch in _STREAMING_SPLIT_CHARS
            and not strike_open
            and not strong_star_open
            and not emphasis_star_open
            and not strong_underscore_open
            and not emphasis_underscore_open
            and not pending_link_dest
        ):
            end = i + 1
            while end < len(text) and text[end] in _STREAMING_SPLIT_CHARS:
                end += 1
            return end - 1

        i += 1

    return None


class QQRestAPIEvent(AstrMessageEvent):
    """AstrBot 事件实现，send 时调用 QQ REST API。"""

    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        sender: QQRestAPISender,
        platform_config: dict | None = None,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self._sender = sender
        self._platform_config = platform_config or {}

    def _resolve_ids(self) -> tuple[str | None, str | None]:
        event_type = getattr(self.message_obj, "qq_event_type", "")
        msg_id = self.message_obj.message_id if event_type in _MSG_TYPES_NEED_MSG_ID else None
        event_id = None
        if event_type in _MSG_TYPES_NEED_EVENT_ID:
            event_id = getattr(self.message_obj, "qq_event_id", None) or self.message_obj.message_id
        if event_type in _MSG_TYPES_NEED_EVENT_PREFIX and not event_id:
            prefix = _EVENT_PREFIX_MAP.get(event_type, "UNKNOWN")
            event_id = getattr(self.message_obj, "qq_event_id", None) or f"{prefix}_{int(time.time())}"
        return msg_id, event_id

    def _target(self) -> dict:
        return _target_from_message_obj(self.message_obj)

    def _extract_message_id(self, response: Any) -> str | None:
        if not response:
            return None
        if isinstance(response, SendResult):
            return response.message_id
        if isinstance(response, dict):
            return response.get("id") or response.get("msg_id") or response.get("message_id")
        return None

    def _record_last_message_id(self, message_id: str | None):
        if not message_id:
            return
        set_last_message_id(self.unified_msg_origin, message_id)

    def _get_conversation_manager(self):
        ctx = get_context()
        if not ctx:
            star_mgr = getattr(StarContext, "_star_manager", None)
            if star_mgr:
                ctx = getattr(star_mgr, "context", None)
        if not ctx:
            return None
        return getattr(ctx, "conversation_manager", None)

    async def _store_history_if_needed(self, bot_text, user_text: str | None = None):
        # LLM 场景由框架内部保存，避免重复写入
        if self.get_extra("provider_request") is not None:
            return
        if self.get_extra("_qq_restapi_history_stored"):
            return
        conv_mgr = self._get_conversation_manager()
        if not conv_mgr:
            logger.warning("写入对话记录失败: 未获取到 conversation_manager")
            return
        platform_id = self.get_platform_id() or "unknown"
        user_text = user_text or self.message_str or self.get_message_outline() or "[empty]"
        assistant_payload = bot_text
        if isinstance(assistant_payload, list):
            assistant_text = _summarize_content_parts(assistant_payload) or "[empty]"
        else:
            assistant_text = assistant_payload or "[empty]"
        logger.info(
            "尝试写入对话记录: umo=%s, platform=%s, user=%s, bot=%s",
            self.unified_msg_origin,
            platform_id,
            user_text[:80],
            assistant_text[:80],
        )
        try:
            cid = await conv_mgr.get_curr_conversation_id(self.unified_msg_origin)
            if not cid:
                cid = await conv_mgr.new_conversation(
                    self.unified_msg_origin,
                    platform_id,
                )
            await conv_mgr.add_message_pair(
                cid,
                UserMessageSegment(content=user_text),
                AssistantMessageSegment(content=assistant_payload or "[empty]"),
            )
            self.set_extra("_qq_restapi_history_stored", True)
            logger.info("对话记录写入成功: cid=%s", cid)
        except Exception as exc:
            logger.warning(f"写入对话记录失败: {exc}")

    async def store_history(self, bot_text: str, user_text: str | None = None):
        await self._store_history_if_needed(bot_text, user_text=user_text)

    async def _schedule_recall(self, message_id: str | None, seconds: int | None):
        if not message_id or not seconds:
            return
        await asyncio.sleep(seconds)
        await self.recall_message(message_id)

    def _should_prefer_markdown_for_default_send(self) -> bool:
        if self.get_extra("_qq_restapi_force_plain_send"):
            return False
        result = self.get_result()
        if result is None:
            return False
        return result.result_content_type in (
            ResultContentType.LLM_RESULT,
            ResultContentType.STREAMING_RESULT,
        )

    async def _send_chain_without_markdown_preference(self, chain: MessageChain):
        previous = self.get_extra("_qq_restapi_force_plain_send")
        self.set_extra("_qq_restapi_force_plain_send", True)
        try:
            await self.send(chain)
        finally:
            self.set_extra("_qq_restapi_force_plain_send", previous)

    async def _send_streaming_text_chain(
        self, chain: MessageChain, *, prefer_markdown: bool
    ):
        if prefer_markdown:
            previous = self.get_extra("_qq_restapi_streaming_segment_send")
            self.set_extra("_qq_restapi_streaming_segment_send", True)
            try:
                await self.send(chain)
                return
            finally:
                self.set_extra("_qq_restapi_streaming_segment_send", previous)
        await self._send_chain_without_markdown_preference(chain)

    async def _process_streaming_buffer(
        self, buffer: str, *, prefer_markdown: bool
    ) -> str:
        while True:
            split_index = _find_safe_streaming_split_index(buffer)
            if split_index is None:
                break
            matched_text = buffer[: split_index + 1]
            await self._send_streaming_text_chain(
                MessageChain([Plain(matched_text)]),
                prefer_markdown=prefer_markdown,
            )
            buffer = buffer[split_index + 1 :]
            await asyncio.sleep(1.5)
        return buffer

    async def _send_text_reply(
        self,
        content: str = "",
        *,
        buttons=None,
        hide_avatar_and_center: bool | None = None,
        auto_delete_time: int | None = None,
        use_markdown: bool = False,
        allow_markdown_fallback: bool = False,
        store_history: bool = True,
        history_requires_success: bool = False,
    ) -> str | None:
        msg_id, event_id = self._resolve_ids()
        target = self._target()

        if use_markdown or buttons:
            markdown_content = content or "\u200B"
            send_result = await self._sender.send_markdown_content(
                target=target,
                content=markdown_content,
                msg_id=msg_id,
                keyboard=buttons,
                hide_avatar_and_center=bool(hide_avatar_and_center),
                event_id=event_id,
            )
            if allow_markdown_fallback and self._sender.should_downgrade_markdown_to_plain(send_result):
                if isinstance(send_result, SendResult):
                    logger.info(
                        "[qq_restapi] 原生 Markdown 发送失败，回退纯文本: scene=%s status=%s code=%s message=%s",
                        target.get("scene"),
                        send_result.http_status,
                        send_result.code,
                        send_result.message or "-",
                    )
                send_result = await self._sender.send_plain(
                    target=target,
                    content=content,
                    msg_id=msg_id,
                    event_id=event_id,
                )
        else:
            send_result = await self._sender.send_plain(
                target=target,
                content=content,
                msg_id=msg_id,
                event_id=event_id,
            )

        message_id = self._extract_message_id(send_result)
        if auto_delete_time:
            asyncio.create_task(self._schedule_recall(message_id, auto_delete_time))
        if store_history and (
            not history_requires_success
            or message_id
            or (isinstance(send_result, SendResult) and send_result.ok)
        ):
            await self._store_history_if_needed(content)
        self._record_last_message_id(message_id)
        return message_id

    async def send(self, message: MessageChain):
        chain = self._strip_group_auto_mention(message.chain)
        content_parts: list[str] = []
        image_comp = None
        record_comp = None
        video_comp = None

        for comp in chain:
            if isinstance(comp, Plain):
                content_parts.append(comp.text)
            elif isinstance(comp, At):
                content_parts.append(f"<@!{comp.qq}>")
            elif isinstance(comp, Image) and image_comp is None:
                image_comp = comp
            elif isinstance(comp, Record) and record_comp is None:
                record_comp = comp
            elif isinstance(comp, Video) and video_comp is None:
                video_comp = comp

        content = "".join(content_parts).strip()
        if record_comp is not None:
            await self.reply_voice(record_comp, content=content)
        elif video_comp is not None:
            await self.reply_video(video_comp, content=content)
        elif image_comp is not None:
            await self.reply_image(image_comp, content=content)
        else:
            prefer_markdown = self._should_prefer_markdown_for_default_send()
            if prefer_markdown and not self.get_extra("_qq_restapi_streaming_segment_send"):
                logger.info(
                    "[qq_restapi] 普通回复启用原生 Markdown 优先发送: scene=%s",
                    getattr(self.message_obj, "qq_scene", "unknown"),
                )
            await self._send_text_reply(
                content=content,
                use_markdown=prefer_markdown,
                allow_markdown_fallback=prefer_markdown,
                store_history=True,
                history_requires_success=True,
            )

        await super().send(message)

    async def send_streaming(self, generator, use_fallback: bool = False):
        if not use_fallback:
            buffer = None
            async for chain in generator:
                if not buffer:
                    buffer = chain
                else:
                    buffer.chain.extend(chain.chain)
            if not buffer:
                return await super().send_streaming(generator, use_fallback)
            buffer.squash_plain()
            await self.send(buffer)
            return await super().send_streaming(generator, use_fallback)

        buffer_text = ""
        prefer_markdown = self._should_prefer_markdown_for_default_send()
        if prefer_markdown:
            logger.info(
                "[qq_restapi] 流式分段回退发送启用原生 Markdown 优先: scene=%s",
                getattr(self.message_obj, "qq_scene", "unknown"),
            )
        async for chain in generator:
            if not isinstance(chain, MessageChain):
                continue
            for comp in chain.chain:
                if isinstance(comp, Plain):
                    buffer_text += comp.text
                    if any(p in buffer_text for p in _STREAMING_SPLIT_CHARS):
                        buffer_text = await self._process_streaming_buffer(
                            buffer_text,
                            prefer_markdown=prefer_markdown,
                        )
                else:
                    await self._send_chain_without_markdown_preference(MessageChain([comp]))
                    await asyncio.sleep(1.5)

        if buffer_text.strip():
            await self._send_streaming_text_chain(
                MessageChain([Plain(buffer_text)]),
                prefer_markdown=prefer_markdown,
            )
        return await super().send_streaming(generator, use_fallback)

    def _strip_group_auto_mention(self, chain):
        if not chain:
            return chain
        if getattr(self.message_obj, "qq_scene", "") != "group":
            return chain
        first = chain[0]
        if not isinstance(first, At):
            return chain
        sender_id = str(self.get_sender_id())
        if str(first.qq) != sender_id:
            return chain
        new_chain = list(chain[1:])
        if new_chain and isinstance(new_chain[0], Plain):
            text = new_chain[0].text
            if text.startswith("\n"):
                new_chain[0] = Plain(text.lstrip("\n"))
        return new_chain

    async def reply(
        self,
        content: str = "",
        buttons=None,
        media=None,
        hide_avatar_and_center: bool | None = None,
        auto_delete_time: int | None = None,
        use_markdown: bool | None = None,
    ):
        if media:
            msg_id, event_id = self._resolve_ids()
            target = self._target()
            if isinstance(media, dict) and media.get("file_info"):
                resp = await self._sender.send_media_file_info(
                    target=target,
                    file_info=media["file_info"],
                    content=content,
                    msg_id=msg_id,
                    event_id=event_id,
                )
            elif isinstance(media, bytes):
                resp = await self._sender.send_media(
                    target=target,
                    file_bytes=media,
                    file_type=3,
                    content=content,
                    msg_id=msg_id,
                    event_id=event_id,
                )
            else:
                resp = await self._sender.send_plain(
                    target=target,
                    content=content,
                    msg_id=msg_id,
                    event_id=event_id,
                )

            message_id = self._extract_message_id(resp)
            if auto_delete_time:
                asyncio.create_task(self._schedule_recall(message_id, auto_delete_time))
            await self._store_history_if_needed(content)
            self._record_last_message_id(message_id)
            return message_id

        return await self._send_text_reply(
            content=content,
            buttons=buttons,
            hide_avatar_and_center=hide_avatar_and_center,
            auto_delete_time=auto_delete_time,
            use_markdown=bool(use_markdown),
            allow_markdown_fallback=False,
            store_history=True,
            history_requires_success=False,
        )

    async def reply_image(self, image, content: str = "", auto_delete_time: int | None = None):
        msg_id, event_id = self._resolve_ids()
        target = self._target()
        image_url = _component_to_url(image)
        if image_url:
            resp = await self._sender.send_image_url(
                target=target,
                image_url=image_url,
                content=content,
                msg_id=msg_id,
                event_id=event_id,
            )
        else:
            image_bytes = await _component_to_bytes(image)
            resp = await self._sender.send_media(
                target=target,
                file_bytes=image_bytes,
                file_type=1,
                content=content,
                msg_id=msg_id,
                event_id=event_id,
            )
        message_id = self._extract_message_id(resp)
        if auto_delete_time:
            asyncio.create_task(self._schedule_recall(message_id, auto_delete_time))
        if image_url:
            assistant_parts = _build_image_content_parts(content, image_url)
            await self._store_history_if_needed(assistant_parts)
        else:
            await self._store_history_if_needed(f"{content} [image]".strip())
        self._record_last_message_id(message_id)
        return message_id

    async def reply_voice(self, voice, content: str = "", auto_delete_time: int | None = None):
        msg_id, event_id = self._resolve_ids()
        target = self._target()
        audio_bytes = await _component_to_voice_bytes(voice)
        resp = await self._sender.send_media(
            target=target,
            file_bytes=audio_bytes,
            file_type=3,
            content=content,
            msg_id=msg_id,
            event_id=event_id,
        )
        message_id = self._extract_message_id(resp)
        if auto_delete_time:
            asyncio.create_task(self._schedule_recall(message_id, auto_delete_time))
        await self._store_history_if_needed(f"{content} [voice]".strip())
        self._record_last_message_id(message_id)
        return message_id

    async def reply_video(self, video, content: str = "", auto_delete_time: int | None = None):
        msg_id, event_id = self._resolve_ids()
        target = self._target()
        video_bytes = await _component_to_bytes(video)
        resp = await self._sender.send_media(
            target=target,
            file_bytes=video_bytes,
            file_type=2,
            content=content,
            msg_id=msg_id,
            event_id=event_id,
        )
        message_id = self._extract_message_id(resp)
        if auto_delete_time:
            asyncio.create_task(self._schedule_recall(message_id, auto_delete_time))
        await self._store_history_if_needed(f"{content} [video]".strip())
        self._record_last_message_id(message_id)
        return message_id

    async def reply_ark(self, template_id: int, kv_data, content: str = "", auto_delete_time: int | None = None):
        msg_id, event_id = self._resolve_ids()
        target = self._target()
        kv_payload = self._convert_simple_ark_data(template_id, kv_data)
        resp = await self._sender.send_ark(
            target=target,
            template_id=template_id,
            kv_data=kv_payload,
            content=content,
            msg_id=msg_id,
            event_id=event_id,
        )
        message_id = self._extract_message_id(resp)
        if auto_delete_time:
            asyncio.create_task(self._schedule_recall(message_id, auto_delete_time))
        await self._store_history_if_needed(f"{content} [ark:{template_id}]".strip())
        self._record_last_message_id(message_id)
        return message_id

    async def reply_markdown(
        self,
        template_id: str,
        params: Sequence[dict] | None = None,
        keyboard_id=None,
        hide_avatar_and_center: bool | None = None,
        auto_delete_time: int | None = None,
    ):
        resolved_id = resolve_template_id(template_id) or template_id
        msg_id, event_id = self._resolve_ids()
        target = self._target()
        resp = await self._sender.send_markdown_template(
            target=target,
            template_id=resolved_id,
            params=params or [],
            msg_id=msg_id,
            keyboard=keyboard_id,
            hide_avatar_and_center=bool(hide_avatar_and_center),
            event_id=event_id,
        )
        message_id = self._extract_message_id(resp)
        if auto_delete_time:
            asyncio.create_task(self._schedule_recall(message_id, auto_delete_time))
        param_pairs, param_map = extract_params(params or [])
        keyboard_meta = normalize_keyboard_meta(keyboard_id)
        meta_line = build_meta_line(resolved_id, param_pairs, keyboard_meta)
        body = get_template_body(resolved_id)
        if body:
            rendered = render_template(body, param_map)
            store_text = f"{meta_line}\n{rendered}".strip()
        else:
            store_text = meta_line
        await self._store_history_if_needed(store_text)
        self._record_last_message_id(message_id)
        return message_id

    async def reply_md(self, *args, **kwargs):
        return await self.reply_markdown(*args, **kwargs)

    async def reply_markdown_aj(
        self,
        text: str,
        template_id: str | None = None,
        keys: Sequence[str] | str | None = None,
        keyboard_id=None,
        hide_avatar_and_center: bool | None = None,
        auto_delete_time: int | None = None,
    ):
        if not template_id:
            template_id = self._platform_config.get("markdown_aj_template_id")
        if not keys:
            keys = self._platform_config.get("markdown_aj_keys")
        if not template_id or not keys:
            raise ValueError("reply_markdown_aj 需要 template_id 与 keys 参数")
        msg_id, event_id = self._resolve_ids()
        target = self._target()
        resp = await self._sender.send_markdown_aj(
            target=target,
            template_id=template_id,
            keys=keys,
            text=text,
            msg_id=msg_id,
            keyboard=keyboard_id,
            hide_avatar_and_center=bool(hide_avatar_and_center),
            event_id=event_id,
        )
        message_id = self._extract_message_id(resp)
        if auto_delete_time:
            asyncio.create_task(self._schedule_recall(message_id, auto_delete_time))
        await self._store_history_if_needed(f"[markdown_aj:{template_id}] {text}")
        self._record_last_message_id(message_id)
        return message_id

    async def recall_message(self, message_id: str):
        target = self._target()
        return await self._sender.recall_message(target, message_id)

    async def upload_media(self, file_bytes: bytes, file_type: int):
        target = self._target()
        return await self._sender.upload_media(target, file_bytes, file_type)

    def rows(self, buttons):
        return self._sender.rows(buttons)

    def button(self, rows=None):
        return self._sender.button(rows)

    def _convert_simple_ark_data(self, template_id: int, simple_data):
        if template_id == 24:
            keys = ["#DESC#", "#PROMPT#", "#TITLE#", "#METADESC#", "#IMG#", "#LINK#", "#SUBTITLE#"]
            kv_data = []
            for i, value in enumerate(simple_data):
                if i < len(keys) and value is not None:
                    kv_data.append({"key": keys[i], "value": str(value)})
            return kv_data
        if template_id == 37:
            keys = ["#PROMPT#", "#METATITLE#", "#METASUBTITLE#", "#METACOVER#", "#METAURL#"]
            kv_data = []
            for i, value in enumerate(simple_data):
                if i < len(keys) and value is not None:
                    kv_data.append({"key": keys[i], "value": str(value)})
            return kv_data
        if template_id == 23:
            kv_data = []
            if len(simple_data) >= 1 and simple_data[0] is not None:
                kv_data.append({"key": "#DESC#", "value": str(simple_data[0])})
            if len(simple_data) >= 2 and simple_data[1] is not None:
                kv_data.append({"key": "#PROMPT#", "value": str(simple_data[1])})
            if len(simple_data) >= 3 and simple_data[2] is not None:
                obj_list = []
                for item in simple_data[2]:
                    if item and len(item) >= 1:
                        obj_kv = []
                        if item[0] and str(item[0]).strip():
                            obj_kv.append({"key": "desc", "value": str(item[0])})
                        if len(item) >= 2 and item[1] and str(item[1]).strip():
                            obj_kv.append({"key": "link", "value": str(item[1])})
                        if obj_kv:
                            obj_list.append({"obj_kv": obj_kv})
                kv_data.append({"key": "#LIST#", "obj": obj_list})
            return kv_data
        return simple_data

    async def uploadToQQImageBed(self, image_data: bytes) -> str:
        return await self.uploadToQQBotImageBed(image_data)

    async def uploadToQQBotImageBed(self, image_data: bytes) -> str:
        channel_id = self._platform_config.get("image_bed_channel_id")
        if not channel_id:
            return ""
        token = await self._sender.token_manager.get_token()
        if not token:
            return ""
        md5hash = hashlib.md5(image_data).hexdigest().upper()
        msg_id = str(int(time.time() * 1000))
        try:
            files = {"file_image": ("image.jpg", image_data, "image/jpeg")}
            data = {"msg_id": msg_id}
            headers = {"Authorization": f"QQBot {token}"}
            client = await get_async_client()
            await client.post(
                f"https://api.sgroup.qq.com/channels/{channel_id}/messages",
                data=data,
                files=files,
                headers=headers,
                timeout=20,
            )
        except Exception as exc:
            logger.warning(f"上传 QQ 图床失败: {exc}")
            return ""
        return f"https://gchat.qpic.cn/qmeetpic/0/0-0-{md5hash}/0"

    async def uploadToBilibiliImageBed(self, image_data: bytes) -> str:
        config = self._platform_config.get("bilibili_image_bed_config", {})
        if not config or not config.get("enabled"):
            return ""
        csrf_token = config.get("csrf_token", "")
        sessdata = config.get("sessdata", "")
        if not csrf_token or not sessdata or len(image_data) > 20 * 1024 * 1024:
            return ""
        try:
            files = {"file": ("image.jpg", image_data, "image/jpeg")}
            data = {"bucket": config.get("bucket", "openplatform"), "csrf": csrf_token}
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Cookie": f"SESSDATA={sessdata}; bili_jct={csrf_token}",
            }
            client = await get_async_client()
            resp = await client.post(
                "https://api.bilibili.com/x/upload/web/image",
                files=files,
                data=data,
                headers=headers,
                timeout=30,
            )
            payload = resp.json()
            if payload.get("code") == 0 and payload.get("data", {}).get("location"):
                url = payload["data"]["location"]
                return url.replace("http://", "https://") if url.startswith("http://") else url
        except Exception as exc:
            logger.warning(f"上传 Bilibili 图床失败: {exc}")
        return ""

    def get_image_size(self, image_input):
        try:
            from PIL import Image as PILImage
            import io
            import os
            if isinstance(image_input, bytes):
                with PILImage.open(io.BytesIO(image_input)) as img:
                    width, height = img.size
                    return {"width": width, "height": height, "px": f"#{width}px #{height}px"}
            if isinstance(image_input, str):
                if image_input.startswith(("http://", "https://")):
                    client = get_sync_client()
                    resp = client.get(
                        image_input,
                        headers={"Range": "bytes=0-65535"},
                        timeout=10,
                    )
                    if resp.status_code not in (200, 206):
                        return None
                    with PILImage.open(io.BytesIO(resp.content)) as img:
                        width, height = img.size
                        return {"width": width, "height": height, "px": f"#{width}px #{height}px"}
                if os.path.exists(image_input):
                    with PILImage.open(image_input) as img:
                        width, height = img.size
                        return {"width": width, "height": height, "px": f"#{width}px #{height}px"}
            return None
        except Exception:
            return None


async def _component_to_bytes(component) -> bytes:
    if isinstance(component, bytes):
        return component
    if isinstance(component, Image):
        base64_data = await component.convert_to_base64()
        return base64.b64decode(base64_data)
    if isinstance(component, Video):
        video_path = await component.convert_to_file_path()
        with open(video_path, "rb") as f:
            return f.read()
    if isinstance(component, str) and component.startswith(("http://", "https://")):
        path = await download_image_by_url(component)
        with open(path, "rb") as f:
            return f.read()
    if isinstance(component, str):
        with open(component, "rb") as f:
            return f.read()
    raise ValueError("不支持的媒体类型")


def _component_to_url(component) -> str | None:
    if isinstance(component, Image):
        url = component.url or component.file
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return url
    if isinstance(component, str) and component.startswith(("http://", "https://")):
        return component
    return None


def _build_image_content_parts(content: str, image_url: str) -> list[dict]:
    parts = []
    text = (content or "").strip()
    if text:
        parts.append({"type": "text", "text": text})
    else:
        parts.append({"type": "text", "text": "[图片]"})
    parts.append({"type": "image_url", "image_url": {"url": image_url}})
    return parts


def _summarize_content_parts(parts: list) -> str:
    text_chunks: list[str] = []
    image_count = 0
    for part in parts:
        if isinstance(part, dict):
            part_type = part.get("type")
            if part_type == "text":
                text_chunks.append(part.get("text", ""))
            elif part_type == "image_url":
                image_count += 1
            continue
        part_type = getattr(part, "type", None)
        if part_type == "text":
            text_chunks.append(getattr(part, "text", ""))
        elif part_type == "image_url":
            image_count += 1
    if image_count:
        text_chunks.append(f"[image*{image_count}]")
    return "".join(text_chunks)


async def _component_to_voice_bytes(component) -> bytes:
    if isinstance(component, bytes):
        return component
    if isinstance(component, Record):
        audio_path = await component.convert_to_file_path()
        silk_b64, _ = await audio_to_tencent_silk_base64(audio_path)
        return base64.b64decode(silk_b64)
    if isinstance(component, str):
        audio_path = component
        if component.startswith(("http://", "https://")):
            from astrbot.core.utils.io import download_file
            import tempfile
            import os
            temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".audio").name
            await download_file(component, temp_path)
            audio_path = temp_path if os.path.exists(temp_path) else component
        silk_b64, _ = await audio_to_tencent_silk_base64(audio_path)
        return base64.b64decode(silk_b64)
    raise ValueError("不支持的语音类型")


def _target_from_message_obj(msg) -> dict:
    """从 AstrBotMessage 提取发送目标。"""
    scene = getattr(msg, "qq_scene", None)
    if scene == "channel_dm":
        return {"scene": "channel_dm", "guild_id": getattr(msg, "guild_id", None)}
    if scene == "channel":
        return {"scene": "channel", "channel_id": getattr(msg, "channel_id", None)}
    if scene == "group":
        return {"scene": "group", "group_id": msg.group_id}
    if scene == "c2c":
        return {"scene": "c2c", "user_id": msg.sender.user_id}
    if getattr(msg, "guild_id", None):
        return {"scene": "channel_dm", "guild_id": msg.guild_id}
    if getattr(msg, "channel_id", None):
        return {"scene": "channel", "channel_id": msg.channel_id}
    if getattr(msg, "group_id", None):
        return {"scene": "group", "group_id": msg.group_id}
    if getattr(msg, "sender", None):
        return {"scene": "c2c", "user_id": msg.sender.user_id}
    return {}
