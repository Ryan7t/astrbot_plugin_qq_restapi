from __future__ import annotations

from typing import Any

from astrbot import logger

from .message_parser import (
    AUDIO_FINISH,
    AUDIO_OFF_MIC,
    AUDIO_ON_MIC,
    AUDIO_OR_LIVE_CHANNEL_MEMBER_ENTER,
    AUDIO_OR_LIVE_CHANNEL_MEMBER_EXIT,
    AUDIO_START,
    CHANNEL_CREATE,
    CHANNEL_DELETE,
    C2C_MSG_RECEIVE,
    C2C_MSG_REJECT,
    CHANNEL_UPDATE,
    GROUP_MSG_RECEIVE,
    GROUP_MSG_REJECT,
    FRIEND_ADD,
    FRIEND_DEL,
    GROUP_ADD_ROBOT,
    GROUP_DEL_ROBOT,
    GUILD_CREATE,
    GUILD_DELETE,
    GUILD_MEMBER_ADD,
    GUILD_MEMBER_REMOVE,
    GUILD_MEMBER_UPDATE,
    GUILD_UPDATE,
    MESSAGE_REACTION_ADD,
    MESSAGE_REACTION_REMOVE,
    MESSAGE_AUDIT_PASS,
    MESSAGE_AUDIT_REJECT,
    PUBLIC_MESSAGE_DELETE,
    DIRECT_MESSAGE_DELETE,
    SUBSCRIBE_MESSAGE_STATUS,
    OPEN_FORUM_THREAD_CREATE,
    OPEN_FORUM_THREAD_UPDATE,
    OPEN_FORUM_THREAD_DELETE,
    OPEN_FORUM_POST_CREATE,
    OPEN_FORUM_POST_DELETE,
    OPEN_FORUM_REPLY_CREATE,
    OPEN_FORUM_REPLY_DELETE,
)
from .template_registry import get_auto_event, get_auto_event_log_group
from .context import get_plugin_config

AUTO_EVENT_MAP = {

    # 群聊添加/删除机器人事件
    GROUP_ADD_ROBOT: "group_add_robot",
    GROUP_DEL_ROBOT: "group_del_robot",
    GROUP_MSG_RECEIVE: "group_msg_receive",
    GROUP_MSG_REJECT: "group_msg_reject",

    #单聊添加/删除事件
    FRIEND_ADD: "friend_add",
    FRIEND_DEL: "friend_del",

    # 频道创建/更新/删除事件
    GUILD_CREATE: "guild_create",
    GUILD_UPDATE: "guild_update",
    GUILD_DELETE: "guild_delete",

    # 子频道创建/更新/删除事件
    CHANNEL_CREATE: "channel_create",
    CHANNEL_UPDATE: "channel_update",
    CHANNEL_DELETE: "channel_delete",

    # 消息表态/审核事件
    MESSAGE_REACTION_ADD: "message_reaction_add",
    MESSAGE_REACTION_REMOVE: "message_reaction_remove",
    MESSAGE_AUDIT_PASS: "message_audit_pass",
    MESSAGE_AUDIT_REJECT: "message_audit_reject",

    # 论坛事件
    OPEN_FORUM_THREAD_CREATE: "open_forum_thread_create",
    OPEN_FORUM_THREAD_UPDATE: "open_forum_thread_update",
    OPEN_FORUM_THREAD_DELETE: "open_forum_thread_delete",
    OPEN_FORUM_POST_CREATE: "open_forum_post_create",
    OPEN_FORUM_POST_DELETE: "open_forum_post_delete",
    OPEN_FORUM_REPLY_CREATE: "open_forum_reply_create",
    OPEN_FORUM_REPLY_DELETE: "open_forum_reply_delete",

    # 频道成员添加和删除事件
    GUILD_MEMBER_ADD: "guild_member_add",
    GUILD_MEMBER_REMOVE: "guild_member_remove",
    
    # NOTE: 频道成员信息更新暂未收到官方回调，待后续验证；勿删此注释与代码。
    # GUILD_MEMBER_UPDATE: "guild_member_update",
    PUBLIC_MESSAGE_DELETE: "channel_message_delete",
    DIRECT_MESSAGE_DELETE: "channel_dm_message_delete",
    # NOTE: 订阅/音频事件暂时禁用（未稳定/需 WSS 模式验证），勿删此注释与代码。
    # SUBSCRIBE_MESSAGE_STATUS: "subscribe_message_status",
    # C2C_MSG_REJECT: "c2c_msg_reject",
    # C2C_MSG_RECEIVE: "c2c_msg_receive",
    # AUDIO_START: "audio_start",
    # AUDIO_FINISH: "audio_finish",
    # AUDIO_ON_MIC: "audio_on_mic",
    # AUDIO_OFF_MIC: "audio_off_mic",
    # AUDIO_OR_LIVE_CHANNEL_MEMBER_ENTER: "audio_member_enter",
    # AUDIO_OR_LIVE_CHANNEL_MEMBER_EXIT: "audio_member_exit",
}

