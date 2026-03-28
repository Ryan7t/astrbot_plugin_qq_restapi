from __future__ import annotations

from sqlalchemy import Column, Index, Integer, text
from sqlalchemy import MetaData
from sqlmodel import Field, SQLModel


class QQRestAPISQLModel(SQLModel):
    metadata = MetaData()


class UserIdentity(QQRestAPISQLModel, table=True):
    __tablename__ = "user_identity"

    union_openid: str = Field(primary_key=True)
    qq_number: str | None = Field(default=None)
    avatar: str | None = Field(default=None)
    nickname: str | None = Field(default=None)
    created_at: int = Field(
        sa_column=Column(
            Integer,
            nullable=False,
            server_default=text("(strftime('%s','now'))"),
        ),
    )
    last_seen_at: int | None = Field(default=None)


class UserScene(QQRestAPISQLModel, table=True):
    __tablename__ = "user_scene"

    scene_id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    scene_type: str = Field(nullable=False)
    union_openid: str | None = Field(
        default=None,
        foreign_key="user_identity.union_openid",
    )
    raw_openid: str = Field(nullable=False)
    group_id: str | None = Field(default=None)
    guild_id: str | None = Field(default=None)
    channel_id: str | None = Field(default=None)
    dm_id: str | None = Field(default=None)
    source_guild_id: str | None = Field(default=None)
    source_channel_id: str | None = Field(default=None)
    source_updated_at: int | None = Field(default=None)
    username: str | None = Field(default=None)
    avatar: str | None = Field(default=None)
    nick: str | None = Field(default=None)
    bot: int | None = Field(default=None)
    union_user_account: str | None = Field(default=None)
    roles_json: str | None = Field(default=None)
    first_seen_at: int = Field(
        sa_column=Column(
            Integer,
            nullable=False,
            server_default=text("(strftime('%s','now'))"),
        ),
    )
    last_seen_at: int = Field(
        sa_column=Column(
            Integer,
            nullable=False,
            server_default=text("(strftime('%s','now'))"),
        ),
    )
    last_event_type: str | None = Field(default=None)

    __table_args__ = (
        Index(
            "uq_user_scene_c2c",
            "scene_type",
            "raw_openid",
            unique=True,
            sqlite_where=text("scene_type='c2c'"),
        ),
        Index(
            "uq_user_scene_group",
            "scene_type",
            "raw_openid",
            "group_id",
            unique=True,
            sqlite_where=text("scene_type='group'"),
        ),
        Index(
            "uq_user_scene_channel",
            "scene_type",
            "raw_openid",
            "guild_id",
            "channel_id",
            unique=True,
            sqlite_where=text("scene_type='channel'"),
        ),
        Index(
            "uq_user_scene_channel_dm",
            "scene_type",
            "raw_openid",
            "guild_id",
            unique=True,
            sqlite_where=text("scene_type='channel_dm'"),
        ),
        Index("idx_user_scene_union", "union_openid"),
        Index("idx_user_scene_group", "group_id"),
        Index("idx_user_scene_guild", "guild_id"),
        Index("idx_user_scene_channel", "channel_id"),
    )


class Guild(QQRestAPISQLModel, table=True):
    __tablename__ = "guild"

    guild_id: str = Field(primary_key=True)
    name: str | None = Field(default=None)
    icon: str | None = Field(default=None)
    owner_id: str | None = Field(default=None)
    owner: int | None = Field(default=None)
    member_count: int | None = Field(default=None)
    max_members: int | None = Field(default=None)
    description: str | None = Field(default=None)
    joined_at: int | None = Field(default=None)
    config_json: str | None = Field(default=None)
    last_seen_at: int | None = Field(default=None)


class Channel(QQRestAPISQLModel, table=True):
    __tablename__ = "channel"

    channel_id: str = Field(primary_key=True)
    guild_id: str = Field(nullable=False, foreign_key="guild.guild_id")
    name: str | None = Field(default=None)
    type: int | None = Field(default=None)
    sub_type: int | None = Field(default=None)
    position: int | None = Field(default=None)
    parent_id: str | None = Field(default=None)
    owner_id: str | None = Field(default=None)
    private_type: int | None = Field(default=None)
    speak_permission: int | None = Field(default=None)
    application_id: str | None = Field(default=None)
    permissions: str | None = Field(default=None)
    config_json: str | None = Field(default=None)
    last_seen_at: int | None = Field(default=None)

    __table_args__ = (Index("idx_channel_guild", "guild_id"),)


class EventLog(QQRestAPISQLModel, table=True):
    __tablename__ = "event_log"

    log_id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    log_level: str = Field(nullable=False)
    event_kind: str = Field(nullable=False)
    event_type: str | None = Field(default=None)
    scene_type: str | None = Field(default=None)
    union_openid: str | None = Field(default=None)
    raw_openid: str | None = Field(default=None)
    group_id: str | None = Field(default=None)
    guild_id: str | None = Field(default=None)
    channel_id: str | None = Field(default=None)
    message_id: str | None = Field(default=None)
    event_id: str | None = Field(default=None)
    payload_json: str | None = Field(default=None)
    created_at: int = Field(
        sa_column=Column(
            Integer,
            nullable=False,
            server_default=text("(strftime('%s','now'))"),
        ),
    )

    __table_args__ = (
        Index("idx_event_log_time", "created_at"),
        Index("idx_event_log_type", "event_type"),
        Index("idx_event_log_scene", "scene_type"),
        Index("idx_event_log_guild", "guild_id"),
        Index("idx_event_log_union", "union_openid"),
    )

