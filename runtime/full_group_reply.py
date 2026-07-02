from __future__ import annotations

import asyncio
import json
import random
import re
import time
from dataclasses import dataclass
from typing import Any

from astrbot import logger

_MODES = {"normal", "random_reply", "all_as_at", "smart_reply", "smart_random"}
_DEFAULT_SMART_JUDGE_PROMPT = """你是一个群聊机器人发言时机判断器。
你的任务不是生成正式回复，只判断机器人现在是否应该自然接话。

请只输出严格 JSON，不要输出 Markdown，不要解释：
{"should_reply": true, "reason": "不超过20字的原因"}

建议回复的情况：
- 群成员在问公开问题、求助、征求意见。
- 群成员在讨论机器人、AI、当前机器人能力或刚才机器人的回复。
- 群聊出现机器人自然接一句会有帮助的空档。

不建议回复的情况：
- 群成员之间明显在互相聊天，没有邀请机器人参与。
- 欢迎新人、表情、刷屏、无实质内容、只是在贴图。
- 机器人刚刚主动插话过，继续回复会显得打扰。

请保守判断。拿不准时 should_reply=false。
"""


@dataclass(slots=True)
class FullGroupReplySettings:
    mode: str = "normal"
    random_probability: float = 0.05
    random_cooldown_seconds: int = 0
    smart_sample_probability: float = 0.2
    smart_cooldown_seconds: int = 60
    smart_judge_provider_id: str = ""
    smart_judge_timeout_seconds: float = 8.0
    smart_recent_context_messages: int = 20
    smart_judge_prompt: str = _DEFAULT_SMART_JUDGE_PROMPT
    per_group_ordered_decision: bool = True
    max_pending_per_group: int = 32
    debug_log: bool = False


@dataclass(slots=True)
class FullGroupReplyDecision:
    should_reply: bool
    mode: str
    reason: str = ""
    natural_history: bool = False


