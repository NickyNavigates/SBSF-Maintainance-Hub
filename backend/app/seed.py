"""Create tables, seed the item-type catalog, and optionally a demo fleet.

Run directly:  python -m app.seed            (catalog only, idempotent)
               python -m app.seed --demo     (also create a demo fleet)
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

from .catalog import CATALOG
from .database import Base, SessionLocal, engine
from .models import (
    Aircraft,
    ComplianceEvent,
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


def _item_from_catalog(entry: dict, **overrides) -> ComplianceItem:
    """Build a ComplianceItem mirroring a catalog entry's defaults."""
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


def _by_name(name: str) -> dict:
    return next(e for e in CATALOG if e["name"] == name)


def seed_demo(db) -> None:
    """Create a small demo fleet with a realistic mix of statuses."""
    if db.query(Aircraft).count() > 0:
        return
    today = date.today()

    fleet = [
        dict(tail="N512SF", make="Cessna", model="208B Grand Caravan",
             serial="208B-1234", year=2014, base="KPIT", engines=1,
             af_hours=3850.0, eng_hours=3850.0, twin=False),
        dict(tail="N88SB", make="Beechcraft", model="B200 King Air",
             serial="BB-1789", year=2009, base="KAGC", engines=2,
             af_hours=6120.0, eng_hours=2100.0, twin=True),
        dict(tail="N304CH", make="Cirrus", model="SR22T",
             serial="1102", year=2018, base="KPIT", engines=1,
             af_hours=1480.0, eng_hours=1480.0, twin=False),
        dict(tail="N17SF", make="Piper", model="PA-46 Malibu",
             serial="4636210", year=2006, base="KBVI", engines=1,
             af_hours=2760.0, eng_hours=620.0, twin=False),
    ]

    for spec in fleet:
        ac = Aircraft(
            tail_number=spec["tail"], make=spec["make"], model=spec["model"],
            serial_number=spec["serial"], year=spec["year"],
            home_base=spec["base"], status="active",
        )
        db.add(ac)
        db.flush()

        # --- Components ---
        airframe = Component(
            aircraft_id=ac.id, type="airframe", position="Airframe",
            make=spec["make"], model=spec["model"], serial_number=spec["serial"],
            current_hours=spec["af_hours"], current_cycles=int(spec["af_hours"] * 1.3),
            hours_as_of=today,
        )
        db.add(airframe)
        db.flush()
        _seed_readings(db, airframe, today, per_month=22)

        engines = []
        for i in range(spec["engines"]):
            eng = Component(
                aircraft_id=ac.id, type="engine",
                position=f"Engine #{i + 1}" if spec["twin"] else "Engine",
                current_hours=spec["eng_hours"], current_cycles=int(spec["eng_hours"] * 1.3),
                hours_as_of=today,
            )
            db.add(eng)
            db.flush()
            _seed_readings(db, eng, today, per_month=22)
            engines.append(eng)

        prop = Component(
            aircraft_id=ac.id, type="propeller", position="Propeller",
            current_hours=spec["eng_hours"], current_cycles=int(spec["eng_hours"] * 1.3),
            hours_as_of=today,
        )
        db.add(prop)
        db.flush()

        # --- Airframe-level calendar / equipment items (varied statuses) ---
        # offsets_months: how long ago the item was last done, to create a mix.
        airframe_items = [
            ("Annual inspection", -2),          # OK (10 months left on 12mo)
            ("Transponder check", -23),         # DUE_SOON (1 month left on 24mo)
            ("Altimeter / pitot-static system check", -25),  # OVERDUE
            ("ELT inspection", -11),            # DUE_SOON
            ("Fire extinguisher inspection", -5),
            ("Life vests inspection", -13),     # OVERDUE
            ("100-hour inspection", None),      # hours-based, see below
        ]
        for name, off in airframe_items:
            entry = _by_name(name)
            if entry["interval_kind"] == "hours":
                last_h = airframe.current_hours - 70  # 30h to go on 100h
                item = _item_from_catalog(
                    entry, aircraft_id=ac.id, component_id=airframe.id,
                    last_done_hours=last_h, last_done_date=today - timedelta(days=60),
                )
            else:
                item = _item_from_catalog(
                    entry, aircraft_id=ac.id, component_id=airframe.id,
                    last_done_date=_months_ago(today, off),
                )
            db.add(item)

        # --- Fixed-expiry equipment items ---
        fixed_items = [
            ("ELT battery replacement", 400),   # OK
            ("Aircraft registration", 900),     # OK
            ("First aid / medical kit", 20),    # DUE_SOON
            ("Flares / pyrotechnic signals", -10),  # OVERDUE (10 days ago)
        ]
        for name, days in fixed_items:
            entry = _by_name(name)
            item = _item_from_catalog(
                entry, aircraft_id=ac.id, component_id=airframe.id,
                fixed_expiry_date=today + timedelta(days=days),
            )
            db.add(item)

        # --- Engine items (hours / combo) ---
        for eng in engines:
            # Oil change: 50h or 4mo whichever first; ~12h to go.
            oil = _by_name("Oil & filter change")
            db.add(_item_from_catalog(
                oil, aircraft_id=ac.id, component_id=eng.id,
                last_done_hours=eng.current_hours - 38,
                last_done_date=today - timedelta(days=40),
            ))
            # Magneto: 500h
            mag = _by_name("Magneto inspection")
            db.add(_item_from_catalog(
                mag, aircraft_id=ac.id, component_id=eng.id,
                last_done_hours=eng.current_hours - 460,  # 40h to go
                last_done_date=today - timedelta(days=300),
            ))
            # TBO
            tbo = _by_name("Engine overhaul (TBO)")
            db.add(_item_from_catalog(
                tbo, aircraft_id=ac.id, component_id=eng.id,
                last_done_hours=0.0, last_done_date=_months_ago(today, -60),
            ))

        # --- Propeller overhaul ---
        po = _by_name("Propeller overhaul")
        db.add(_item_from_catalog(
            po, aircraft_id=ac.id, component_id=prop.id,
            last_done_hours=0.0, last_done_date=_months_ago(today, -50),
        ))

    db.commit()


def _seed_readings(db, component, today: date, per_month: float) -> None:
    """Add a few months of hour readings so the projection has real data."""
    rate = per_month / 30.4368
    for months_back in (6, 4, 2, 0):
        d = _months_ago(today, -months_back)
        hours = component.current_hours - rate * (today - d).days
        db.add(HoursReading(
            component_id=component.id, reading_date=d,
            hours=round(max(hours, 0.0), 1),
            cycles=int(max(hours, 0.0) * 1.3), source="manual",
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
            print(f"Demo fleet: {db.query(Aircraft).count()} aircraft, "
                  f"{db.query(ComplianceItem).count()} tracked items.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
