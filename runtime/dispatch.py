from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable

from astrbot import logger
from astrbot.api.platform import MessageType, PlatformMetadata

from .auto_events import (
    AUTO_EVENT_MAP,
    auto_event_storage_enabled,
    handle_new_user_welcome,
    handle_relation_event,
)
from .db_service import get_db_service
from .message_parser import parse_event
from .qq_restapi_event import QQRestAPIEvent
from .sender import QQRestAPISender

_DEDUP_TTL_SECONDS = 300
_DEDUP_MAX_KEYS = 4096


@dataclass(slots=True)
class QQDispatchResult:
    source: str
    event_type: str | None = None
    session_id: str | None = None
    message_id: str | None = None
    event_id: str | None = None
    ignored: bool = False
    deduplicated: bool = False
    committed: bool = False


class _TTLSeenCache:
    def __init__(self, ttl_seconds: int, max_keys: int):
        self.ttl_seconds = ttl_seconds
        self.max_keys = max_keys
        self._seen: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def mark_duplicate(self, key: str | None) -> bool:
        if not key:
            return False
        now = time.monotonic()
        async with self._lock:
            expires_at = self._seen.get(key)
            if expires_at and expires_at > now:
                return True
            self._seen[key] = now + self.ttl_seconds
            self._cleanup(now)
            return False

    def _cleanup(self, now: float):
        if len(self._seen) <= self.max_keys:
            expired = [key for key, expires_at in self._seen.items() if expires_at <= now]
            for key in expired:
                self._seen.pop(key, None)
            return

        for key, expires_at in list(self._seen.items()):
            if expires_at <= now:
                self._seen.pop(key, None)
        while len(self._seen) > self.max_keys:
            oldest_key = min(self._seen, key=self._seen.get)
            self._seen.pop(oldest_key, None)


_DEDUP_CACHE = _TTLSeenCache(_DEDUP_TTL_SECONDS, _DEDUP_MAX_KEYS)


def _raw_event_type(payload: dict) -> str:
    raw_t = (
        payload.get("t")
        or payload.get("event_type")
        or payload.get("eventType")
        or payload.get("type")
    )
    if raw_t:
        return str(raw_t)
    data = payload.get("d")
    if isinstance(data, dict):
        raw_t = data.get("t") or data.get("event_type") or data.get("eventType") or data.get("type")
        if raw_t:
            return str(raw_t)
    return ""


def _payload_data_keys(payload: dict) -> str:
    data = payload.get("d") if isinstance(payload.get("d"), dict) else {}
    return ",".join(sorted(data.keys())) if data else "-"


def _ensure_session_id(abm) -> str:
    session_id = getattr(abm, "session_id", "") or ""
    if session_id:
        return session_id
    session_id = (
        getattr(abm, "group_id", None)
        or getattr(abm, "channel_id", None)
        or getattr(abm, "guild_id", None)
        or getattr(getattr(abm, "sender", None), "user_id", None)
        or ""
    )
    if session_id:
        abm.session_id = session_id
    return session_id


def _dedup_key(abm, appid: str | None) -> str | None:
    appid_part = appid or "unknown_app"
    event_type = getattr(abm, "qq_event_type", None) or "unknown_event"
    event_id = getattr(abm, "qq_event_id", None)
    if event_id:
        return f"event:{appid_part}:{event_id}"

    message_id = getattr(abm, "message_id", None)
    if message_id:
        session_id = getattr(abm, "session_id", None) or ""
        return f"message:{appid_part}:{event_type}:{session_id}:{message_id}"
    return None


def _should_commit_to_astrbot(abm) -> bool:
    if getattr(abm, "type", None) not in {
        MessageType.GROUP_MESSAGE,
        MessageType.FRIEND_MESSAGE,
    }:
        return False
    return bool(getattr(abm, "session_id", None))


async def handle_qq_payload(
    payload: dict,
    *,
    source: str,
    meta: PlatformMetadata,
    sender: QQRestAPISender,
    effective_config: dict,
    commit_event: Callable[[QQRestAPIEvent], None],
) -> QQDispatchResult:
    raw_t = _raw_event_type(payload)
    if effective_config.get("debug_event_log", False):
        logger.debug(
            "[qq_restapi][debug] %s收到事件: op=%s t=%s d_keys=%s",
            source,
            payload.get("op"),
            raw_t,
            _payload_data_keys(payload),
        )

    abm = parse_event(
        payload,
        bot_id=None,
        use_union_id_for_group=effective_config.get("use_union_id_for_group", True),
        use_union_id_for_channel=effective_config.get("use_union_id_for_channel", True),
    )
    session_id = _ensure_session_id(abm)
    event_type = getattr(abm, "qq_event_type", None)
    message_id = getattr(abm, "message_id", None)
    event_id = getattr(abm, "qq_event_id", None)
    result = QQDispatchResult(
        source=source,
        event_type=event_type,
        session_id=session_id,
        message_id=message_id,
        event_id=event_id,
    )

    if effective_config.get("debug_event_log", False):
        logger.debug(
            "[qq_restapi][debug] %s解析结果: t=%s scene=%s session_id=%s guild=%s channel=%s user=%s union=%s raw=%s",
            source,
            event_type,
            getattr(abm, "qq_scene", None),
            session_id,
            getattr(abm, "guild_id", None),
            getattr(abm, "channel_id", None),
            getattr(getattr(abm, "sender", None), "user_id", None),
            getattr(abm, "qq_union_openid", None),
            getattr(abm, "qq_raw_user_id", None),
        )

    if getattr(abm, "qq_ignore", False):
        result.ignored = True
        return result

    if await _DEDUP_CACHE.mark_duplicate(_dedup_key(abm, effective_config.get("appid"))):
        result.deduplicated = True
        if effective_config.get("debug_event_log", False):
            logger.debug(
                "[qq_restapi][debug] %s跳过重复事件: t=%s session_id=%s message_id=%s event_id=%s",
                source,
                event_type,
                session_id,
                message_id,
                event_id,
            )
        return result

    if not session_id and getattr(abm, "type", None) in {
        MessageType.GROUP_MESSAGE,
        MessageType.FRIEND_MESSAGE,
    }:
        result.ignored = True
        return result

    event = QQRestAPIEvent(
        abm.message_str,
        abm,
        meta,
        session_id,
        sender,
        effective_config,
    )

    db_service = get_db_service()
    if db_service:
        if auto_event_storage_enabled(event_type):
            event_kind = "auto" if event_type in AUTO_EVENT_MAP else "message"
            if event_kind == "message" and abm.type not in (
                MessageType.GROUP_MESSAGE,
                MessageType.FRIEND_MESSAGE,
            ):
                event_kind = "system"
            await db_service.record_event(event, event_kind=event_kind)

    if await handle_relation_event(event):
        return result

    await handle_new_user_welcome(event)

    if not _should_commit_to_astrbot(abm):
        return result

    commit_event(event)
    result.committed = True
    return result
