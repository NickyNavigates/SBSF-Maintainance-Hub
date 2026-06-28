"""Compliance item, completion-event, and catalog-seeding endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import service
from ..database import get_db
from ..models import Aircraft, ComplianceEvent, ComplianceItem, Component, ItemType
from ..schemas import (
    ComplianceItemIn,
    ComplianceItemUpdate,
    EventIn,
    EventOut,
    SeedFromCatalog,
)

router = APIRouter(prefix="/api", tags=["items"])


@router.post("/aircraft/{aircraft_id}/items", status_code=201)
def create_item(aircraft_id: int, payload: ComplianceItemIn, db: Session = Depends(get_db)):
    if not db.get(Aircraft, aircraft_id):
        raise HTTPException(404, "Aircraft not found")
    item = ComplianceItem(aircraft_id=aircraft_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return service.serialize_item(db, item)


@router.patch("/items/{item_id}")
def update_item(item_id: int, payload: ComplianceItemUpdate, db: Session = Depends(get_db)):
    item = db.get(ComplianceItem, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return service.serialize_item(db, item)


@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ComplianceItem, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    db.delete(item)
    db.commit()


@router.get("/items/{item_id}/events", response_model=list[EventOut])
def list_events(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ComplianceItem, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return item.events


@router.post("/items/{item_id}/events", status_code=201)
def log_event(item_id: int, payload: EventIn, db: Session = Depends(get_db)):
    """Record a completion and advance the item's last-done state."""
    item = db.get(ComplianceItem, item_id)
    if not item:
        raise HTTPException(404, "Item not found")

    event = ComplianceEvent(
        compliance_item_id=item.id,
        performed_date=payload.performed_date,
        performed_at_hours=payload.performed_at_hours,
        performed_at_cycles=payload.performed_at_cycles,
        performed_by=payload.performed_by,
        signed_off_by=payload.signed_off_by,
        vendor=payload.vendor,
        cost=payload.cost,
        notes=payload.notes,
    )
    db.add(event)

    # Advance the item's last-done markers.
    item.last_done_date = payload.performed_date
    if payload.performed_at_hours is not None:
        item.last_done_hours = payload.performed_at_hours
    if payload.performed_at_cycles is not None:
        item.last_done_cycles = payload.performed_at_cycles

    # Optionally bump the component's running totals to the completion values.
    if payload.update_component_hours and item.component_id:
        comp = db.get(Component, item.component_id)
        if comp:
            if payload.performed_at_hours is not None and payload.performed_at_hours > comp.current_hours:
                comp.current_hours = payload.performed_at_hours
            if payload.performed_at_cycles is not None and payload.performed_at_cycles > comp.current_cycles:
                comp.current_cycles = payload.performed_at_cycles

    db.commit()
    db.refresh(item)
    return service.serialize_item(db, item)


@router.post("/aircraft/{aircraft_id}/seed-from-catalog")
def seed_from_catalog(aircraft_id: int, payload: SeedFromCatalog, db: Session = Depends(get_db)):
    """Create tracked items on an aircraft from selected catalog templates."""
    ac = db.get(Aircraft, aircraft_id)
    if not ac:
        raise HTTPException(404, "Aircraft not found")
    created = 0
    for type_id in payload.item_type_ids:
        t = db.get(ItemType, type_id)
        if not t:
            continue
        db.add(ComplianceItem(
            aircraft_id=aircraft_id,
            component_id=payload.component_id,
            item_type_id=t.id,
            name=t.name,
            category=t.category,
            reg_reference=t.reg_reference,
            interval_kind=t.interval_kind,
            interval_months=t.default_interval_months,
            interval_hours=t.default_interval_hours,
            interval_cycles=t.default_interval_cycles,
            warning_days=t.default_warning_days,
            is_required_for_airworthiness=t.is_required_for_airworthiness,
        ))
        created += 1
    db.commit()
    return {"created": created}
