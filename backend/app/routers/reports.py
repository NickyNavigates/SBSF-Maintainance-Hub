"""Compliance report export: per-aircraft / fleet CSV and a printable HTML report."""

from __future__ import annotations

import csv
import io
from datetime import date
from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from .. import service
from ..database import get_db
from ..models import Aircraft

router = APIRouter(prefix="/api", tags=["reports"])

_CSV_HEADER = [
    "tail_number", "category", "item", "reg_reference", "component",
    "interval_kind", "status", "airworthiness",
    "last_done_date", "last_done_hours",
    "next_due_date", "next_due_hours", "effective_due_date",
    "remaining_days", "remaining_hours",
]

_STATUS_TEXT = {"ok": "Current", "due_soon": "Due soon", "overdue": "OVERDUE", "unknown": "No data"}


def _rows_for(db: Session, ac: Aircraft) -> list[list]:
    rows = []
    for it in sorted(ac.items, key=lambda i: (i.category, i.name)):
        if not it.is_active:
            continue
        p = service.serialize_item(db, it)
        c = p["compliance"]
        rows.append([
            ac.tail_number, p["category"], p["name"], p["reg_reference"] or "",
            p["component_position"] or "", p["interval_kind"],
            _STATUS_TEXT.get(c["status"], c["status"]),
            "YES" if p["is_required_for_airworthiness"] else "",
            p["last_done_date"] or "", p["last_done_hours"] if p["last_done_hours"] is not None else "",
            c["next_due_date"] or "", c["next_due_hours"] if c["next_due_hours"] is not None else "",
            c["effective_due_date"] or "",
            c["remaining_days"] if c["remaining_days"] is not None else "",
            c["remaining_hours"] if c["remaining_hours"] is not None else "",
        ])
    return rows


def _csv_response(rows: list[list], filename: str) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_CSV_HEADER)
    w.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/report.csv")
def fleet_report_csv(db: Session = Depends(get_db)):
    rows = []
    for ac in db.query(Aircraft).order_by(Aircraft.tail_number):
        rows.extend(_rows_for(db, ac))
    return _csv_response(rows, f"sbsf-fleet-compliance-{date.today().isoformat()}.csv")


@router.get("/aircraft/{aircraft_id}/report.csv")
def aircraft_report_csv(aircraft_id: int, db: Session = Depends(get_db)):
    ac = db.get(Aircraft, aircraft_id)
    if not ac:
        raise HTTPException(404, "Aircraft not found")
    return _csv_response(_rows_for(db, ac),
                         f"{ac.tail_number}-compliance-{date.today().isoformat()}.csv")


@router.get("/aircraft/{aircraft_id}/report.html", response_class=HTMLResponse)
def aircraft_report_html(aircraft_id: int, db: Session = Depends(get_db)):
    ac = db.get(Aircraft, aircraft_id)
    if not ac:
        raise HTTPException(404, "Aircraft not found")
    today = date.today()

    comps = "".join(
        f"<span class='comp'><b>{escape(c.position or c.type)}</b> "
        f"{c.current_hours:g} h · {c.current_cycles:g} cyc</span>"
        for c in ac.components
    )

    items = [service.serialize_item(db, it) for it in ac.items if it.is_active]
    items.sort(key=lambda p: (p["category"], p["name"]))
    counts = {"overdue": 0, "due_soon": 0, "ok": 0}
    rows_html = []
    for p in items:
        c = p["compliance"]
        counts[c["status"]] = counts.get(c["status"], 0) + 1
        aw = " <span class='aw'>AW</span>" if p["is_required_for_airworthiness"] else ""
        due = c["effective_due_date"] or "—"
        if c["remaining_days"] is not None:
            due += f" ({c['remaining_days']}d)"
        hrs = f"{c['remaining_hours']:g} h left" if c["remaining_hours"] is not None else ""
        rows_html.append(
            f"<tr class='{c['status']}'>"
            f"<td>{escape(p['category'])}</td>"
            f"<td>{escape(p['name'])}{aw}<br><small>{escape(p['reg_reference'] or '')} "
            f"{escape(p['component_position'] or '')}</small></td>"
            f"<td class='st'>{_STATUS_TEXT.get(c['status'], c['status'])}</td>"
            f"<td>{escape(p['last_done_date'] or '—')}</td>"
            f"<td>{escape(due)}<br><small>{escape(hrs)}</small></td>"
            f"</tr>"
        )

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{escape(ac.tail_number)} — Compliance report</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; color:#1d2733; margin:32px; }}
  h1 {{ margin:0 0 2px; }} .sub {{ color:#6b7785; margin:0 0 14px; }}
  .comp {{ display:inline-block; background:#f1f4f8; border-radius:8px; padding:5px 10px; margin:0 8px 8px 0; font-size:13px; }}
  .summary span {{ display:inline-block; margin-right:18px; font-weight:600; }}
  .red {{ color:#cf2f3b; }} .amber {{ color:#c97c00; }} .green {{ color:#1f9d57; }}
  table {{ border-collapse:collapse; width:100%; margin-top:14px; font-size:13px; }}
  th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid #e2e7ee; vertical-align:top; }}
  th {{ background:#0f2a43; color:#fff; }}
  small {{ color:#8a96a3; }}
  tr.overdue td.st {{ color:#cf2f3b; font-weight:700; }}
  tr.due_soon td.st {{ color:#c97c00; font-weight:700; }}
  tr.ok td.st {{ color:#1f9d57; }}
  .aw {{ background:#0f2a43; color:#fff; font-size:9px; padding:1px 5px; border-radius:6px; vertical-align:middle; }}
  .foot {{ margin-top:22px; color:#8a96a3; font-size:12px; border-top:1px solid #e2e7ee; padding-top:10px; }}
  @media print {{ body {{ margin:12px; }} th {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }} }}
</style></head><body>
<h1>{escape(ac.tail_number)} — Compliance report</h1>
<p class="sub">{escape(' '.join(filter(None, [ac.make, ac.model, str(ac.year or '')])))} ·
  S/N {escape(ac.serial_number or '—')} · {escape(ac.home_base or '')} · generated {today.isoformat()}</p>
<div>{comps}</div>
<p class="summary">
  <span class="red">{counts.get('overdue', 0)} overdue</span>
  <span class="amber">{counts.get('due_soon', 0)} due soon</span>
  <span class="green">{counts.get('ok', 0)} current</span>
</p>
<table>
  <thead><tr><th>Category</th><th>Item</th><th>Status</th><th>Last done</th><th>Next due</th></tr></thead>
  <tbody>{''.join(rows_html)}</tbody>
</table>
<p class="foot">Advisory report only — the signed aircraft records remain authoritative.
  Intervals are defaults and must be verified against this aircraft, applicable ADs,
  and current regulations. AW = required for airworthiness.</p>
<script>window.onload = () => {{ if (location.search.includes('print')) window.print(); }}</script>
</body></html>"""
    return HTMLResponse(html)
