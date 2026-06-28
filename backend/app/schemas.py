"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Aircraft ---------------------------------------------------------------


class AircraftIn(BaseModel):
    tail_number: str
    make: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    year: Optional[int] = None
    home_base: Optional[str] = None
    status: str = "active"
    notes: Optional[str] = None


class AircraftOut(ORMModel):
    id: int
    tail_number: str
    make: Optional[str]
    model: Optional[str]
    serial_number: Optional[str]
    year: Optional[int]
    home_base: Optional[str]
    status: str
    notes: Optional[str]


# --- Component --------------------------------------------------------------


class ComponentIn(BaseModel):
    type: str
    position: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    current_hours: float = 0.0
    current_cycles: int = 0


class ComponentOut(ORMModel):
    id: int
    aircraft_id: int
    type: str
    position: Optional[str]
    make: Optional[str]
    model: Optional[str]
    serial_number: Optional[str]
    current_hours: float
    current_cycles: int
    hours_as_of: Optional[date]


class HoursIn(BaseModel):
    hours: float
    cycles: Optional[int] = None
    reading_date: Optional[date] = None
    entered_by: Optional[str] = None


# --- Compliance items -------------------------------------------------------


class ComplianceItemIn(BaseModel):
    component_id: Optional[int] = None
    item_type_id: Optional[int] = None
    name: str
    category: str
    reg_reference: Optional[str] = None
    interval_kind: str
    interval_months: Optional[int] = None
    interval_hours: Optional[float] = None
    interval_cycles: Optional[int] = None
    fixed_expiry_date: Optional[date] = None
    warning_days: int = 30
    warning_hours: Optional[float] = None
    last_done_date: Optional[date] = None
    last_done_hours: Optional[float] = None
    last_done_cycles: Optional[int] = None
    is_active: bool = True
    is_required_for_airworthiness: bool = False
    notes: Optional[str] = None


class ComplianceItemUpdate(BaseModel):
    name: Optional[str] = None
    interval_kind: Optional[str] = None
    interval_months: Optional[int] = None
    interval_hours: Optional[float] = None
    interval_cycles: Optional[int] = None
    fixed_expiry_date: Optional[date] = None
    warning_days: Optional[int] = None
    warning_hours: Optional[float] = None
    last_done_date: Optional[date] = None
    last_done_hours: Optional[float] = None
    last_done_cycles: Optional[int] = None
    is_active: Optional[bool] = None
    is_required_for_airworthiness: Optional[bool] = None
    notes: Optional[str] = None


class EventIn(BaseModel):
    performed_date: date
    performed_at_hours: Optional[float] = None
    performed_at_cycles: Optional[int] = None
    performed_by: Optional[str] = None
    signed_off_by: Optional[str] = None
    vendor: Optional[str] = None
    cost: Optional[float] = None
    notes: Optional[str] = None
    # If true, also bump the component's current hours/cycles to match.
    update_component_hours: bool = True


class EventOut(ORMModel):
    id: int
    compliance_item_id: int
    performed_date: date
    performed_at_hours: Optional[float]
    performed_at_cycles: Optional[int]
    performed_by: Optional[str]
    signed_off_by: Optional[str]
    vendor: Optional[str]
    cost: Optional[float]
    notes: Optional[str]


class ItemTypeOut(ORMModel):
    id: int
    name: str
    category: str
    reg_reference: Optional[str]
    interval_kind: str
    default_interval_months: Optional[int]
    default_interval_hours: Optional[float]
    default_interval_cycles: Optional[int]
    default_warning_days: int
    applies_to_component_type: Optional[str]
    is_required_for_airworthiness: bool
    description: Optional[str]


class SeedFromCatalog(BaseModel):
    """Create items on an aircraft from selected catalog item types."""

    item_type_ids: list[int] = Field(default_factory=list)
    component_id: Optional[int] = None