_REACTION_KEYS = {
    "message_reaction_add",
    "message_reaction_remove",
}
_AUDIT_KEYS = {
    "message_audit_pass",
    "message_audit_reject",
}
_FORUM_KEYS = {
    "open_forum_thread_create",
    "open_forum_thread_update",
    "open_forum_thread_delete",
    "open_forum_post_create",
    "open_forum_post_delete",
    "open_forum_reply_create",
    "open_forum_reply_delete",
}

_LOG_ONLY_KEYS = {
    "group_msg_receive",
    "group_msg_reject",
    "guild_create",
    "guild_update",
    "guild_delete",
    "channel_create",
    "channel_update",
    "channel_delete",
    "message_reaction_add",
    "message_reaction_remove",
    "message_audit_pass",
    "message_audit_reject",
    "open_forum_thread_create",
    "open_forum_thread_update",
    "open_forum_thread_delete",
    "open_forum_post_create",
    "open_forum_post_delete",
    "open_forum_reply_create",
    "open_forum_reply_delete",
    "guild_member_add",
    "guild_member_remove",
    # NOTE: 频道成员信息更新暂未收到官方回调，待后续验证；勿删此注释与代码。
    # "guild_member_update",
    "channel_message_delete",
    "channel_dm_message_delete",
    # NOTE: 订阅/音频事件暂时禁用（未稳定/需 WSS 模式验证），勿删此注释与代码。
    # "subscribe_message_status",
    # "c2c_msg_reject",
    # "c2c_msg_receive",
    # "audio_start",
    # "audio_finish",
    # "audio_on_mic",
    # "audio_off_mic",
    # "audio_member_enter",
    # "audio_member_exit",
}


def _resolve_event_group(key: str) -> str | None:
    if key in _REACTION_KEYS:
        return "reaction"
    if key in _AUDIT_KEYS:
        return "audit"
    if key in _FORUM_KEYS:
        return "forum"
    return None


def _group_log_enabled(key: str) -> bool:
    group = _resolve_event_group(key)
    if not group:
        return True
    plugin_cfg = get_plugin_config() or {}
    group_cfg = plugin_cfg.get("auto_event_log_groups")
    if isinstance(group_cfg, dict) and group in group_cfg:
        value = group_cfg.get(group)
        if isinstance(value, bool):
            return value
    cfg = get_auto_event_log_group(group) or {}
    return cfg.get("log") is not False


def auto_event_log_enabled(key: str, config: dict[str, Any] | None = None) -> bool:
    if not _group_log_enabled(key):
        return False
    cfg = config if config is not None else (get_auto_event(key) or {})
    if cfg is not None and cfg.get("log") is False:
        return False
    return True


def auto_event_storage_enabled(event_type: str | None) -> bool:
    if not event_type:
        return True
    key = AUTO_EVENT_MAP.get(event_type)
    if not key:
        return True
    config = get_auto_event(key) or {}
    return auto_event_log_enabled(key, config)


