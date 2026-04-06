from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Rep(Base):
    __tablename__ = "reps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    territory_code: Mapped[str] = mapped_column(String(8), index=True)
    weekly_visit_cap: Mapped[int] = mapped_column(Integer, default=10)
    max_new_targets_per_week: Mapped[int] = mapped_column(Integer, default=5)
    travel_friction_score: Mapped[float] = mapped_column(Float, default=0.2)

    commitments: Mapped[list[RepCommitment]] = relationship(back_populates="rep")
    interactions: Mapped[list[InteractionHistory]] = relationship(back_populates="rep")


class HCP(Base):
    __tablename__ = "hcps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(String(255))
    specialty: Mapped[str] = mapped_column(String(128), default="")
    territory_code: Mapped[str] = mapped_column(String(8), index=True)

    prescribing_signals: Mapped[list[PrescribingSignal]] = relationship(back_populates="hcp")
    interactions: Mapped[list[InteractionHistory]] = relationship(back_populates="hcp")


class PrescribingSignal(Base):
    __tablename__ = "prescribing_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hcp_id: Mapped[int] = mapped_column(ForeignKey("hcps.id"), index=True)
    drug_id: Mapped[str] = mapped_column(String(64), index=True)
    signal_date: Mapped[date] = mapped_column(Date, index=True)
    volume: Mapped[float] = mapped_column(Float, default=0.0)

    hcp: Mapped[HCP] = relationship(back_populates="prescribing_signals")


class InteractionHistory(Base):
    __tablename__ = "interaction_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hcp_id: Mapped[int] = mapped_column(ForeignKey("hcps.id"), index=True)
    rep_id: Mapped[int] = mapped_column(ForeignKey("reps.id"), index=True)
    interaction_date: Mapped[date] = mapped_column(Date, index=True)
    interaction_type: Mapped[str] = mapped_column(String(64), default="visit")
    sentiment: Mapped[str] = mapped_column(String(32), default="neutral")
    objection: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    hcp: Mapped[HCP] = relationship(back_populates="interactions")
    rep: Mapped[Rep] = relationship(back_populates="interactions")


class RepCommitment(Base):
    __tablename__ = "rep_commitments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rep_id: Mapped[int] = mapped_column(ForeignKey("reps.id"), index=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    committed_visits: Mapped[int] = mapped_column(Integer, default=0)
    admin_blocks: Mapped[int] = mapped_column(Integer, default=0)

    rep: Mapped[Rep] = relationship(back_populates="commitments")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    rep_code: Mapped[str] = mapped_column(String(32), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
