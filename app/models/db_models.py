"""SQLAlchemy ORM models for dg-core."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    api_key_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String(16), default="user")  # "user", "admin"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    platform_bindings: Mapped[list[PlatformBinding]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    game_links: Mapped[list[GamePlayer]] = relationship(back_populates="user")
    patients: Mapped[list[Patient]] = relationship(back_populates="user")


class PlatformBinding(Base):
    """Links a User to an external platform identity (QQ, Discord, web, etc.)."""

    __tablename__ = "platform_bindings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)  # "qq", "discord", "web"
    platform_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped[User] = relationship(back_populates="platform_bindings")

    __table_args__ = (
        Index("ix_binding_platform", "platform", "platform_uid", unique=True),
        Index("ix_binding_user", "user_id"),
    )


class Game(Base):
    """A complete game instance — top-level container for regions, characters, sessions."""

    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("preparing", "active", "paused", "ended", name="game_status"),
        default="preparing",
    )
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    flags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user_links: Mapped[list[GamePlayer]] = relationship(back_populates="game")
    regions: Mapped[list[Region]] = relationship(back_populates="game")
    patients: Mapped[list[Patient]] = relationship(back_populates="game")
    ghosts: Mapped[list[Ghost]] = relationship(back_populates="game")
    sessions: Mapped[list[Session]] = relationship(back_populates="game")


class GamePlayer(Base):
    """Player participation in a game — role and current location tracking."""

    __tablename__ = "game_players"

    game_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("games.id"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id"), primary_key=True
    )
    role: Mapped[str] = mapped_column(
        Enum("KP", "PL", name="player_role"), nullable=False
    )
    current_region_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("regions.id"), nullable=True
    )
    current_location_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("locations.id"), nullable=True
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    game: Mapped[Game] = relationship(back_populates="user_links")
    user: Mapped[User] = relationship(back_populates="game_links")
    current_region: Mapped[Region | None] = relationship()
    current_location: Mapped[Location | None] = relationship()


class Region(Base):
    """A geographical area within a game (e.g., A/B/C/D districts)."""

    __tablename__ = "regions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    game_id: Mapped[str] = mapped_column(String(32), ForeignKey("games.id"))
    code: Mapped[str] = mapped_column(String(8), nullable=False)  # "A", "B", "C", "D"
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    game: Mapped[Game] = relationship(back_populates="regions")
    locations: Mapped[list[Location]] = relationship(back_populates="region")

    __table_args__ = (
        Index("ix_region_game", "game_id"),
        Index("ix_region_game_code", "game_id", "code", unique=True),
    )


class Location(Base):
    """A specific place within a region (e.g., data ruins, signal tower)."""

    __tablename__ = "locations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    region_id: Mapped[str] = mapped_column(String(32), ForeignKey("regions.id"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)  # Rich text for RAG indexing
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    region: Mapped[Region] = relationship(back_populates="locations")

    __table_args__ = (
        Index("ix_location_region", "region_id"),
    )


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    game_id: Mapped[str] = mapped_column(String(32), ForeignKey("games.id"))
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    identity: Mapped[str | None] = mapped_column(String(128), nullable=True)
    portrait_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    soul_color: Mapped[str] = mapped_column(String(1), nullable=False)  # C/M/Y/K
    personality_archives_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ideal_projection: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped[User] = relationship(back_populates="patients")
    game: Mapped[Game] = relationship(back_populates="patients")
    ghost: Mapped[Ghost | None] = relationship(back_populates="patient", uselist=False)

    __table_args__ = (
        Index("ix_patient_game", "game_id"),
    )


class Ghost(Base):
    __tablename__ = "ghosts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("patients.id"), unique=True
    )
    creator_user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    game_id: Mapped[str] = mapped_column(String(32), ForeignKey("games.id"))
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    appearance: Mapped[str | None] = mapped_column(Text, nullable=True)
    personality: Mapped[str | None] = mapped_column(Text, nullable=True)
    cmyk_json: Mapped[str] = mapped_column(Text, nullable=False)  # {"C":1,"M":0,"Y":0,"K":0}
    hp: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    hp_max: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    patient: Mapped[Patient] = relationship(back_populates="ghost")
    game: Mapped[Game] = relationship(back_populates="ghosts")
    print_abilities: Mapped[list[PrintAbility]] = relationship(back_populates="ghost")
    color_fragments: Mapped[list[ColorFragment]] = relationship(back_populates="holder_ghost")

    __table_args__ = (
        Index("ix_ghost_game", "game_id"),
    )


class PrintAbility(Base):
    __tablename__ = "print_abilities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    ghost_id: Mapped[str] = mapped_column(String(32), ForeignKey("ghosts.id"))
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(String(1), nullable=False)  # C/M/Y/K
    ability_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    ghost: Mapped[Ghost] = relationship(back_populates="print_abilities")


class Session(Base):
    """A single play session — from /session start to /session end."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    game_id: Mapped[str] = mapped_column(String(32), ForeignKey("games.id"))
    region_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("regions.id"), nullable=True
    )
    started_by: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(
        Enum("active", "ended", name="session_status"),
        default="active",
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    game: Mapped[Game] = relationship(back_populates="sessions")
    region: Mapped[Region | None] = relationship()
    timeline_events: Mapped[list[TimelineEvent]] = relationship(back_populates="session")

    __table_args__ = (
        Index("ix_session_game", "game_id"),
    )


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(32), ForeignKey("sessions.id"))
    game_id: Mapped[str] = mapped_column(String(32), ForeignKey("games.id"))
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped[Session] = relationship(back_populates="timeline_events")

    __table_args__ = (
        Index("ix_timeline_session_seq", "session_id", "seq"),
        Index("ix_timeline_game", "game_id"),
    )


class ColorFragment(Base):
    __tablename__ = "color_fragments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    game_id: Mapped[str] = mapped_column(String(32), ForeignKey("games.id"))
    holder_ghost_id: Mapped[str] = mapped_column(String(32), ForeignKey("ghosts.id"))
    color: Mapped[str] = mapped_column(String(1), nullable=False)  # C/M/Y/K
    value: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    holder_ghost: Mapped[Ghost] = relationship(back_populates="color_fragments")

    __table_args__ = (
        Index("ix_fragment_game", "game_id"),
    )
