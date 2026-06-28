"""Fleet-wide timeline: every active item with an effective due date."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import service
from ..database import get_db
from ..models import Aircraft

router = APIRouter(prefix="/api", tags=["calendar"])


@router.get("/calendar")
def calendar(db: Session = Depends(get_db)):
    """Items with a (real or projected) due date, sorted earliest first."""
    entries = []
    for ac in db.query(Aircraft).order_by(Aircraft.tail_number):
        for item in ac.items:
            if not item.is_active:
                continue
            r = service.evaluate(db, item)
            if not r.effective_due_date:
                continue
            entries.append({
                "aircraft_id": ac.id,
                "tail_number": ac.tail_number,
                "item_id": item.id,
                "name": item.name,
                "category": item.category,
                "component_position": item.component.position if item.component else None,
                "status": r.status.value,
                "is_required_for_airworthiness": item.is_required_for_airworthiness,
                "due_date": r.effective_due_date.isoformat(),
                "projected": r.projected_due_date is not None
                and r.next_due_date is None,
                "remaining_days": r.remaining_days,
            })
    entries.sort(key=lambda e: e["due_date"])
    return {"entries": entries}
