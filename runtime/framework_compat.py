"""Feature-based AstrBot compatibility checks for plugin startup."""

from __future__ import annotations

from importlib import import_module
from typing import Final


MIN_ASTRBOT_VERSION: Final = "4.26.0"

_REQUIRED_FRAMEWORK_FEATURES: Final = (
    ("astrbot.core.utils.media_utils", "MediaResolver"),
    ("astrbot.core.platform.webhook_server", "FastAPIWebhookServer"),
)


def _compatibility_error_message(feature_name: str, detail: str) -> str:
    return (
        f"QQ REST API 适配器需要完整安装的 AstrBot >= {MIN_ASTRBOT_VERSION}；"
        f"当前缺少框架能力 {feature_name}。"
        "如果管理面板显示的 AstrBot 版本已达到要求，通常表示升级残留或不同版本的框架文件发生混装。"
        "请先通过 AstrBot 官方升级或重装方式修复框架，再重新安装本插件；"
        "本插件不会修改 AstrBot 框架代码。"
        f"原始错误：{detail}"
    )


def ensure_supported_astrbot() -> None:
    """Verify the framework capabilities required by both plugin adapters.

    Feature checks are used instead of parsing a framework version string so a
    partially upgraded AstrBot installation is reported as incompatible too.
    """

    for module_name, attribute_name in _REQUIRED_FRAMEWORK_FEATURES:
        feature_name = f"{module_name}.{attribute_name}"
        try:
            module = import_module(module_name)
        except ImportError as exc:
            raise RuntimeError(
                _compatibility_error_message(feature_name, str(exc))
            ) from exc

        if getattr(module, attribute_name, None) is None:
            raise RuntimeError(
                _compatibility_error_message(
                    feature_name,
                    f"模块 {module_name} 未提供 {attribute_name}",
                )
            )
