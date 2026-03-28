from __future__ import annotations

from pathlib import Path

from astrbot.core.star.context import Context

from .core.qq.sender import build_markdown_params, send_markdown_template
from .runtime.httpx_pool import get_async_client, get_sync_client
from .runtime.last_message_cache import get_last_message_id
from .runtime.template_registry import (
    get_auto_event,
    get_auto_event_log_group,
    get_template_entry,
    get_template_file,
    get_template_keyboard_id,
    register_template_source,
    resolve_template_id,
    unregister_template_source,
)
from .runtime.template_store import (
    build_meta_line,
    extract_params,
    get_template_body,
    normalize_keyboard_meta,
    render_template,
)
from .utils.scene import (
    SceneContext,
    SceneType,
    allowed_scenes_text,
    ensure_channel,
    ensure_channel_dm,
    ensure_message_target,
    ensure_scene,
    ensure_sub_channel,
    resolve_scene,
)


def resolve_qq_platform(context: Context | None):
    if not context:
        return None

    try:
        from astrbot.api.event.filter import PlatformAdapterType
    except ImportError:
        PlatformAdapterType = None

    if PlatformAdapterType is not None:
        try:
            platform = context.get_platform(PlatformAdapterType.QQOFFICIAL)
            if platform:
                return platform
        except Exception:
            pass

    for key in (
        "qq_official",
        "qq_official_webhook",
        "qq_restapi",
        "qq_restapi_webhook",
        "qqbot",
    ):
        platform = context.get_platform(key)
        if platform:
            return platform

    manager = getattr(context, "platform_manager", None)
    if manager is None:
        return None
    for inst in manager.get_insts():
        cfg = getattr(inst, "config", {}) or {}
        pid = cfg.get("id", "")
        ptype = cfg.get("type", "")
        if pid in {
            "qq_official",
            "qq_official_webhook",
            "qq_restapi",
            "qq_restapi_webhook",
        } or (
            isinstance(ptype, str)
            and ("qq_official" in ptype or "qq_restapi" in ptype)
        ):
            return inst

    return None


def get_app_credentials(context: Context | None) -> tuple[str | None, str | None]:
    platform = resolve_qq_platform(context)
    if not platform:
        return None, None

    cfg = getattr(platform, "config", {}) or {}
    app_id = (
        getattr(platform, "appid", None)
        or cfg.get("appid")
        or cfg.get("appId")
        or cfg.get("app_id")
    )
    client_secret = (
        getattr(platform, "secret", None)
        or cfg.get("secret")
        or cfg.get("clientSecret")
        or cfg.get("client_secret")
    )
    return (
        str(app_id) if app_id is not None and str(app_id).strip() else None,
        str(client_secret)
        if client_secret is not None and str(client_secret).strip()
        else None,
    )


def get_app_credentials_from_plugin(plugin) -> tuple[str | None, str | None]:
    context = getattr(plugin, "context", None)
    return get_app_credentials(context)


async def get_shared_async_client():
    return await get_async_client()


def get_shared_sync_client():
    return get_sync_client()


def register_external_template_source(
    template_dir: str | Path,
    registry_path: str | Path | None = None,
    source_name: str | None = None,
) -> str:
    return register_template_source(
        template_dir=template_dir,
        registry_path=registry_path,
        source_name=source_name,
    )


def unregister_external_template_source(source_key: str) -> bool:
    return unregister_template_source(source_key)


__all__ = [
    "SceneContext",
    "SceneType",
    "allowed_scenes_text",
    "build_markdown_params",
    "build_meta_line",
    "ensure_channel",
    "ensure_channel_dm",
    "ensure_message_target",
    "ensure_scene",
    "ensure_sub_channel",
    "extract_params",
    "get_app_credentials",
    "get_app_credentials_from_plugin",
    "get_auto_event",
    "get_auto_event_log_group",
    "get_last_message_id",
    "get_shared_async_client",
    "get_shared_sync_client",
    "get_template_body",
    "get_template_entry",
    "get_template_file",
    "get_template_keyboard_id",
    "normalize_keyboard_meta",
    "register_external_template_source",
    "render_template",
    "resolve_qq_platform",
    "resolve_scene",
    "resolve_template_id",
    "send_markdown_template",
    "unregister_external_template_source",
]
