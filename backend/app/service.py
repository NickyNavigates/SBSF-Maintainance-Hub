"""Glue between ORM rows and the pure compliance engine."""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from . import engine as eng
from .models import ComplianceItem, Component, HoursReading


def component_rates(db: Session, component: Component) -> tuple[float, Optional[float]]:
    """Return (hours_per_day, cycles_per_day) estimated from reading history."""
    readings = (
        db.query(HoursReading)
        .filter(HoursReading.component_id == component.id)
        .order_by(HoursReading.reading_date)
        .all()
    )
    hours_pts = [(r.reading_date, r.hours) for r in readings if r.hours is not None]
    cycle_pts = [(r.reading_date, float(r.cycles)) for r in readings if r.cycles is not None]
    hrate = eng.utilisation_rate_per_day(hours_pts)
    crate = eng.utilisation_rate_per_day(cycle_pts) if len(cycle_pts) >= 2 else None
    return hrate, crate


def evaluate(db: Session, item: ComplianceItem, *, today: Optional[date] = None) -> eng.DueResult:
    """Compute the DueResult for a single tracked item."""
    today = today or date.today()
    timing = eng.ItemTiming(
        interval_kind=eng.IntervalKind(item.interval_kind),
        interval_months=item.interval_months,
        interval_hours=item.interval_hours,
        interval_cycles=item.interval_cycles,
        last_done_date=item.last_done_date,
        last_done_hours=item.last_done_hours,
        last_done_cycles=item.last_done_cycles,
        fixed_expiry_date=item.fixed_expiry_date,
        warning_days=item.warning_days,
        warning_hours=item.warning_hours,
    )

    current_hours = current_cycles = None
    hrate = crate = None
    if item.component is not None:
        current_hours = item.component.current_hours
        current_cycles = item.component.current_cycles
        hrate, crate = component_rates(db, item.component)

    return eng.compute_status(
        timing,
        today=today,
        current_hours=current_hours,
        current_cycles=current_cycles,
        hours_rate_per_day=hrate,
        cycles_rate_per_day=crate,
    )


def result_dict(result: eng.DueResult) -> dict:
    """Serialise a DueResult to a JSON-friendly dict."""
    return {
        "status": result.status.value,
        "effective_due_date": _iso(result.effective_due_date),
        "remaining_days": result.remaining_days,
        "next_due_date": _iso(result.next_due_date),
        "next_due_hours": result.next_due_hours,
        "next_due_cycles": result.next_due_cycles,
        "remaining_hours": result.remaining_hours,
        "remaining_cycles": result.remaining_cycles,
        "projected_due_date": _iso(result.projected_due_date),
        "reasons": result.reasons,
    }


def serialize_item(db: Session, item: ComplianceItem, *, today: Optional[date] = None) -> dict:
    """Full item payload including computed compliance status."""
    return {
        "id": item.id,
        "aircraft_id": item.aircraft_id,
        "component_id": item.component_id,
        "component_position": item.component.position if item.component else None,
        "name": item.name,
        "category": item.category,
        "reg_reference": item.reg_reference,
        "interval_kind": item.interval_kind,
        "interval_months": item.interval_months,
        "interval_hours": item.interval_hours,
        "interval_cycles": item.interval_cycles,
        "fixed_expiry_date": _iso(item.fixed_expiry_date),
        "warning_days": item.warning_days,
        "warning_hours": item.warning_hours,
        "last_done_date": _iso(item.last_done_date),
        "last_done_hours": item.last_done_hours,
        "last_done_cycles": item.last_done_cycles,
        "is_active": item.is_active,
        "is_required_for_airworthiness": item.is_required_for_airworthiness,
        "notes": item.notes,
        "compliance": result_dict(evaluate(db, item, today=today)),
    }


def serialize_event(event) -> dict:
    """A completion event including its attachments."""
    return {
        "id": event.id,
        "compliance_item_id": event.compliance_item_id,
        "performed_date": _iso(event.performed_date),
        "performed_at_hours": event.performed_at_hours,
        "performed_at_cycles": event.performed_at_cycles,
        "performed_by": event.performed_by,
        "signed_off_by": event.signed_off_by,
        "vendor": event.vendor,
        "cost": event.cost,
        "notes": event.notes,
        "attachments": [
            {
                "id": a.id,
                "filename": a.filename,
                "content_type": a.content_type,
                "size_bytes": a.size_bytes,
            }
            for a in event.attachments
        ],
    }


def _iso(d) -> Optional[str]:
    return d.isoformat() if d is not None else None
