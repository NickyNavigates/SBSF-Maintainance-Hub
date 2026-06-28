# SBSF Maintenance Hub

Aircraft compliance & maintenance tracking for the Soaring by the Sea Foundation — calendar items (annual, transponder, pitot-static, ELT,
registration, emergency equipment) and hours/cycle items (oil, 100-hr, TBO,
mags, props, rotor/drivetrain time-life) across the fleet.

## Live app

**https://nickynavigates.github.io/SBSF-Maintainance-Hub/**

This is the self-contained single-file build (in `site/index.html`): the
compliance engine and fleet data run entirely in the browser, and changes are
saved on your device. Open it on a phone and use Safari's **Add to Home
Screen** to keep it one tap away.

> Advisory tool only — the signed aircraft records remain authoritative. Verify
> all intervals against the specific aircraft, ADs and current regulations.

## Full multi-user app

The complete server application (FastAPI + SQLAlchemy API, document
attachments, CSV / printable reports, shared data) lives on the
`claude/aircraft-maintenance-tracking-zn3jyr` branch, with the design document
in `docs/DESIGN.md`. Deploy that when the whole department needs to share one
set of records.
