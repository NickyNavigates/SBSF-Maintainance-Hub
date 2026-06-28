"""Create tables, seed the item-type catalog, and optionally the SBSF fleet.

Run directly:  python -m app.seed            (catalog only, idempotent)
               python -m app.seed --demo     (also create the SBSF fleet)
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

from .catalog import CATALOG
from .database import Base, SessionLocal, engine
from .models import (
    Aircraft,
    ComplianceItem,
    Component,
    HoursReading,
    ItemType,
)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def seed_catalog(db) -> int:
    """Insert catalog item types if the table is empty. Returns count added."""
    if db.query(ItemType).count() > 0:
        return 0
    for entry in CATALOG:
        db.add(ItemType(**entry))
    db.commit()
    return len(CATALOG)


def _by_name(name: str) -> dict:
    return next(e for e in CATALOG if e["name"] == name)


def _item_from_catalog(entry: dict, **overrides) -> ComplianceItem:
    item = ComplianceItem(
        name=entry["name"],
        category=entry["category"],
        reg_reference=entry.get("reg_reference"),
        interval_kind=entry["interval_kind"],
        interval_months=entry.get("default_interval_months"),
        interval_hours=entry.get("default_interval_hours"),
        interval_cycles=entry.get("default_interval_cycles"),
        warning_days=entry.get("default_warning_days", 30),
        is_required_for_airworthiness=entry.get("is_required_for_airworthiness", False),
    )
    for k, v in overrides.items():
        setattr(item, k, v)
    return item


def _add(db, ac, comp, today, name, *, months_ago=None, expiry_days=None,
         hours_to_go=None, cycles_to_go=None, date_months_ago=None):
    """Create one tracked item from the catalog with a chosen 'remaining' state."""
    entry = _by_name(name)
    kw = dict(aircraft_id=ac.id, component_id=comp.id if comp else None)

    # months_ago / date_months_ago use the negative-is-past convention,
    # e.g. months_ago=-2 means "last performed two months ago".
    if months_ago is not None:
        kw["last_done_date"] = _months_ago(today, months_ago)
    if expiry_days is not None:
        kw["fixed_expiry_date"] = today + timedelta(days=expiry_days)
    if hours_to_go is not None and comp is not None:
        interval = entry["default_interval_hours"]
        kw["last_done_hours"] = round(comp.current_hours - (interval - hours_to_go), 1)
    if cycles_to_go is not None and comp is not None:
        interval_c = entry["default_interval_cycles"]
        kw["last_done_cycles"] = int(comp.current_cycles - (interval_c - cycles_to_go))
    if date_months_ago is not None:
        kw["last_done_date"] = _months_ago(today, date_months_ago)

    db.add(_item_from_catalog(entry, **kw))


def _component(db, ac, today, ctype, position, hours, *, cyc_ratio=1.0,
               make=None, model=None, readings_per_month=18):
    c = Component(
        aircraft_id=ac.id, type=ctype, position=position, make=make, model=model,
        current_hours=hours, current_cycles=int(hours * cyc_ratio), hours_as_of=today,
    )
    db.add(c)
    db.flush()
    _seed_readings(db, c, today, per_month=readings_per_month)
    return c


def seed_demo(db) -> None:
    """Create the SBSF warbird/vintage fleet with a realistic mix of statuses."""
    if db.query(Aircraft).count() > 0:
        return
    today = date.today()

    _seed_pby(db, today)
    _seed_p40(db, today)
    _seed_ad4(db, today)
    _seed_uh1(db, today)
    db.commit()


# --- common airframe items (regulatory + emergency) --------------------------

def _common_airframe(db, ac, af, today, *, overdue_altimeter=True):
    _add(db, ac, af, today, "Condition inspection (annual)", months_ago=-2)        # OK
    _add(db, ac, af, today, "Transponder check", months_ago=-23)                   # due soon
    _add(db, ac, af, today, "Altimeter / pitot-static system check",
         months_ago=-25 if overdue_altimeter else -3)                              # overdue/ok
    _add(db, ac, af, today, "ELT inspection", months_ago=-11)                      # due soon
    _add(db, ac, af, today, "ELT battery replacement", expiry_days=480)            # OK
    _add(db, ac, af, today, "Aircraft registration", expiry_days=1000)             # OK
    _add(db, ac, af, today, "Fire extinguisher inspection", months_ago=-6)         # OK
    _add(db, ac, af, today, "First aid / medical kit", expiry_days=22)             # due soon


# --- PBY-5A Catalina (twin R-1830 radial amphibian) --------------------------

def _seed_pby(db, today):
    ac = Aircraft(tail_number="N314PB", make="Consolidated", model="PBY-5A Catalina",
                  serial_number="CV-417", year=1943, home_base="KAGC", status="active",
                  notes="Amphibious flying boat; twin Pratt & Whitney R-1830 Twin Wasp.")
    db.add(ac); db.flush()
    af = _component(db, ac, today, "airframe", "Airframe", 4180.0, cyc_ratio=0.9,
                    make="Consolidated", model="PBY-5A")
    e1 = _component(db, ac, today, "engine", "Engine #1", 5210.0, make="P&W", model="R-1830")
    e2 = _component(db, ac, today, "engine", "Engine #2", 5185.0, make="P&W", model="R-1830")
    p1 = _component(db, ac, today, "propeller", "Propeller #1", 5210.0)
    p2 = _component(db, ac, today, "propeller", "Propeller #2", 5185.0)

    _common_airframe(db, ac, af, today)
    _add(db, ac, af, today, "Hull / float inspection", months_ago=-13)             # overdue
    _add(db, ac, af, today, "Landing gear retraction inspection", months_ago=-2)
    _add(db, ac, af, today, "Life raft repack / recertification", months_ago=-10)  # due soon
    _add(db, ac, af, today, "Life vests inspection", months_ago=-7)
    _add(db, ac, af, today, "Flares / pyrotechnic signals", expiry_days=-6)        # overdue

    for eng, prop in ((e1, p1), (e2, p2)):
        _add(db, ac, eng, today, "Oil & filter change", hours_to_go=9, date_months_ago=-3)
        _add(db, ac, eng, today, "Cylinder compression check", months_ago=-11)     # due soon
        _add(db, ac, eng, today, "Magneto inspection", hours_to_go=60)
        _add(db, ac, eng, today, "Engine top overhaul", hours_to_go=90)
        _add(db, ac, eng, today, "Engine overhaul (TBO)", hours_to_go=180, date_months_ago=-90)
        _add(db, ac, prop, today, "Propeller overhaul", hours_to_go=260, date_months_ago=-40)


# --- P-40N-1 Warhawk (single Allison V-1710 inline) --------------------------

def _seed_p40(db, today):
    ac = Aircraft(tail_number="NX340P", make="Curtiss", model="P-40N-1 Warhawk",
                  serial_number="28954", year=1943, home_base="KAGC", status="active",
                  notes="Single Allison V-1710 liquid-cooled inline.")
    db.add(ac); db.flush()
    af = _component(db, ac, today, "airframe", "Airframe", 3120.0, cyc_ratio=1.1,
                    make="Curtiss", model="P-40N")
    eng = _component(db, ac, today, "engine", "Engine", 470.0, make="Allison", model="V-1710")
    prop = _component(db, ac, today, "propeller", "Propeller", 470.0)

    _common_airframe(db, ac, af, today)
    _add(db, ac, af, today, "Life vests inspection", months_ago=-4)

    _add(db, ac, eng, today, "Oil & filter change", hours_to_go=6, date_months_ago=-3)  # due soon
    _add(db, ac, eng, today, "Coolant system inspection", months_ago=-13)          # overdue
    _add(db, ac, eng, today, "Magneto inspection", hours_to_go=130)
    _add(db, ac, eng, today, "Spark plug service", hours_to_go=45)
    _add(db, ac, eng, today, "Engine overhaul (TBO)", hours_to_go=330, date_months_ago=-30)
    _add(db, ac, prop, today, "Propeller overhaul", hours_to_go=420, date_months_ago=-30)


# --- AD-4N Skyraider (single Wright R-3350 radial) ---------------------------

def _seed_ad4(db, today):
    ac = Aircraft(tail_number="N4DN", make="Douglas", model="AD-4N Skyraider",
                  serial_number="7722", year=1951, home_base="KBVI", status="active",
                  notes="Single Wright R-3350 radial.")
    db.add(ac); db.flush()
    af = _component(db, ac, today, "airframe", "Airframe", 2580.0, cyc_ratio=1.0,
                    make="Douglas", model="AD-4N")
    eng = _component(db, ac, today, "engine", "Engine", 310.0, make="Wright", model="R-3350")
    prop = _component(db, ac, today, "propeller", "Propeller", 310.0)

    _add(db, ac, af, today, "Condition inspection (annual)", months_ago=-11)       # due soon
    _add(db, ac, af, today, "Transponder check", months_ago=-2)
    _add(db, ac, af, today, "Altimeter / pitot-static system check", months_ago=-2)
    _add(db, ac, af, today, "ELT inspection", months_ago=-1)
    _add(db, ac, af, today, "ELT battery replacement", expiry_days=12)             # due soon
    _add(db, ac, af, today, "Aircraft registration", expiry_days=1300)
    _add(db, ac, af, today, "Fire extinguisher inspection", months_ago=-13)        # overdue
    _add(db, ac, af, today, "First aid / medical kit", expiry_days=200)
    _add(db, ac, af, today, "Flares / pyrotechnic signals", expiry_days=-3)        # overdue

    _add(db, ac, eng, today, "Oil & filter change", hours_to_go=3, date_months_ago=-3)  # due soon
    _add(db, ac, eng, today, "Cylinder compression check", months_ago=-2)
    _add(db, ac, eng, today, "Magneto inspection", hours_to_go=18)                 # due soon
    _add(db, ac, eng, today, "Engine top overhaul", hours_to_go=420)
    _add(db, ac, eng, today, "Engine overhaul (TBO)", hours_to_go=600, date_months_ago=-20)
    _add(db, ac, prop, today, "Propeller overhaul", hours_to_go=900, date_months_ago=-20)


# --- UH-1 Huey (turbine helicopter) ------------------------------------------

def _seed_uh1(db, today):
    ac = Aircraft(tail_number="N118HU", make="Bell", model="UH-1H Iroquois (Huey)",
                  serial_number="66-16718", year=1966, home_base="KPIT", status="active",
                  notes="Turbine helicopter; Lycoming T53. Tracks rotor & drivetrain "
                        "time-life components by hours and cycles.")
    db.add(ac); db.flush()
    af = _component(db, ac, today, "airframe", "Airframe", 3760.0, cyc_ratio=1.4,
                    make="Bell", model="UH-1H")
    eng = _component(db, ac, today, "engine", "Engine", 640.0, make="Lycoming", model="T53-L-13")
    mr = _component(db, ac, today, "main_rotor", "Main rotor", 1980.0, cyc_ratio=4.0)
    tr = _component(db, ac, today, "tail_rotor", "Tail rotor", 1980.0, cyc_ratio=4.0)
    tx = _component(db, ac, today, "transmission", "Main transmission", 1980.0)
    g42 = _component(db, ac, today, "gearbox", "42° gearbox", 1980.0)
    g90 = _component(db, ac, today, "gearbox", "90° gearbox", 1980.0)

    _common_airframe(db, ac, af, today)
    _add(db, ac, af, today, "Hydraulic system inspection", hours_to_go=20)         # due soon

    _add(db, ac, eng, today, "Oil & filter change", hours_to_go=14, date_months_ago=-2)
    _add(db, ac, eng, today, "Hot section inspection", hours_to_go=80)
    _add(db, ac, eng, today, "Engine overhaul (TBO)", hours_to_go=220, date_months_ago=-40)

    _add(db, ac, mr, today, "Main rotor blade retirement", hours_to_go=130, cycles_to_go=600)  # due soon
    _add(db, ac, mr, today, "Main rotor hub & grip inspection", hours_to_go=45)
    _add(db, ac, tr, today, "Tail rotor blade retirement", hours_to_go=300)
    _add(db, ac, tx, today, "Main transmission overhaul", hours_to_go=170)
    _add(db, ac, g42, today, "42° / intermediate gearbox overhaul", hours_to_go=400)
    _add(db, ac, g90, today, "90° / tail rotor gearbox overhaul", hours_to_go=350)


# --- helpers -----------------------------------------------------------------

def _seed_readings(db, component, today: date, per_month: float) -> None:
    """Add a few months of hour readings so the projection has real data."""
    rate = per_month / 30.4368
    for months_back in (6, 4, 2, 0):
        d = _months_ago(today, -months_back)
        hours = component.current_hours - rate * (today - d).days
        db.add(HoursReading(
            component_id=component.id, reading_date=d,
            hours=round(max(hours, 0.0), 1),
            cycles=int(max(hours, 0.0) * (component.current_cycles / max(component.current_hours, 1))),
            source="manual",
        ))


def _months_ago(today: date, months: int) -> date:
    """months is negative for the past (e.g. -2 = two months ago)."""
    total = today.year * 12 + (today.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(today.day, 28)
    return date(year, month, day)


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        added = seed_catalog(db)
        print(f"Catalog item types: +{added} (existing kept).")
        if "--demo" in sys.argv:
            seed_demo(db)
            print(f"Fleet: {db.query(Aircraft).count()} aircraft, "
                  f"{db.query(ComplianceItem).count()} tracked items.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
