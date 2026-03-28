from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from astrbot import logger

_CORE_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_CORE_REGISTRY_NAME = "qq_restapi_core"

_SOURCE_REGISTRATIONS: dict[str, dict[str, Any]] = {}
_SOURCE_CACHE: dict[str, dict[str, Any]] = {}
_REGISTRY_CACHE: dict[str, Any] | None = None
_REGISTRY_SIGNATURE: tuple[tuple[str, float | None], ...] | None = None


def _load_yaml(path: Path) -> dict[str, Any] | None:
    try:
        import yaml  # type: ignore
    except Exception:
        logger.warning("模板注册表加载失败：未安装 PyYAML（需要解析 %s）", path)
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("模板注册表加载失败：%s", exc)
        return None


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("模板注册表加载失败：%s", exc)
        return None


def _resolve_registry_path(
    template_dir: Path,
    registry_path: str | Path | None,
) -> Path | None:
    if registry_path is not None:
        path = Path(registry_path)
        if not path.is_absolute():
            path = template_dir / path
        return path.resolve()

    yaml_path = template_dir / "registry.yaml"
    if yaml_path.exists():
        return yaml_path.resolve()
    yml_path = template_dir / "registry.yml"
    if yml_path.exists():
        return yml_path.resolve()
    json_path = template_dir / "registry.json"
    if json_path.exists():
        return json_path.resolve()
    return None


def _registry_key(template_dir: Path, registry_path: Path | None) -> str:
    return f"{template_dir.as_posix()}::{registry_path.as_posix() if registry_path else ''}"


def _ensure_core_source() -> None:
    register_template_source(
        template_dir=_CORE_TEMPLATE_DIR,
        source_name=_CORE_REGISTRY_NAME,
    )


def _invalidate_registry_cache() -> None:
    global _REGISTRY_CACHE, _REGISTRY_SIGNATURE
    _REGISTRY_CACHE = None
    _REGISTRY_SIGNATURE = None


def register_template_source(
    template_dir: str | Path,
    registry_path: str | Path | None = None,
    source_name: str | None = None,
) -> str:
    root = Path(template_dir).resolve()
    resolved_registry = _resolve_registry_path(root, registry_path)
    key = _registry_key(root, resolved_registry)

    next_source = {
        "key": key,
        "name": source_name or key,
        "template_dir": root,
        "registry_path": resolved_registry,
    }
    existing = _SOURCE_REGISTRATIONS.get(key)
    if existing == next_source:
        return key

    _SOURCE_REGISTRATIONS[key] = next_source
    _SOURCE_CACHE.pop(key, None)
    _invalidate_registry_cache()
    return key


def unregister_template_source(source_key: str) -> bool:
    removed = _SOURCE_REGISTRATIONS.pop(source_key, None)
    _SOURCE_CACHE.pop(source_key, None)
    if removed:
        _invalidate_registry_cache()
        return True
    return False


def list_template_sources() -> list[dict[str, str]]:
    _ensure_core_source()
    sources: list[dict[str, str]] = []
    for source in _SOURCE_REGISTRATIONS.values():
        registry_path = source.get("registry_path")
        template_dir = source.get("template_dir")
        sources.append(
            {
                "key": source["key"],
                "name": str(source.get("name") or source["key"]),
                "template_dir": str(template_dir) if template_dir else "",
                "registry_path": str(registry_path) if registry_path else "",
            }
        )
    return sources


def _source_mtime(source: dict[str, Any]) -> float | None:
    path: Path | None = source.get("registry_path")
    if not path or not path.exists():
        return None
    try:
        return path.stat().st_mtime
    except Exception:
        return None


def _load_source_registry(source: dict[str, Any], force: bool = False) -> dict[str, Any]:
    key = source["key"]
    path: Path | None = source.get("registry_path")
    mtime = _source_mtime(source)
    cached = _SOURCE_CACHE.get(key)
    if (
        not force
        and cached is not None
        and cached.get("mtime") == mtime
        and isinstance(cached.get("data"), dict)
    ):
        return cached["data"]

    data: dict[str, Any] = {}
    if path and path.exists():
        if path.suffix.lower() in {".yaml", ".yml"}:
            loaded = _load_yaml(path)
        else:
            loaded = _load_json(path)
        if isinstance(loaded, dict):
            data = loaded

    _SOURCE_CACHE[key] = {"mtime": mtime, "data": data}
    return data


