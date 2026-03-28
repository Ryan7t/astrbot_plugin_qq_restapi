from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

from astrbot.api.event import AstrMessageEvent


class SceneType:
    CHANNEL_SUB_CHANNEL = "频道讨论组"
    CHANNEL_DM = "频道私聊"
    GROUP_CHAT = "群聊"
    PRIVATE_CHAT = "单聊"
    UNKNOWN = "未知"


@dataclass
class SceneContext:
    scene_type: str = SceneType.UNKNOWN
    platform_name: str = ""
    guild_id: Optional[str] = None
    channel_id: Optional[str] = None
    dm_id: Optional[str] = None
    group_id: Optional[str] = None
    user_id: Optional[str] = None
    message_id: Optional[str] = None
    # TODO: 回调按钮可能需要 event_id（INTERACTION_CREATE 的 id）来 ACK。
    # 先不加入字段，待测试确认后再实现。勿删此注释。
    api_url: Optional[str] = None
    supports_keyboard: bool = False
    error: Optional[str] = None
    debug_hint: Optional[str] = None
    source_guild_id: Optional[str] = None
    source_channel_id: Optional[str] = None

    @property
    def is_channel(self) -> bool:
        return self.scene_type in {
            SceneType.CHANNEL_SUB_CHANNEL,
            SceneType.CHANNEL_DM,
        }

    @property
    def is_sub_channel(self) -> bool:
        return self.scene_type == SceneType.CHANNEL_SUB_CHANNEL

    @property
    def is_channel_dm(self) -> bool:
        return self.scene_type == SceneType.CHANNEL_DM

    @property
    def is_group(self) -> bool:
        return self.scene_type == SceneType.GROUP_CHAT

    @property
    def is_private(self) -> bool:
        return self.scene_type == SceneType.PRIVATE_CHAT

    @property
    def effective_guild_id(self) -> Optional[str]:
        return self.source_guild_id or self.guild_id

    @property
    def effective_channel_id(self) -> Optional[str]:
        return self.source_channel_id or self.channel_id


def _normalize_identifier(value):
    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None

    return value


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        lowered = value.strip().lower()
        if not lowered:
            return False
        return lowered in {"1", "true", "yes", "y", "t", "on"}

    if isinstance(value, (int, float)):
        return value != 0

    return False


def _compose_debug_hint(platform: str, base: Optional[str]) -> Optional[str]:
    if not base:
        return base

    if platform:
        return f"[{platform}] {base}"

    return base


def _try_get_from_raw(plugin, raw_obj, *keys):
    if raw_obj is None:
        return None

    if hasattr(plugin, "_get_from_obj"):
        value = plugin._get_from_obj(raw_obj, *keys)
        if value is not None:
            return value

    if isinstance(raw_obj, dict):
        for key in keys:
            if key in raw_obj and raw_obj[key] is not None:
                return raw_obj[key]
        payload_data = raw_obj.get("d")
        if isinstance(payload_data, dict):
            for key in keys:
                if key in payload_data and payload_data[key] is not None:
                    return payload_data[key]

    for key in keys:
        if hasattr(raw_obj, key):
            val = getattr(raw_obj, key)
            if val is not None:
                return val

    return None


def _normalize_message_type(event: AstrMessageEvent) -> str:
    try:
        msg_type = event.get_message_type()
    except Exception:
        return ""

    if msg_type is None:
        return ""

    if isinstance(msg_type, str):
        return msg_type.lower()

    value = getattr(msg_type, "value", None)
    if isinstance(value, str) and value:
        return value.lower()

    name = getattr(msg_type, "name", None)
    if isinstance(name, str) and name:
        return name.lower()

    try:
        return str(msg_type).lower()
    except Exception:
        return ""


def _is_channel_dm(
    event: AstrMessageEvent,
    message_type_repr: str,
    *,
    has_channel_dimension: bool,
    direct_flag: bool = False,
) -> bool:
    if not has_channel_dimension:
        return False

    try:
        if event.is_private_chat():
            return True
    except Exception:
        pass

    if direct_flag:
        return True

    if message_type_repr and any(
        keyword in message_type_repr for keyword in ("direct", "private", "dm")
    ):
        return True

    return False


