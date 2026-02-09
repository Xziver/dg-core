"""SQLAlchemy ORM models for dg-core."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
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


class Player(Base):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)  # "discord", "qq", "web"
    platform_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    api_key_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session_links: Mapped[list[SessionPlayer]] = relationship(back_populates="player")
    patients: Mapped[list[Patient]] = relationship(back_populates="player")

    __table_args__ = (
        Index("ix_player_platform", "platform", "platform_uid", unique=True),
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("preparing", "active", "paused", "ended", name="session_status"),
        default="preparing",
    )
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    created_by: Mapped[str] = mapped_column(String(32), ForeignKey("players.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    player_links: Mapped[list[SessionPlayer]] = relationship(back_populates="session")
    patients: Mapped[list[Patient]] = relationship(back_populates="session")
    ghosts: Mapped[list[Ghost]] = relationship(back_populates="session")
    timeline_events: Mapped[list[TimelineEvent]] = relationship(back_populates="session")
    world_state: Mapped[WorldState | None] = relationship(back_populates="session", uselist=False)


class SessionPlayer(Base):
    __tablename__ = "session_players"

    session_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sessions.id"), primary_key=True
    )
    player_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("players.id"), primary_key=True
    )
    role: Mapped[str] = mapped_column(
        Enum("KP", "PL", name="player_role"), nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped[Session] = relationship(back_populates="player_links")
    player: Mapped[Player] = relationship(back_populates="session_links")


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("players.id"))
    session_id: Mapped[str] = mapped_column(String(32), ForeignKey("sessions.id"))
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    identity: Mapped[str | None] = mapped_column(String(128), nullable=True)
    portrait_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    soul_color: Mapped[str] = mapped_column(String(1), nullable=False)  # C/M/Y/K
    personality_archives_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ideal_projection: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    player: Mapped[Player] = relationship(back_populates="patients")
    session: Mapped[Session] = relationship(back_populates="patients")
    ghost: Mapped[Ghost | None] = relationship(back_populates="patient", uselist=False)

    __table_args__ = (
        Index("ix_patient_session", "session_id"),
    )


class Ghost(Base):
    __tablename__ = "ghosts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("patients.id"), unique=True
    )
    creator_player_id: Mapped[str] = mapped_column(String(32), ForeignKey("players.id"))
    session_id: Mapped[str] = mapped_column(String(32), ForeignKey("sessions.id"))
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    appearance: Mapped[str | None] = mapped_column(Text, nullable=True)
    personality: Mapped[str | None] = mapped_column(Text, nullable=True)
    cmyk_json: Mapped[str] = mapped_column(Text, nullable=False)  # {"c":1,"m":0,"y":0,"k":0}
    hp: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    hp_max: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    patient: Mapped[Patient] = relationship(back_populates="ghost")
    session: Mapped[Session] = relationship(back_populates="ghosts")
    print_abilities: Mapped[list[PrintAbility]] = relationship(back_populates="ghost")
    color_fragments: Mapped[list[ColorFragment]] = relationship(back_populates="holder_ghost")

    __table_args__ = (
        Index("ix_ghost_session", "session_id"),
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


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(32), ForeignKey("sessions.id"))
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
    )


class WorldState(Base):
    __tablename__ = "world_states"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sessions.id"), unique=True
    )
    current_sector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sector_data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    global_flags_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    session: Mapped[Session] = relationship(back_populates="world_state")


class ColorFragment(Base):
    __tablename__ = "color_fragments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(32), ForeignKey("sessions.id"))
    holder_ghost_id: Mapped[str] = mapped_column(String(32), ForeignKey("ghosts.id"))
    color: Mapped[str] = mapped_column(String(1), nullable=False)  # C/M/Y/K
    value: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    holder_ghost: Mapped[Ghost] = relationship(back_populates="color_fragments")

    __table_args__ = (
        Index("ix_fragment_session", "session_id"),
    )
