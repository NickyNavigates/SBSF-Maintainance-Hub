"""Fleet dashboard rollup and in-app alerts feed."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import service
from ..database import get_db
from ..engine import Status
from ..models import Aircraft, ItemType
from ..schemas import ItemTypeOut

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    """Fleet-wide counts plus a sorted list of attention items (alerts)."""
    aircraft = db.query(Aircraft).order_by(Aircraft.tail_number).all()
    alerts = []
    totals = {"overdue": 0, "due_soon": 0, "ok": 0, "airworthiness_overdue": 0}

    for ac in aircraft:
        for item in ac.items:
            if not item.is_active:
                continue
            r = service.evaluate(db, item)
            if r.status == Status.OVERDUE:
                totals["overdue"] += 1
                if item.is_required_for_airworthiness:
                    totals["airworthiness_overdue"] += 1
            elif r.status == Status.DUE_SOON:
                totals["due_soon"] += 1
            elif r.status == Status.OK:
                totals["ok"] += 1

            if r.status in (Status.OVERDUE, Status.DUE_SOON):
                alerts.append({
                    "aircraft_id": ac.id,
                    "tail_number": ac.tail_number,
                    "item_id": item.id,
                    "name": item.name,
                    "category": item.category,
                    "status": r.status.value,
                    "is_required_for_airworthiness": item.is_required_for_airworthiness,
                    "effective_due_date": r.effective_due_date.isoformat() if r.effective_due_date else None,
                    "remaining_days": r.remaining_days,
                    "reasons": r.reasons,
                })

    # Overdue first, then soonest due. Airworthiness items rank above others.
    def sort_key(a):
        sev = 0 if a["status"] == "overdue" else 1
        aw = 0 if a["is_required_for_airworthiness"] else 1
        return (sev, aw, a["remaining_days"] if a["remaining_days"] is not None else 99999)

    alerts.sort(key=sort_key)
    return {
        "fleet_size": len(aircraft),
        "totals": totals,
        "alerts": alerts,
    }


@router.get("/catalog", response_model=list[ItemTypeOut])
def list_catalog(db: Session = Depends(get_db)):
    return db.query(ItemType).order_by(ItemType.category, ItemType.name).all()