def _extract_message_id(event: AstrMessageEvent) -> Optional[str]:
    raw_msg = getattr(event.message_obj, "raw_message", None)
    if raw_msg is not None:
        if isinstance(raw_msg, dict):
            payload_data = raw_msg.get("d") if isinstance(raw_msg.get("d"), dict) else None
            if payload_data:
                for key in ("id", "message_id", "msg_id"):
                    if payload_data.get(key):
                        return payload_data[key]
            if raw_msg.get("id"):
                return raw_msg["id"]
        if hasattr(raw_msg, "id") and getattr(raw_msg, "id"):
            return getattr(raw_msg, "id")

    message_id = getattr(event.message_obj, "message_id", None)
    if message_id:
        return message_id

    return None


def resolve_scene(plugin, event: AstrMessageEvent) -> SceneContext:
    raw_msg = getattr(event.message_obj, "raw_message", None)
    platform_name = event.get_platform_name() or ""
    raw_group_id = getattr(event.message_obj, "group_id", None)
    raw_user_id = event.get_sender_id()

    guild_id = _normalize_identifier(
        _try_get_from_raw(plugin, raw_msg, "guild_id", "guildId")
    )
    channel_id = _normalize_identifier(
        _try_get_from_raw(plugin, raw_msg, "channel_id", "channelId")
    )
    dm_id = _normalize_identifier(
        _try_get_from_raw(plugin, raw_msg, "dm_id", "dmId")
    )
    group_id = _normalize_identifier(raw_group_id)
    user_id = _normalize_identifier(raw_user_id)

    message_id = _extract_message_id(event)
    message_type_repr = _normalize_message_type(event)
    direct_flag = False
    if raw_msg is not None:
        direct_flag = _coerce_bool(
            _try_get_from_raw(plugin, raw_msg, "direct_message", "directMessage")
        )

    source_guild_id = _normalize_identifier(
        _try_get_from_raw(
            plugin,
            raw_msg,
            "src_guild_id",
            "srcGuildId",
            "src_guild",
            "source_guild_id",
            "sourceGuildId",
        )
    )
    source_channel_id = _normalize_identifier(
        _try_get_from_raw(
            plugin,
            raw_msg,
            "src_channel_id",
            "srcChannelId",
            "source_channel_id",
            "sourceChannelId",
        )
    )

    context = SceneContext(
        platform_name=platform_name,
        guild_id=guild_id,
        channel_id=channel_id,
        dm_id=dm_id,
        group_id=group_id,
        user_id=user_id,
        message_id=message_id,
        source_guild_id=source_guild_id,
        source_channel_id=source_channel_id,
    )

    is_qq_official = platform_name in {
        "qq_official",
        "qq_official_webhook",
        "qq_restapi",
        "qq_restapi_webhook",
    }

    has_channel_dimension = bool(dm_id or guild_id or channel_id)

    if is_qq_official:
        if _is_channel_dm(
            event,
            message_type_repr,
            has_channel_dimension=has_channel_dimension,
            direct_flag=direct_flag,
        ):
            dm_target = dm_id or guild_id
            if dm_target:
                context.scene_type = SceneType.CHANNEL_DM
                context.dm_id = dm_target
                context.api_url = f"https://api.sgroup.qq.com/dms/{dm_target}/messages"
                context.debug_hint = _compose_debug_hint(
                    platform_name, f"频道私聊 ID: {dm_target}"
                )
                return context
            # 没有频道维度 ID，回退到后续的普通私聊逻辑
            context.debug_hint = _compose_debug_hint(
                platform_name, "未提供频道私聊会话 ID，准备回退到用户私聊。"
            )

        if channel_id:
            context.scene_type = SceneType.CHANNEL_SUB_CHANNEL
            context.api_url = (
                f"https://api.sgroup.qq.com/channels/{channel_id}/messages"
            )
            context.supports_keyboard = True
            context.debug_hint = _compose_debug_hint(
                platform_name, f"频道讨论组 ID: {channel_id}"
            )
            return context

        if group_id:
            context.scene_type = SceneType.GROUP_CHAT
            context.api_url = f"https://api.sgroup.qq.com/v2/groups/{group_id}/messages"
            context.supports_keyboard = True
            context.debug_hint = _compose_debug_hint(
                platform_name, f"群聊 ID: {group_id}"
            )
            return context

        if guild_id:
            context.scene_type = SceneType.CHANNEL_DM
            context.dm_id = guild_id
            context.api_url = f"https://api.sgroup.qq.com/dms/{guild_id}/messages"
            context.debug_hint = _compose_debug_hint(
                platform_name, f"频道私聊 ID: {guild_id}"
            )
            return context

    if group_id:
        context.scene_type = SceneType.GROUP_CHAT
        context.api_url = f"https://api.sgroup.qq.com/v2/groups/{group_id}/messages"
        context.supports_keyboard = True
        context.debug_hint = _compose_debug_hint(
            platform_name, f"群聊 ID: {group_id}"
        )
        return context

    if user_id:
        context.scene_type = SceneType.PRIVATE_CHAT
        context.api_url = f"https://api.sgroup.qq.com/v2/users/{user_id}/messages"
        context.supports_keyboard = True
        context.debug_hint = _compose_debug_hint(
            platform_name, f"单聊用户 ID: {user_id}"
        )
        return context

    context.error = "未能获取目标 ID，无法发送消息。"
    return context


