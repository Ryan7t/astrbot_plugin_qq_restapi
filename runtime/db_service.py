from __future__ import annotations

from .context import get_plugin_db
from ..db import QQRestAPIService

_SERVICE: QQRestAPIService | None = None


def get_db_service() -> QQRestAPIService | None:
    global _SERVICE
    db = get_plugin_db()
    if db is None:
        return None
    if _SERVICE is None or _SERVICE.db is not db:
        _SERVICE = QQRestAPIService(db)
    return _SERVICE