def _scene_allowed(config: dict[str, Any] | None, scene: str | None) -> bool:
    if not config:
        return True
    scenes = config.get("scenes")
    if not scenes:
        return True
    if not scene:
        return False
    if isinstance(scenes, (list, tuple, set)):
        return scene in scenes
    return scene == str(scenes)


def _get_auto_reply_text(
    key: str,
    config: dict[str, Any] | None,
    platform_config: dict[str, Any] | None,
) -> str:
    if key == "group_add_robot":
        value = (platform_config or {}).get("group_add_robot_message")
    elif key == "friend_add":
        value = (platform_config or {}).get("friend_add_message")
    elif key == "new_user_welcome":
        value = (platform_config or {}).get("new_user_welcome_message")
    else:
        value = config.get("fallback_text") if config else ""
    return str(value or "").strip()


def _config_enabled(
    key: str,
    config: dict[str, Any] | None,
    platform_config: dict[str, Any] | None,
) -> bool:
    enabled = bool(config.get("enabled")) if config else False
    if key in {"group_add_robot", "friend_add"}:
        return bool(_get_auto_reply_text(key, config, platform_config))
    if not platform_config:
        return enabled
    if key == "group_del_robot":
        return enabled and bool(platform_config.get("enable_group_remove_notice", False))
    if key == "friend_del":
        return enabled and bool(platform_config.get("enable_friend_remove_notice", False))
    return enabled


def _render_extra_fields(msg) -> str:
    def render(value):
        if value is None or value == "":
            return "无"
        return str(value)

    extras: list[str] = []
    recall_message_id = getattr(msg, "qq_recall_message_id", None)
    if recall_message_id:
        extras.append(f" 被撤回消息ID={render(recall_message_id)}")
    subscribe_status = getattr(msg, "qq_subscribe_status", None)
    if subscribe_status is not None:
        extras.append(f" 订阅状态={render(subscribe_status)}")
    audio_event = getattr(msg, "qq_audio_event", None)
    if audio_event:
        extras.append(f" 音频事件={render(audio_event)}")
    audio_channel_type = getattr(msg, "qq_audio_channel_type", None)
    if audio_channel_type is not None:
        extras.append(f" 频道类型={render(audio_channel_type)}")
    forum_event = getattr(msg, "qq_forum_event", None)
    if forum_event:
        extras.append(f" 论坛事件={render(forum_event)}")
    reaction_emoji_id = getattr(msg, "qq_reaction_emoji_id", None)
    if reaction_emoji_id:
        extras.append(f" 表态emoji_id={render(reaction_emoji_id)}")
    reaction_target_id = getattr(msg, "qq_reaction_target_id", None)
    if reaction_target_id:
        extras.append(f" 表态目标ID={render(reaction_target_id)}")
    audit_id = getattr(msg, "qq_audit_id", None)
    if audit_id:
        extras.append(f" 审核ID={render(audit_id)}")
    audit_message_id = getattr(msg, "qq_audit_message_id", None)
    if audit_message_id:
        extras.append(f" 审核消息ID={render(audit_message_id)}")
    return "".join(extras)


