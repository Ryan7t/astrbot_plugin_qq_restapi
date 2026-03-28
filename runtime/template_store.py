from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Mapping, Sequence

_DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_TEMPLATE_CACHE: dict[str, str] = {}
_VAR_PATTERN = re.compile(r"{{\s*\.?([a-zA-Z0-9_]+)\s*}}")


def get_template_body(template_id: str) -> str | None:
    if not template_id:
        return None
    if template_id in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[template_id]

    resolved_id = template_id
    template_root: Path | None = None
    try:
        from .template_registry import (
            get_template_file_info,
            get_template_roots,
            resolve_template_id,
        )
        resolved_id = resolve_template_id(template_id) or template_id
        if resolved_id in _TEMPLATE_CACHE:
            return _TEMPLATE_CACHE[resolved_id]
        file_name, template_root = get_template_file_info(template_id)
        if not file_name:
            file_name, template_root = get_template_file_info(resolved_id)
        template_roots = get_template_roots()
    except Exception:
        file_name = None
        template_roots = [_DEFAULT_TEMPLATE_DIR]

    if file_name:
        path = Path(file_name)
        if not path.is_absolute():
            if template_root:
                path = template_root / file_name
            else:
                path = _DEFAULT_TEMPLATE_DIR / file_name
    else:
        path = None
        for root in template_roots:
            candidate = root / f"{resolved_id}.md"
            if candidate.exists():
                path = candidate
                break

    if path is None or not path.exists():
        return None
    body = path.read_text(encoding="utf-8")
    _TEMPLATE_CACHE[template_id] = body
    _TEMPLATE_CACHE[resolved_id] = body
    return body


def extract_params(params: Sequence[dict] | None) -> tuple[list[tuple[str, str]], dict[str, str]]:
    pairs: list[tuple[str, str]] = []
    mapping: dict[str, str] = {}
    if not params:
        return pairs, mapping
    for item in params:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        if not key:
            continue
        values = item.get("values")
        if isinstance(values, list):
            value = values[0] if values else ""
        else:
            value = values if values is not None else ""
        value_str = str(value)
        pairs.append((key, value_str))
        mapping[key] = value_str
    return pairs, mapping


def render_template(body: str, params: Mapping[str, str]) -> str:
    if not body:
        return ""

    def replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        return params.get(key, match.group(0))

    return _VAR_PATTERN.sub(replacer, body)


def normalize_keyboard_meta(keyboard_id: object | None) -> str | None:
    if not keyboard_id:
        return None
    if isinstance(keyboard_id, str):
        return keyboard_id
    if isinstance(keyboard_id, dict):
        for key in ("id", "keyboard_id", "template_id"):
            value = keyboard_id.get(key)
            if value:
                return str(value)
        return "custom"
    return str(keyboard_id)


def build_meta_line(
    template_id: str,
    param_pairs: Iterable[tuple[str, str]],
    keyboard_meta: str | None = None,
) -> str:
    parts = [f"template_id={template_id}"]
    if keyboard_meta:
        parts.append(f"keyboard_id={keyboard_meta}")
    params_text = ", ".join(f"{key}={value}" for key, value in param_pairs)
    if params_text:
        parts.append(f"params={params_text}")
    return "【模板消息】" + "; ".join(parts)