class FullGroupReplyController:
    def __init__(self, context, config) -> None:
        self.context = context
        self.config = config
        self._locks: dict[str, asyncio.Lock] = {}
        self._pending: dict[str, int] = {}
        self._last_reply_at: dict[str, float] = {}

    async def decide(self, event) -> FullGroupReplyDecision:
        settings = self._settings()
        if settings.mode == "normal":
            return FullGroupReplyDecision(False, settings.mode, "normal")

        key = self._key(event)
        if settings.per_group_ordered_decision:
            if self._queue_is_full(key, settings):
                logger.warning(
                    "[qq_restapi] 全量群消息回复判断队列已满，改为只入库: "
                    "umo=%s max_pending=%s",
                    key,
                    settings.max_pending_per_group,
                )
                return FullGroupReplyDecision(False, settings.mode, "queue_full")
            self._pending[key] = self._pending.get(key, 0) + 1
            try:
                async with self._lock_for(key):
                    return await self._decide_unlocked(event, settings, key)
            finally:
                current = self._pending.get(key, 0) - 1
                if current > 0:
                    self._pending[key] = current
                else:
                    self._pending.pop(key, None)

        return await self._decide_unlocked(event, settings, key)

    async def _decide_unlocked(
        self,
        event,
        settings: FullGroupReplySettings,
        key: str,
    ) -> FullGroupReplyDecision:
        if settings.mode == "all_as_at":
            self._mark_reply(key)
            return FullGroupReplyDecision(
                True,
                settings.mode,
                "all_as_at",
                natural_history=False,
            )

        if settings.mode == "random_reply":
            if self._in_cooldown(key, settings.random_cooldown_seconds):
                return FullGroupReplyDecision(False, settings.mode, "cooldown")
            if random.random() >= settings.random_probability:
                return FullGroupReplyDecision(False, settings.mode, "random_miss")
            self._mark_reply(key)
            return FullGroupReplyDecision(
                True,
                settings.mode,
                "random_hit",
                natural_history=True,
            )

        if settings.mode == "smart_reply":
            should_reply, reason = await self._judge(event, settings)
            if not should_reply:
                return FullGroupReplyDecision(False, settings.mode, reason or "judge_no")
            if self._in_cooldown(key, settings.smart_cooldown_seconds):
                return FullGroupReplyDecision(
                    False,
                    settings.mode,
                    "cooldown_after_judge",
                )
            self._mark_reply(key)
            return FullGroupReplyDecision(
                True,
                settings.mode,
                reason or "judge_yes",
                natural_history=True,
            )

        if settings.mode == "smart_random":
            if self._in_cooldown(key, settings.smart_cooldown_seconds):
                return FullGroupReplyDecision(False, settings.mode, "cooldown")
            if random.random() >= settings.smart_sample_probability:
                return FullGroupReplyDecision(False, settings.mode, "sample_miss")
            should_reply, reason = await self._judge(event, settings)
            if not should_reply:
                return FullGroupReplyDecision(False, settings.mode, reason or "judge_no")
            self._mark_reply(key)
            return FullGroupReplyDecision(
                True,
                settings.mode,
                reason or "judge_yes",
                natural_history=True,
            )

        return FullGroupReplyDecision(False, settings.mode, "unsupported_mode")

    def _settings(self) -> FullGroupReplySettings:
        raw = {}
        if isinstance(self.config, dict):
            value = self.config.get("full_group_reply")
            if isinstance(value, dict):
                raw = value

        mode = str(raw.get("mode") or "normal").strip()
        if mode not in _MODES:
            logger.warning(
                "[qq_restapi] full_group_reply.mode=%s 无效，已回退 normal",
                mode,
            )
            mode = "normal"

        prompt = str(raw.get("smart_judge_prompt") or "").strip()
        return FullGroupReplySettings(
            mode=mode,
            random_probability=_clamp_probability(
                raw.get("random_probability"),
                0.05,
            ),
            random_cooldown_seconds=_non_negative_int(
                raw.get("random_cooldown_seconds"),
                0,
            ),
            smart_sample_probability=_clamp_probability(
                raw.get("smart_sample_probability"),
                0.2,
            ),
            smart_cooldown_seconds=_non_negative_int(
                raw.get("smart_cooldown_seconds"),
                60,
            ),
            smart_judge_provider_id=str(raw.get("smart_judge_provider_id") or "").strip(),
            smart_judge_timeout_seconds=_positive_float(
                raw.get("smart_judge_timeout_seconds"),
                8.0,
            ),
            smart_recent_context_messages=_non_negative_int(
                raw.get("smart_recent_context_messages"),
                20,
            ),
            smart_judge_prompt=prompt or _DEFAULT_SMART_JUDGE_PROMPT,
            per_group_ordered_decision=bool(raw.get("per_group_ordered_decision", True)),
            max_pending_per_group=_non_negative_int(
                raw.get("max_pending_per_group"),
                32,
            ),
            debug_log=bool(raw.get("debug_log", False)),
        )

    async def _judge(
        self,
        event,
        settings: FullGroupReplySettings,
    ) -> tuple[bool, str]:
        provider = self._resolve_judge_provider(event, settings)
        if not provider:
            logger.warning(
                "[qq_restapi] %s 判断失败: 未找到可用判断模型 provider_id=%s",
                settings.mode,
                settings.smart_judge_provider_id or "<current>",
            )
            return False, "provider_missing"

        current_message = self._format_current_message(event)
        contexts = await self._recent_contexts(
            event,
            settings.smart_recent_context_messages,
            settings.mode,
        )
        prompt = (
            "下面是当前群聊最新消息，请判断机器人是否应该自然接话。\n\n"
            f"{current_message}\n\n"
            "只输出 JSON。"
        )

        try:
            response = await asyncio.wait_for(
                provider.text_chat(
                    prompt=prompt,
                    contexts=contexts,
                    system_prompt=settings.smart_judge_prompt,
                    session_id=f"{event.unified_msg_origin}:full_group_reply_judge",
                ),
                timeout=settings.smart_judge_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[qq_restapi] %s 判断超时，改为只入库: umo=%s timeout=%ss",
                settings.mode,
                event.unified_msg_origin,
                settings.smart_judge_timeout_seconds,
            )
            return False, "judge_timeout"
        except Exception as exc:
            logger.warning(
                "[qq_restapi] %s 判断失败，改为只入库: %s",
                settings.mode,
                exc,
            )
            return False, "judge_error"

        text = str(getattr(response, "completion_text", "") or "").strip()
        should_reply, reason = _parse_judge_json(text)
        if settings.debug_log:
            logger.info(
                "[qq_restapi] %s 判断结果: should_reply=%s reason=%s raw=%s",
                settings.mode,
                should_reply,
                reason,
                text[:200],
            )
        return should_reply, reason

    def _resolve_judge_provider(
        self,
        event,
        settings: FullGroupReplySettings,
    ):
        if not self.context:
            return None
        if settings.smart_judge_provider_id:
            provider = self.context.get_provider_by_id(settings.smart_judge_provider_id)
        else:
            provider = self.context.get_using_provider(event.unified_msg_origin)
        if provider and callable(getattr(provider, "text_chat", None)):
            return provider
        return None

    async def _recent_contexts(self, event, limit: int, mode: str) -> list[dict]:
        if limit <= 0 or not self.context:
            return []
        conv_mgr = getattr(self.context, "conversation_manager", None)
        if not conv_mgr:
            return []
        try:
            cid = await conv_mgr.get_curr_conversation_id(event.unified_msg_origin)
            if not cid:
                return []
            conversation = await conv_mgr.get_conversation(event.unified_msg_origin, cid)
            if not conversation or not conversation.history:
                return []
            history = json.loads(conversation.history)
            if not isinstance(history, list):
                return []
            return history[-limit:]
        except Exception as exc:
            logger.warning(
                "[qq_restapi] %s 读取最近上下文失败: %s",
                mode,
                exc,
            )
            return []

    @staticmethod
    def _format_current_message(event) -> str:
        formatter = getattr(event, "format_group_history_text", None)
        text = event.message_str or event.get_message_outline() or "[empty]"
        if callable(formatter):
            return formatter(text, directed=False)
        sender = getattr(event.message_obj, "sender", None)
        nickname = getattr(sender, "nickname", "") if sender else ""
        user_id = getattr(sender, "user_id", "") if sender else ""
        label = nickname or user_id or "unknown"
        if user_id and user_id != label:
            return f"[{label}/{user_id}]: {text}"
        return f"[{label}]: {text}"

    def _lock_for(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def _queue_is_full(
        self,
        key: str,
        settings: FullGroupReplySettings,
    ) -> bool:
        if settings.max_pending_per_group <= 0:
            return False
        return self._pending.get(key, 0) >= settings.max_pending_per_group

    def _in_cooldown(self, key: str, cooldown_seconds: int) -> bool:
        if cooldown_seconds <= 0:
            return False
        last = self._last_reply_at.get(key)
        return bool(last and time.monotonic() - last < cooldown_seconds)

    def _mark_reply(self, key: str) -> None:
        self._last_reply_at[key] = time.monotonic()

    @staticmethod
    def _key(event) -> str:
        return str(
            getattr(event, "unified_msg_origin", "")
            or getattr(event, "session_id", "")
            or "unknown",
        )


def _parse_judge_json(text: str) -> tuple[bool, str]:
    if not text:
        return False, "empty_judge_response"
    candidates = [text]
    match = re.search(r"\{.*\}", text, flags=re.S)
    if match:
        candidates.append(match.group(0))

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        value = data.get("should_reply")
        if isinstance(value, bool):
            return value, str(data.get("reason") or "").strip()
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "1"}:
                return True, str(data.get("reason") or "").strip()
            if normalized in {"false", "no", "0"}:
                return False, str(data.get("reason") or "").strip()
    return False, "invalid_judge_json"


def _clamp_probability(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(0.0, min(1.0, parsed))


def _non_negative_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(0, parsed)


def _positive_float(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = fallback
    return parsed if parsed > 0 else fallback
