"""Aircraft, components, and hours-reading endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import service
from ..database import get_db
from ..engine import Status
from ..models import Aircraft, Component, HoursReading
from ..schemas import (
    AircraftIn,
    AircraftOut,
    ComponentIn,
    ComponentOut,
    HoursIn,
)

router = APIRouter(prefix="/api", tags=["aircraft"])

_SEVERITY = {"overdue": 3, "due_soon": 2, "ok": 1, "unknown": 0}


def _aircraft_summary(db: Session, ac: Aircraft) -> dict:
    overdue = due_soon = 0
    airworthiness_overdue = 0
    soonest = None
    for item in ac.items:
        if not item.is_active:
            continue
        r = service.evaluate(db, item)
        if r.status == Status.OVERDUE:
            overdue += 1
            if item.is_required_for_airworthiness:
                airworthiness_overdue += 1
        elif r.status == Status.DUE_SOON:
            due_soon += 1
        if r.effective_due_date and r.status in (Status.OVERDUE, Status.DUE_SOON, Status.OK):
            if soonest is None or r.effective_due_date < soonest[0]:
                soonest = (r.effective_due_date, item.name)
    if airworthiness_overdue or overdue:
        light = "red"
    elif due_soon:
        light = "amber"
    else:
        light = "green"
    return {
        "id": ac.id,
        "tail_number": ac.tail_number,
        "make": ac.make,
        "model": ac.model,
        "year": ac.year,
        "home_base": ac.home_base,
        "status": ac.status,
        "light": light,
        "overdue_count": overdue,
        "due_soon_count": due_soon,
        "airworthiness_overdue": airworthiness_overdue,
        "next_due": (
            {"date": soonest[0].isoformat(), "name": soonest[1]} if soonest else None
        ),
    }


@router.get("/aircraft")
def list_aircraft(db: Session = Depends(get_db)):
    return [_aircraft_summary(db, ac) for ac in db.query(Aircraft).order_by(Aircraft.tail_number)]


@router.post("/aircraft", response_model=AircraftOut, status_code=201)
def create_aircraft(payload: AircraftIn, db: Session = Depends(get_db)):
    if db.query(Aircraft).filter(Aircraft.tail_number == payload.tail_number).first():
        raise HTTPException(409, "Tail number already exists")
    ac = Aircraft(**payload.model_dump())
    db.add(ac)
    db.commit()
    db.refresh(ac)
    return ac


@router.get("/aircraft/{aircraft_id}")
def get_aircraft(aircraft_id: int, db: Session = Depends(get_db)):
    ac = db.get(Aircraft, aircraft_id)
    if not ac:
        raise HTTPException(404, "Aircraft not found")
    components = [ComponentOut.model_validate(c).model_dump() for c in ac.components]
    items = [
        service.serialize_item(db, it)
        for it in sorted(ac.items, key=lambda i: (i.category, i.name))
        if it.is_active
    ]
    items.sort(key=lambda i: _SEVERITY.get(i["compliance"]["status"], 0), reverse=True)
    return {
        **AircraftOut.model_validate(ac).model_dump(),
        "components": components,
        "items": items,
    }


@router.delete("/aircraft/{aircraft_id}", status_code=204)
def delete_aircraft(aircraft_id: int, db: Session = Depends(get_db)):
    ac = db.get(Aircraft, aircraft_id)
    if not ac:
        raise HTTPException(404, "Aircraft not found")
    db.delete(ac)
    db.commit()


# --- Components --------------------------------------------------------------


@router.post("/aircraft/{aircraft_id}/components", response_model=ComponentOut, status_code=201)
def add_component(aircraft_id: int, payload: ComponentIn, db: Session = Depends(get_db)):
    ac = db.get(Aircraft, aircraft_id)
    if not ac:
        raise HTTPException(404, "Aircraft not found")
    comp = Component(aircraft_id=aircraft_id, hours_as_of=date.today(), **payload.model_dump())
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


@router.post("/components/{component_id}/hours", response_model=ComponentOut)
def update_hours(component_id: int, payload: HoursIn, db: Session = Depends(get_db)):
    comp = db.get(Component, component_id)
    if not comp:
        raise HTTPException(404, "Component not found")
    reading_date = payload.reading_date or date.today()
    db.add(HoursReading(
        component_id=comp.id, reading_date=reading_date, hours=payload.hours,
        cycles=payload.cycles, source="manual", entered_by=payload.entered_by,
    ))
    comp.current_hours = payload.hours
    if payload.cycles is not None:
        comp.current_cycles = payload.cycles
    comp.hours_as_of = reading_date
    db.commit()
    db.refresh(comp)
    return comp
