from __future__ import annotations

import json
import time
from typing import Any

from astrbot import logger

from .database import QQRestAPIDatabase
from .repository import QQRestAPIRepository

_SCENE_TYPES = {"c2c", "group", "channel", "channel_dm"}
_EVENT_KINDS = {"message", "auto", "system"}


def _normalize_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value)


def _pick_value(data: dict, *keys):
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _extract_event_data(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return {}
    data = raw.get("d") or raw.get("data") or raw.get("event_data") or raw.get("eventData") or {}
    if isinstance(data, dict):
        inner_type = data.get("event_type") or data.get("eventType") or data.get("type")
        inner_data = data.get("event_data") or data.get("eventData") or data.get("data")
        if inner_type and not raw.get("t"):
            pass
        if isinstance(inner_data, dict):
            data = inner_data
    if not isinstance(data, dict):
        return {}
    return data


def _coerce_bool_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if not lowered:
            return None
        if lowered in {"1", "true", "yes", "y", "t", "on"}:
            return 1
        if lowered in {"0", "false", "no", "n", "f", "off"}:
            return 0
    return None


def _serialize_json(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=True, separators=(",", ":"), default=str)
    except Exception:
        return None


def _extract_user_info(data: dict) -> dict:
    user_info = data.get("author") or data.get("user") or data.get("member") or {}
    return user_info if isinstance(user_info, dict) else {}


def _extract_roles_json(user_info: dict, data: dict) -> str | None:
    roles = user_info.get("roles")
    if roles is None:
        roles = data.get("roles")
    if roles is None:
        return None
    if isinstance(roles, str):
        stripped = roles.strip()
        if stripped.startswith("["):
            return stripped
        return _serialize_json([roles])
    if isinstance(roles, (list, tuple, set)):
        return _serialize_json(list(roles))
    return None


def _extract_source_fields(data: dict) -> tuple[str | None, str | None, str | None]:
    source_guild_id = _normalize_str(
        _pick_value(
            data,
            "src_guild_id",
            "srcGuildId",
            "src_guild",
            "source_guild_id",
            "sourceGuildId",
        )
    )
    source_channel_id = _normalize_str(
        _pick_value(
            data,
            "src_channel_id",
            "srcChannelId",
            "source_channel_id",
            "sourceChannelId",
        )
    )
    dm_id = _normalize_str(_pick_value(data, "dm_id", "dmId"))
    return source_guild_id, source_channel_id, dm_id


class QQRestAPIService:
    def __init__(self, db: QQRestAPIDatabase) -> None:
        self.db = db
        self.repo = QQRestAPIRepository(db)

    def _resolve_user_ids(self, msg) -> tuple[str | None, str | None, str | None]:
        sender_id = _normalize_str(getattr(getattr(msg, "sender", None), "user_id", None))
        union_openid = _normalize_str(getattr(msg, "qq_union_openid", None))
        raw_openid = _normalize_str(getattr(msg, "qq_raw_user_id", None))
        scene = getattr(msg, "qq_scene", None)
        if scene in {"group", "c2c"} and not union_openid:
            union_openid = sender_id or raw_openid
        if not raw_openid:
            raw_openid = sender_id or union_openid
        return union_openid, raw_openid, sender_id

    async def record_event(self, event, *, event_kind: str) -> None:
        msg = getattr(event, "message_obj", None)
        if msg is None:
            return
        kind = event_kind.lower().strip() if isinstance(event_kind, str) else "system"
        if kind not in _EVENT_KINDS:
            kind = "system"

        scene = getattr(msg, "qq_scene", None)
        event_type = _normalize_str(getattr(msg, "qq_event_type", None))
        raw_payload = getattr(msg, "raw_message", None)
        payload_json = _serialize_json(raw_payload)
        data = _extract_event_data(raw_payload)
        now = int(time.time())

        union_openid, raw_openid, sender_id = self._resolve_user_ids(msg)

        user_info = _extract_user_info(data)
        username = _normalize_str(user_info.get("username"))
        nick = _normalize_str(
            user_info.get("nick")
            or user_info.get("nickname")
            or user_info.get("name")
        )
        avatar = _normalize_str(
            user_info.get("avatar")
            or user_info.get("avatar_url")
            or user_info.get("avatarUrl")
        )
        bot_flag = _coerce_bool_int(user_info.get("bot") or user_info.get("is_bot"))
        union_user_account = _normalize_str(
            user_info.get("union_user_account")
            or user_info.get("unionUserAccount")
            or user_info.get("union_user_account_id")
        )
        roles_json = _extract_roles_json(user_info, data)

        group_id = _normalize_str(getattr(msg, "group_id", None))
        guild_id = _normalize_str(getattr(msg, "guild_id", None))
        channel_id = _normalize_str(getattr(msg, "channel_id", None))

        source_guild_id, source_channel_id, dm_id = _extract_source_fields(data)
        if scene == "channel_dm":
            if source_guild_id is None and guild_id:
                source_guild_id = guild_id

        message_id = _normalize_str(getattr(msg, "message_id", None))
        event_id = _normalize_str(getattr(msg, "qq_event_id", None))

        try:
            async with self.db.get_db() as session:
                async with session.begin():
                    if union_openid:
                        await self.repo.upsert_user_identity(
                            union_openid=union_openid,
                            avatar=avatar,
                            nickname=nick or username,
                            last_seen_at=now,
                            session=session,
                        )

                    if scene in _SCENE_TYPES and raw_openid:
                        if scene == "group" and not group_id:
                            pass
                        elif scene == "channel" and (not guild_id or not channel_id):
                            pass
                        elif scene == "channel_dm" and not guild_id:
                            pass
                        else:
                            await self.repo.upsert_user_scene(
                                scene_type=scene,
                                raw_openid=raw_openid,
                                union_openid=union_openid,
                                group_id=group_id if scene == "group" else None,
                                guild_id=guild_id if scene in {"channel", "channel_dm"} else None,
                                channel_id=channel_id if scene == "channel" else None,
                                dm_id=dm_id if scene == "channel_dm" else None,
                                source_guild_id=source_guild_id,
                                source_channel_id=source_channel_id,
                                source_updated_at=now if source_guild_id or source_channel_id else None,
                                username=username,
                                avatar=avatar,
                                nick=nick,
                                bot=bot_flag,
                                union_user_account=union_user_account,
                                roles_json=roles_json,
                                last_seen_at=now,
                                last_event_type=event_type,
                                session=session,
                            )

                    if guild_id:
                        guild_data = data if isinstance(data, dict) else {}
                        await self.repo.upsert_guild(
                            guild_id=guild_id,
                            name=_normalize_str(
                                _pick_value(guild_data, "name", "guild_name", "guildName")
                            ),
                            icon=_normalize_str(_pick_value(guild_data, "icon", "guild_icon", "guildIcon")),
                            owner_id=_normalize_str(
                                _pick_value(guild_data, "owner_id", "ownerId")
                            ),
                            owner=_coerce_bool_int(_pick_value(guild_data, "owner")),
                            member_count=_pick_value(guild_data, "member_count", "memberCount"),
                            max_members=_pick_value(guild_data, "max_members", "maxMembers"),
                            description=_normalize_str(_pick_value(guild_data, "description")),
                            joined_at=_pick_value(guild_data, "joined_at", "joinedAt"),
                            last_seen_at=now,
                            session=session,
                        )

                    if channel_id and guild_id:
                        channel_data = data if isinstance(data, dict) else {}
                        await self.repo.upsert_channel(
                            channel_id=channel_id,
                            guild_id=guild_id,
                            name=_normalize_str(_pick_value(channel_data, "name", "channel_name", "channelName")),
                            type=_pick_value(channel_data, "type", "channel_type", "channelType"),
                            sub_type=_pick_value(channel_data, "sub_type", "subType"),
                            position=_pick_value(channel_data, "position"),
                            parent_id=_normalize_str(_pick_value(channel_data, "parent_id", "parentId")),
                            owner_id=_normalize_str(_pick_value(channel_data, "owner_id", "ownerId")),
                            private_type=_pick_value(channel_data, "private_type", "privateType"),
                            speak_permission=_pick_value(channel_data, "speak_permission", "speakPermission"),
                            application_id=_normalize_str(_pick_value(channel_data, "application_id", "applicationId")),
                            permissions=_normalize_str(_pick_value(channel_data, "permissions")),
                            last_seen_at=now,
                            session=session,
                        )

                    await self.repo.insert_event_log(
                        log_level="info",
                        event_kind=kind,
                        event_type=event_type,
                        scene_type=_normalize_str(scene),
                        union_openid=union_openid,
                        raw_openid=raw_openid,
                        group_id=group_id,
                        guild_id=guild_id,
                        channel_id=channel_id,
                        message_id=message_id,
                        event_id=event_id,
                        payload_json=payload_json,
                        created_at=now,
                        session=session,
                    )
        except Exception:
            logger.exception(
                "DB write failed: event_kind=%s event_type=%s",
                kind,
                event_type,
            )
