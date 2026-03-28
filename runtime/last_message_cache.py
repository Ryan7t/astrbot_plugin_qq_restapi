from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class _LastMessageEntry:
    message_id: str
    updated_at: float


_CACHE: Dict[str, _LastMessageEntry] = {}


def set_last_message_id(origin: str | None, message_id: str | None) -> None:
    if not origin or not message_id:
        return
    _CACHE[origin] = _LastMessageEntry(message_id=message_id, updated_at=time.time())


def get_last_message_id(origin: str | None) -> Optional[str]:
    if not origin:
        return None
    entry = _CACHE.get(origin)
    return entry.message_id if entry else None
