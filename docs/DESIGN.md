# SBSF Maintenance Hub — Design Document

**Owner:** Superior Steel Fab (SBSF) Flight Department
**Status:** Draft for review (v0.1)
**Date:** 2026-06-28

---

## 1. Purpose

SBSF operates one or more aircraft and must keep dozens of recurring
compliance and maintenance items current on each airframe. Today these are
tracked informally (spreadsheets, logbooks, memory), which makes it easy to
miss a due date and risks operating an aircraft that is out of annual,
out of inspection, or carrying expired emergency equipment.

The **Maintenance Hub** is a single system of record that tracks every
recurring item per aircraft, computes when each is next due (by **calendar
date**, **flight hours**, or **landing cycles**), surfaces what is **due
soon** or **overdue**, and notifies the responsible people in time to act.

### Goals

- One dashboard showing the airworthiness/compliance status of every aircraft.
- Track **calendar-based**, **hours-based**, and **cycle-based** recurring items.
- Project hours-based items onto the calendar using each aircraft's actual
  utilization rate, so everything can live on one timeline.
- Log completions with who/when/at-what-hours plus supporting documents
  (work orders, 8130s, repack cards, weigh tags).
- Proactive alerts (email, optionally SMS) ahead of every due date.
- Audit trail and exportable compliance reports for inspections/insurance.

### Non-goals (initial release)

- Not a digital logbook replacement or signed maintenance record of record
  (the aircraft logbooks remain authoritative; this tool *tracks and reminds*).
- Not flight scheduling / dispatch.
- Not a regulatory authority — interval defaults are **advisory** and must be
  confirmed by the A&P/IA against the aircraft's specific make/model,
  Airworthiness Directives, manufacturer ICAs, and applicable FARs.

---

## 2. Users & Roles

| Role | Description | Capabilities |
|------|-------------|--------------|
| **Admin** | Flight dept manager / DOM | Full access; manage aircraft, users, item catalog, settings |
| **Maintenance** | A&P / IA / mechanic | Log completions, add/edit items, upload documents |
| **Pilot / Operator** | Logs flights/hours | Update aircraft hours & cycles, view status, acknowledge alerts |
| **Viewer** | Insurance, auditor, owner | Read-only dashboards and exported reports |

Most flight departments are small, so role assignment should be simple and a
single person may hold multiple roles.

---

## 3. Domain Background — What We Track

Recurring items fall into three timing categories. The Hub must support all
three and combinations of them ("**whichever comes first**").

> ⚠️ **Intervals below are typical defaults for illustration.** Actual
> intervals depend on the specific aircraft, equipment manufacturer, type of
> operation (Part 91 vs 135), IFR vs VFR, and applicable ADs. Every default
> in the seed catalog is editable per aircraft and must be verified by
> qualified maintenance personnel.

### 3.1 Calendar-based regulatory inspections (Part 91 examples)

| Item | Reg | Typical interval | Applies when |
|------|-----|------------------|--------------|
| Annual inspection | 91.409(a) | 12 calendar months | All |
| Transponder check | 91.413 | 24 calendar months | Transponder installed |
| Altimeter / pitot-static / static system | 91.411 | 24 calendar months | IFR |
| ELT inspection | 91.207(d) | 12 calendar months | ELT installed |
| ELT battery replacement | 91.207(c) | Battery expiry, or after 1 hr cumulative use / ½ useful life | ELT installed |
| Aircraft registration | — | Up to 7-year expiry (FAA) | All |
| VOR check (IFR) | 91.171 | 30 days | IFR using VOR |
| Weighing / weight & balance | — | Per ops type / mods | As required |

### 3.2 Emergency / survival equipment (expiry & service intervals)

| Item | Typical interval | Notes |
|------|------------------|-------|
| Fire extinguisher — inspection | 12 months | Plus periodic hydrostatic test (5–12 yr by type) |
| Fire extinguisher — hydrostatic test | 5–12 years | By cylinder type |
| First aid / medical kit | Earliest content expiry | Track per-kit earliest expiry; flag individual contents |
| Life vests / life preservers | Per mfr (often annual inspection) | CO₂ cylinder hydro/service life |
| Life raft — repack/recert | 1–5 years (per mfr) | Inspect raft, valves, canopy, survival pack contents |
| Flares / pyrotechnic signals | ~36 months from manufacture | Replace at expiry |
| Parachutes (if carried) | 180 days repack (FAR 105.43) | Per rigger requirements |
| Portable oxygen — hydrostatic | 3 or 5 years (cylinder spec) | DOT cylinder rules |
| Survival kit contents | Earliest content expiry | Composite item like medical kit |

### 3.3 Hours-based and cycle-based maintenance (a few dozen per aircraft)