def ensure_scene(
    context: SceneContext,
    allowed: Sequence[str],
    error_message: Optional[str] = None,
) -> Optional[str]:
    if context.error:
        return context.error

    if context.scene_type not in allowed:
        return error_message or f"此指令仅限在{allowed_scenes_text(allowed)}中使用。"

    return None


def ensure_channel(
    context: SceneContext,
    error_message: Optional[str] = None,
    *,
    allow_channel_dm: bool = True,
) -> Optional[str]:
    if context.error:
        return context.error

    if (
        allow_channel_dm
        and context.scene_type == SceneType.CHANNEL_DM
        and context.source_guild_id
    ):
        return None

    return ensure_scene(
        context,
        (SceneType.CHANNEL_SUB_CHANNEL,),
        error_message or "此指令仅限在频道讨论组（文字子频道）中使用。",
    )


def ensure_sub_channel(
    context: SceneContext, error_message: Optional[str] = None
) -> Optional[str]:
    return ensure_scene(
        context,
        (SceneType.CHANNEL_SUB_CHANNEL, SceneType.CHANNEL_DM),
        error_message or "此指令仅限在频道讨论组（文字子频道）或频道私聊中使用。",
    )


def ensure_channel_dm(
    context: SceneContext, error_message: Optional[str] = None
) -> Optional[str]:
    return ensure_scene(context, (SceneType.CHANNEL_DM,), error_message)


def ensure_message_target(
    context: SceneContext, error_message: Optional[str] = None
) -> Optional[str]:
    return ensure_scene(
        context,
        (
            SceneType.CHANNEL_SUB_CHANNEL,
            SceneType.CHANNEL_DM,
            SceneType.GROUP_CHAT,
            SceneType.PRIVATE_CHAT,
        ),
        error_message
        or "此指令仅限在频道讨论组（文字子频道）、频道私聊、群聊或单聊中使用。",
    )


def allowed_scenes_text(allowed: Iterable[str]) -> str:
    mapping = {
        SceneType.CHANNEL_SUB_CHANNEL: "频道讨论组（文字子频道）",
        SceneType.CHANNEL_DM: "频道私聊",
        SceneType.GROUP_CHAT: "群聊",
        SceneType.PRIVATE_CHAT: "单聊",
    }
    names = [mapping.get(scene, scene) for scene in allowed]
    return "、".join(names)
