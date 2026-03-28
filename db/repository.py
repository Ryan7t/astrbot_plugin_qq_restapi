from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from .database import QQRestAPIDatabase
from .models import Channel, EventLog, Guild, UserIdentity, UserScene

TxResult = TypeVar("TxResult")


class QQRestAPIRepository:
    def __init__(self, db: QQRestAPIDatabase) -> None:
        self.db = db

    async def _run_in_session(
        self,
        session: AsyncSession | None,
        fn: Callable[[AsyncSession], Awaitable[TxResult]],
    ) -> TxResult:
        if session is not None:
            return await fn(session)
        async with self.db.get_db() as session:
            async with session.begin():
                return await fn(session)

    @staticmethod
    def _apply_updates(model, **updates) -> None:
        for field, value in updates.items():
            if value is not None:
                setattr(model, field, value)

    async def get_user_identity(
        self,
        union_openid: str,
        *,
        session: AsyncSession | None = None,
    ) -> UserIdentity | None:
        async def _op(db_session: AsyncSession):
            return await db_session.get(UserIdentity, union_openid)

        return await self._run_in_session(session, _op)

    async def upsert_user_identity(
        self,
        *,
        union_openid: str,
        qq_number: str | None = None,
        avatar: str | None = None,
        nickname: str | None = None,
        last_seen_at: int | None = None,
        session: AsyncSession | None = None,
    ) -> UserIdentity:
        async def _op(db_session: AsyncSession):
            record = await db_session.get(UserIdentity, union_openid)
            if not record:
                record = UserIdentity(
                    union_openid=union_openid,
                    qq_number=qq_number,
                    avatar=avatar,
                    nickname=nickname,
                    last_seen_at=last_seen_at,
                )
                db_session.add(record)
            else:
                self._apply_updates(
                    record,
                    qq_number=qq_number,
                    avatar=avatar,
                    nickname=nickname,
                )
                if last_seen_at is not None:
                    record.last_seen_at = last_seen_at
            await db_session.flush()
            await db_session.refresh(record)
            return record

        return await self._run_in_session(session, _op)

    async def get_user_scene(
        self,
        *,
        scene_type: str,
        raw_openid: str,
        group_id: str | None = None,
        guild_id: str | None = None,
        channel_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> UserScene | None:
        async def _op(db_session: AsyncSession):
            query = select(UserScene).where(
                UserScene.scene_type == scene_type,
                UserScene.raw_openid == raw_openid,
            )
            if scene_type == "group":
                query = query.where(UserScene.group_id == group_id)
            elif scene_type == "channel":
                query = query.where(
                    UserScene.guild_id == guild_id,
                    UserScene.channel_id == channel_id,
                )
            elif scene_type == "channel_dm":
                query = query.where(UserScene.guild_id == guild_id)
            result = await db_session.execute(query)
            return result.scalar_one_or_none()

        return await self._run_in_session(session, _op)

    async def list_user_scenes_by_union(
        self,
        union_openid: str,
        *,
        scene_type: str | None = None,
        session: AsyncSession | None = None,
    ) -> list[UserScene]:
        async def _op(db_session: AsyncSession):
            query = select(UserScene).where(UserScene.union_openid == union_openid)
            if scene_type:
                query = query.where(UserScene.scene_type == scene_type)
            result = await db_session.execute(query)
            return list(result.scalars().all())

        return await self._run_in_session(session, _op)

    async def upsert_user_scene(
        self,
        *,
        scene_type: str,
        raw_openid: str,
        union_openid: str | None = None,
        group_id: str | None = None,
        guild_id: str | None = None,
        channel_id: str | None = None,
        dm_id: str | None = None,
        source_guild_id: str | None = None,
        source_channel_id: str | None = None,
        source_updated_at: int | None = None,
        username: str | None = None,
        avatar: str | None = None,
        nick: str | None = None,
        bot: int | None = None,
        union_user_account: str | None = None,
        roles_json: str | None = None,
        last_seen_at: int | None = None,
        last_event_type: str | None = None,
        session: AsyncSession | None = None,
    ) -> UserScene:
        async def _op(db_session: AsyncSession):
            record = await self.get_user_scene(
                scene_type=scene_type,
                raw_openid=raw_openid,
                group_id=group_id,
                guild_id=guild_id,
                channel_id=channel_id,
                session=db_session,
            )
            if not record:
                record = UserScene(
                    scene_type=scene_type,
                    raw_openid=raw_openid,
                    union_openid=union_openid,
                    group_id=group_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    dm_id=dm_id,
                    source_guild_id=source_guild_id,
                    source_channel_id=source_channel_id,
                    source_updated_at=source_updated_at,
                    username=username,
                    avatar=avatar,
                    nick=nick,
                    bot=bot,
                    union_user_account=union_user_account,
                    roles_json=roles_json,
                    last_event_type=last_event_type,
                )
                if last_seen_at is not None:
                    record.last_seen_at = last_seen_at
                db_session.add(record)
            else:
                self._apply_updates(
                    record,
                    union_openid=union_openid,
                    group_id=group_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    dm_id=dm_id,
                    username=username,
                    avatar=avatar,
                    nick=nick,
                    bot=bot,
                    union_user_account=union_user_account,
                    roles_json=roles_json,
                    last_event_type=last_event_type,
                )
                if source_guild_id is not None and source_guild_id != record.source_guild_id:
                    record.source_guild_id = source_guild_id
                    record.source_updated_at = source_updated_at or record.source_updated_at
                if source_channel_id is not None and source_channel_id != record.source_channel_id:
                    record.source_channel_id = source_channel_id
                    record.source_updated_at = source_updated_at or record.source_updated_at
                if last_seen_at is not None:
                    record.last_seen_at = last_seen_at
            await db_session.flush()
            await db_session.refresh(record)
            return record

        return await self._run_in_session(session, _op)

    async def get_guild(
        self,
        guild_id: str,
        *,
        session: AsyncSession | None = None,
    ) -> Guild | None:
        async def _op(db_session: AsyncSession):
            return await db_session.get(Guild, guild_id)

        return await self._run_in_session(session, _op)

    async def upsert_guild(
        self,
        *,
        guild_id: str,
        name: str | None = None,
        icon: str | None = None,
        owner_id: str | None = None,
        owner: int | None = None,
        member_count: int | None = None,
        max_members: int | None = None,
        description: str | None = None,
        joined_at: int | None = None,
        config_json: str | None = None,
        last_seen_at: int | None = None,
        session: AsyncSession | None = None,
    ) -> Guild:
        async def _op(db_session: AsyncSession):
            record = await db_session.get(Guild, guild_id)
            if not record:
                record = Guild(
                    guild_id=guild_id,
                    name=name,
                    icon=icon,
                    owner_id=owner_id,
                    owner=owner,
                    member_count=member_count,
                    max_members=max_members,
                    description=description,
                    joined_at=joined_at,
                    config_json=config_json,
                    last_seen_at=last_seen_at,
                )
                db_session.add(record)
            else:
                self._apply_updates(
                    record,
                    name=name,
                    icon=icon,
                    owner_id=owner_id,
                    owner=owner,
                    member_count=member_count,
                    max_members=max_members,
                    description=description,
                    joined_at=joined_at,
                    config_json=config_json,
                )
                if last_seen_at is not None:
                    record.last_seen_at = last_seen_at
            await db_session.flush()
            await db_session.refresh(record)
            return record

        return await self._run_in_session(session, _op)

    async def get_channel(
        self,
        channel_id: str,
        *,
        session: AsyncSession | None = None,
    ) -> Channel | None:
        async def _op(db_session: AsyncSession):
            return await db_session.get(Channel, channel_id)

        return await self._run_in_session(session, _op)

    async def list_channels_by_guild(
        self,
        guild_id: str,
        *,
        session: AsyncSession | None = None,
    ) -> list[Channel]:
        async def _op(db_session: AsyncSession):
            result = await db_session.execute(
                select(Channel).where(Channel.guild_id == guild_id),
            )
            return list(result.scalars().all())

        return await self._run_in_session(session, _op)

    async def upsert_channel(
        self,
        *,
        channel_id: str,
        guild_id: str,
        name: str | None = None,
        type: int | None = None,
        sub_type: int | None = None,
        position: int | None = None,
        parent_id: str | None = None,
        owner_id: str | None = None,
        private_type: int | None = None,
        speak_permission: int | None = None,
        application_id: str | None = None,
        permissions: str | None = None,
        config_json: str | None = None,
        last_seen_at: int | None = None,
        session: AsyncSession | None = None,
    ) -> Channel:
        async def _op(db_session: AsyncSession):
            record = await db_session.get(Channel, channel_id)
            if not record:
                record = Channel(
                    channel_id=channel_id,
                    guild_id=guild_id,
                    name=name,
                    type=type,
                    sub_type=sub_type,
                    position=position,
                    parent_id=parent_id,
                    owner_id=owner_id,
                    private_type=private_type,
                    speak_permission=speak_permission,
                    application_id=application_id,
                    permissions=permissions,
                    config_json=config_json,
                    last_seen_at=last_seen_at,
                )
                db_session.add(record)
            else:
                self._apply_updates(
                    record,
                    guild_id=guild_id,
                    name=name,
                    type=type,
                    sub_type=sub_type,
                    position=position,
                    parent_id=parent_id,
                    owner_id=owner_id,
                    private_type=private_type,
                    speak_permission=speak_permission,
                    application_id=application_id,
                    permissions=permissions,
                    config_json=config_json,
                )
                if last_seen_at is not None:
                    record.last_seen_at = last_seen_at
            await db_session.flush()
            await db_session.refresh(record)
            return record

        return await self._run_in_session(session, _op)

    async def insert_event_log(
        self,
        *,
        log_level: str,
        event_kind: str,
        event_type: str | None = None,
        scene_type: str | None = None,
        union_openid: str | None = None,
        raw_openid: str | None = None,
        group_id: str | None = None,
        guild_id: str | None = None,
        channel_id: str | None = None,
        message_id: str | None = None,
        event_id: str | None = None,
        payload_json: str | None = None,
        created_at: int | None = None,
        session: AsyncSession | None = None,
    ) -> EventLog:
        async def _op(db_session: AsyncSession):
            record = EventLog(
                log_level=log_level,
                event_kind=event_kind,
                event_type=event_type,
                scene_type=scene_type,
                union_openid=union_openid,
                raw_openid=raw_openid,
                group_id=group_id,
                guild_id=guild_id,
                channel_id=channel_id,
                message_id=message_id,
                event_id=event_id,
                payload_json=payload_json,
                created_at=created_at,
            )
            db_session.add(record)
            await db_session.flush()
            await db_session.refresh(record)
            return record

        return await self._run_in_session(session, _op)

    async def list_event_logs(
        self,
        *,
        limit: int = 100,
        event_kind: str | None = None,
        event_type: str | None = None,
        scene_type: str | None = None,
        guild_id: str | None = None,
        union_openid: str | None = None,
        session: AsyncSession | None = None,
    ) -> list[EventLog]:
        async def _op(db_session: AsyncSession):
            query = select(EventLog)
            if event_kind:
                query = query.where(EventLog.event_kind == event_kind)
            if event_type:
                query = query.where(EventLog.event_type == event_type)
            if scene_type:
                query = query.where(EventLog.scene_type == scene_type)
            if guild_id:
                query = query.where(EventLog.guild_id == guild_id)
            if union_openid:
                query = query.where(EventLog.union_openid == union_openid)
            query = query.order_by(EventLog.created_at.desc()).limit(limit)
            result = await db_session.execute(query)
            return list(result.scalars().all())

        return await self._run_in_session(session, _op)