These accrue against **flight hours** (Hobbs/tach) or **landing cycles** and
typically attach to a **component** (airframe, a specific engine, a propeller)
because each component carries its own hour/cycle counter.

| Item (examples) | Typical interval |
|-----------------|------------------|
| Oil & filter change | 50 hours (or calendar, whichever first) |
| 100-hour inspection | 100 hours (if required by ops) |
| Engine overhaul (TBO) | e.g. 1,800–2,200 hours / 12 yr |
| Magneto inspection / overhaul | 500 hours |
| Spark plug service | 100–300 hours |
| Vacuum pump replacement | On condition / hours |
| Propeller overhaul | Hours and/or calendar (mfr) |
| Recurring Airworthiness Directives | Per AD (hours, cycles, and/or calendar) |
| Hose / filter replacements | Hours or calendar |

**Key insight:** hours-based items have no fixed calendar date. The Hub
estimates a *projected due date* from the component's current hours plus the
aircraft's recent utilization rate (avg hours/month). This lets hours-based
and calendar-based items share one dashboard, calendar, and alert pipeline.

---

## 4. Core Concepts & Data Model

### 4.1 Entities

```
Organization (SBSF)
  └─ Aircraft (tail number, make/model/serial, year, base)
       ├─ Component (Airframe, Engine #1, Engine #2, Propeller, …)
       │    └─ has its own current hours / cycles
       ├─ HoursReading  (date, component, hours, cycles, source)
       └─ ComplianceItem  (a tracked recurring requirement)
            ├─ references an ItemType (from catalog) — optional
            ├─ interval definition (calendar / hours / cycles / combo)
            ├─ warning window (how early to alert)
            └─ ComplianceEvent[]  (completion history)
                 └─ Attachment[]  (work order, 8130, repack card, photo)

User (role) — belongs to Organization
Notification — generated alert, per item/event
ItemType — catalog/template of standard items + default intervals
```

### 4.2 Key tables (relational)

**aircraft**
- `id`, `tail_number` (unique), `make`, `model`, `serial_number`, `year`,
  `home_base`, `status` (active/inactive/sold), `notes`

**component**
- `id`, `aircraft_id`, `type` (airframe|engine|propeller|apu|other),
  `position` (e.g. "Engine #1"), `make`, `model`, `serial_number`,
  `current_hours`, `current_cycles`, `hours_as_of` (datetime)

**hours_reading** (history; lets us compute utilization rate)
- `id`, `component_id`, `reading_date`, `hours`, `cycles`,
  `source` (manual|import), `entered_by`

**item_type** (catalog/template, org-editable, seeded)
- `id`, `name`, `category` (inspection|emergency_equipment|engine|prop|airframe|avionics|registration|ad|other),
  `reg_reference` (e.g. "91.413"), `default_interval_*` fields,
  `default_warning_*`, `applies_to_component_type`, `description`

**compliance_item** (the live tracked item on a specific aircraft/component)
- `id`, `aircraft_id`, `component_id` (nullable — null = whole aircraft),
  `item_type_id` (nullable), `name`, `category`,
  `interval_kind` (calendar | hours | cycles | combo_first | combo_last),
  `interval_months`, `interval_hours`, `interval_cycles`,
  `fixed_expiry_date` (for one-shot expiries like a flare lot or registration),
  `warning_days`, `warning_hours`,
  `last_done_date`, `last_done_hours`, `last_done_cycles`,
  `is_active`, `is_required_for_airworthiness` (bool), `notes`
- *Derived (computed, not stored or cached):* `next_due_date`,
  `next_due_hours`, `projected_due_date`, `status`, `remaining_days`,
  `remaining_hours`