def _log_auto_event(event, key: str, config: dict[str, Any] | None):
    if not auto_event_log_enabled(key, config):
        return
    msg = event.message_obj
    scene = getattr(msg, "qq_scene", None)
    scene_label = {
        "group": "群聊",
        "c2c": "单聊",
        "channel": "频道讨论组",
        "channel_dm": "频道私聊",
        "guild": "频道",
        "group_msg_setting": "群聊通知设置",
        "channel_event": "子频道事件",
        "guild_member": "频道成员事件",
        "channel_recall": "频道撤回",
        "channel_dm_recall": "频道私聊撤回",
        "reaction": "消息表态",
        "audit": "消息审核",
        "forum": "论坛事件",
        "subscribe": "订阅状态",
        "audio": "音频事件",
    }.get(scene, "未知")

    def render(value):
        if value is None or value == "":
            return "无"
        return str(value)

    union_id = getattr(msg, "qq_union_openid", None)
    raw_id = getattr(msg, "qq_raw_user_id", None)
    sender_id = getattr(getattr(msg, "sender", None), "user_id", None)
    op_user_id = getattr(msg, "qq_op_user_id", None)

    if scene in {"group", "c2c"} and not union_id:
        union_id = sender_id or raw_id

    if scene in {"channel", "channel_dm", "guild_member", "forum", "reaction", "audit", "audio", "channel_recall", "channel_dm_recall", "subscribe"} and raw_id and raw_id != union_id:
        logger.info(
            "自动事件：%s 场景/scene=%s/%s Union OpenID=%s Raw OpenID=%s 操作人ID=%s 群ID=%s 频道ID=%s 子频道ID=%s%s",
            key,
            scene_label,
            render(scene),
            render(union_id),
            render(raw_id),
            render(op_user_id),
            render(getattr(msg, "group_id", None)),
            render(getattr(msg, "guild_id", None)),
            render(getattr(msg, "channel_id", None)),
            _render_extra_fields(msg),
        )
        return

    logger.info(
        "自动事件：%s 场景/scene=%s/%s Union OpenID=%s 操作人ID=%s 群ID=%s 频道ID=%s 子频道ID=%s%s",
        key,
        scene_label,
        render(scene),
        render(union_id),
        render(op_user_id),
        render(getattr(msg, "group_id", None)),
        render(getattr(msg, "guild_id", None)),
        render(getattr(msg, "channel_id", None)),
        _render_extra_fields(msg),
    )


async def handle_relation_event(event) -> bool:
    """处理好友添加/删除、机器人入群/退群等事件。返回 True 表示已处理。"""
    event_type = getattr(event.message_obj, "qq_event_type", None)
    if not event_type:
        return False
    key = AUTO_EVENT_MAP.get(event_type)
    if not key:
        return False
    config = get_auto_event(key) or {}
    _log_auto_event(event, key, config)
    if key in _LOG_ONLY_KEYS:
        return True
    if not _scene_allowed(config, getattr(event.message_obj, "qq_scene", None)):
        return True

    enabled = _config_enabled(key, config, getattr(event, "_platform_config", None))
    if not enabled:
        return True

    text = _get_auto_reply_text(key, config, getattr(event, "_platform_config", None))
    if not text:
        return True

    msg_id, event_id = event._resolve_ids()
    await event._sender.send_plain(
        target=event._target(),
        content=text,
        msg_id=msg_id,
        event_id=event_id,
    )
    return True


async def handle_new_user_welcome(event) -> bool:
    """新用户首次交互欢迎（不写入对话记录，避免覆盖真实对话）。"""
    config = get_auto_event("new_user_welcome") or {}
    if not _scene_allowed(config, getattr(event.message_obj, "qq_scene", None)):
        return False

    text = _get_auto_reply_text(
        "new_user_welcome",
        config,
        getattr(event, "_platform_config", None),
    )
    if not text:
        return False

    event_type = getattr(event.message_obj, "qq_event_type", "")
    if event_type in AUTO_EVENT_MAP:
        return False
    conv_mgr = event._get_conversation_manager()
    if not conv_mgr:
        return False

    if event.get_extra("_qq_restapi_new_user_checked"):
        return False
    event.set_extra("_qq_restapi_new_user_checked", True)

    try:
        cid = await conv_mgr.get_curr_conversation_id(event.unified_msg_origin)
    except Exception:
        cid = None

    if cid:
        return False

    _log_auto_event(event, "new_user_welcome", config)
    msg_id, event_id = event._resolve_ids()
    await event._sender.send_plain(
        target=event._target(),
        content=text,
        msg_id=msg_id,
        event_id=event_id,
    )
    return True
