from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .models import QQRestAPISQLModel


def get_default_db_path() -> str:
    base_dir = get_astrbot_plugin_data_path()
    return os.path.join(base_dir, "qq_restapi", "qq_restapi.db")


class QQRestAPIDatabase:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or get_default_db_path()
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.DATABASE_URL = f"sqlite+aiosqlite:///{self.db_path}"
        self.engine = create_async_engine(
            self.DATABASE_URL,
            echo=False,
            future=True,
        )
        self.AsyncSessionLocal = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._inited = False

    async def initialize(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(QQRestAPISQLModel.metadata.create_all)
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA cache_size=20000"))
            await conn.execute(text("PRAGMA temp_store=MEMORY"))
            await conn.execute(text("PRAGMA mmap_size=134217728"))
            await conn.execute(text("PRAGMA optimize"))
            await conn.commit()
        self._inited = True

    @asynccontextmanager
    async def get_db(self) -> AsyncGenerator[AsyncSession, None]:
        if not self._inited:
            await self.initialize()
        async with self.AsyncSessionLocal() as session:
            yield session

    async def close(self) -> None:
        await self.engine.dispose()