**compliance_event** (completion log — the audit trail)
- `id`, `compliance_item_id`, `performed_date`, `performed_at_hours`,
  `performed_at_cycles`, `performed_by`, `signed_off_by` (A&P/IA + cert #),
  `cost`, `vendor`, `notes`, `created_by`, `created_at`
- On insert, this updates the parent item's `last_done_*` fields.

**attachment**
- `id`, `compliance_event_id` (or `compliance_item_id`), `filename`,
  `content_type`, `storage_url`, `uploaded_by`, `uploaded_at`

**user**
- `id`, `email`, `name`, `role`, `phone` (for SMS), `notify_prefs`, `active`

**notification**
- `id`, `compliance_item_id`, `channel` (email|sms|in_app), `due_status`,
  `sent_at`, `acknowledged_by`, `acknowledged_at`

### 4.3 Interval model — handling "whichever comes first"

A `compliance_item` can carry more than one interval. `interval_kind`
determines how they combine:

- `calendar` — due = `last_done_date + interval_months`
- `hours` — due at `last_done_hours + interval_hours`
- `cycles` — due at `last_done_cycles + interval_cycles`
- `combo_first` — multiple intervals; due = the **earliest** of them
  (most common, e.g. oil change "50 hours or 4 months, whichever first")
- `combo_last` — due = the **latest** (rare)
- `fixed_expiry` — a hard date with no recurrence (flare lot, registration);
  resets only when a new expiry is entered

---

## 5. Due-Date & Status Logic

This is the heart of the app. For each active `compliance_item`:

### 5.1 Calendar due date
```
next_due_date = last_done_date + interval_months
```

### 5.2 Hours due + projection onto the calendar
```
hours_remaining   = (last_done_hours + interval_hours) - component.current_hours
util_rate         = avg hours/day over last N days of hours_reading history
                    (fallback to an org-default rate if no history)
projected_due_date = today + (hours_remaining / util_rate)
```
Cycles are projected the same way using a cycles/day rate.

### 5.3 Effective due date
- For `combo_first`, take `min(next_due_date, projected_due_date, …)`.
- The **effective due date** is what drives the dashboard, calendar, and alerts.

### 5.4 Status
```
days_out = effective_due_date - today
status =
  OVERDUE    if days_out < 0  (or hours/cycles already exceeded)
  DUE_SOON   if 0 <= days_out <= warning_days
  OK         otherwise
```
Hours-based items also get a hard check on hours remaining, independent of the
projection, so a sudden spike in flying still trips DUE_SOON/OVERDUE even if
the date projection lagged.

A separate, prominent **"Airworthiness"** rollup per aircraft answers the one
question that matters most: *is anything required-for-airworthiness overdue?*

---

## 6. Features

### 6.1 Fleet dashboard
- Card per aircraft: tail number, current hours, overall status light
  (green/amber/red), count of due-soon and overdue items, next item due.
- Filter/sort by status, aircraft, category.

### 6.2 Aircraft detail
- Component list with current hours/cycles and an inline "update hours" action.
- Full item list grouped by category, each showing interval, last done,
  next due (date + hours), remaining, and status chip.
- "Log completion" button per item.

### 6.3 Calendar / timeline view
- All items (calendar + projected hours-based) on a month/timeline view.
- Useful for planning shop visits and bundling work.

### 6.4 Log a completion
- Form: date, hours/cycles at completion, performed by, sign-off (A&P/IA + cert),
  vendor, cost, notes, document upload. Saving advances the item's next-due.

### 6.5 Hours entry
- Quick per-aircraft "update current hours/cycles" (pilots after flights).
- Each entry is stored as a `hours_reading` to feed the utilization rate.
- Optional CSV import.

### 6.6 Alerts & notifications
- Nightly job recomputes status for every item and sends:
  - email digest (per recipient) of due-soon/overdue items,
  - optional SMS for overdue airworthiness items,
  - in-app notification list.
- Configurable lead time per item (e.g. 30/14/7/1 days, or N hours remaining).

### 6.7 Documents
- Per-completion attachments stored in object storage; downloadable from the
  item history. Supports the "show me proof it was done" inspection scenario.

### 6.8 Reporting / export
- Per-aircraft compliance status PDF/CSV (for insurance, audits, sale).
- Full event history export per aircraft (the audit trail).

### 6.9 Item catalog & seeding
- New aircraft can be seeded from the standard `item_type` catalog (Section 3),
  pre-creating the common items with default intervals to edit.

---

## 7. Architecture & Tech Stack (recommendation)

A small flight department needs something **reliable, low-maintenance, and
accessible from phone and desktop** (hours get entered at the hangar). A
web app (responsive, installable as a PWA) fits better than a native app.

**Recommended stack**
- **Frontend:** React + TypeScript, responsive/PWA, component library
  (e.g. shadcn/ui or MUI).
- **Backend:** Node.js (NestJS or Express) **or** Python (FastAPI/Django).
  REST/JSON API. Either is fine; pick by team familiarity.
- **Database:** PostgreSQL (relational fits this domain cleanly; strong dates).
- **Object storage:** S3-compatible bucket for attachments.
- **Background jobs:** a scheduled worker (cron/queue) for the nightly
  status recompute + notifications.
- **Email/SMS:** transactional email provider; SMS provider (optional).
- **Auth:** email/password + roles, or SSO/Google if SBSF uses Google
  Workspace.
- **Hosting:** a managed PaaS (single small instance + managed Postgres) is
  more than enough for this scale.

**Why this shape**
- The due-date logic is the core value and is pure server-side computation —
  keep it in one place (a `compliance` service) with thorough unit tests
  covering each `interval_kind` and the projection math.
- Relational DB because the data is highly relational and date-centric, and
  reporting/queries (e.g. "everything due in 30 days across the fleet") are
  trivial in SQL.

> Stack choices above are recommendations, not decisions — confirm with the
> team in Section 11 before implementation.

---

## 8. MVP Scope & Phased Roadmap

**Phase 1 — MVP (core tracking)**
1. Aircraft + component management.
2. Compliance items with all interval kinds + the due/status engine.
3. Manual hours entry + utilization-based projection.
4. Log completions with history.
5. Fleet dashboard + aircraft detail + status chips.
6. Seed catalog of standard FAA/equipment items.

**Phase 2 — Stay-ahead**
7. Email notifications + nightly recompute job.
8. Document attachments.
9. Calendar/timeline view.
10. Compliance report export (PDF/CSV).

**Phase 3 — Polish & scale**
11. SMS alerts, configurable per-item lead times.
12. CSV hours import; optional integration with an hours source.
13. Per-content tracking inside composite kits (medical/survival).
14. Audit log, SSO, finer-grained permissions.

---

## 9. Example: how one item flows through the system

> Oil change on Engine #1, interval "50 hours or 4 months, whichever first".

1. Item created: `interval_kind=combo_first`, `interval_hours=50`,
   `interval_months=4`, `component=Engine #1`, `warning_days=14`.
2. Last done at 1,200.0 hrs on 2026-03-01.
3. Pilot logs hours weekly; history shows ~25 hrs/month (~0.83 hrs/day).
4. Engine now at 1,235.0 hrs (2026-06-28).
   - Hours due at 1,250.0 → 15.0 hrs remaining → ~18 days projected.
   - Calendar due 2026-07-01 → 3 days remaining.
   - `combo_first` → effective due **2026-07-01**, status **DUE_SOON**.
5. Dashboard flags it; nightly job emails the digest.
6. Mechanic logs completion at 1,251 hrs on 2026-06-30 with the work order
   attached → item advances to next due (hours 1,301 / date 2026-10-30).

---

## 10. Compliance & Data Considerations

- **Advisory, not authoritative:** the app reminds; the signed aircraft
  records remain the legal record. State this in the UI.
- **Editable intervals:** every interval is per-aircraft editable; ADs and
  mfr ICAs override catalog defaults.
- **Auditability:** completions are append-only events; edits are tracked.
- **Backups:** regular DB + attachment backups; data export available.
- **Time zones / "calendar months":** FAA "calendar month" = through the last
  day of the month N months later. The date engine must implement this
  precisely (not naive 30-day math).

---

## 11. Open Questions (please confirm before build)

1. **Fleet size:** how many aircraft, and single-engine/twin/turbine mix?
   (Drives component modeling and item counts.)
2. **Operation type:** Part 91 only, or any Part 135? (Changes required items.)
3. **Users:** how many people, and which roles? SSO/Google Workspace?
4. **Platform preference:** web app (recommended) vs. desktop vs. native mobile?
5. **Hours source:** manual entry only, or is there an existing log/system to
   import from?
6. **Notifications:** email enough for v1, or is SMS required day one?
7. **Hosting:** any IT constraints (must self-host vs. managed cloud OK)?
8. **Existing data:** is there a spreadsheet of current items/due dates to
   migrate as the seed?

---

## Appendix A — Seed Item Catalog (starting point)

Categories: `inspection`, `emergency_equipment`, `engine`, `propeller`,
`airframe`, `avionics`, `registration`, `ad`, `other`.

The catalog ships with the items listed in Sections 3.1–3.3 as `item_type`
templates with editable default intervals, so adding a new aircraft
pre-populates the common items for the team to confirm.

## Appendix B — Sources (interval references)

- AOPA — Altimeter and transponder checks:
  https://www.aopa.org/news-and-media/all-news/2020/june/09/aircraft-maintenance-altimeter-and-transponder-checks
- eCFR 14 CFR 91.411 (altimeter/static):
  https://www.ecfr.gov/current/title-14/chapter-I/subchapter-F/part-91/subpart-E/section-91.411
- First Flight Aviation — 91.411 & 91.413 explained:
  https://firstflightaviation.com/far-91-411-and-91-413-certifications-explained-what-aircraft-owners-need-to-know/
- eCFR 14 CFR 91.513 (emergency equipment):
  https://www.ecfr.gov/current/title-14/chapter-I/subchapter-F/part-91/subpart-F/section-91.513
- Pilot John — Aviation life rafts guide:
  https://pilotjohn.com/blog/aircraft-life-rafts-101-everything-you-need-to-know
- HRD Aero Systems — Safety equipment servicing guide:
  https://www.hrd-aerosystems.com/blog/aircraft-safety-equipment-servicing-guide/

*All regulatory intervals are advisory defaults and must be verified by
qualified maintenance personnel against the specific aircraft and current
regulations.*
