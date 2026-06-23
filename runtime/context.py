from __future__ import annotations

from astrbot.core.star.context import Context

_CONTEXT: Context | None = None
_PLUGIN_CONFIG: dict | None = None
_PLUGIN_DB = None
_PLUGIN_CONFIG_KEYS = {
    "use_union_id_for_group",
    "use_union_id_for_channel",
    "markdown_aj_template_id",
    "markdown_aj_keys",
    "image_bed_channel_id",
    "bilibili_image_bed_config",
    "debug_event_log",
    "group_add_robot_message",
    "group_member_add_message",
    "friend_add_message",
    "new_user_welcome_message",
    "enable_group_remove_notice",
    "enable_friend_remove_notice",
    "auto_event_log_groups",
}


def set_context(context: Context) -> None:
    global _CONTEXT
    _CONTEXT = context


def get_context() -> Context | None:
    return _CONTEXT


def set_plugin_config(config) -> None:
    global _PLUGIN_CONFIG
    _PLUGIN_CONFIG = dict(config) if config is not None else None


def get_plugin_config() -> dict | None:
    return _PLUGIN_CONFIG


def merge_plugin_config(base: dict | None) -> dict:
    merged = dict(base or {})
    plugin_cfg = _PLUGIN_CONFIG or {}
    for key in _PLUGIN_CONFIG_KEYS:
        if key in plugin_cfg:
            merged[key] = plugin_cfg[key]
    return merged


def set_plugin_db(db) -> None:
    global _PLUGIN_DB
    _PLUGIN_DB = db


def get_plugin_db():
    return _PLUGIN_DB
