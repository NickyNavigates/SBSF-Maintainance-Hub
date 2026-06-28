"""Compliance due-date & status engine.

Pure functions with no database or framework dependencies so the core
logic can be unit-tested in isolation. Everything operates on plain values
and small dataclasses.

Timing dimensions a tracked item may use:
  - calendar : due N calendar months after it was last performed
  - hours    : due after N flight hours on the parent component
  - cycles   : due after N landing cycles on the parent component
  - fixed    : a hard expiry date with no recurrence (e.g. flare lot, registration)

An item may combine several dimensions:
  - combo_first : due at the EARLIEST of its dimensions ("50 hrs or 4 mo, whichever first")
  - combo_last  : due at the LATEST of its dimensions (rare)

Hours/cycle dimensions have no intrinsic calendar date, so we *project* one
from the component's recent utilisation rate. That lets every item share a
single dashboard, timeline and alert pipeline.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Optional

# --- Defaults (org-configurable later) ---------------------------------------

DEFAULT_WARNING_DAYS = 30
# Fallback utilisation when we don't have enough hours history to measure it.
DEFAULT_HOURS_PER_MONTH = 25.0
DAYS_PER_MONTH = 30.4368  # mean Gregorian month
# A date far enough out to act as "no calendar due date" when taking a min().
_FAR_FUTURE = date(9999, 12, 31)


class IntervalKind(str, Enum):
    CALENDAR = "calendar"
    HOURS = "hours"
    CYCLES = "cycles"
    FIXED = "fixed"
    COMBO_FIRST = "combo_first"
    COMBO_LAST = "combo_last"


class Status(str, Enum):
    OK = "ok"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    UNKNOWN = "unknown"  # not enough data to determine (e.g. never performed)


# Severity ordering so we can take the "worst" across dimensions.
_SEVERITY = {Status.UNKNOWN: 0, Status.OK: 1, Status.DUE_SOON: 2, Status.OVERDUE: 3}


def worst(*statuses: Status) -> Status:
    return max(statuses, key=lambda s: _SEVERITY[s])


# --- Inputs / outputs --------------------------------------------------------


@dataclass
class ItemTiming:
    """The timing definition + last-done state for one tracked item."""

    interval_kind: IntervalKind

    interval_months: Optional[int] = None
    interval_hours: Optional[float] = None
    interval_cycles: Optional[int] = None

    last_done_date: Optional[date] = None
    last_done_hours: Optional[float] = None
    last_done_cycles: Optional[int] = None

    # Hard expiry for FIXED items (no recurrence).
    fixed_expiry_date: Optional[date] = None

    warning_days: int = DEFAULT_WARNING_DAYS
    # Optional secondary trigger for hours-based items: warn within N hours.
    warning_hours: Optional[float] = None


@dataclass
class DueResult:
    status: Status
    effective_due_date: Optional[date] = None
    remaining_days: Optional[int] = None

    next_due_date: Optional[date] = None      # calendar dimension
    next_due_hours: Optional[float] = None     # hours dimension
    next_due_cycles: Optional[int] = None      # cycles dimension
    remaining_hours: Optional[float] = None
    remaining_cycles: Optional[int] = None
    projected_due_date: Optional[date] = None  # earliest of projected hrs/cycles dates

    # Human-readable reasons for the status (one per triggering dimension).
    reasons: list[str] = field(default_factory=list)


# --- Calendar math -----------------------------------------------------------


def add_calendar_months(start: date, months: int) -> date:
    """Return the FAA 'calendar month' expiry: the LAST day of the month that
    falls ``months`` after ``start``'s month.

    Example: a 24-month check performed any day in June 2026 is good through
    30 Jun 2028 (it expires at the end of the 24th calendar month).
    """
    total = (start.year * 12 + (start.month - 1)) + months
    year, month = divmod(total, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


# --- Utilisation rate --------------------------------------------------------


def utilisation_rate_per_day(
    readings: list[tuple[date, float]],
    *,
    window_days: int = 180,
    as_of: Optional[date] = None,
    default_per_month: float = DEFAULT_HOURS_PER_MONTH,
) -> float:
    """Estimate units (hours or cycles) accrued per day.

    ``readings`` is a list of (date, cumulative_value) points. Uses points
    within ``window_days`` of the most recent reading. Falls back to a default
    rate when there isn't enough history to measure a positive trend.
    """
    fallback = default_per_month / DAYS_PER_MONTH
    if not readings or len(readings) < 2:
        return fallback

    pts = sorted(readings, key=lambda r: r[0])
    latest_date, latest_val = pts[-1]
    cutoff = latest_date - timedelta(days=window_days)
    window = [p for p in pts if p[0] >= cutoff]
    if len(window) < 2:
        window = pts  # not enough in-window points; use full history

    first_date, first_val = window[0]
    span_days = (latest_date - first_date).days
    delta = latest_val - first_val
    if span_days <= 0 or delta <= 0:
        return fallback
    return delta / span_days


# --- Status helper -----------------------------------------------------------


def _status_from_days(remaining_days: int, warning_days: int) -> Status:
    if remaining_days < 0:
        return Status.OVERDUE
    if remaining_days <= warning_days:
        return Status.DUE_SOON
    return Status.OK


# --- Core computation --------------------------------------------------------


def compute_status(
    timing: ItemTiming,
    *,
    today: date,
    current_hours: Optional[float] = None,
    current_cycles: Optional[int] = None,
    hours_rate_per_day: Optional[float] = None,
    cycles_rate_per_day: Optional[float] = None,
) -> DueResult:
    """Compute the due dates and overall status for a single tracked item."""

    kind = timing.interval_kind
    res = DueResult(status=Status.UNKNOWN)

    # Which dimensions are active for this item?
    use_calendar = kind in (IntervalKind.CALENDAR, IntervalKind.COMBO_FIRST, IntervalKind.COMBO_LAST) \
        and timing.interval_months is not None
    use_hours = kind in (IntervalKind.HOURS, IntervalKind.COMBO_FIRST, IntervalKind.COMBO_LAST) \
        and timing.interval_hours is not None
    use_cycles = kind in (IntervalKind.CYCLES, IntervalKind.COMBO_FIRST, IntervalKind.COMBO_LAST) \
        and timing.interval_cycles is not None

    # Each active dimension contributes (status, effective_date).
    dimensions: list[tuple[Status, date]] = []

    # --- FIXED expiry --------------------------------------------------------
    if kind == IntervalKind.FIXED:
        if timing.fixed_expiry_date is None:
            return res  # UNKNOWN
        res.next_due_date = timing.fixed_expiry_date
        rem = (timing.fixed_expiry_date - today).days
        st = _status_from_days(rem, timing.warning_days)
        res.status = st
        res.effective_due_date = timing.fixed_expiry_date
        res.remaining_days = rem
        if st != Status.OK:
            res.reasons.append(f"Expires {timing.fixed_expiry_date.isoformat()}")
        return res

    # --- Calendar ------------------------------------------------------------
    if use_calendar:
        if timing.last_done_date is not None:
            due = add_calendar_months(timing.last_done_date, timing.interval_months)
            res.next_due_date = due
            rem = (due - today).days
            st = _status_from_days(rem, timing.warning_days)
            dimensions.append((st, due))
            if st != Status.OK:
                res.reasons.append(f"Calendar due {due.isoformat()} ({rem}d)")
        else:
            dimensions.append((Status.UNKNOWN, _FAR_FUTURE))

    # --- Hours ---------------------------------------------------------------
    if use_hours:
        if timing.last_done_hours is not None and current_hours is not None:
            due_hours = timing.last_done_hours + timing.interval_hours
            res.next_due_hours = due_hours
            rem_hours = due_hours - current_hours
            res.remaining_hours = rem_hours

            rate = hours_rate_per_day if hours_rate_per_day and hours_rate_per_day > 0 \
                else DEFAULT_HOURS_PER_MONTH / DAYS_PER_MONTH
            if rem_hours <= 0:
                proj = today  # already due
            else:
                proj = today + timedelta(days=rem_hours / rate)
            res.projected_due_date = _min_date(res.projected_due_date, proj)

            # Status: hard hours check OR the projected-date warning.
            rem_days = (proj - today).days
            st = _status_from_days(rem_days, timing.warning_days)
            if rem_hours <= 0:
                st = Status.OVERDUE
            elif timing.warning_hours is not None and rem_hours <= timing.warning_hours:
                st = worst(st, Status.DUE_SOON)
            dimensions.append((st, proj))
            if st != Status.OK:
                res.reasons.append(
                    f"Hours due at {due_hours:g}h ({rem_hours:g}h left, ~{proj.isoformat()})"
                )
        else:
            dimensions.append((Status.UNKNOWN, _FAR_FUTURE))

    # --- Cycles --------------------------------------------------------------
    if use_cycles:
        if timing.last_done_cycles is not None and current_cycles is not None:
            due_cycles = timing.last_done_cycles + timing.interval_cycles
            res.next_due_cycles = due_cycles
            rem_cycles = due_cycles - current_cycles
            res.remaining_cycles = rem_cycles

            rate = cycles_rate_per_day if cycles_rate_per_day and cycles_rate_per_day > 0 else None
            if rem_cycles <= 0:
                proj = today
            elif rate:
                proj = today + timedelta(days=rem_cycles / rate)
            else:
                proj = _FAR_FUTURE  # can't project without a rate
            if proj != _FAR_FUTURE:
                res.projected_due_date = _min_date(res.projected_due_date, proj)

            if rem_cycles <= 0:
                st = Status.OVERDUE
            elif proj != _FAR_FUTURE:
                st = _status_from_days((proj - today).days, timing.warning_days)
            else:
                st = Status.OK
            dimensions.append((st, proj))
            if st != Status.OK:
                res.reasons.append(f"Cycles due at {due_cycles} ({rem_cycles} left)")
        else:
            dimensions.append((Status.UNKNOWN, _FAR_FUTURE))

    if not dimensions:
        return res  # UNKNOWN (no usable interval defined)

    # --- Combine dimensions --------------------------------------------------
    known = [d for d in dimensions if d[0] != Status.UNKNOWN]
    if not known:
        res.status = Status.UNKNOWN
        return res

    if kind == IntervalKind.COMBO_LAST:
        # Due only when the LATEST dimension is reached.
        chosen = max(known, key=lambda d: d[1])
        res.status = chosen[0]
        res.effective_due_date = chosen[1] if chosen[1] != _FAR_FUTURE else None
    else:
        # CALENDAR / HOURS / CYCLES (single) and COMBO_FIRST:
        # earliest date drives the timeline; status is the worst across dims.
        res.status = worst(*[d[0] for d in known])
        eff = min((d[1] for d in known), default=_FAR_FUTURE)
        res.effective_due_date = eff if eff != _FAR_FUTURE else None

    if res.effective_due_date is not None:
        res.remaining_days = (res.effective_due_date - today).days
    return res


def _min_date(a: Optional[date], b: date) -> date:
    return b if a is None else min(a, b)
