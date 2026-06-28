# SBSF Maintenance Hub

Aircraft compliance & maintenance tracking for the Soaring by the Sea
Foundation (SBSF). Tracks every recurring item per aircraft — **calendar** items
(annual, transponder, pitot-static, ELT, registration, emergency equipment)
and **hours/cycle** items (oil changes, 100-hr, TBO, mags, props, ADs) — and
shows what is **due soon** or **overdue** across the fleet.

> ⚠️ **Advisory tool only.** The signed aircraft records remain the legal
> record. Every interval is an editable default and must be verified by
> qualified maintenance personnel against the specific aircraft, applicable
> Airworthiness Directives, manufacturer ICAs, and current regulations.

See [`docs/DESIGN.md`](docs/DESIGN.md) for the full design.

## What's here

- **Compliance engine** (`backend/app/engine.py`) — pure, unit-tested logic for
  FAA calendar-month due dates, hours/cycle due points, the
  "whichever-comes-first" combination, and projection of hours-based items onto
  the calendar using each component's measured utilisation rate.
- **REST API** (FastAPI + SQLAlchemy, SQLite by default) — aircraft, components,
  hours readings, tracked items, completion events, document attachments,
  fleet dashboard, fleet-wide timeline, catalog, and report export.
- **Responsive PWA** (`frontend/`, zero build) — fleet dashboard with status
  lights, per-aircraft detail grouped by category, log-completion and
  update-hours actions, an in-app attention list, a fleet **timeline** view,
  per-completion **document attachments** with history, and CSV / printable
  report export.
- **Seed catalog** — ~34 item templates (Part 91 regulatory, emergency
  equipment, warbird radial/inline powerplant, amphibian, and helicopter
  rotor/drivetrain time-life items).

## The SBSF fleet (demo seed)

The `--demo` seed builds the actual SBSF fleet, which exercises the model's
range — twins, vintage radial and inline engines, an amphibian, and a turbine
helicopter with rotor/drivetrain time-life components tracked by hours **and**
cycles:

| Tail | Aircraft | Notable components |
|------|----------|--------------------|
| N9767 | Consolidated **PBY-5A Catalina** "Princess of the Stars" | Twin R-1830 radials, 2 props, hull/float & gear-retraction |
| N4730 | Curtiss **P-40N-1 Warhawk** "Currawong" | Allison V-1710 inline (coolant system) |
| N5716 | Douglas **AD-4N Skyraider** | Wright R-3350 radial |
| N6828 | Bell **UH-1H Huey** | T53 turbine, main/tail rotor, transmission, 42°/90° gearboxes |

## Quick start

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# Create the DB + catalog and load a demo fleet (optional but recommended):
python -m app.seed --demo

# Run the app (serves the API and the frontend):
uvicorn app.main:app --reload
```

Then open <http://localhost:8000>. The API docs are at `/docs`.

To start empty (catalog only, no demo data), run `python -m app.seed` instead,
or just start the server — the catalog is seeded automatically on first run.

## Tests

```bash
cd backend && . .venv/bin/activate && python -m pytest
```

## Configuration

- `DATABASE_URL` — defaults to `sqlite:///./maintenance_hub.db`. Point it at a
  PostgreSQL URL to use Postgres (per the design doc) with no code changes.
- `UPLOAD_DIR` — where attachment files are stored (defaults to
  `backend/uploads/`, which is git-ignored).

## Project layout

```
backend/
  app/
    engine.py      # pure due/status computation (unit-tested)
    models.py      # SQLAlchemy models
    schemas.py     # Pydantic request/response models
    service.py     # glue between ORM rows and the engine
    catalog.py     # seed item-type catalog (Part 91 defaults)
    seed.py        # init DB + seed catalog + demo fleet
    main.py        # FastAPI app
    routers/       # aircraft, items, attachments, reports, calendar, dashboard
  tests/
    test_engine.py
frontend/          # zero-build responsive PWA (HTML/CSS/vanilla JS)
docs/
  DESIGN.md        # design document
```

## Roadmap (next)

Per `docs/DESIGN.md`: outbound notifications (email/SMS) with a nightly
recompute job, per-content tracking inside composite kits (medical/survival),
authentication/roles, and a recurring-AD import. Alerts are currently
**in-app only** (dashboard + timeline).