def _merge_templates(
    merged_templates: dict[str, Any],
    source_templates: dict[str, Any],
    template_dir: Path,
) -> None:
    for name, entry in source_templates.items():
        if not isinstance(entry, dict):
            continue
        copied = dict(entry)
        copied["__template_root__"] = str(template_dir)
        merged_templates[name] = copied


def _merge_named_dict(
    merged: dict[str, Any],
    source: dict[str, Any],
) -> None:
    for key, value in source.items():
        if isinstance(value, dict):
            merged[key] = dict(value)


def _build_signature() -> tuple[tuple[str, float | None], ...]:
    return tuple(
        (key, _source_mtime(source))
        for key, source in _SOURCE_REGISTRATIONS.items()
    )


def load_registry(force: bool = False) -> dict[str, Any]:
    global _REGISTRY_CACHE, _REGISTRY_SIGNATURE
    _ensure_core_source()
    signature = _build_signature()

    if (
        not force
        and _REGISTRY_CACHE is not None
        and _REGISTRY_SIGNATURE == signature
    ):
        return _REGISTRY_CACHE

    merged_templates: dict[str, Any] = {}
    merged_auto_events: dict[str, Any] = {}
    merged_log_groups: dict[str, Any] = {}

    for source in _SOURCE_REGISTRATIONS.values():
        root = source.get("template_dir")
        if not isinstance(root, Path):
            continue
        data = _load_source_registry(source, force=force)
        templates = data.get("templates")
        if isinstance(templates, dict):
            _merge_templates(merged_templates, templates, root)
        auto_events = data.get("auto_events")
        if isinstance(auto_events, dict):
            _merge_named_dict(merged_auto_events, auto_events)
        groups = data.get("auto_event_log_groups")
        if isinstance(groups, dict):
            _merge_named_dict(merged_log_groups, groups)

    _REGISTRY_CACHE = {
        "templates": merged_templates,
        "auto_events": merged_auto_events,
        "auto_event_log_groups": merged_log_groups,
    }
    _REGISTRY_SIGNATURE = signature
    return _REGISTRY_CACHE


def reload_registry() -> dict[str, Any]:
    return load_registry(force=True)


def get_registry() -> dict[str, Any]:
    return load_registry()


def get_templates() -> dict[str, Any]:
    registry = get_registry()
    templates = registry.get("templates")
    return templates if isinstance(templates, dict) else {}


def get_template_entry(name_or_id: str | None) -> dict[str, Any] | None:
    if not name_or_id:
        return None
    templates = get_templates()
    if name_or_id in templates:
        entry = templates.get(name_or_id)
        return entry if isinstance(entry, dict) else None
    for entry in templates.values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("id", "")).strip() == str(name_or_id).strip():
            return entry
    return None


def resolve_template_id(name_or_id: str | None) -> str | None:
    if not name_or_id:
        return None
    entry = get_template_entry(name_or_id)
    if entry and entry.get("id"):
        return str(entry["id"])
    return str(name_or_id)


def get_template_file_info(name_or_id: str | None) -> tuple[str | None, Path | None]:
    entry = get_template_entry(name_or_id)
    if not entry:
        return None, None
    file_name = entry.get("file")
    root = entry.get("__template_root__")
    file_str = str(file_name) if file_name else None
    root_path = Path(root) if isinstance(root, str) and root else None
    return file_str, root_path


def get_template_file(name_or_id: str | None) -> str | None:
    file_name, _ = get_template_file_info(name_or_id)
    return file_name


def get_template_keyboard_id(name_or_id: str | None) -> str | None:
    entry = get_template_entry(name_or_id)
    if not entry:
        return None
    keyboard_id = entry.get("keyboard_id")
    return str(keyboard_id) if keyboard_id else None


def get_template_roots() -> list[Path]:
    _ensure_core_source()
    roots: list[Path] = []
    seen: set[str] = set()
    for source in _SOURCE_REGISTRATIONS.values():
        root = source.get("template_dir")
        if not isinstance(root, Path):
            continue
        key = root.as_posix()
        if key in seen:
            continue
        seen.add(key)
        roots.append(root)
    return roots


def get_auto_event(key: str) -> dict[str, Any] | None:
    registry = get_registry()
    auto_events = registry.get("auto_events")
    if not isinstance(auto_events, dict):
        return None
    cfg = auto_events.get(key)
    return cfg if isinstance(cfg, dict) else None


def get_auto_event_log_group(group: str) -> dict[str, Any] | None:
    registry = get_registry()
    groups = registry.get("auto_event_log_groups")
    if not isinstance(groups, dict):
        return None
    cfg = groups.get(group)
    return cfg if isinstance(cfg, dict) else None
