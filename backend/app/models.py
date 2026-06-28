"""SQLAlchemy ORM models for the Maintenance Hub.

See docs/DESIGN.md section 4 for the conceptual model. The compliance engine
(app.engine) consumes the timing fields here but lives independently so it
stays unit-testable.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# Categories used across the catalog and items.
CATEGORIES = [
    "inspection",
    "emergency_equipment",
    "engine",
    "propeller",
    "rotor",
    "transmission",
    "airframe",
    "avionics",
    "registration",
    "ad",
    "other",
]

COMPONENT_TYPES = [
    "airframe",
    "engine",
    "propeller",
    "main_rotor",
    "tail_rotor",
    "transmission",
    "gearbox",
    "apu",
    "other",
]


class Aircraft(Base):
    __tablename__ = "aircraft"

    id: Mapped[int] = mapped_column(primary_key=True)
    tail_number: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    make: Mapped[Optional[str]] = mapped_column(String(64))
    model: Mapped[Optional[str]] = mapped_column(String(64))
    serial_number: Mapped[Optional[str]] = mapped_column(String(64))
    year: Mapped[Optional[int]] = mapped_column(Integer)
    home_base: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="active")
    notes: Mapped[Optional[str]] = mapped_column(Text)

    components: Mapped[list["Component"]] = relationship(
        back_populates="aircraft", cascade="all, delete-orphan"
    )
    items: Mapped[list["ComplianceItem"]] = relationship(
        back_populates="aircraft", cascade="all, delete-orphan"
    )


class Component(Base):
    __tablename__ = "component"

    id: Mapped[int] = mapped_column(primary_key=True)
    aircraft_id: Mapped[int] = mapped_column(ForeignKey("aircraft.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(16))  # COMPONENT_TYPES
    position: Mapped[Optional[str]] = mapped_column(String(32))  # e.g. "Engine #1"
    make: Mapped[Optional[str]] = mapped_column(String(64))
    model: Mapped[Optional[str]] = mapped_column(String(64))
    serial_number: Mapped[Optional[str]] = mapped_column(String(64))
    current_hours: Mapped[float] = mapped_column(Float, default=0.0)
    current_cycles: Mapped[int] = mapped_column(Integer, default=0)
    hours_as_of: Mapped[Optional[date]] = mapped_column(Date)

    aircraft: Mapped["Aircraft"] = relationship(back_populates="components")
    readings: Mapped[list["HoursReading"]] = relationship(
        back_populates="component", cascade="all, delete-orphan"
    )
    items: Mapped[list["ComplianceItem"]] = relationship(back_populates="component")


class HoursReading(Base):
    """History of hour/cycle readings; feeds the utilisation-rate projection."""

    __tablename__ = "hours_reading"

    id: Mapped[int] = mapped_column(primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("component.id", ondelete="CASCADE"))
    reading_date: Mapped[date] = mapped_column(Date)
    hours: Mapped[float] = mapped_column(Float)
    cycles: Mapped[Optional[int]] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16), default="manual")
    entered_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    component: Mapped["Component"] = relationship(back_populates="readings")


class ItemType(Base):
    """Catalog template of a standard tracked item, with default intervals."""

    __tablename__ = "item_type"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(32))
    reg_reference: Mapped[Optional[str]] = mapped_column(String(32))
    interval_kind: Mapped[str] = mapped_column(String(16))
    default_interval_months: Mapped[Optional[int]] = mapped_column(Integer)
    default_interval_hours: Mapped[Optional[float]] = mapped_column(Float)
    default_interval_cycles: Mapped[Optional[int]] = mapped_column(Integer)
    default_warning_days: Mapped[int] = mapped_column(Integer, default=30)
    applies_to_component_type: Mapped[Optional[str]] = mapped_column(String(16))
    is_required_for_airworthiness: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[Optional[str]] = mapped_column(Text)


class ComplianceItem(Base):
    """A live tracked requirement on a specific aircraft (and maybe component)."""

    __tablename__ = "compliance_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    aircraft_id: Mapped[int] = mapped_column(ForeignKey("aircraft.id", ondelete="CASCADE"))
    component_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("component.id", ondelete="SET NULL")
    )
    item_type_id: Mapped[Optional[int]] = mapped_column(ForeignKey("item_type.id"))

    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(32))
    reg_reference: Mapped[Optional[str]] = mapped_column(String(32))

    interval_kind: Mapped[str] = mapped_column(String(16))
    interval_months: Mapped[Optional[int]] = mapped_column(Integer)
    interval_hours: Mapped[Optional[float]] = mapped_column(Float)
    interval_cycles: Mapped[Optional[int]] = mapped_column(Integer)
    fixed_expiry_date: Mapped[Optional[date]] = mapped_column(Date)

    warning_days: Mapped[int] = mapped_column(Integer, default=30)
    warning_hours: Mapped[Optional[float]] = mapped_column(Float)

    last_done_date: Mapped[Optional[date]] = mapped_column(Date)
    last_done_hours: Mapped[Optional[float]] = mapped_column(Float)
    last_done_cycles: Mapped[Optional[int]] = mapped_column(Integer)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_required_for_airworthiness: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    aircraft: Mapped["Aircraft"] = relationship(back_populates="items")
    component: Mapped[Optional["Component"]] = relationship(back_populates="items")
    events: Mapped[list["ComplianceEvent"]] = relationship(
        back_populates="item", cascade="all, delete-orphan",
        order_by="ComplianceEvent.performed_date.desc()",
    )


class ComplianceEvent(Base):
    """Append-only log of a completion. Advances the parent item's last_done_*."""

    __tablename__ = "compliance_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    compliance_item_id: Mapped[int] = mapped_column(
        ForeignKey("compliance_item.id", ondelete="CASCADE")
    )
    performed_date: Mapped[date] = mapped_column(Date)
    performed_at_hours: Mapped[Optional[float]] = mapped_column(Float)
    performed_at_cycles: Mapped[Optional[int]] = mapped_column(Integer)
    performed_by: Mapped[Optional[str]] = mapped_column(String(64))
    signed_off_by: Mapped[Optional[str]] = mapped_column(String(128))  # A&P/IA + cert #
    vendor: Mapped[Optional[str]] = mapped_column(String(128))
    cost: Mapped[Optional[float]] = mapped_column(Float)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    item: Mapped["ComplianceItem"] = relationship(back_populates="events")
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class Attachment(Base):
    """A document attached to a completion event (work order, 8130, repack card)."""

    __tablename__ = "attachment"

    id: Mapped[int] = mapped_column(primary_key=True)
    compliance_event_id: Mapped[int] = mapped_column(
        ForeignKey("compliance_event.id", ondelete="CASCADE")
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[Optional[str]] = mapped_column(String(128))
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(String(512))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    event: Mapped["ComplianceEvent"] = relationship(back_populates="attachments")
